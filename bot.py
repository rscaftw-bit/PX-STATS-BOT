# bot_v3.py
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

# ========== KEEP-ALIVE (Render) ==========
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
        await asyncio.sleep(600)  # elke 10 minuten
        save_events()

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

# ========== PARSER (met fixes: invasion→rocket, stricte shiny) ==========
def parse_polygonx_embed(e: discord.Embed):
    full  = _gather_text(e)
    title = (e.title or "").strip().lower()

    # Alleen PolygonX-achtige embeds verwerken
    if not ("pokemon" in full or "encounter" in full or "caught" in full or "flee" in full or "fled" in full):
        return (None, None)

    name = _extract_pokemon_name(e)
    ivt  = _extract_iv_triplet(e)

    # --- ROCKET / INVASION (VÓÓR generic encounter!) ---
    if any(k in full for k in ["rocket","invasion","grunt","leader","giovanni"]):
        return ("Rocket", {"name": name})

    # --- SHINY (alleen echte catch) ---
    if ("shiny" in full or "✨" in full or ":sparkles:" in full) and \
       ("pokemon caught" in full or "caught successfully" in full):
        return ("Shiny", {"name": name, "iv": ivt})

    # --- CATCH ---
    if "caught successfully" in full or "pokemon caught" in full:
        return ("Catch", {"name": name, "iv": ivt})

    # --- FLED ---
    if any(k in full for k in ["flee","fled","ran away"]):
        return ("Fled", {"name": name})

    # --- QUEST ---
    if "quest" in full:
        return ("Quest", {"name": name})

    # --- GENERIC ENCOUNTER (wild/lure/incense) ---
    if "encounter" in full:
        src="wild"
        if "incense" in full: src="incense"
        elif "lure" in full:  src="lure"
        return ("Encounter", {"name": name, "source": src})

    # --- RAID / MAXBATTLE ---
    if "raid" in full:
        return ("Raid", {"name": name})
    if "battle" in full and "encounter" in full and "raid" not in full and "rocket" not in full and "invasion" not in full:
        return ("MaxBattle", {"name": name})

    # --- HATCH / LURE / INCENSE (losse meldingen) ---
    if "hatch" in full:   return ("Hatch", {"name": name})
    if "lure" in full:    return ("Lure", {"name": title})
    if "incense" in full: return ("Incense", {"name": title})

    return (None, None)

# ========== STATS ==========
def build_stats():
    rows=last_24h()
    by_type={}
    for r in rows:
        by_type[r["type"]]=by_type.get(r["type"],0)+1

    # Encounters per bron via Encounter+source (incl. rocket/maxbattle/raid/quest)
    enc=lambda src: sum(1 for r in rows if r["type"]=="Encounter" and r["data"].get("source")==src)
    enc_wild    = enc("wild")
    enc_lure    = enc("lure")
    enc_incense = enc("incense")
    enc_max     = enc("maxbattle")
    enc_raid    = enc("raid")
    enc_quest   = enc("quest")
    enc_rocket  = enc("rocket")

    enc_hatch   = by_type.get("Hatch",0)   # tonen, niet in rate
    fled_count  = by_type.get("Fled",0)    # tonen

    enc_total_sources = enc_wild+enc_lure+enc_incense+enc_max+enc_quest+enc_rocket+enc_raid
    catches_count     = by_type.get("Catch",0)
    rate_base         = max(enc_total_sources, catches_count)

    perfect = sum(1 for r in rows if r["type"]=="Catch" and r["data"].get("iv")==(15,15,15))

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
    s["runaways"]  = max(0, s["enc_total"] - s["catches"] )
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

    # Latest sections
    def fmt_latest(lst, mark_shiny=False):
        if not lst: return "—"
        lines=[]
        for it in lst:
            n = it["data"].get("name") or "?"
            ivt = it["data"].get("iv")
            ivtxt = f" {ivt[0]}/{ivt[1]}/{ivt[2]}" if isinstance(ivt, tuple) and len(ivt)==3 else ""
            prefix = "✨ " if mark_shiny else ""
            lines.append(f"{prefix}{n}{ivtxt} ({_fmt_when(it['ts'],'f')})")
        return "\n".join(lines)

    emb.add_field(name="🕓 Latest Catches", value=fmt_latest(s["latest_catches"], False), inline=False)
    emb.add_field(name="✨ Latest Shinies", value=fmt_latest(s["latest_shinies"], True), inline=False)

    emb.set_footer(text=f"Since {_fmt_when(s['since'],'f')} • Now {_fmt_when(time.time(),'t')} • Rate base: {s['enc_total']}")
    return emb

