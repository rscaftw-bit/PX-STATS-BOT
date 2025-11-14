# PXstats • main.py • v4.2 • 2025-11-14

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

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
    last_24h,
    load_pokedex,
)

print("=== PXstats startup initiated ===")

# Pokédex pre-load (optioneel)
try:
    pokedex = load_pokedex()
    print(f"[INIT] Pokédex geladen: {len(pokedex)} entries")
except Exception as e:
    print(f"[INIT ERROR] Pokédex kon niet geladen worden: {e}")

# Events laden
load_events()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None

intents = discord.Intents.default()
intents.message_content = True  # nodig om embeds van andere bots te lezen

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# ======================================================
# Keep-alive server (Render)
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
# Ready
# ======================================================

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (id={bot.user.id})")

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
        print("[SYNC ERROR]", e)


# ======================================================
# Ingest van PolygonX / Spidey embeds
# ======================================================

@bot.event
async def on_message(msg: discord.Message):
    # Negeer eigen berichten
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

    if processed:
        print(f"[INGEST] processed embeds from {msg.author} ({processed} events)")
        save_events()


# ======================================================
# /summary
# ======================================================

@tree.command(name="summary", description="Toon statistieken van de laatste 24 uur")
async def summary_cmd(inter: discord.Interaction):
    try:
        await inter.response.defer(ephemeral=False, thinking=False)
        rows = last_24h(EVENTS)
        embed = build_embed(rows)
        await inter.followup.send(embed=embed)
    except Exception as e:
        print("[SUMMARY ERROR]", e)
        try:
            await inter.followup.send("Er ging iets mis bij /summary.")
        except Exception:
            pass


# ======================================================
# /recent_shinies
# ======================================================

@tree.command(name="recent_shinies", description="Toon de laatste 5 shinies (laatste 24h)")
async def recent_shinies_cmd(inter: discord.Interaction):
    try:
        await inter.response.defer(ephemeral=False)
        rows = last_24h(EVENTS)
        shinies = [
            e for e in rows
            if e.get("type") == "Catch" and e.get("shiny")
        ]
        shinies = sorted(shinies, key=lambda x: x["timestamp"], reverse=True)[:5]

        if not shinies:
            await inter.followup.send("Geen shinies gevonden in de laatste 24 uur.")
            return

        lines = []
        for e in shinies:
            ts = e["timestamp"].strftime("%d %B %Y %H:%M")
            lines.append(f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} ({ts})")

        await inter.followup.send("✨ **Laatste Shinies:**\n" + "\n".join(lines))
    except Exception as e:
        print("[SHINIES ERROR]", e)
        await inter.followup.send("Fout bij ophalen van shinies.")


# ======================================================
# /csv
# ======================================================

@tree.command(name="csv", description="Download volledige CSV-log")
async def csv_cmd(inter: discord.Interaction):
    try:
        await inter.response.defer(ephemeral=True)

        lines = ["timestamp,type,name,iv0,iv1,iv2,shiny"]
        for e in EVENTS:
            iv = e.get("iv") or [None, None, None]
            shiny = 1 if e.get("shiny") else 0
            ts = e.get("timestamp")
            if isinstance(ts, datetime):
                ts_str = ts.isoformat()
            else:
                ts_str = str(ts)
            lines.append(f"{ts_str},{e.get('type')},{e.get('name')},{iv[0]},{iv[1]},{iv[2]},{shiny}")

        csv_bytes = "\n".join(lines).encode("utf-8")
        file = discord.File(fp=csv_bytes, filename="pxstats.csv")
        await inter.followup.send(file=file)
    except Exception as e:
        print("[CSV ERROR]", e)
        await inter.followup.send("Fout bij CSV-export.")


# ======================================================
# Start bot
# ======================================================

bot.run(DISCORD_TOKEN)
