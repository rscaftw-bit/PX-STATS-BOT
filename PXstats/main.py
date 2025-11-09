# main.py
VERSION = "main-v3.7 • 2025-11-09 (pairing+shiny-log+robust-download+cmd-fixes)"

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

PAIR_WINDOW_SEC = 10
RECENT_BATTLES = deque(maxlen=200)  # (ts, name, kind)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# -------- helpers: pairing --------
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
    if _battle_recent_for(name, ts) == kind:
        return False
    RECENT_BATTLES.append((ts, name, kind))
    return True

# -------- helpers: file sending --------
MAX_DISCORD_BYTES = 7_500_000

async def _send_bytes_as_file(i: discord.Interaction, data: bytes, filename: str, content: str):
    await i.followup.send(content=content, file=discord.File(io.BytesIO(data), filename=filename), ephemeral=False)

def _serialize_events_slice(evs):
    return json.dumps(evs, ensure_ascii=False, separators=(",", ":")).encode()

def _read_events_bytes():
    if os.path.exists(SAVE_PATH):
        try:
            with open(SAVE_PATH, "rb") as f:
                return f.read()
        except Exception:
            pass
    return _serialize_events_slice(list(EVENTS))

# -------- ingest --------
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

        if evt == "Encounter":
            if _battle_recent_for(name, ts):
                continue
            add_event("Encounter", p, ts)
            wrote = True
            continue

        if evt == "Shiny":
            p = p or {}
            p["shiny"] = True
            print(f"[SHINY] {p.get('name')} IV {p.get('iv')} • ts={int(ts)}")
            add_event("Catch", p, ts)
            add_event("Shiny", p, ts)
            wrote = True
            continue

        if evt == "Catch":
            add_event("Catch", p, ts)
            wrote = True
            continue

        add_event(evt, p, ts)
        wrote = True

    if wrote:
        save_events()

# -------- command error logging --------
@tree.error
async def on_app_cmd_error(interaction: discord.Interaction, error: Exception):
    print("[CMD ERROR]", repr(error))

# -------- commands --------
@tree.command(name="summary", description="Toon de laatste 24u stats")
async def summary(i: discord.Interaction):
    try:
        await i.response.defer(ephemeral=True, thinking=True)
    except discord.InteractionResponded:
        pass
    ch = client.get_channel(CHANNEL_ID) or i.channel
    await ch.send(embed=build_embed(), view=SummaryView())
    try:
        await i.followup.send("📊 Summary geplaatst.", ephemeral=True)
    except Exception:
        pass

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
async def reload_cmd(i: discord.Interaction):
    try:
        await i.response.defer(ephemeral=True)
    except discord.InteractionResponded:
        pass
    from utils import _load_pokedex, load_events
    load_events(); _load_pokedex()
    await i.followup.send("🔄 Pokédex en events opnieuw geladen!", ephemeral=True)

@tree.command(name="download_events", description="Download events.json (auto-compress/split).")
async def download_events(i: discord.Interaction):
    try:
        await i.response.defer(ephemeral=False, thinking=True)
    except discord.InteractionResponded:
        pass

    raw = _read_events_bytes()
    if len(raw) <= MAX_DISCORD_BYTES:
        await _send_bytes_as_file(i, raw, "events.json", "📦 events.json")
        return

    gz = gzip.compress(raw)
    if len(gz) <= MAX_DISCORD_BYTES:
        await _send_bytes_as_file(i, gz, "events.json.gz", "📦 events.json.gz (compressed)")
        return

    evs = list(EVENTS)
    if not evs:
        await i.followup.send("Geen events om te downloaden.", ephemeral=False); return

    avg = max(1, len(raw) // max(1, len(evs)))
    per_part = max(1, (MAX_DISCORD_BYTES // avg))
    parts = math.ceil(len(evs) / per_part)
    await i.followup.send(f"📄 events.json is groot; ik stuur {parts} delen…", ephemeral=False)

    start, idx = 0, 1
    while start < len(evs):
        chunk = evs[start:start+per_part]; start += per_part
        payload = _serialize_events_slice(chunk)
        name = f"events.part{idx:02d}.json"; idx += 1
        await _send_bytes_as_file(i, payload, name, f"📦 {name}")

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
        await i.followup.send("Geen events gevonden.", ephemeral=False); return

    data = _serialize_events_slice(evs)
    fn = f"events_last_{len(evs)}.json"
    if len(data) > MAX_DISCORD_BYTES:
        data = gzip.compress(data); fn += ".gz"
    await _send_bytes_as_file(i, data, fn, f"📦 {fn}")

@tree.command(name="recent_shinies", description="Toon de laatste shinies (default 10).")
@app_commands.describe(limit="Aantal regels (max 50)")
async def recent_shinies(i: discord.Interaction, limit: int = 10):
    try:
        await i.response.defer(ephemeral=False, thinking=False)  # niet-ephemeral
    except discord.InteractionResponded:
        pass
    limit = max(1, min(50, limit))
    rows = list(EVENTS)
    shinies = [r for r in rows if r["type"] == "Shiny" or (r["type"] == "Catch" and r["data"].get("shiny"))]
    shinies.sort(key=lambda x: x["ts"], reverse=True)
    shinies = shinies[:limit]
    if not shinies:
        await i.followup.send("Geen shinies gevonden in de huidige logs.", ephemeral=False); return

    def fmt(r):
        name = r["data"].get("name","?")
        iv   = r["data"].get("iv")
        ivs  = f" {iv[0]}/{iv[1]}/{iv[2]}" if isinstance(iv, (list, tuple)) and len(iv) == 3 else ""
        return f"✨ {name}{ivs} • <t:{int(r['ts'])}:f>"
    msg = "\n".join(fmt(r) for r in shinies)
    await i.followup.send(msg, ephemeral=False)

# -------- daily summary --------
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

# -------- ready --------
@client.event
async def on_ready():
    print(f"[READY] {client.user} • {VERSION}")
    load_events()
    try:
        if GUILD_ID:
            await tree.sync(guild=discord.Object(id=int(GUILD_ID)))
        else:
            await tree.sync()
    except Exception as e:
        print("[SYNC ERR]", e)
    client.loop.create_task(daily_summary())
    client.start_time = time.time()

# -------- main --------
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("❌ DISCORD_TOKEN ontbreekt")
    start_keepalive()
    print("[INIT] PXstats main.py loaded •", VERSION)
    client.run(DISCORD_TOKEN)
