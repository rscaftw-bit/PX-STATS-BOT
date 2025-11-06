# bot.py
import os
import time
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque

import discord
from discord import app_commands
from discord.ui import View, Button

# =========================
# Config & Intents
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================
# Simple keep-alive HTTP server (for Render)
# =========================
class _HealthzHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args, **kwargs):
        return

def start_keepalive():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("", port), _HealthzHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[KEEPALIVE] Serving health on :{port}")

# =========================
# In-memory event storage
# =========================
EVENTS = deque(maxlen=10000)  # ring buffer

def add_event(evt_type: str, payload: dict):
    EVENTS.append({
        "ts": time.time(),     # epoch UTC
        "type": evt_type,      # "Catch", "Shiny", "Raid", "Rocket", "Hatch", "Quest", "Reward", "Encounter"
        "data": payload or {}
    })

def last_24h():
    cutoff = time.time() - 24 * 3600
    return [e for e in EVENTS if e["ts"] >= cutoff]

# =========================
# PolygonX embed parser
# =========================
RC_PAT = re.compile(r"(rare\s*candy|rc)\s*[:xX]?\s*(\d+)", re.I)
PKM_LINE_PAT = re.compile(r"^Pokemon:\s*([A-Za-zÀ-ÿ' .-]+)", re.I | re.M)  # vang bv. "Pokemon: Cottonee"

def _field_value(emb: discord.Embed, wanted_name: str):
    for f in emb.fields:
        if (f.name or "").strip().lower() == wanted_name.lower():
            return (f.value or "").strip()
    return None

def _extract_pokemon_name(e: discord.Embed):
    # 1) Field "Pokemon"
    val = _field_value(e, "Pokemon")
    if val:
        name = val.split("(")[0].strip()
        if name:
            return name

    # 2) Description: "Pokemon: NAME"
    if e.description:
        m = PKM_LINE_PAT.search(e.description)
        if m:
            return m.group(1).strip()

    # 3) Title fallback: "Pokemon caught successfully!" / others -> nothing there, but try in parentheses
    title = (e.title or "")
    m2 = re.search(r"([A-Za-zÀ-ÿ' .-]+)\s*\(", title)
    if m2:
        return m2.group(1).strip()

    return "?"

def parse_polygonx_embed(e: discord.Embed):
    """
    Return (evt_type, payload) or (None, None) if not recognized.
    """
    title = (e.title or "").strip()
    t = title.lower()

    # ---- Shiny (behandel eerst; sommige titels bevatten ook 'caught') ----
    if "shiny" in t:
        return ("Shiny", {"name": _extract_pokemon_name(e)})

    # ---- Catch success ----
    if "pokemon caught successfully" in t or "caught successfully" in t:
        return ("Catch", {"name": _extract_pokemon_name(e)})

    # ---- Incense Encounter ----
    if "incense encounter" in t or "encounter" in t:
        # voorkom dat 'rocket encounter' per ongeluk telt
        if "rocket" not in t:
            return ("Encounter", {"name": _extract_pokemon_name(e)})

    # ---- Raids / Rockets / Hatches / Rewards ----
    if "raid" in t:
        return ("Raid", {"title": title})
    if "rocket" in t:
        return ("Rocket", {"title": title})
    if "hatch" in t:
        return ("Hatch", {"name": _extract_pokemon_name(e) or title})
    if "reward" in t or "rewards" in t or "loot" in t:
        rare_candy = 0
        texts = [e.description or ""]
        for f in e.fields:
            texts.append(f"{f.name}\n{f.value}")
        blob = "\n".join(texts)
        m = RC_PAT.search(blob)
        if m:
            rare_candy = int(m.group(2))
        return ("Reward", {"title": title, "rare_candy": rare_candy})

    return (None, None)

# =========================
# Stats & embed builder
# =========================
def build_stats():
    rows = last_24h()
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    s = {
        "encounters": by_type.get("Encounter", 0),
        "catches":    by_type.get("Catch", 0),
        "shinies":    by_type.get("Shiny", 0),
        "raids":      by_type.get("Raid", 0),
        "rockets":    by_type.get("Rocket", 0),
        "hatches":    by_type.get("Hatch", 0),
        "quests":     by_type.get("Quest", 0),
        "rewards":    by_type.get("Reward", 0),
        "rare_candy": 0,
        "latest_catches": [],
        "latest_shinies": [],
        "latest_rewards": [],
        "since_unix": min((r["ts"] for r in rows), default=time.time())
    }

    # Sum rare candy
    for r in rows:
        if r["type"] == "Reward":
            rc = r["data"].get("rare_candy", 0) or r["data"].get("rc", 0)
            try:
                s["rare_candy"] += int(rc)
            except Exception:
                pass

    s["latest_catches"] = [r for r in rows if r["type"] == "Catch"][-3:]
    s["latest_shinies"] = [r for r in rows if r["type"] == "Shiny"][-3:]
    s["latest_rewards"] = [r for r in rows if r["type"] == "Reward"][-3:]
    return s

