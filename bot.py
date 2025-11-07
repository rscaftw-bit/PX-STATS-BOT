# bot.py
import os, re, time, threading, unicodedata
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque
from typing import Optional
import discord
from discord import app_commands
from discord.ui import View, Button

# ========== CONFIG ==========
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ========== KEEP-ALIVE (Render) ==========
class _Healthz(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self,*a,**k): return
def start_keepalive():
    port=int(os.getenv("PORT","10000"))
    s=HTTPServer(("",port),_Healthz)
    threading.Thread(target=s.serve_forever,daemon=True).start()
    print(f"[KEEPALIVE] active on :{port}")

# ========== MEMORY ==========
EVENTS=deque(maxlen=10000)
def add_event(t,p,ts: Optional[float]=None):
    EVENTS.append({"ts": ts or time.time(), "type": t, "data": p or {}})
def last_24h():
    cutoff=time.time()-86400
    return [e for e in EVENTS if e["ts"]>=cutoff]

# ========== REGEX HELPERS ==========
IV_TRIPLE = re.compile(r"IV\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)
PKM_LINE  = re.compile(r"^\s*Pok[eé]mon:\s*([A-Za-zÀ-ÿ' .-]+|p\s*\d+)", re.I|re.M)

def _norm(s): return unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower().strip()

def _field_value(e: discord.Embed, name: str):
    wn=_norm(name)
    for f in e.fields:
        if _norm(f.name)==wn or "pokemon" in _norm(f.name):
            return (f.value or "").strip()
    return None

def _normalize_pname(name: str) -> str:
    return re.sub(r"^p\s*(\d+)$", r"p\1", name, flags=re.I)

def _extract_pokemon_name(e: discord.Embed):
    val=_field_value(e,"Pokemon")
    if val:
        name=_normalize_pname(val.split("(")[0].strip())
        if name: return name
    if e.description:
        m=PKM_LINE.search(e.description)
        if m:
            return _normalize_pname(m.group(1).strip())
    title=(e.title or "")
    m2=re.search(r"([A-Za-zÀ-ÿ' .-]+|p\s*\d+)\s*\(", title)
    if m2:
        return _normalize_pname(m2.group(1).strip())
    return "?"

def _extract_iv_triplet(e: discord.Embed):
    text=e.description or ""
    for f in e.fields:
        text+=f"{f.name}\n{f.value}"
    m=IV_TRIPLE.search(text)
    return (int(m.group(1)),int(m.group(2)),int(m.group(3))) if m else None

def _gather_text(e: discord.Embed):
    return "\n".join([e.title or "",e.description or ""]+[f"{f.name}\n{f.value}" for f in e.fields]).lower()

# ========== PARSER ==========
def parse_polygonx_embed(e: discord.Embed):
    full=_gather_text(e)
    title=(e.title or "").strip()

    # Shiny
    if any(x in full for x in ["shiny","✨",":sparkles:"]):
        return ("Shiny", {"name": _extract_pokemon_name(e), "iv": _extract_iv_triplet(e)})

    # Catch
    if "caught successfully" in full or "pokemon caught" in full:
        return ("Catch", {"name": _extract_pokemon_name(e), "iv": _extract_iv_triplet(e)})

    # Fled
    if "flee" in full or "fled" in full or "ran away" in full:
        return ("Fled", {"name": _extract_pokemon_name(e)})

    # Quest
    if "quest" in full:
        return ("Quest", {"name": _extract_pokemon_name(e)})

    # Generic Encounter (wild/lure/incense)
    if "encounter" in full and "rocket" not in full:
        src="wild"
        if "incense" in full: src="incense"
        elif "lure" in full:  src="lure"
        return ("Encounter", {"name": _extract_pokemon_name(e), "source": src})

    # Raid (incl. raid battle encounter)
    if "raid" in full:
        return ("Raid", {"name": _extract_pokemon_name(e)})

    # Max Battle (battle encounter zonder raid/rocket)
    if "battle" in full and "encounter" in full and "raid" not in full and "rocket" not in full:
        return ("MaxBattle", {"name": _extract_pokemon_name(e)})

    # Rocket / Invasion / Grunt / Leader / Giovanni
    if any(k in full for k in ["rocket","invasion","grunt","leader","giovanni"]):
        return ("Rocket", {"name": _extract_pokemon_name(e) or title})

    # Overige
    if "hatch" in full:   return ("Hatch", {"name": _extract_pokemon_name(e) or title})
    if "lure" in full:    return ("Lure", {"name": title})
    if "incense" in full: return ("Incense", {"name": title})
    return (None, None)

# ========== STATS ==========
def build_stats():
    rows=last_24h()
    by_type={}
    for r in rows:
        by_type[r["type"]]=by_type.get(r["type"],0)+1

    # Encounters per bron
    enc=lambda src: sum(1 for r in rows if r["type"]=="Encounter" and r["data"].get("source")==src)
    enc_wild    = enc("wild")
    enc_lure    = enc("lure")
    enc_incense = enc("incense")
    enc_max     = by_type.get("MaxBattle",0)
    enc_raid    = by_type.get("Raid",0)
    enc_quest   = by_type.get("Quest",0)
    enc_rocket  = by_type.get("Rocket",0)
    enc_hatch   = by_type.get("Hatch",0)     # tonen, niet in rate
    fled_count  = by_type.get("Fled",0)      # tonen

    # Totale encounters (zonder Hatch) en rate-basis (nooit < catches)
    enc_total_sources = enc_wild+enc_lure+enc_incense+enc_max+enc_quest+enc_rocket+enc_raid
    catches_count     = by_type.get("Catch",0)
    rate_base         = max(enc_total_sources, catches_count)

    # Perfect 100
    perfect = sum(1 for r in rows if r["type"]=="Catch" and r["data"].get("iv")==(15,15,15))

    # Laatste items (chronologisch recent → oud)
    catches=[r for r in rows if r["type"]=="Catch"]; catches.sort(key=lambda x:x["ts"],reverse=True)
    shinies=[r for r in rows if r["type"]=="Shiny"]; shinies.sort(key=lambda x:x["ts"],reverse=True)

    s={
        "enc_total": rate_base,
        "wild": enc_wild, "lure": enc_lure, "inc": enc_incense,
        "max": enc_max, "raid": enc_raid, "quest": enc_quest, "rocket": enc_rocket,
        "hatch": enc_hatch, "fled": fled_count,
        "catches": catches_count, "shinies": by_type.get("Shiny",0),
        "perfect": perfect,
        "latest_catches": catches[:5], "latest_shinies": shinies[:5],
        "since": min((r["ts"] for r in rows), default=time.time()),
        "rows": rows
    }
    s["runaways"]  = max(0, s["enc_total"] - s["catches"])
    s["catch_rate"]= (s["catches"]/s["enc_total"]*100) if s["enc_total"]>0 else 0
    s["shiny_rate"]= (s["shinies"]/s["catches"]*100) if s["catches"]>0 else 0
    return s

def _fmt_when(ts,style="f"): return f"<t:{int(ts)}:{style}>"

def build_embed(mode="catch"):
    s=build_stats()
    emb=discord.Embed(title="📊 Today’s Stats (Last 24h)", color=discord.Color.blurple())

    # Top row
    emb.add_field(name="Encounters", value=str(s["enc_total"]), inline=True)
    emb.add_field(name="Catches",   value=str(s["catches"]),    inline=True)
    emb.add_field(name="Shinies",   value=str(s["shinies"]),    inline=True)

    # Breakdown
    breakdown=(f"Wild: {s['wild']}\n"
               f"Lure: {s['lure']}\n"
               f"Incense: {s['inc']}\n"
               f"Max Battle: {s['max']}\n"
               f"Quest: {s['quest']}\n"
               f"Rocket Battle: {s['rocket']}\n"
               f"Raid: {s['raid']}\n"
               f"Runaways: {s['fled']}\n"
               f"Hatch: {s['hatch']}")
    emb.add_field(name="**Event breakdown**", value=breakdown, inline=False)

    # Rates
    if mode=="catch":
        emb.add_field(name="🎯 Catch rate", value=f"{s['catch_rate']:.1f}%", inline=True)
    else:
        emb.add_field(name="✨ Shiny rate", value=f"{s['shiny_rate']:.3f}%", inline=True)
    emb.add_field(name="🏃 Runaways (est.)", value=str(s["runaways"]), inline=True)
    emb.add_field(name="🏆 Perfect 100 IV", value=str(s["perfect"]), inline=True)

    # Latest sections (IV als 15/15/15)
    def fmt_latest(lst, mark_shiny=False):
        if not lst: return "—"
        lines=[]
        for it in lst:
            n = it["data"].get("name") or "?"
            ivt = it["data"].get("iv")
            ivtxt = f" {ivt[0]}/{ivt[1]}/{ivt[2]}" if ivt else ""
            prefix = "✨ " if mark_shiny else ""
            lines.append(f"{prefix}{n}{ivtxt} ({_fmt_when(it['ts'],'f')})")
        return "\n".join(lines)

    emb.add_field(name="🕓 Latest Catches", value=fmt_latest(s["latest_catches"], False), inline=False)
    emb.add_field(name="✨ Latest Shinies", value=fmt_latest(s["latest_shinies"], True), inline=False)

    emb.set_footer(text=f"Since {_fmt_when(s['since'],'f')} • Today at {_fmt_when(time.time(),'t')} • Rate base: {s['enc_total']}")
    return emb

# ========== BACKFILL ==========
async def backfill_from_channel(limit=500):
    ch=client.get_channel(CHANNEL_ID) if CHANNEL_ID else None
    if not ch: print("[BACKFILL] no channel"); return
    before=len(EVENTS)
    async for m in ch.history(limit=limit):
        for e in m.embeds:
            evt,p=parse_polygonx_embed(e)
            if not evt: continue
            ts=m.created_at.timestamp()
            title=(e.title or "").lower()

            # Shiny dat ook 'caught' zegt → tel als Catch
            if evt=="Shiny" and ("caught" in title or "caught successfully" in title):
                add_event("Catch", p, ts)

            # Quest/Raid/MaxBattle/Rocket → óók Encounter met bronlabel
            if evt=="Quest":
                add_event("Encounter", {"name": p.get("name"), "source": "quest"}, ts)
            if evt=="Raid":
                add_event("Encounter", {"name": p.get("name"), "source": "raid"}, ts)
            if evt=="MaxBattle":
                add_event("Encounter", {"name": p.get("name"), "source": "maxbattle"}, ts)
            if evt=="Rocket":
                add_event("Encounter", {"name": p.get("name"), "source": "rocket"}, ts)

            add_event(evt, p, ts)
    print(f"[BACKFILL] +{len(EVENTS)-before}")

# ========== INGEST ==========
@client.event
async def on_message(m: discord.Message):
    if m.author==client.user or not m.embeds: return
    rec=0
    for e in m.embeds:
        evt,p=parse_polygonx_embed(e)
        if not evt: continue
        ts=m.created_at.timestamp()
        title=(e.title or "").lower()

        # Shiny dat ook 'caught' zegt → tel als Catch
        if evt=="Shiny" and ("caught" in title or "caught successfully" in title):
            add_event("Catch", p, ts); rec+=1

        # Quest/Raid/MaxBattle/Rocket → óók Encounter met bronlabel
        if evt=="Quest":
            add_event("Encounter", {"name": p.get("name"), "source": "quest"}, ts); rec+=1
        if evt=="Raid":
            add_event("Encounter", {"name": p.get("name"), "source": "raid"}, ts); rec+=1
        if evt=="MaxBattle":
            add_event("Encounter", {"name": p.get("name"), "source": "maxbattle"}, ts); rec+=1
        if evt=="Rocket":
            add_event("Encounter", {"name": p.get("name"), "source": "rocket"}, ts); rec+=1

        add_event(evt, p, ts); rec+=1
    if rec: print(f"[INGEST] {rec} from msg {m.id}")

# ========== VIEW ==========
class SummaryView(View):
    def __init__(self, mode="catch"):
        super().__init__(timeout=180); self.mode=mode
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, i: discord.Interaction, b: Button):
        try: await i.response.edit_message(embed=build_embed(self.mode), view=self)
        except: await i.followup.send("Refresh failed", ephemeral=True)
    @discord.ui.button(label="Rate: Catch", style=discord.ButtonStyle.secondary)
    async def toggle(self, i: discord.Interaction, b: Button):
        self.mode="shiny" if self.mode=="catch" else "catch"
        b.label="Rate: Shiny" if self.mode=="shiny" else "Rate: Catch"
        await i.response.edit_message(embed=build_embed(self.mode), view=self)

# ========== COMMAND ==========
@tree.command(name="summary", description="Toon de 24u stats (met refresh & rate-toggle)")
async def summary(inter: discord.Interaction):
    try: await inter.response.send_message("📊 Summary wordt geplaatst…", ephemeral=True)
    except: pass
    ch=client.get_channel(CHANNEL_ID) or inter.channel
    await ch.send(embed=build_embed(), view=SummaryView())

@tree.error
async def on_cmd_err(i, e): print("[CMD ERR]", e)

@client.event
async def on_ready():
    try:
        if GUILD_ID: await tree.sync(guild=discord.Object(id=GUILD_ID))
        else:        await tree.sync()
        await client.change_presence(status=discord.Status.online, activity=discord.Game("PXstats · /summary"))
        print(f"[READY] {client.user}")
        await backfill_from_channel()
    except Exception as er:
        print("[READY ERR]", er)

if __name__=="__main__":
    if not DISCORD_TOKEN: raise SystemExit("DISCORD_TOKEN missing")
    start_keepalive()
    client.run(DISCORD_TOKEN)
