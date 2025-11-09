# main.py
VERSION = "main-v3.5 • 2025-11-09 (pairing+shiny-log+download)"

import os, io, json, time, asyncio, datetime, discord
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

        # 1) Battle types
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

        # 2) Encounter wild/quest/rocket
        if evt == "Encounter":
            if _battle_recent_for(name, ts):
                continue
            add_event("Encounter", p, ts)
            wrote = True
            continue

        # 3) Shiny => Catch(shiny=True) + Shiny
        if evt == "Shiny":
            p = p or {}
            p["shiny"] = True
            print(f"[SHINY] {p.get('name')} IV {p.get('iv')} • ts={int(ts)}")
            add_event("Catch", p, ts)
            add_event("Shiny", p, ts)
            wrote = True
            continue

        # 4) Catch
        if evt == "Catch":
            add_event("Catch", p, ts)
            wrote = True
            continue

        # 5) Overige
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


# --------- NIEUW: events.json downloaden ----------
@tree.command(name="download_events", description="Download events.json als bestand (ephemeral).")
async def download_events(i: discord.Interaction):
    try:
        await i.response.defer(ephemeral=True, thinking=False)
    except discord.InteractionResponded:
        pass

    # Lees file indien aanwezig, anders maak JSON vanuit memory
    payload = None
    if os.path.exists(SAVE_PATH):
        try:
            with open(SAVE_PATH, "rb") as f:
                payload = f.read()
        except Exception as e:
            print("[DOWNLOAD ERR] reading file:", e)

    if payload is None:
        try:
            payload = json.dumps(list(EVENTS), ensure_ascii=False).encode()
        except Exception as e:
            await i.followup.send(f"⚠️ Kon events niet serialiseren: {e}", ephemeral=True)
            return

    await i.followup.send(
        file=discord.File(io.BytesIO(payload), filename="events.json"),
        ephemeral=True
    )

# --------- NIEUW: recente shinies ----------
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
