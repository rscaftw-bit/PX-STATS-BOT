# main.py
VERSION = "main-v3.6 • 2025-11-09 (pairing+shiny-log+robust-download)"

import os, io, json, gzip, math, time, asyncio, datetime, discord
from discord import app_commands
from collections import deque

from utils import (
    start_keepalive, load_events, save_events, EVENTS, TZ, add_event, SAVE_PATH
)
from parser import parse_polygonx_embed
from stats import build_embed, SummaryView, export_csv

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = os.getenv("GUILD_ID")  # optional

# ---------------- Pairing config ----------------
PAIR_WINDOW_SEC = 10  # Catch binnen 10s na Raid/MaxBattle = gepaird
RECENT_BATTLES = deque(maxlen=200)  # items: (ts, name, kind) kind in {"raid","maxbattle"}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------- helpers ----------
def _battle_recent_for(name: str, now_ts: float) -> str | None:
    if not name:
        return None
    for (ts, nm, kind) in reversed(RECENT_BATTLES):
        if nm == name and (now_ts - ts) <= PAIR_WINDOW_SEC:
            return kind
    return None

def _push_battle(name: str, kind: str, ts: float):
    if not name:
        return False
    # Als exact dezelfde battle (naam+kind) al net kwam binnen window, negeren
    if _battle_recent_for(name, ts) == kind:
        return False
    RECENT_BATTLES.append((ts, name, kind))
    return True

# ---------- robust file sending ----------
MAX_DISCORD_BYTES = 7_500_000  # ~7.5 MB marge

async def _send_bytes_as_file(i: discord.Interaction, data: bytes, filename: str, content: str):
    await i.followup.send(content=content, file=discord.File(io.BytesIO(data), filename=filename), ephemeral=False)

def _serialize_events_slice(evs):
    return json.dumps(evs, ensure_ascii=False, separators=(",", ":")).encode()

def _read_events_bytes():
    # Prefer file op disk; fallback naar in-memory
    if os.path.exists(SAVE_PATH):
        try:
            with open(SAVE_PATH, "rb") as f:
                return f.read()
        except Exception:
            pass
    return _serialize_events_slice(list(EVENTS))


# --------- INGEST + ENCOUNTER-AUGMENT + PAIRING ----------
@client.event
async def on_message(m: discord.Message):
    if m.author == client.user or not m.embeds:
        return

    wrote = False
    for e in m.embeds:
        evt, p = parse_polygonx_embed(e)
        if not evt:
            continue

        ts = m.created_at.timestamp()
        name = (p or {}).get("name") or ""

        # 1) Raid/MaxBattle: onthouden + 1× loggen (+ eigen Encounter)
        if evt == "Raid":
            if _push_battle(name, "raid", ts):
                add_event("Encounter", {"name": name, "source": "raid"}, ts)
                add_event("Raid", {"name": name}, ts)
                wrote = True
            continue

        if evt == "MaxBattle":
            if _push_battle(name, "maxbattle", ts):
                add_event("Encounter", {"name": name, "source": "maxbattle"}, ts)
                add_event("MaxBattle", {"name": name}, ts)
                wrote = True
            continue

        # 2) Wild/Quest/Rocket Encounters: skippen als net gepaird met battle
        if evt == "Encounter":
            if _battle_recent_for(name, ts):
                continue  # Raid/MaxBattle hebben hun eigen Encounter al gelogd
            add_event("Encounter", p, ts)
            wrote = True
            continue

        # 3) Shiny: ALTIJD Catch(shiny=True) + Shiny loggen
        if evt == "Shiny":
            p = p or {}
            p["shiny"] = True
            print(f"[SHINY] {p.get('name')} IV {p.get('iv')} • ts={int(ts)}")
            add_event("Catch", p, ts)
            add_event("Shiny", p, ts)
            wrote = True
            continue

        # 4) Catch (gewone vangst)
        if evt == "Catch":
            add_event("Catch", p, ts)
            wrote = True
            continue

        # 5) Overigen rechtstreeks loggen (Quest/Rocket/Hatch/Fled, etc.)
        add_event(evt, p, ts)
        wrote = True

    if wrote:
        save_events()


# --------- COMMANDS (met veilige defer) ----------
@tree.command(name="summary", description="Toon de laatste 24u stats")
async def summary(i: discord.Interaction):
    try:
        await i.response.defer(ephemeral=True, thinking=True)
    except discord.InteractionResponded:
        pass
    ch = client.get_channel(CHANNEL_ID) or i.channel
    await ch.send(embed=build_embed(), view=SummaryView())
    await i.followup.send("📊 Summary geplaatst.", ephemeral=True)

@tree.command(name="status", description="Toon uptime en aantal events")
async def status(i: discord.Interaction):
    try:
        await i.response.defer(ephemeral=True)
    except discord.InteractionResponded:
        pass
    up = time.time() - getattr(client, "start_time", time.time())
    await i.followup.send(
        f"🟢 Online • {VERSION}\n"
        f"Events: {len(EVENTS)}\n"
        f"Uptime: {int(up//3600)}h {int((up%3600)//60)}m",
        ephemeral=True
    )

@tree.command(name="export", description="Export CSV van 24u")
async def export(i: discord.Interaction):
    try:
        await i.response.defer(ephemeral=True, thinking=True)
    except discord.InteractionResponded:
        pass
    await export_csv(i)

