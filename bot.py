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

# ========== KEEP-ALIVE ==========
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
def add_event(t,p,ts=None): EVENTS.append({"ts":ts or time.time(),"type":t,"data":p or {}})
def last_24h(): 
    c=time.time()-86400
    return [e for e in EVENTS if e["ts"]>=c]

# ========== REGEX HELPERS ==========
IV_TRIPLE=re.compile(r"IV\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})",re.I)
PKM_LINE=re.compile(r"^\s*Pok[eé]mon:\s*([A-Za-zÀ-ÿ' .-]+|p\s*\d+)",re.I|re.M)

def _norm(s): return unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower().strip()

def _field_value(e,name):
    wn=_norm(name)
    for f in e.fields:
        if _norm(f.name)==wn or "pokemon" in _norm(f.name):
            return (f.value or "").strip()
    return None

def _extract_pokemon_name(e):
    val=_field_value(e,"Pokemon")
    if val:
        name=val.split("(")[0].strip()
        name=re.sub(r"^p\s*(\d+)$",r"p\1",name,flags=re.I)
        if name: return name
    if e.description:
        m=PKM_LINE.search(e.description)
        if m:
            name=m.group(1).strip()
            name=re.sub(r"^p\s*(\d+)$",r"p\1",name,flags=re.I)
            return name
    title=(e.title or "")
    m2=re.search(r"([A-Za-zÀ-ÿ' .-]+|p\s*\d+)\s*\(",title)
    if m2:
        name=m2.group(1).strip()
        name=re.sub(r"^p\s*(\d+)$",r"p\1",name,flags=re.I)
        return name
    return "?"

def _extract_iv_triplet(e):
    text=e.description or ""
    for f in e.fields: text+=f"{f.name}\n{f.value}"
    m=IV_TRIPLE.search(text)
    return (int(m.group(1)),int(m.group(2)),int(m.group(3))) if m else None

def _gather_text(e):
    return "\n".join([e.title or "",e.description or ""]+[f"{f.name}\n{f.value}" for f in e.fields]).lower()

# ========== PARSER ==========
def parse_polygonx_embed(e):
    full=_gather_text(e); title=(e.title or "").strip()

    if any(x in full for x in ["shiny","✨",":sparkles:"]):
        return ("Shiny",{"name":_extract_pokemon_name(e),"iv":_extract_iv_triplet(e)})

    if "caught successfully" in full or "pokemon caught" in full:
        return ("Catch",{"name":_extract_pokemon_name(e),"iv":_extract_iv_triplet(e)})

    if "flee" in full or "fled" in full or "ran away" in full:
        return ("Fled",{"name":_extract_pokemon_name(e)})

    if "quest" in full:
        return ("Quest",{"name":_extract_pokemon_name(e)})

    if "encounter" in full and "rocket" not in full:
        src="wild"
        if "incense" in full: src="incense"
        elif "lure" in full: src="lure"
        return ("Encounter",{"name":_extract_pokemon_name(e),"source":src})

    if "raid" in full: return ("Raid",{"name":_extract_pokemon_name(e)})
    if "battle" in full and "encounter" in full and "raid" not in full and "rocket" not in full:
        return ("MaxBattle",{"name":_extract_pokemon_name(e)})
    if "rocket" in full: return ("Rocket",{"name":title})
    if "hatch" in full:  return ("Hatch",{"name":_extract_pokemon_name(e) or title})
    if "lure" in full:   return ("Lure",{"name":title})
    if "incense" in full:return ("Incense",{"name":title})
    return (None,None)

# ========== STATS ==========
def build_stats():
    rows=last_24h(); by_type={}
    for r in rows: by_type[r["type"]]=by_type.get(r["type"],0)+1

    enc=lambda src:sum(1 for r in rows if r["type"]=="Encounter" and r["data"].get("source")==src)
    enc_wild=enc("wild"); enc_lure=enc("lure"); enc_inc=enc("incense")
    enc_max=by_type.get("MaxBattle",0); enc_raid=by_type.get("Raid",0)
    enc_q=by_type.get("Quest",0); enc_r=by_type.get("Rocket",0)
    enc_h=by_type.get("Hatch",0); fled=by_type.get("Fled",0)

    # Totale encounters (voor catch rate)
    enc_total=enc_wild+enc_lure+enc_inc+enc_max+enc_q+enc_r+enc_raid
    rate_base=max(enc_total,by_type.get("Catch",0))

    # perfect 100
    perfect=sum(1 for r in rows if r["type"]=="Catch" and r["data"].get("iv")== (15,15,15))

    # meest recente correct sorteren
    catches=[r for r in rows if r["type"]=="Catch"]; shinies=[r for r in rows if r["type"]=="Shiny"]
    catches.sort(key=lambda x:x["ts"],reverse=True); shinies.sort(key=lambda x:x["ts"],reverse=True)

    s={
        "enc_total":rate_base,"wild":enc_wild,"lure":enc_lure,"inc":enc_inc,"max":enc_max,
        "quest":enc_q,"rocket":enc_r,"raid":enc_raid,"hatch":enc_h,"fled":fled,
        "catches":by_type.get("Catch",0),"shinies":by_type.get("Shiny",0),
        "perfect":perfect,"rows":rows,
        "latest_catches":catches[:5],"latest_shinies":shinies[:5],
        "since":min((r["ts"] for r in rows),default=time.time())
    }
    s["runaways"]=max(0,s["enc_total"]-s["catches"])
    s["catch_rate"]=(s["catches"]/s["enc_total"]*100) if s["enc_total"]>0 else 0
    s["shiny_rate"]=(s["shinies"]/s["catches"]*100) if s["catches"]>0 else 0
    return s

