# PXstats v3.8 – main.py
# Fixes: shiny double logging, persistent storage, pokedex init

import os, re, time, json, threading, asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque
from typing import Optional, Dict, List

import discord
from discord import app_commands
from discord.ui import View, Button

from PXstats.parser import parse_polygonx_embed
from PXstats.stats import build_embed
from PXstats.utils import init_pokedex, TZ

# ========= CONFIG =========
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None

# ========= DISCORD =========
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ========= KEEPALIVE =========
class _Healthz(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *a, **k): return

def start_keepalive():
    port = int(os.getenv("PORT", "10000"))
    HTTPServer(("", port), _Healthz).serve_forever()

def start_keepalive_bg():
    threading.Thread(target=start_keepalive, daemon=True).start()
    print(f"[KEEPALIVE] started on :10000")

# ========= STORAGE =========
EVENTS_FILE = "events.json"
EVENTS: deque = deque(maxlen=10000)

def save_events():
    try:
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(EVENTS), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[SAVE ERR]", e)

def load_events():
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            for e in json.load(f):
                EVENTS.append(e)
        print(f"[LOAD] {len(EVENTS)} events restored")

def add_event(evt_type: str, data: dict, ts: Optional[float] = None):
    EVENTS.append({"ts": ts if ts else time.time(), "type": evt_type, "data": data or {}})
    save_events()

def last_24h() -> List[Dict]:
    cutoff = time.time() - 86400
    return [e for e in EVENTS if e["ts"] >= cutoff]

# ========= BACKFILL =========
async def backfill_from_channel(limit=500):
    if not CHANNEL_ID: return
    ch = client.get_channel(CHANNEL_ID)
    if not ch: 
        print("[BACKFILL] Channel not found")
        return
    before = len(EVENTS)
    async for m in ch.history(limit=limit):
        for e in m.embeds:
            evt, p = parse_polygonx_embed(e)
            if not evt: continue
            ts = m.created_at.timestamp()

            if evt == "Shiny":
                p["shiny"] = True
                add_event("Catch", p, ts)
                add_event("Shiny", p, ts)
                continue

            if evt in {"Quest","Raid","MaxBattle","Rocket"}:
                src = evt.lower()
                add_event("Encounter", {"name": p.get("name"), "source": src}, ts)

            add_event(evt, p, ts)
    print(f"[BACKFILL] +{len(EVENTS)-before} events restored")

# ========= MESSAGE PARSER =========
@client.event
async def on_message(m: discord.Message):
    if m.author == client.user or not m.embeds: return
    for e in m.embeds:
        evt, p = parse_polygonx_embed(e)
        if not evt: continue
        ts = m.created_at.timestamp()

        if evt == "Shiny":
            p["shiny"] = True
            add_event("Catch", p, ts)
            add_event("Shiny", p, ts)
            continue

        if evt in {"Quest","Raid","MaxBattle","Rocket"}:
            src = evt.lower()
            add_event("Encounter", {"name": p.get("name"), "source": src}, ts)

        add_event(evt, p, ts)
    print(f"[INGEST] processed embeds from {m.author}")

# ========= UI =========
class SummaryView(View):
    def __init__(self, mode="catch"):
        super().__init__(timeout=180); self.mode = mode

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, i: discord.Interaction, b: Button):
        try:
            await i.response.edit_message(embed=build_embed(self.mode), view=self)
        except Exception as e:
            await i.followup.send("Refresh failed", ephemeral=True)
            print("[REFRESH ERR]", e)

    @discord.ui.button(label="Toggle Rate", style=discord.ButtonStyle.secondary)
    async def toggle(self, i: discord.Interaction, b: Button):
        self.mode = "shiny" if self.mode == "catch" else "catch"
        await i.response.edit_message(embed=build_embed(self.mode), view=self)

@tree.command(name="summary", description="Toon de 24u statistieken (met refresh & toggle)")
async def summary(inter: discord.Interaction):
    await inter.response.send_message("📊 Summary geplaatst.", ephemeral=True)
    await inter.channel.send(embed=build_embed(), view=SummaryView())

# ========= DAILY SUMMARY =========
async def daily_summary_loop():
    last_key = None
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = datetime.now(TZ)
            key = now.strftime("%Y-%m-%d")
            if now.hour == 0 and now.minute == 5 and key != last_key:
                ch = client.get_channel(CHANNEL_ID)
                if ch:
                    await ch.send(embed=build_embed(), view=SummaryView())
                    last_key = key
                    print(f"[DAILY] autosummary {key}")
                await asyncio.sleep(60)
            await asyncio.sleep(5)
        except Exception as e:
            print("[DAILY ERR]", e)
            await asyncio.sleep(10)

# ========= READY =========
@client.event
async def on_ready():
    print(f"[READY] {client.user}")
    init_pokedex()
    load_events()
    await backfill_from_channel(limit=500)
    client.loop.create_task(daily_summary_loop())
    if GUILD_ID:
        await tree.sync(guild=discord.Object(id=GUILD_ID))
    else:
        await tree.sync()
    await client.change_presence(activity=discord.Game("PXstats v3.8 • /summary"))

# ========= MAIN =========
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("❌ DISCORD_TOKEN ontbreekt")
    start_keepalive_bg()
    client.run(DISCORD_TOKEN)