@tree.command(name="reload", description="Herlaad Pokédex en events zonder restart")
async def reload_cmd(inter: discord.Interaction):
    try:
        await inter.response.defer(ephemeral=True)
    except discord.InteractionResponded:
        pass
    from utils import _load_pokedex, load_events
    load_events()
    _load_pokedex()
    await inter.followup.send("🔄 Pokédex en events opnieuw geladen!", ephemeral=True)

# ---------- downloads ----------
@tree.command(name="download_events", description="Download events.json (auto-compress/split).")
async def download_events(i: discord.Interaction):
    try:
        await i.response.defer(ephemeral=False, thinking=True)
    except discord.InteractionResponded:
        pass

    raw = _read_events_bytes()

    # 1) Past? stuur plain JSON
    if len(raw) <= MAX_DISCORD_BYTES:
        await _send_bytes_as_file(i, raw, "events.json", "📦 events.json")
        return

    # 2) Probeer gzip
    gz = gzip.compress(raw)
    if len(gz) <= MAX_DISCORD_BYTES:
        await _send_bytes_as_file(i, gz, "events.json.gz", "📦 events.json.gz (compressed)")
        return

    # 3) Split in meerdere delen (JSON)
    evs = list(EVENTS)
    if not evs:
        await i.followup.send("Geen events om te downloaden.", ephemeral=False)
        return

    avg = max(1, len(raw) // max(1, len(evs)))
    per_part = max(1, (MAX_DISCORD_BYTES // avg))
    parts = math.ceil(len(evs) / per_part)
    await i.followup.send(f"📄 events.json is groot; ik stuur {parts} delen…", ephemeral=False)

    start = 0
    part_idx = 1
    while start < len(evs):
        chunk = evs[start:start+per_part]
        start += per_part
        payload = _serialize_events_slice(chunk)
        name = f"events.part{part_idx:02d}.json"
        await _send_bytes_as_file(i, payload, name, f"📦 {name}")
        part_idx += 1

@tree.command(name="download_last", description="Download de laatste N events als JSON.")
@app_commands.describe(count="Aantal events (1–50000), default 5000")
async def download_last(i: discord.Interaction, count: int = 5000):
    try:
        await i.response.defer(ephemeral=False, thinking=False)
    except discord.InteractionResponded:
        pass

    count = max(1, min(50000, count))
    evs = list(EVENTS)[-count:]
    if not evs:
        await i.followup.send("Geen events gevonden.", ephemeral=False)
        return

    data = _serialize_events_slice(evs)
    fn = f"events_last_{len(evs)}.json"
    if len(data) > MAX_DISCORD_BYTES:
        data = gzip.compress(data)
        fn += ".gz"
        await _send_bytes_as_file(i, data, fn, f"📦 {fn} (compressed)")
    else:
        await _send_bytes_as_file(i, data, fn, f"📦 {fn}")

@tree.command(name="recent_shinies", description="Toon de laatste shinies (default 10).")
@app_commands.describe(limit="Aantal regels (max 50)")
async def recent_shinies(i: discord.Interaction, limit: int = 10):
    try:
        await i.response.defer(ephemeral=True, thinking=False)
    except discord.InteractionResponded:
        pass
    limit = max(1, min(50, limit))
    rows = list(EVENTS)
    shinies = [r for r in rows if r["type"] == "Shiny" or (r["type"] == "Catch" and r["data"].get("shiny"))]
    shinies.sort(key=lambda x: x["ts"], reverse=True)
    shinies = shinies[:limit]
    if not shinies:
        await i.followup.send("Geen shinies gevonden in de huidige logs.", ephemeral=True)
        return

    def fmt(r):
        name = r["data"].get("name","?")
        iv   = r["data"].get("iv")
        ivs  = f" {iv[0]}/{iv[1]}/{iv[2]}" if isinstance(iv, (list, tuple)) and len(iv) == 3 else ""
        return f"✨ {name}{ivs} • <t:{int(r['ts'])}:f>"
    msg = "\n".join(fmt(r) for r in shinies)
    await i.followup.send(msg, ephemeral=True)


# --------- DAILY SUMMARY LOOP ----------
async def daily_summary():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = datetime.datetime.now(TZ)
            target = datetime.datetime.combine(now.date(), datetime.time(9, 0, tzinfo=TZ))
            if now >= target:
                target += datetime.timedelta(days=1)
            wait = (target - now).total_seconds()
            print(f"[DAILY] Next summary at {target.isoformat()} (in {int(wait)}s)")
            await asyncio.sleep(wait)
            ch = client.get_channel(CHANNEL_ID)
            if ch:
                await ch.send(embed=build_embed(), view=SummaryView())
                print("[DAILY] Summary sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print("[DAILY ERR]", e)
            await asyncio.sleep(60)

# --------- READY ----------
@client.event
async def on_ready():
    print(f"[READY] {client.user} • {VERSION}")
    load_events()
    if GUILD_ID:
        await tree.sync(guild=discord.Object(id=int(GUILD_ID)))
    else:
        await tree.sync()
    client.loop.create_task(daily_summary())
    client.start_time = time.time()

# --------- MAIN ----------
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("❌ DISCORD_TOKEN ontbreekt")
    start_keepalive()
    print("[INIT] PXstats main.py loaded •", VERSION)
    client.run(DISCORD_TOKEN)
