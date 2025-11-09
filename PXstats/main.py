# main.py
VERSION = "main-v3.3 • 2025-11-09 (pairing 10s)"

import os, time, asyncio, datetime, discord
from discord import app_commands
from collections import deque

from utils import (
    start_keepalive, load_events, save_events, EVENTS, TZ, add_event
)
from parser import parse_polygonx_embed
from stats import build_embed, SummaryView, export_csv

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = os.getenv("GUILD_ID")  # optional

# ---------------- Pairing config ----------------
PAIR_WINDOW_SEC = 10  # Catch binnen 10s na Raid/MaxBattle = gepaird
# Bewaar de laatste "battle encounters" per naam
RECENT_BATTLES = deque(maxlen=200)  # items: (ts, name, kind) kind in {"raid","maxbattle"}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def _battle_recent_for(name: str, now_ts: float) -> str | None:
    """Return 'raid'/'maxbattle' als er binnen window een battle van dezelfde naam was."""
    if not name:
        return None
    for (ts, nm, kind) in reversed(RECENT_BATTLES):
        if nm == name and (now_ts - ts) <= PAIR_WINDOW_SEC:
            return kind
    return None


def _push_battle(name: str, kind: str, ts: float):
    """Sla battle event op voor pairing; voorkom dubbele 'raid/maxbattle' spam."""
    # Als exact dezelfde battle (naam+kind) al net kwam binnen 10s, negeren
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

        # 1) Battle types: onthouden voor pairing (10s)
        if evt == "Raid":
            if _push_battle(name, "raid", ts):
                # tel raid encounter één keer
                add_event("Encounter", {"name": name, "source": "raid"}, ts)
                add_event("Raid", {"name": name}, ts)
                wrote = True
            # Als duplicate binnen 10s: sla over
            continue

        if evt == "MaxBattle":
            if _push_battle(name, "maxbattle", ts):
                add_event("Encounter", {"name": name, "source": "maxbattle"}, ts)
                add_event("MaxBattle", {"name": name}, ts)
                wrote = True
            continue

        # 2) Encounter van wild/quest/rocket: skippen indien net gepaird met battle
        if evt == "Encounter":
            paired_kind = _battle_recent_for(name, ts)
            if paired_kind:
                # Laat Encounter die enkel het battle-event duidt weg
                # (Raid/MaxBattle hierboven hebben zelf al een Encounter entry toegevoegd)
                continue
            add_event("Encounter", p, ts)
            wrote = True
            continue

        # 3) Shiny: telt als Catch + Shiny
        if evt == "Shiny":
            # koppelen mag, maar Catch blijft meetellen (doel = 1 Raid + 1 Catch)
            add_event("Catch", p, ts)
            add_event("Shiny", p, ts)
            wrote = True
            continue

        # 4) Catch: koppelen aan battle indien aanwezig (geen extra Encounter nodig)
        if evt == "Catch":
            # geen extra logic nodig; pairing vermijdt al dubbele encounter events
            add_event("Catch", p, ts)
            wrote = True
            continue

        # 5) Overige types direct loggen
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
    client.run(DISCORD_TOKEN)
