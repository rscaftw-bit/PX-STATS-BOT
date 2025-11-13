# ======================================================
# PXstats • main.py • v4.0 (13-11-2025)
# Clean, stable, fixed release
# ======================================================

import os
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

import discord
from discord import app_commands

# ------------------------------------------------------
# Local modules
# ------------------------------------------------------
from PXstats.parser import parse_polygonx_embed
from PXstats.stats import build_embed
from PXstats.utils import load_events, save_events, add_event, EVENTS, TZ
from PXstats.pokedex import load_pokedex


# ======================================================
# STARTUP
# ======================================================

print("=== PXstats startup initiated ===")

try:
    pokedex = load_pokedex()
    print(f"[INIT] Pokédex geladen: {len(pokedex)} entries")
except Exception as e:
    print(f"[ERROR] Pokédex kon niet geladen worden: {e}")


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# ======================================================
# KEEP-ALIVE SERVER (Render)
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
# DISCORD READY
# ======================================================

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user}")

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
            print("[SYNC] Commands gesynchroniseerd (guild)")
        else:
            await tree.sync()
            print("[SYNC] Commands gesynchroniseerd (global)")
    except Exception as e:
        print(f"[SYNC ERROR] {e}")


# ======================================================
# INGEST FROM POLYGONX / SPIDEY BOT
# ======================================================

@bot.event
async def on_message(msg: discord.Message):

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
        print(f"[INGEST] processed embeds from {msg.author} ({processed} events)")
        save_events()


# ======================================================
# /summary
# ======================================================

@tree.command(name="summary", description="Toon statistieken van de laatste 24h")
async def summary_cmd(inter):
    try:
        await inter.response.defer(ephemeral=False, thinking=False)
        embed = build_embed(EVENTS)
        await inter.followup.send(embed=embed)
    except Exception as e:
        print("[SUMMARY ERROR]", e)
        try:
            await inter.followup.send("Er ging iets mis bij /summary.")
        except:
            pass


# ======================================================
# /recent_shinies
# ======================================================

@tree.command(name="recent_shinies", description="Toon de laatste 5 shinies")
async def recent_shinies(inter):
    try:
        await inter.response.defer(ephemeral=False)
        shinies = [e for e in EVENTS if e["type"] == "Shiny"][-5:]

        if not shinies:
            await inter.followup.send("Geen shinies gevonden in de logs.")
            return

        txt = "\n".join(
            f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
            f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
            for e in reversed(shinies)
        )
        await inter.followup.send(f"✨ **Laatste Shinies:**\n{txt}")

    except Exception as e:
        print("[SHINIES ERROR]", e)
        await inter.followup.send("Fout bij ophalen van shinies.")


# ======================================================
# /csv EXPORT
# ======================================================

@tree.command(name="csv", description="Download volledige CSV-log")
async def csv_export(inter):
    try:
        await inter.response.defer(ephemeral=True)

        lines = [
            "timestamp,type,name,iv0,iv1,iv2"
        ]
        for e in EVENTS:
            iv0, iv1, iv2 = (e.get("iv") or [None, None, None])
            line = f"{e['timestamp']},{e['type']},{e['name']},{iv0},{iv1},{iv2}"
            lines.append(line)

        content = "\n".join(lines)

        await inter.followup.send(
            file=discord.File(fp=bytes(content, "utf-8"), filename="pxstats.csv")
        )

    except Exception as e:
        print("[CSV ERROR]", e)
        await inter.followup.send("Fout bij CSV export.")


# ======================================================
# START BOT
# ======================================================

bot.run(DISCORD_TOKEN)