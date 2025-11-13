# =========================================================
# PXstats • main.py • v3.9.3 (FINAL)
# =========================================================

import os
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord import app_commands
from discord.ui import View, Button

# PXstats modules
from PXstats.parser import parse_polygonx_embed
from PXstats.stats import build_embed, make_csv_rows
from PXstats.utils import (
    EVENTS, add_event, load_events, save_events,
    last_24h, TZ
)

print("=== PXstats STARTUP ===")

# Load existing events
load_events()

# Load Pokédex (full file)
try:
    from PXstats.pokedex import load_pokedex
    pok = load_pokedex()
    print(f"[INIT] Pokédex loaded: {len(pok)} entries")
except Exception as e:
    print(f"[ERROR] Failed loading Pokédex: {e}")

# ---------------------------------------------------------
# Discord setup
# ---------------------------------------------------------

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ---------------------------------------------------------
# Keep-alive tiny webserver (GET/HEAD only)
# ---------------------------------------------------------

class PingHandler(BaseHTTPRequestHandler):

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"PXstats OK")

    def log_message(self, *args):
        return  # keep console clean


def run_keepalive():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    print(f"[KEEPALIVE] Running at :{port}")
    server.serve_forever()


threading.Thread(target=run_keepalive, daemon=True).start()


# ---------------------------------------------------------
# Utility
# ---------------------------------------------------------

def safe_filename(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_ ").strip()


# ---------------------------------------------------------
# Slash Commands
# ---------------------------------------------------------

@tree.command(name="summary", description="Show today's stats (last 24h)")
async def summary_cmd(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True, thinking=False)

    rows = last_24h()
    emb = build_embed(rows)

    await interaction.followup.send(embed=emb, ephemeral=True)


@tree.command(name="recent_shinies", description="Show last shiny Pokémon")
async def recent_shinies(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    rows = last_24h()
    shiny_rows = [e for e in rows if e["data"].get("shiny")]

    if not shiny_rows:
        await interaction.followup.send("Geen shiny gevonden in de laatste 24 uur.", ephemeral=True)
        return

    txt = "\n".join(
        f"{e['data']['name']} {e['data']['iv'][0]}/{e['data']['iv'][1]}/{e['data']['iv'][2]} "
        f"({datetime.fromtimestamp(e['ts'], TZ).strftime('%d %B %Y %H:%M')})"
        for e in sorted(shiny_rows, key=lambda x: x["ts"], reverse=True)[:10]
    )

    await interaction.followup.send(f"✨ **Laatste shinies**:\n{txt}", ephemeral=True)


@tree.command(name="csv", description="Download CSV van de laatste 24u")
async def csv_cmd(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    rows = last_24h()
    data = make_csv_rows(rows)

    # Build CSV
    header = "timestamp,type,name,iv,shiny,source\n"
    lines = [header]
    for r in data:
        line = f"{r['timestamp']},{r['type']},{r['name']},{r['iv']},{r['shiny']},{r['source']}\n"
        lines.append(line)

    csv_data = "".join(lines).encode("utf-8")

    await interaction.followup.send(
        "📄 CSV van de laatste 24h:",
        file=discord.File(fp=bytes(csv_data), filename="pxstats_24h.csv"),
        ephemeral=True
    )


# ---------------------------------------------------------
# Message Listener — ingest PolygonX / Spidey embeds
# ---------------------------------------------------------

@client.event
async def on_message(msg: discord.Message):

    # ignore bot itself
    if msg.author.id == client.user.id:
        return
    if not msg.embeds:
        return

    # Parse embeds
    processed = 0

    for e in msg.embeds:
        ev_type, data = parse_polygonx_embed(e)
        if ev_type:
            add_event(ev_type, data)
            processed += 1

    if processed:
        print(f"[INGEST] Processed {processed} event(s) from {msg.author}")


# ---------------------------------------------------------
# Ready event
# ---------------------------------------------------------

@client.event
async def on_ready():
    print(f"[READY] Logged in as {client.user}")
    try:
        guild = discord.Object(id=GUILD_ID)
        await tree.sync(guild=guild)
        print(f"[SLASH] Synced in guild {GUILD_ID}")
    except Exception as e:
        print(f"[ERROR] Slash sync: {e}")


# ---------------------------------------------------------
# Run the bot
# ---------------------------------------------------------

client.run(DISCORD_TOKEN)