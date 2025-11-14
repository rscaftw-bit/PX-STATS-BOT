# ======================================================
# PXstats • main.py • Final Sync with utils.py
# ======================================================

import os
import asyncio
from datetime import datetime
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

# ------------------------------------------------------
# Startup
# ------------------------------------------------------

print("=== PXstats startup initiated ===")

try:
    pokedex = load_pokedex()
    print(f"[INIT] Pokédex loaded: {len(pokedex)} entries")
except Exception as e:
    print(f"[INIT ERROR] Could not load Pokédex: {e}")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# ------------------------------------------------------
# Keepalive server for Render
# ------------------------------------------------------

class KeepAlive(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_server():
    server = HTTPServer(("0.0.0.0", 10000), KeepAlive)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()

# ------------------------------------------------------
# Ready
# ------------------------------------------------------

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user}")

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
        else:
            await tree.sync()
        print("[SYNC] Commands synced")
    except Exception as e:
        print("[SYNC ERROR]", e)

# ------------------------------------------------------
# PolygonX ingest
# ------------------------------------------------------

@bot.event
async def on_message(msg):

    if msg.author == bot.user:
        return
    if not msg.embeds:
        return

    processed = 0

    for e in msg.embeds:
        etype, data = parse_polygonx_embed(e)
        if not etype:
            continue

        ts = e.timestamp or datetime.now(TZ)
        data["timestamp"] = ts
        data["type"] = etype

        add_event(data)
        processed += 1

    if processed > 0:
        print(f"[INGEST] {processed} events")
        save_events()

# ------------------------------------------------------
# Commands
# ------------------------------------------------------

@tree.command(name="summary", description="Show last 24h stats")
async def summary(inter):
    try:
        await inter.response.defer(thinking=False)
        embed = build_embed(EVENTS)
        await inter.followup.send(embed=embed)
    except Exception as e:
        print("[SUMMARY ERROR]", e)
        await inter.followup.send("Summary error.")

# ------------------------------------------------------
# Start
# ------------------------------------------------------

bot.run(DISCORD_TOKEN)