def _fmt_when(ts,style="f"): return f"<t:{int(ts)}:{style}>"

def build_embed(mode="catch"):
    s=build_stats(); emb=discord.Embed(title="📊 Today’s Stats (Last 24h)",color=discord.Color.blurple())
    emb.add_field(name="Encounters",value=str(s["enc_total"]),inline=True)
    emb.add_field(name="Catches",value=str(s["catches"]),inline=True)
    emb.add_field(name="Shinies",value=str(s["shinies"]),inline=True)

    breakdown=(f"Wild: {s['wild']}\nLure: {s['lure']}\nIncense: {s['inc']}\nMax Battle: {s['max']}\n"
               f"Quest: {s['quest']}\nRocket Battle: {s['rocket']}\nRaid: {s['raid']}\n"
               f"Runaways: {s['fled']}\nHatch: {s['hatch']}")
    emb.add_field(name="**Event breakdown**",value=breakdown,inline=False)

    if mode=="catch": emb.add_field(name="🎯 Catch rate",value=f"{s['catch_rate']:.1f}%",inline=True)
    else: emb.add_field(name="✨ Shiny rate",value=f"{s['shiny_rate']:.3f}%",inline=True)
    emb.add_field(name="🏃 Runaways (est.)",value=str(s["runaways"]),inline=True)
    emb.add_field(name="🏆 Perfect 100 IV",value=str(s["perfect"]),inline=True)

    def fmt_latest(lst,mark_shiny=False):
        if not lst: return "—"
        lines=[]
        for it in lst:
            n=it["data"].get("name") or "?"
            ivt=it["data"].get("iv")
            ivtxt=f" {ivt[0]}/{ivt[1]}/{ivt[2]}" if ivt else ""
            lines.append(f"{'✨ ' if mark_shiny else ''}{n}{ivtxt} ({_fmt_when(it['ts'],'f')})")
        return "\n".join(lines)

    emb.add_field(name="🕓 Latest Catches",value=fmt_latest(s["latest_catches"],False),inline=False)
    emb.add_field(name="✨ Latest Shinies",value=fmt_latest(s["latest_shinies"],True),inline=False)
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
            if evt:
                ts=m.created_at.timestamp(); title=(e.title or "").lower()
                if evt=="Shiny" and "caught" in title: add_event("Catch",p,ts)
                if evt in {"Quest","Raid","MaxBattle"}:
                    src=evt.lower() if evt!="MaxBattle" else "maxbattle"
                    add_event("Encounter",{"name":p.get("name"),"source":src},ts)
                add_event(evt,p,ts)
    print(f"[BACKFILL] +{len(EVENTS)-before}")

# ========== INGEST ==========
@client.event
async def on_message(m):
    if m.author==client.user: return
    if not m.embeds: return
    rec=0
    for e in m.embeds:
        evt,p=parse_polygonx_embed(e)
        if evt:
            ts=m.created_at.timestamp(); title=(e.title or "").lower()
            if evt=="Shiny" and "caught" in title: add_event("Catch",p,ts); rec+=1
            if evt in {"Quest","Raid","MaxBattle"}:
                src=evt.lower() if evt!="MaxBattle" else "maxbattle"
                add_event("Encounter",{"name":p.get("name"),"source":src},ts); rec+=1
            add_event(evt,p,ts); rec+=1
    if rec: print(f"[INGEST] {rec} from msg {m.id}")

# ========== VIEW ==========
class SummaryView(View):
    def __init__(self,mode="catch"):
        super().__init__(timeout=180); self.mode=mode
    @discord.ui.button(label="Refresh",style=discord.ButtonStyle.primary)
    async def refresh(self,i,b):
        try: await i.response.edit_message(embed=build_embed(self.mode),view=self)
        except: await i.followup.send("Refresh failed",ephemeral=True)
    @discord.ui.button(label="Rate: Catch",style=discord.ButtonStyle.secondary)
    async def toggle(self,i,b):
        self.mode="shiny" if self.mode=="catch" else "catch"
        b.label="Rate: Shiny" if self.mode=="shiny" else "Rate: Catch"
        await i.response.edit_message(embed=build_embed(self.mode),view=self)

# ========== COMMAND ==========
@tree.command(name="summary",description="Toon de 24u stats (met refresh & rate-toggle)")
async def summary(inter):
    try: await inter.response.send_message("📊 Summary wordt geplaatst…",ephemeral=True)
    except: pass
    ch=client.get_channel(CHANNEL_ID) or inter.channel
    await ch.send(embed=build_embed(),view=SummaryView())

@tree.error
async def on_err(i,e): print("[CMD ERR]",e)

@client.event
async def on_ready():
    try:
        if GUILD_ID: await tree.sync(guild=discord.Object(id=GUILD_ID))
        else: await tree.sync()
        await client.change_presence(status=discord.Status.online,activity=discord.Game("PXstats · /summary"))
        print(f"[READY] {client.user}")
        await backfill_from_channel()
    except Exception as er: print("[READY ERR]",er)

if __name__=="__main__":
    if not DISCORD_TOKEN: raise SystemExit("DISCORD_TOKEN missing")
    start_keepalive(); client.run(DISCORD_TOKEN)
