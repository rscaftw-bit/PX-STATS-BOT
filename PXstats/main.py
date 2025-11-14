# PXstats • main.py
# Stable v4.1 – 2025-11-14
#
# - Uses new parser + stats modules
# - Stores events locally as JSON
# - Supports /summary, /recent_shinies and /csv
# - Simple HTTP keep-alive server for Render

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

import discord
from discord import app_commands

from PXstats.parser import parse_polygonx_embed
from PXstats.stats import build_embed
from PXstats.utils import (
    load_events,
    save_events,
    add_event,
    EVENTS,
    TZ,
    load_pokedex,
)


# --------------------------------------------------
# Startup
# --------------------------------------------------
print("=== PXstats startup initiated ===")

# Pre-load events & Pokédex (non-fatal on error)
load_events()
try:
    pokedex = load_pokedex()
    print(f"[INIT] Pokédex loaded: {len(pokedex)} entries")
except Exception as e:
    print(f"[INIT] Pokédex could not be loaded: {e}")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# --------------------------------------------------
# Keep-alive HTTP server (for Render)
# --------------------------------------------------
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


# --------------------------------------------------
# Discord events
# --------------------------------------------------
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
        print(f"[SYNC ERROR] {e}")


@bot.event
async def on_message(msg: discord.Message):
    # Ignore our own messages
    if msg.author == bot.user:
        return

    if not msg.embeds:
        return

    processed = 0

    for e in msg.embeds:
        etype, data = parse_polygonx_embed(e)
        if not etype:
            continue

        # timestamp from embed or message
        ts = e.timestamp or msg.created_at
        data["timestamp"] = ts
        data["type"] = etype

        add_event(data)
        processed += 1

    if processed:
        print(f"[INGEST] processed embeds from {msg.author} ({processed} events)")
        save_events()


# --------------------------------------------------
# Slash commands
# --------------------------------------------------
@tree.command(name="summary", description="Toon statistieken van de laatste 24 uur.")
async def summary_cmd(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=False, thinking=False)
        embed = build_embed(EVENTS)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("[SUMMARY ERROR]", e)
        try:
            await interaction.followup.send("Er ging iets mis bij /summary.")
        except Exception:
            pass


@tree.command(name="recent_shinies", description="Toon de laatste 5 shinies.")
async def recent_shinies_cmd(interaction: discord.Interaction):
    from datetime import datetime, timedelta

    try:
        await interaction.response.defer(ephemeral=False, thinking=False)
        cutoff = datetime.now(TZ) - timedelta(hours=24)
        shinies = [
            e for e in EVENTS
            if e.get("shiny") is True and e.get("timestamp") and e["timestamp"] >= cutoff
        ]
        shinies.sort(key=lambda x: x["timestamp"], reverse=True)
        shinies = shinies[:5]

        if not shinies:
            await interaction.followup.send("Geen shinies gevonden in de laatste 24 uur.")
            return

        lines = []
        for e in shinies:
            ts = e["timestamp"].strftime("%d %B %Y %H:%M")
            iv = e.get("iv")
            iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}" if iv else "?"
            lines.append(f"{e['name']} {iv_str} ({ts})")

        await interaction.followup.send("✨ **Laatste Shinies (24h):**\n" + "\n".join(lines))
    except Exception as e:
        print("[SHINIES ERROR]", e)
        try:
            await interaction.followup.send("Er ging iets mis bij /recent_shinies.")
        except Exception:
            pass


@tree.command(name="csv", description="Download een CSV-export van alle events.")
async def csv_cmd(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True, thinking=False)

        lines = ["timestamp,type,name,iv0,iv1,iv2,shiny,source"]
        for e in EVENTS:
            iv = e.get("iv")
            iv0, iv1, iv2 = (iv or (None, None, None))
            ts = e.get("timestamp")
            ts_str = ts.isoformat() if ts is not None else ""
            line = (
                f"{ts_str},{e.get('type','')},{e.get('name','')},"
                f"{iv0},{iv1},{iv2},{e.get('shiny', False)},{e.get('source','')}"
            )
            lines.append(line)

        content = "\n".join(lines).encode("utf-8")
        buf = BytesIO(content)

        await interaction.followup.send(
            file=discord.File(fp=buf, filename="pxstats.csv")
        )
    except Exception as e:
        print("[CSV ERROR]", e)
        try:
            await interaction.followup.send("Er ging iets mis bij /csv.")
        except Exception:
            pass


# --------------------------------------------------
# Run bot
# --------------------------------------------------
if not DISCORD_TOKEN:
    print("[FATAL] DISCORD_TOKEN omgevingsvariabele ontbreekt.")
else:
    bot.run(DISCORD_TOKEN)
