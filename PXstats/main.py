# ======================================================
# PXstats • main.py • Final Stable Build • 14-11-2025
# ======================================================

import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

import discord
from discord import app_commands

from PXstats.parser import parse_polygonx_embed
from PXstats.stats import build_embed
from PXstats.utils import (
    load_events, save_events, add_event, EVENTS, TZ, load_pokedex
)

# ======================================================
# STARTUP
# ======================================================

print("=== PXstats startup ===")

try:
    pokedex = load_pokedex()
    print(f"[INIT] Pokedex loaded: {len(pokedex)} entries")
except Exception as e:
    print(f"[ERROR] Could not load pokedex: {e}")


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# ======================================================
# KEEP ALIVE SERVER (Render)
# ======================================================

class KeepAlive(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()


def start_server():
    server = HTTPServer(("0.0.0.0", 10000), KeepAlive)
    server.serve_forever()


threading.Thread(target=start_server, daemon=True).start()


# ======================================================
# READY
# ======================================================

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user}")

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
            print("[SYNC] Commands synced (guild)")
        else:
            await tree.sync()
            print("[SYNC] Commands synced (global)")
    except Exception as e:
        print("[SYNC ERROR]", e)


# ======================================================
# INGEST POLYGONX EMBEDS
# ======================================================

@bot.event
async def on_message(msg: discord.Message):

    # Skip own bot
    if msg.author == bot.user:
        return

    # Must contain embeds
    if not msg.embeds:
        return

    processed = 0

    for e in msg.embeds:

        etype, data = parse_polygonx_embed(e)
        if not etype:
            continue

        ts = e.timestamp or datetime.now(TZ)

        # Base event stored
        base_evt = dict(data)
        base_evt["timestamp"] = ts
        base_evt["type"] = etype

        add_event(base_evt)
        processed += 1

        # Dual-event for shiny catches
        if etype == "Catch" and data.get("shiny", False):
            shiny_evt = dict(base_evt)
            shiny_evt["type"] = "Shiny"
            add_event(shiny_evt)
            processed += 1

    if processed > 0:
        print(f"[INGEST] Processed {processed} embeds from {msg.author}")
        save_events()


# ======================================================
# SUMMARY COMMAND
# ======================================================

@tree.command(name="summary", description="Toon de statistieken van de laatste 24 uur.")
async def summary_cmd(inter):
    try:
        await inter.response.defer(ephemeral=False)
        embed = build_embed(EVENTS)
        await inter.followup.send(embed=embed)
    except Exception as e:
        print("[SUMMARY ERROR]", e)
        await inter.followup.send("Er ging iets mis bij /summary.")


# ======================================================
# LAST SHINIES
# ======================================================

@tree.command(name="recent_shinies", description="Toon de laatste 5 shinies.")
async def recent_shinies(inter):
    try:
        await inter.response.defer(ephemeral=False)

        shinies = [e for e in EVENTS if e["type"] == "Shiny"][-5:]

        if not shinies:
            await inter.followup.send("✨ Geen shinies gevonden.")
            return

        msg = "\n".join(
            f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
            f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
            for e in reversed(shinies)
        )

        await inter.followup.send(f"✨ **Laatste Shinies:**\n{msg}")

    except Exception as e:
        print("[SHINIES ERROR]", e)
        await inter.followup.send("Fout bij ophalen shinies.")


# ======================================================
# CSV EXPORT
# ======================================================

@tree.command(name="csv", description="Download de volledige CSV log.")
async def csv_export(inter):
    try:
        await inter.response.defer(ephemeral=True)

        lines = [
            "timestamp,type,name,iv0,iv1,iv2"
        ]

        for e in EVENTS:
            iv = e.get("iv") or [None, None, None]
            line = f"{e['timestamp']},{e['type']},{e['name']},{iv[0]},{iv[1]},{iv[2]}"
            lines.append(line)

        csv_data = "\n".join(lines).encode("utf-8")

        await inter.followup.send(
            file=discord.File(fp=csv_data, filename="pxstats.csv")
        )

    except Exception as e:
        print("[CSV ERROR]", e)
        await inter.followup.send("Fout bij CSV export.")


# ======================================================
# START BOT
# ======================================================

bot.run(DISCORD_TOKEN)