# ========== BACKFILL ==========
async def backfill_from_channel(limit=500):
    ch=client.get_channel(CHANNEL_ID) if CHANNEL_ID else None
    if not ch:
        print("[BACKFILL] no channel")
        return
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
    if rec:
        print(f"[INGEST] {rec} from msg {m.id}")

# ========== VIEW ==========
class SummaryView(View):
    def __init__(self, mode="catch"):
        super().__init__(timeout=180); self.mode=mode
        for child in self.children:
            if isinstance(child, Button) and child.callback == self.toggle:
                child.label = "Rate: Catch" if self.mode=="catch" else "Rate: Shiny"

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, i: discord.Interaction, b: Button):
        try:
            await i.response.edit_message(embed=build_embed(self.mode), view=self)
        except Exception:
            await i.followup.send("Refresh failed", ephemeral=True)

    @discord.ui.button(label="Rate: Catch", style=discord.ButtonStyle.secondary)
    async def toggle(self, i: discord.Interaction, b: Button):
        self.mode="shiny" if self.mode=="catch" else "catch"
        b.label="Rate: Shiny" if self.mode=="shiny" else "Rate: Catch"
        await i.response.edit_message(embed=build_embed(self.mode), view=self)

# ========== COMMANDS ==========
@tree.command(name="summary", description="Toon de 24u stats (met refresh & rate-toggle)")
async def summary(inter: discord.Interaction):
    try:
        await inter.response.send_message("📊 Summary wordt geplaatst…", ephemeral=True)
    except Exception:
        pass
    ch=client.get_channel(CHANNEL_ID) or inter.channel
    await ch.send(embed=build_embed(), view=SummaryView())

@tree.command(name="status", description="Toon uptime, ping en aantal events")
async def status(inter: discord.Interaction):
    uptime_sec = time.time() - getattr(client, "start_time", time.time())
    hours = int(uptime_sec // 3600)
    minutes = int((uptime_sec % 3600) // 60)
    latency_ms = round(client.latency * 1000) if client.latency is not None else 0
    msg = (
        f"🟢 **Online**\n"
        f"Uptime: {hours}h {minutes}m\n"
        f"Events in geheugen: {len(EVENTS)}\n"
        f"Ping: {latency_ms} ms"
    )
    await inter.response.send_message(msg, ephemeral=True)

@tree.command(name="export", description="Exporteer laatste 24u naar CSV-bestand")
async def export_cmd(inter: discord.Interaction):
    rows = last_24h()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp","type","pokemon","iv"])
    for e in rows:
        n = e["data"].get("name","?")
        iv = e["data"].get("iv")
        w.writerow([int(e["ts"]), e["type"], n, "/".join(map(str,iv)) if isinstance(iv, tuple) else ""])
    data = buf.getvalue().encode()
    await inter.response.send_message(
        file=discord.File(io.BytesIO(data), filename="pxstats_last24h.csv"),
        ephemeral=True
    )

@tree.error
async def on_cmd_err(i, e): print("[CMD ERR]", e)

# ========== DAILY SUMMARY SCHEDULER ==========
async def daily_summary_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            ch = client.get_channel(CHANNEL_ID)
            if not ch:
                print("[DAILY] Channel not found; retry in 5 min")
                await asyncio.sleep(300)
                continue
            now = datetime.datetime.now(TZ)
            target = datetime.datetime.combine(now.date(), datetime.time(9, 0, tzinfo=TZ))
            if now >= target:
                target += datetime.timedelta(days=1)
            wait = (target - now).total_seconds()
            print(f"[DAILY] Next summary at {target.isoformat()} (in {int(wait)}s)")
            await asyncio.sleep(wait)
            await ch.send(embed=build_embed(), view=SummaryView())
            print("[DAILY] Summary sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print("[DAILY ERR]", e)
            await asyncio.sleep(60)

# ========== READY ==========
@client.event
async def on_ready():
    try:
        if GUILD_ID:
            await tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await tree.sync()
        await client.change_presence(status=discord.Status.online, activity=discord.Game("PXstats · /summary"))
        client.start_time = time.time()
        print(f"[READY] {client.user}")

        load_events()
        await backfill_from_channel()

        client.loop.create_task(periodic_save_loop())
        client.loop.create_task(daily_summary_loop())

        save_events()
    except Exception as er:
        print("[READY ERR]", er)

# ========== MAIN ==========
if __name__=="__main__":
    if not DISCORD_TOKEN: raise SystemExit("DISCORD_TOKEN missing")
    start_keepalive()
    try:
        client.run(DISCORD_TOKEN)
    finally:
        save_events()
