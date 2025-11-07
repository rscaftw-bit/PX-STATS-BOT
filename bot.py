# bot_v4.py
import os, re, time, json, csv, io, threading, unicodedata, asyncio, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ui import View, Button

# ========== CONFIG ==========
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None
TIMEZONE = os.getenv("TIMEZONE", "Europe/Brussels")
TZ = ZoneInfo(TIMEZONE)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ========== KEEP-ALIVE ==========
class _Healthz(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self,*a,**k): return

def start_keepalive():
    port=int(os.getenv("PORT","10000"))
    s=HTTPServer(("",port),_Healthz)
    threading.Thread(target=s.serve_forever,daemon=True).start()
    print(f"[KEEPALIVE] active on :{port}")

# ========== MEMORY + PERSISTENCE ==========
EVENTS=deque(maxlen=10000)
SAVE_PATH = os.getenv("SAVE_PATH","events.json")

def add_event(t,p,ts: Optional[float]=None):
    EVENTS.append({"ts": ts or time.time(), "type": t, "data": p or {}})

def last_24h():
    cutoff=time.time()-86400
    return [e for e in EVENTS if e["ts"]>=cutoff]

def save_events():
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(list(EVENTS), f, ensure_ascii=False)
        print(f"[SAVE] {len(EVENTS)} events -> {SAVE_PATH}")
    except Exception as e:
        print("[SAVE ERR]", e)

def load_events():
    try:
        if os.path.exists(SAVE_PATH):
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                data=json.load(f)
            if isinstance(data, list):
                for e in data[-EVENTS.maxlen:]:
                    EVENTS.append(e)
            print(f"[LOAD] restored {len(EVENTS)} events from {SAVE_PATH}")
    except Exception as e:
        print("[LOAD ERR]", e)

async def periodic_save_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(600)
        save_events()

# ========== POKEDEX NAAMVERTALING ==========
POKEDEX_FILE = "pokedex.json"

def _load_pokedex():
    if os.path.exists(POKEDEX_FILE):
        with open(POKEDEX_FILE,"r",encoding="utf-8") as f:
            return json.load(f)
    # compacte officiële lijst van 1–1025
    from urllib.request import urlopen
    try:
        with urlopen("https://raw.githubusercontent.com/fanzeyi/pokemon.json/master/pokedex.json") as r:
            data=json.load(r)
        mapping={p["id"]:p["name"]["english"] for p in data}
        with open(POKEDEX_FILE,"w",encoding="utf-8") as f: json.dump(mapping,f)
        print(f"[POKEDEX] created local file with {len(mapping)} entries")
        return mapping
    except Exception as e:
        print("[POKEDEX ERR]", e)
        return {}
POKEDEX=_load_pokedex()

def _translate_pnumber(name:str)->str:
    m=re.match(r"p(\d+)$",name.strip(),re.I)
    if m:
        n=int(m.group(1))
        return POKEDEX.get(str(n),POKEDEX.get(n,name))
    return name

# ========== REGEX HELPERS ==========
IV_TRIPLE=re.compile(r"IV\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})",re.I)
PKM_LINE=re.compile(r"^\s*Pok[eé]mon:\s*([A-Za-zÀ-ÿ' .-]+|p\s*\d+)",re.I|re.M)

def _norm(s): 
    return unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower().strip()

def _field_value(e:discord.Embed,name:str):
    wn=_norm(name)
    for f in e.fields:
        if _norm(f.name)==wn or "pokemon" in _norm(f.name):
            return (f.value or "").strip()
    return None

def _normalize_pname(name:str)->str:
    return re.sub(r"^p\s*(\d+)",r"p\1",name.strip(),flags=re.I)

def _extract_pokemon_name(e:discord.Embed):
    val=_field_value(e,"Pokemon")
    if val:
        name=_normalize_pname(val.split("(")[0].strip())
        if name: return _translate_pnumber(name)
    if e.description:
        m=PKM_LINE.search(e.description)
        if m:
            return _translate_pnumber(_normalize_pname(m.group(1).strip()))
    title=(e.title or "")
    m2=re.search(r"([A-Za-zÀ-ÿ' .-]+|p\s*\d+)\s*\(",title)
    if m2:
        return _translate_pnumber(_normalize_pname(m2.group(1).strip()))
    return "?"

def _extract_iv_triplet(e:discord.Embed):
    text=e.description or ""
    for f in e.fields:
        text+=f"{f.name}\n{f.value}"
    m=IV_TRIPLE.search(text)
    return (int(m.group(1)),int(m.group(2)),int(m.group(3))) if m else None

def _gather_text(e:discord.Embed):
    return "\n".join([e.title or "",e.description or ""]+[f"{f.name}\n{f.value}" for f in e.fields]).lower()

# ========== PARSER ==========
def parse_polygonx_embed(e:discord.Embed):
    full=_gather_text(e)
    title=(e.title or "").strip().lower()
    if not ("pokemon" in full or "encounter" in full or "caught" in full or "flee" in full or "fled" in full):
        return (None,None)
    name=_extract_pokemon_name(e)
    ivt=_extract_iv_triplet(e)
    if any(k in full for k in ["rocket","invasion","grunt","leader","giovanni"]):
        return ("Rocket",{"name":name})
    if ("shiny" in full or "✨" in full or ":sparkles:" in full) and ("pokemon caught" in full or "caught successfully" in full):
        return ("Shiny",{"name":name,"iv":ivt})
    if "caught successfully" in full or "pokemon caught" in full:
        return ("Catch",{"name":name,"iv":ivt})
    if any(k in full for k in ["flee","fled","ran away"]):
        return ("Fled",{"name":name})
    if "quest" in full:
        return ("Quest",{"name":name})
    if "encounter" in full:
        src="wild"
        if "incense" in full: src="incense"
        elif "lure" in full: src="lure"
        return ("Encounter",{"name":name,"source":src})
    if "raid" in full:
        return ("Raid",{"name":name})
    if "battle" in full and "encounter" in full and "raid" not in full and "rocket" not in full and "invasion" not in full:
        return ("MaxBattle",{"name":name})
    if "hatch" in full:   return ("Hatch",{"name":name})
    if "lure" in full:    return ("Lure",{"name":title})
    if "incense" in full: return ("Incense",{"name":title})
    return (None,None)

# ========== REST VAN BOT ==========
# (gebruik identieke code van bot_v3.py vanaf build_stats() tot einde)
#⬇️ je kunt dit deel uit je vorige bot_v3.py onveranderd laten
