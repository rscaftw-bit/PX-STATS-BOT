# main.py
import os, time, asyncio, datetime, discord
from discord import app_commands

from utils import (
    start_keepalive, load_events, save_events, EVENTS,
    TZ, add_event
)
from parser import parse_polygonx_embed
from stats import build_embed, SummaryView, export_csv, build_stats

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = os.getenv("GUILD_ID")
BACKFILL_LIMIT = int(os.getenv("BACKFILL_LIMIT", "500"))

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ========== MESSAGES PARSER ==========
@client.event
async def on_message(m):
    """Luistert naar PolygonX-webhooks en logt automatisch."""
    if m.author == client.user or not m.embeds:
        return
    for e in m.embeds:
        evt, p = parse_polygonx_embed(e)
        if not evt:
            continue
        ts = m.created_at.timestamp()
        add_event(evt, p, ts)
    save_events()


# ========== COMMANDS ==========
@tree.command(name="summary", description="Toon de laatste 24u stats")
async def summary(i: discord.Interaction):
    await i.response.send_message(embed=build_embed(), view=SummaryView())

@tree.command(name="status", description="Toon uptime en aantal events")
async def status(i: discord.Interaction):
    up = time.time() - getattr(client, "start_time", time.time())
    await i.response.send_message(
        f"🟢 Online\nEvents: {len(EVENTS)}\nUptime: {int(up//3600)}h {int((up%3600)//60)}m",
        ephemeral=True
    )

@tree.command(name="export", description="Export CSV van 24u")
async def export(i: discord.Interaction):
    await export_csv(i)

@tree.command(name="reload", description="Herlaad Pokédex en events zonder restart")
async def reload_cmd(inter: discord.Interaction):
    """Herlaadt lokale JSON en Pokédex, zonder Render-restart."""
    from utils import _load_pokedex, load_events
    try:
        load_events()
        _load_pokedex()
        await inter.response.send_message("🔄 Pokédex en events opnieuw geladen!", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"⚠️ Fout bij herladen: {e}", ephemeral=True)


# ========== DAILY SUMMARY LOOP ==========
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


# ========== READY ==========
@client.event
async def on_ready():
    print(f"[READY] {client.user}")
    load_events()

    if GUILD_ID:
        await tree.sync(guild=discord.Object(id=int(GUILD_ID)))
    else:
        await tree.sync()

    client.loop.create_task(daily_summary())
    client.start_time = time.time()


# ========== MAIN ==========
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("❌ DISCORD_TOKEN ontbreekt")
    start_keepalive()
    client.run(DISCORD_TOKEN)
