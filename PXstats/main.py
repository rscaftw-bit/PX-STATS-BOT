# =========================================================
# PXstats • main-v3.8.3 • 2025-11-10
# Fixes:
# - build_embed(rows) everywhere
# - /summary defers to avoid Unknown interaction
# - Shiny => double log (Catch + Shiny) with data["shiny"]=True
# - Encounter pairing for Quest/Raid/Rocket/MaxBattle
# - Keepalive answers GET + HEAD (no 501)
# - Pokedex failsafe: always expand to 1..1025 and map "p###"
# =========================================================

import os, re, time, threading, asyncio, json
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any

import discord
from discord import app_commands
from discord.ui import View, Button

# ===== Imports from PXstats modules =====
from PXstats.parser import parse_polygonx_embed
from PXstats.stats import build_embed
from PXstats.utils import (
    last_24h, add_event, load_events, save_events, EVENTS,
    load_pokedex, TZ  # TZ from utils (defaults to Europe/Brussels)
)
print("=== PXstats startup initiated ===")

try:
    from PXstats.pokedex import load_pokedex
    pokedex = load_pokedex()
    print(f"[INIT] Pokédex geladen: {len(pokedex)} entries")
except Exception as e:
    print(f"[ERROR] Pokédex kon niet geladen worden: {e}")

# ===== Discord setup =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ======== POKEDEX FAILSAFE ========
_POKEDEX: Dict[str, str] = {}
_POKEDEX_PATH = os.path.join(os.path.dirname(__file__), "pokedex.json")

def _ensure_full_pokedex() -> None:
    """Load current pokedex and make sure we have entries 1..1025 (placeholders if missing)."""
    global _POKEDEX
    _POKEDEX = load_pokedex() or {}
    changed = False
    # Backfill placeholders for any missing id
    for i in range(1, 1026):
        k = str(i)
        if k not in _POKEDEX or not _POKEDEX.get(k):
            _POKEDEX[k] = f"Pokemon {i}"
            changed = True
    if changed:
        try:
            with open(_POKEDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(_POKEDEX, f, ensure_ascii=False, indent=2)
            print(f"[POKEDEX] expanded to {len(_POKEDEX)} entries")
        except Exception as e:
            print("[POKEDEX SAVE ERR]", e)

_PNUM = re.compile(r"(?i)^\s*p\s*(\d{1,4})\s*$")

def _dex_name_safe(name: str) -> str:
    """Map 'p###' to a readable name using our in-memory pokedex; fallback to 'Pokemon ###'."""
    if not name:
        return "?"
    s = str(name).strip()
    m = _PNUM.match(s)
    if m:
        n = m.group(1).lstrip("0") or "0"
        return _POKEDEX.get(n, f"Pokemon {n}")
    return s

def _normalize_name_in_event(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data:
        return {}
    nm = data.get("name")
    if isinstance(nm, str):
        data["name"] = _dex_name_safe(nm.replace("(", "").replace(")", "").strip())
    return data

# ===== Keepalive server (Render requirement) =====
class _Healthz(BaseHTTPRequestHandler):
    def _ok(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):  self._ok()
    def do_HEAD(self): self._ok()
    def log_message(self, *args, **kwargs): return

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
        p = _normalize_name_in_event(p or {})
        title_l = (e.title or "").lower()

        # Shiny handling (double log: Catch + Shiny)
        if evt == "Shiny":
            p["shiny"] = True
            add_event("Catch", p, ts); rec += 1
            add_event("Shiny", p, ts); rec += 1
            continue

        # Quest / Raid / Rocket / MaxBattle -> also log an Encounter(source=...)
        if evt in {"Quest", "Raid", "Rocket", "MaxBattle"}:
            src = (
                "quest" if evt == "Quest"
                else "raid" if evt == "Raid"
                else "rocket" if evt == "Rocket"
                else "maxbattle"
            )
            add_event("Encounter", {"name": p.get("name"), "source": src}, ts); rec += 1

        # Always log the base event
        add_event(evt, p, ts); rec += 1

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
            p = _normalize_name_in_event(p or {})
            title_l = (e.title or "").lower()

            if evt == "Shiny":
                p["shiny"] = True
                add_event("Catch", p, ts)
                add_event("Shiny", p, ts)
                continue

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
        except discord.InteractionResponded:
            await i.edit_original_response(embed=build_embed(last_24h(), self.mode), view=self)
        except Exception as e:
            try:    await i.followup.send(f"Refresh failed: {e}", ephemeral=True)
            except: pass

    @discord.ui.button(label="Rate: Catch", style=discord.ButtonStyle.secondary)
    async def toggle(self, i: discord.Interaction, b: Button):
        self.mode = "shiny" if self.mode == "catch" else "catch"
        b.label = "Rate: Shiny" if self.mode == "shiny" else "Rate: Catch"
        try:
            await i.response.edit_message(embed=build_embed(last_24h(), self.mode), view=self)
        except discord.InteractionResponded:
            await i.edit_original_response(embed=build_embed(last_24h(), self.mode), view=self)

# ===== /summary command =====
@tree.command(name="summary", description="Toont de samenvatting van de laatste 24 uur")
async def summary(inter: discord.Interaction):
    try:
        # Defert onmiddellijk om timeout te vermijden
        await inter.response.defer(ephemeral=False, thinking=True)

        # Bouw de embed
        embed = build_embed(last_24h())

        # Antwoord via followup (na defer mag enkel dit)
        await inter.followup.send(embed=embed)

    except discord.errors.NotFound:
        print("[WARNING] Interaction expired before defer() — fallback naar kanaal.")
        try:
            embed = build_embed(last_24h())
            await inter.channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Kon summary niet posten: {e}")
    except Exception as e:
        print(f"[ERROR] Summary command failed: {e}")

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
        # Slash commands
        if GUILD_ID:
            await tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await tree.sync()

        # Presence
        await client.change_presence(status=discord.Status.online, activity=discord.Game("PXstats · /summary"))

        # Pokedex + events
        _ensure_full_pokedex()
        load_events()

        # Backfill & daily summary
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
