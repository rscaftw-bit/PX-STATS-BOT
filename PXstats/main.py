# ======================================================
# PXstats • main.py • 2025-11-13
# Volledig gefixt: events, pokedex, shiny, /summary, /csv
# ======================================================

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

import discord
from discord import app_commands

from PXstats import utils
from PXstats.parser import parse_polygonx_embed
from PXstats.stats import build_embed
from PXstats.pokedex import load_pokedex
from PXstats.utils import TZ

# ------------------------------------------------------
# Discord config
# ------------------------------------------------------

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0) or None

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# ------------------------------------------------------
# Keepalive (Render)
# ------------------------------------------------------

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


# ------------------------------------------------------
# Ready
# ------------------------------------------------------

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user}")

    # laad pokedex + events
    load_pokedex()
    utils.load_events()

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
            print("[SYNC] Commands gesynchroniseerd (guild).")
        else:
            await tree.sync()
            print("[SYNC] Commands gesynchroniseerd (global).")
    except Exception as e:
        print(f"[SYNC ERROR] {e}")


# ------------------------------------------------------
# Ingest PolygonX embeds
# ------------------------------------------------------

@bot.event
async def on_message(msg: discord.Message):

    # eigen bot negeren, maar andere bots (Spidey) niet
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

        utils.add_event(data)
        processed += 1

    if processed > 0:
        print(f"[INGEST] processed embeds from {msg.author} ({processed} events)")
        utils.save_events()


# ------------------------------------------------------
# /summary
# ------------------------------------------------------

@tree.command(name="summary", description="Toon statistieken van de laatste 24h")
async def summary_cmd(inter: discord.Interaction):
    try:
        await inter.response.defer(ephemeral=False, thinking=False)
        embed = build_embed(utils.EVENTS)
        await inter.followup.send(embed=embed)
    except Exception as e:
        print("[SUMMARY ERROR]", e)
        try:
            await inter.followup.send("Er ging iets mis bij /summary.")
        except Exception:
            pass


# ------------------------------------------------------
# /recent_shinies
# ------------------------------------------------------

@tree.command(name="recent_shinies", description="Toon de laatste 5 shinies")
async def recent_shinies(inter: discord.Interaction):
    try:
        await inter.response.defer(ephemeral=False)

        shinies = [
            e for e in utils.EVENTS
            if e.get("type") == "Catch" and e.get("shiny") is True
        ][-5:]

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
        try:
            await inter.followup.send("Fout bij ophalen van shinies.")
        except Exception:
            pass


# ------------------------------------------------------
# /csv export
# ------------------------------------------------------

@tree.command(name="csv", description="Download volledige CSV-log")
async def csv_export(inter: discord.Interaction):
    try:
        await inter.response.defer(ephemeral=True)

        lines = ["timestamp,type,name,iv0,iv1,iv2,shiny"]

        for e in utils.EVENTS:
            iv = e.get("iv") or [None, None, None]
            iv0, iv1, iv2 = iv
            shiny_flag = 1 if e.get("shiny") else 0
            line = (
                f"{e['timestamp'].isoformat()},{e['type']},{e['name']},"
                f"{iv0},{iv1},{iv2},{shiny_flag}"
            )
            lines.append(line)

        content = "\n".join(lines)
        data = content.encode("utf-8")

        await inter.followup.send(
            file=discord.File(fp=bytes(data), filename="pxstats.csv")
        )

    except Exception as e:
        print("[CSV ERROR]", e)
        try:
            await inter.followup.send("Fout bij CSV export.")
        except Exception:
            pass


# ------------------------------------------------------
# Start bot
# ------------------------------------------------------

bot.run(DISCORD_TOKEN)