def build_embed():
    s = build_stats()

    def fmt_latest(items):
        if not items:
            return "—"
        names = []
        for it in items:
            nm = it["data"].get("name") or it["data"].get("title") or "?"
            names.append(nm)
        return ", ".join(names)

    emb = discord.Embed(
        title="📊 Today’s Stats (Last 24h)",
        color=discord.Color.blurple()
    )

    emb.add_field(name="Encounters", value=str(s["encounters"]), inline=False)
    emb.add_field(name="Catches", value=str(s["catches"]), inline=False)
    emb.add_field(name="Shinies", value=str(s["shinies"]), inline=False)
    emb.add_field(name="🧪 Rare Candy earned", value=str(s["rare_candy"]), inline=False)

    emb.add_field(
        name="Event breakdown",
        value=(
            f"Encounter: {s['encounters']}\n"
            f"Lure: 0\n"
            f"Incense: 0\n"
            f"Max Battle: 0\n"
            f"Quest: {s['quests']}\n"
            f"Rocket Battle: {s['rockets']}\n"
            f"Raid: {s['raids']}\n"
            f"Hatch: {s['hatches']}\n"
            f"Reward: {s['rewards']}"
        ),
        inline=False
    )

    since = time.strftime('%d/%m/%y %H:%M', time.localtime(s["since_unix"]))
    emb.add_field(name="⚪ Latest Catches", value=fmt_latest(s["latest_catches"]), inline=False)
    emb.add_field(name="✨ Latest Shinies", value=fmt_latest(s["latest_shinies"]), inline=False)
    emb.add_field(name="🎁 Recent Rewards", value=fmt_latest(s["latest_rewards"]), inline=False)
    emb.set_footer(text=f"Since — Today at {since}")
    return emb

# =========================
# Backfill (optional but recommended)
# =========================
async def backfill_from_channel(limit: int = 500):
    try:
        ch = client.get_channel(CHANNEL_ID) if CHANNEL_ID else None
        if not ch:
            print("[BACKFILL] No channel, skipping")
            return
        count_before = len(EVENTS)
        async for m in ch.history(limit=limit):
            if not m.embeds:
                continue
            for e in m.embeds:
                evt, payload = parse_polygonx_embed(e)
                if evt:
                    # use message timestamp for historical accuracy
                    EVENTS.append({"ts": m.created_at.timestamp(), "type": evt, "data": payload or {}})
        print(f"[BACKFILL] Loaded {len(EVENTS)-count_before} events from history")
    except Exception as e:
        print(f"[BACKFILL ERROR] {e}")

# =========================
# Message ingest
# =========================
@client.event
async def on_message(message: discord.Message):
    try:
        # Ignore our own bot messages
        if message.author == client.user:
            return

        # Parse embeds (webhook posts etc.)
        if message.embeds:
            recognized = 0
            for e in message.embeds:
                evt, payload = parse_polygonx_embed(e)
                if evt:
                    add_event(evt, payload)
                    recognized += 1
            if recognized:
                print(f"[INGEST] Parsed {recognized} PolygonX event(s) from message {message.id}")
    except Exception as e:
        print(f"[ON_MESSAGE ERROR] {e}")

# =========================
# UI: Summary view (Refresh)
# =========================
class SummaryView(View):
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, custom_id="refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.edit_message(embed=build_embed(), view=self)
        except discord.InteractionResponded:
            try:
                await interaction.message.edit(embed=build_embed(), view=self)
            except Exception as e:
                print(f"[Refresh edit fallback error] {e}")
        except discord.errors.NotFound:
            try:
                await interaction.followup.send("⏳ Interaction verlopen, gebruik /summary opnieuw.", ephemeral=True)
            except Exception as e:
                print(f"[Refresh followup error] {e}")
        except Exception as e:
            print(f"[Refresh error] {e}")

# =========================
# /summary command (no defer)
# =========================
@tree.command(name="summary", description="Toon/refresh de 24u stats")
async def summary(inter: discord.Interaction):
    try:
        await inter.response.send_message("📊 Summary wordt geplaatst…", ephemeral=True)
    except discord.InteractionResponded:
        pass

    try:
        ch = client.get_channel(CHANNEL_ID) if CHANNEL_ID else inter.channel
        if ch is None:
            ch = inter.channel
        await ch.send(embed=build_embed(), view=SummaryView())
    except Exception as e:
        print(f"[Summary error] {e}")
        try:
            await inter.followup.send("❌ Kon de summary niet posten in het kanaal.", ephemeral=True)
        except Exception:
            pass

# =========================
# Global app-command error handler
# =========================
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"[COMMAND ERROR] {type(error).__name__}: {error}")
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Er ging iets mis met dit commando.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Er ging iets mis met dit commando.", ephemeral=True)
    except Exception as e:
        print(f"[COMMAND ERROR FOLLOWUP] {e}")

# =========================
# Ready: sync & backfill
# =========================
@client.event
async def on_ready():
    try:
        if GUILD_ID:
            await tree.sync(guild=discord.Object(id=GUILD_ID))
            print(f"[SYNC] Commands gesynct voor guild {GUILD_ID}")
        else:
            await tree.sync()
            print("[SYNC] Commands globaal gesynct")
    except Exception as e:
        print(f"[SYNC ERROR] {e}")

    await backfill_from_channel(limit=500)
    print(f"[READY] Logged in as {client.user} (id: {client.user.id})")

# =========================
# Main
# =========================
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN ontbreekt in environment")
    start_keepalive()
    client.run(DISCORD_TOKEN)
