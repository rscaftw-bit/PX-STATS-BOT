# =========================================================
# PXstats • main-v3.8 • 2025-11-10
# Includes: (fix) build_embed(rows), improved /summary handling
# =========================================================

import os, time, threading, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord import app_commands
from discord.ui import View, Button

# ===== Imports from PXstats modules =====
from PXstats.parser import parse_polygonx_embed
from PXstats.stats import build_embed
from PXstats.utils import last_24h
from PXstats.utils import add_event, load_events, save_events, EVENTS, load_pokedex

# ===== Discord setup =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None
TZ = ZoneInfo("Europe/Brussels")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ===== Keepalive server (Render requirement) =====
class _Healthz(BaseHTTPRequestHandler):
    def _ok(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self._ok()

    def do_HEAD(self):
        self._ok()

    def log_message(self, *args, **kwargs):
        return


def start_keepalive():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("", port), _Healthz)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[KEEPALIVE] started on :{port}")

# ===== On message: parse PolygonX embeds =====
@client.event
async def on_message(m: discord.Message):
    if m.author == client.user or not m.embeds:
        return
    rec = 0
    for e in m.embeds:
        evt, p = parse_polygonx_embed(e)
        if not evt:
            continue
        ts = m.created_at.timestamp()
        title_l = (e.title or "").lower()

        # Shiny handling
        if evt == "Shiny" and ("caught" in title_l or "caught successfully" in title_l):
            add_event("Catch", p, ts)
            rec += 1

        # Quest / Raid / Rocket / MaxBattle get Encounter flag too
        if evt in {"Quest", "Raid", "Rocket", "MaxBattle"}:
            src = (
                "quest" if evt == "Quest"
                else "raid" if evt == "Raid"
                else "rocket" if evt == "Rocket"
                else "maxbattle"
            )
            add_event("Encounter", {"name": p.get("name"), "source": src}, ts)
            rec += 1

        add_event(evt, p, ts)
        rec += 1

    if rec:
        print(f"[INGEST] processed embeds from {m.author} ({rec} events)")

# ===== Backfill from history =====
async def backfill_from_channel(limit=500):
    ch = client.get_channel(CHANNEL_ID) if CHANNEL_ID else None
    if not ch:
        print("[BACKFILL] no valid channel configured")
        return
    before = len(EVENTS)
    async for m in ch.history(limit=limit):
        for e in m.embeds:
            evt, p = parse_polygonx_embed(e)
            if not evt:
                continue
            ts = m.created_at.timestamp()
            title_l = (e.title or "").lower()

            if evt == "Shiny" and ("caught" in title_l or "caught successfully" in title_l):
                add_event("Catch", p, ts)

            if evt in {"Quest", "Raid", "Rocket", "MaxBattle"}:
                src = (
                    "quest" if evt == "Quest"
                    else "raid" if evt == "Raid"
                    else "rocket" if evt == "Rocket"
                    else "maxbattle"
                )
                add_event("Encounter", {"name": p.get("name"), "source": src}, ts)

            add_event(evt, p, ts)
    print(f"[BACKFILL] +{len(EVENTS) - before} events restored")

# ===== Summary UI =====
class SummaryView(View):
    def __init__(self, mode="catch"):
        super().__init__(timeout=180)
        self.mode = mode

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, i: discord.Interaction, b: Button):
        try:
            await i.response.edit_message(embed=build_embed(last_24h(), self.mode), view=self)
        except Exception as e:
            await i.followup.send(f"Refresh failed: {e}", ephemeral=True)

    @discord.ui.button(label="Rate: Catch", style=discord.ButtonStyle.secondary)
    async def toggle(self, i: discord.Interaction, b: Button):
        self.mode = "shiny" if self.mode == "catch" else "catch"
        b.label = "Rate: Shiny" if self.mode == "shiny" else "Rate: Catch"
        await i.response.edit_message(embed=build_embed(last_24h(), self.mode), view=self)

# ===== /summary command =====
@tree.command(name="summary", description="Toon de 24u stats met refresh en toggle")
async def summary(inter: discord.Interaction):
    try:
        await inter.response.send_message("📊 Summary geplaatst.", ephemeral=True)
    except Exception as e:
        print("[WARN] Ephemeral send failed:", e)
    ch = client.get_channel(CHANNEL_ID) or inter.channel
    await ch.send(embed=build_embed(last_24h()), view=SummaryView())

# ===== Daily summary at 00:05 =====
_last_daily_key = None

async def daily_summary_loop():
    global _last_daily_key
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = datetime.now(TZ)
            key = now.strftime("%Y-%m-%d")
            if now.hour == 0 and now.minute == 5 and _last_daily_key != key:
                ch = client.get_channel(CHANNEL_ID)
                if ch:
                    await ch.send(embed=build_embed(last_24h()), view=SummaryView())
                    _last_daily_key = key
                    print(f"[DAILY] Posted autosummary for {key}")
                await asyncio.sleep(60)
            await asyncio.sleep(5)
        except Exception as e:
            print("[DAILY ERROR]", e)
            await asyncio.sleep(10)

# ===== Ready event =====
@client.event
async def on_ready():
    print(f"[READY] {client.user}")
    try:
        if GUILD_ID:
            await tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await tree.sync()
        await client.change_presence(status=discord.Status.online, activity=discord.Game("PXstats · /summary"))
        load_pokedex()
        load_events()
        await backfill_from_channel(limit=500)
        client.loop.create_task(daily_summary_loop())
        print("[INIT] Bot is actief en volledig geladen.")
    except Exception as er:
        print("[READY ERROR]", er)

# ===== Main =====
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("❌ DISCORD_TOKEN ontbreekt")
    start_keepalive()
    client.run(DISCORD_TOKEN)
