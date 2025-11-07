# bot.py
import os
import time
import re
import threading
import unicodedata
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque
from typing import Optional

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
intents.message_content = True     # nodig om webhook-embeds te lezen
intents.members = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================
# Keep-alive HTTP server (Render)
# =========================
class _HealthzHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def log_message(self, *_, **__): return

def start_keepalive():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("", port), _HealthzHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[KEEPALIVE] Serving health on :{port}")

# =========================
# In-memory event storage
# =========================
EVENTS = deque(maxlen=10000)  # ringbuffer

def add_event(evt_type: str, payload: dict, ts: Optional[float] = None):
    EVENTS.append({
        "ts": ts if ts is not None else time.time(),  # epoch UTC
        "type": evt_type,                              # "Catch", "Shiny", "Encounter", ...
        "data": payload or {}
    })

def last_24h():
    cutoff = time.time() - 24 * 3600
    return [e for e in EVENTS if e["ts"] >= cutoff]

# =========================
# Parser helpers
# =========================
IV_PAT        = re.compile(r"IV\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)
PKM_LINE_PAT  = re.compile(r"^\s*Pok[eé]mon:\s*([A-Za-zÀ-ÿ' .-]+|p\d+)", re.I | re.M)

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower().strip()

def _field_value(emb: discord.Embed, wanted_name: str):
    wn = _norm(wanted_name)
    for f in emb.fields:
        fname = _norm(f.name or "")
        if fname == wn or "pokemon" in fname:  # accepteer "Pokemon" / "Pokémon" / varianten
            return (f.value or "").strip()
    return None

def _extract_pokemon_name(e: discord.Embed):
    # 1) Field "Pokemon"/"Pokémon"
    val = _field_value(e, "Pokemon")
    if val:
        name = val.split("(")[0].strip()
        if name:
            return name
    # 2) Description-regel
    if e.description:
        m = PKM_LINE_PAT.search(e.description)
        if m:
            return m.group(1).strip()
    # 3) Title fallback (pak token vóór "(" als die er is)
    title = (e.title or "")
    m2 = re.search(r"([A-Za-zÀ-ÿ' .-]+|p\d+)\s*\(", title)
    if m2:
        return m2.group(1).strip()
    return "?"

def _extract_iv_pct(e: discord.Embed) -> Optional[int]:
    texts = [e.description or ""]
    for f in e.fields:
        texts.append(f"{f.name}\n{f.value}")
    blob = "\n".join(texts)
    m = IV_PAT.search(blob)
    if not m:
        return None
    atk, de, st = map(int, m.groups())
    return round((atk + de + st) / 45 * 100)

def _gather_text(e: discord.Embed) -> str:
    parts = [e.title or "", e.description or ""]
    for f in e.fields:
        parts.append(f"{f.name}\n{f.value}")
    return "\n".join(parts).lower()

# =========================
# PolygonX embed parser
# =========================
def parse_polygonx_embed(e: discord.Embed):
    title = (e.title or "").strip()
    full = _gather_text(e)

    # --- Shiny: kan in titel/description/fields ---
    if any(x in full for x in ["shiny", "✨", ":sparkles:"]):
        return ("Shiny", {"name": _extract_pokemon_name(e), "iv_pct": _extract_iv_pct(e)})

    # --- Catch ---
    if "caught successfully" in full or "pokemon caught" in full:
        return ("Catch", {"name": _extract_pokemon_name(e), "iv_pct": _extract_iv_pct(e)})

    # --- Fled ---
    if "fled" in full or "ran away" in full or "ran-away" in full:
        return ("Fled", {"name": _extract_pokemon_name(e)})

    # --- Quest (met naam) ---
    if "quest" in full:
        return ("Quest", {"name": _extract_pokemon_name(e)})

    # --- Breed Encounter (we tellen ALLE non-rocket encounters) ---
    if "encounter" in full and "rocket" not in full:
        payload = {"name": _extract_pokemon_name(e)}
        if "incense" in full: payload["incense"] = True
        if "lure" in full:    payload["lure"] = True
        encounter_guess = ("Encounter", payload)
    else:
        encounter_guess = (None, None)

    # --- Raid (ook 'raid battle encounter') ---
    if "raid" in full or "raid battle" in full:
        return ("Raid", {"title": title, "name": _extract_pokemon_name(e)})

    # --- Max Battle (alles met 'battle'+'encounter' zonder raid/rocket) ---
    if "battle" in full and "encounter" in full and "raid" not in full and "rocket" not in full:
        return ("MaxBattle", {"title": title, "name": _extract_pokemon_name(e)})

    # --- Rockets / overige types ---
    if "rocket" in full:
        return ("Rocket", {"title": title})
    if "hatch" in full:
        return ("Hatch", {"name": _extract_pokemon_name(e) or title})
    if "lure" in full:
        return ("Lure", {"title": title})
    if "incense" in full:
        return ("Incense", {"title": title})

    # geen match → val terug op generieke Encounter (als gedetecteerd)
    return encounter_guess

# =========================
# Stats & embed builder
# =========================
def build_stats():
    rows = last_24h()
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    # Subcounters uit Encounter payload
    lure    = sum(1 for r in rows if r["type"] == "Encounter" and r["data"].get("lure"))
    incense = sum(1 for r in rows if r["type"] == "Encounter" and r["data"].get("incense"))

    # 100% IV counter (alleen op Catch-events met iv_pct==100)
    perfect_100 = sum(1 for r in rows if r["type"] == "Catch" and r["data"].get("iv_pct") == 100)

    s = {
        "encounters": by_type.get("Encounter", 0),
        "catches":    by_type.get("Catch", 0),
        "shinies":    by_type.get("Shiny", 0),
        "raids":      by_type.get("Raid", 0),
        "rockets":    by_type.get("Rocket", 0),
        "hatches":    by_type.get("Hatch", 0),
        "quests":     by_type.get("Quest", 0),
        "max_battle": by_type.get("MaxBattle", 0),
        "lure":       lure or by_type.get("Lure", 0),
        "incense":    incense or by_type.get("Incense", 0),
        "fled":       by_type.get("Fled", 0),

        "perfect_100": perfect_100,

        "latest_catches": [],
        "latest_shinies": [],
        "since_unix": min((r["ts"] for r in rows), default=time.time()),
        "rows": rows,  # voor cross-match (shiny ↔ catch)
    }

    # Afgeleide metrics
    s["runaways"]   = max(0, s["encounters"] - s["catches"])
    s["catch_rate"] = (s["catches"] / s["encounters"] * 100.0) if s["encounters"] > 0 else 0.0
    s["shiny_rate"] = (s["shinies"] / s["catches"] * 100.0)    if s["catches"]    > 0 else 0.0

    # Laatste X
    s["latest_catches"] = [r for r in rows if r["type"] == "Catch"][-5:]
    s["latest_shinies"] = [r for r in rows if r["type"] == "Shiny"][-5:]
    return s

def _fmt_when(ts: float, style: str = "f"):
    # Discord timestamp markup: <t:unix:style>
    return f"<t:{int(ts)}:{style}>"

def build_embed(mode: str = "catch"):
    """
    mode: 'catch' → toon Catch rate
          'shiny' → toon Shiny rate
    """
    s = build_stats()

    # ✨ in Latest Catches: index van shiny-events per naam
    shiny_by_name = {}
    for ev in s["rows"]:
        if ev["type"] == "Shiny":
            nm = (ev["data"].get("name") or "").lower()
            shiny_by_name.setdefault(nm, []).append(ev["ts"])

    def is_catch_shiny(name: str, ts: float) -> bool:
        key = (name or "").lower()
        if key not in shiny_by_name:
            return False
        for t2 in shiny_by_name[key]:
            if abs(t2 - ts) <= 180:  # ±3 min
                return True
        return False

    def fmt_latest(items, with_iv=True, mark_shiny_in_catches=False):
        if not items: return "—"
        lines = []
        for it in items[::-1]:  # recentste eerst
            name = it["data"].get("name") or it["data"].get("title") or "?"
            ivp  = it["data"].get("iv_pct")
            ts   = it["ts"]
            shiny_prefix = "✨ " if (mark_shiny_in_catches and is_catch_shiny(name, ts)) else ""
            if with_iv and ivp is not None:
                lines.append(f"{shiny_prefix}{name} **{ivp}%** ({_fmt_when(ts, 'f')})")
            else:
                lines.append(f"{shiny_prefix}{name} ({_fmt_when(ts, 'f')})")
        return "\n".join(lines[:5])

    emb = discord.Embed(title="📊 Today’s Stats (Last 24h)", color=discord.Color.blurple())

    # Bovenste rij (inline)
    emb.add_field(name="Encounters", value=str(s["encounters"]), inline=True)
    emb.add_field(name="Catches",   value=str(s["catches"]),   inline=True)
    emb.add_field(name="Shinies",   value=str(s["shinies"]),   inline=True)

    # Breakdown
    breakdown = (
        f"Encounter: {s['encounters']}\n"
        f"Lure: {s['lure']}\n"
        f"Incense: {s['incense']}\n"
        f"Max Battle: {s['max_battle']}\n"
        f"Quest: {s['quests']}\n"
        f"Rocket Battle: {s['rockets']}\n"
        f"Raid: {s['raids']}\n"
        f"Hatch: {s['hatches']}"
    )
    emb.add_field(name="**Event breakdown**", value=breakdown, inline=False)

    # Rates + Runaways + Perfect 100 (inline)
    if mode == "catch":
        emb.add_field(name="🎯 Catch rate", value=f"{s['catch_rate']:.1f}%", inline=True)
    else:
        emb.add_field(name="✨ Shiny rate", value=f"{s['shiny_rate']:.3f}%", inline=True)
    emb.add_field(name="🏃 Runaways (est.)", value=str(s["runaways"]), inline=True)
    emb.add_field(name="🏆 Perfect 100 IV", value=str(s["perfect_100"]), inline=True)

    # Latest
    emb.add_field(
        name="🕓 Latest Catches",
        value=fmt_latest(s["latest_catches"], with_iv=True, mark_shiny_in_catches=True),
        inline=False
    )
    emb.add_field(
        name="✨ Latest Shinies",
        value=fmt_latest(s["latest_shinies"], with_iv=True, mark_shiny_in_catches=False),
        inline=False
    )

    since = _fmt_when(s["since_unix"], "f")
    now   = _fmt_when(time.time(), "t")
    emb.set_footer(text=f"Since {since} • Today at {now}")
    return emb

# =========================
# Backfill (na restart)
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
                    ts = m.created_at.timestamp()
                    title_l = (e.title or "").lower()

                    # Shiny die ook duidelijk een 'caught'-titel heeft → tel ook als Catch
                    if evt == "Shiny" and ("caught" in title_l or "caught successfully" in title_l):
                        add_event("Catch", payload, ts=ts)

                    # Quest & Raid/MaxBattle tellen ook als Encounter
                    if evt == "Quest" or evt in {"Raid", "MaxBattle"}:
                        add_event("Encounter", {"name": payload.get("name")}, ts=ts)

                    add_event(evt, payload, ts=ts)
        print(f"[BACKFILL] Loaded {len(EVENTS)-count_before} events from history")
    except Exception as e:
        print(f"[BACKFILL ERROR] {e}")

# =========================
# Message ingest
# =========================
@client.event
async def on_message(message: discord.Message):
    try:
        if message.author == client.user:
            return
        if message.embeds:
            recognized = 0
            for e in message.embeds:
                evt, payload = parse_polygonx_embed(e)
                if evt:
                    ts = message.created_at.timestamp()
                    title_l = (e.title or "").lower()

                    # Shiny die ook als Catch telt
                    if evt == "Shiny" and ("caught" in title_l or "caught successfully" in title_l):
                        add_event("Catch", payload, ts=ts); recognized += 1

                    # Quest & Raid/MaxBattle tellen ook als Encounter
                    if evt == "Quest" or evt in {"Raid", "MaxBattle"}:
                        add_event("Encounter", {"name": payload.get("name")}, ts=ts); recognized += 1

                    add_event(evt, payload, ts=ts); recognized += 1
            if recognized:
                print(f"[INGEST] Parsed {recognized} PolygonX event(s) from message {message.id}")
    except Exception as e:
        print(f"[ON_MESSAGE ERROR] {e}")

# =========================
# Summary view (Refresh + Rate-toggle)
# =========================
class SummaryView(View):
    def __init__(self, mode: str = "catch"):
        super().__init__(timeout=180)
        self.mode = mode

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, custom_id="refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.edit_message(embed=build_embed(mode=self.mode), view=self)
        except discord.InteractionResponded:
            try:
                await interaction.message.edit(embed=build_embed(mode=self.mode), view=self)
            except Exception as e:
                print(f"[Refresh edit fallback error] {e}")
        except discord.errors.NotFound:
            try:
                await interaction.followup.send("⏳ Interaction verlopen, gebruik /summary opnieuw.", ephemeral=True)
            except Exception as e:
                print(f"[Refresh followup error] {e}")
        except Exception as e:
            print(f"[Refresh error] {e}")

    @discord.ui.button(label="Rate: Catch", style=discord.ButtonStyle.secondary, custom_id="toggle_rate")
    async def toggle_rate(self, interaction: discord.Interaction, button: Button):
        self.mode = "shiny" if self.mode == "catch" else "catch"
        button.label = "Rate: Shiny" if self.mode == "shiny" else "Rate: Catch"
        try:
            await interaction.response.edit_message(embed=build_embed(mode=self.mode), view=self)
        except Exception as e:
            print(f"[Toggle error] {e}")

# =========================
# /summary command (no defer)
# =========================
@tree.command(name="summary", description="Toon de 24u stats (met refresh & rate-toggle)")
async def summary(inter: discord.Interaction):
    try:
        await inter.response.send_message("📊 Summary wordt geplaatst…", ephemeral=True)
    except discord.InteractionResponded:
        pass

    try:
        ch = client.get_channel(CHANNEL_ID) if CHANNEL_ID else inter.channel
        if ch is None: ch = inter.channel
        await ch.send(embed=build_embed(mode="catch"), view=SummaryView(mode="catch"))
    except Exception as e:
        print(f"[Summary error] {e}")
        try:
            await inter.followup.send("❌ Kon de summary niet posten in het kanaal.", ephemeral=True)
        except Exception:
            pass

# =========================
# Error handler
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
# on_ready (sync + presence + backfill)
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

    # Zet expliciet online + activiteit
    try:
        await client.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name="PXstats · /summary")
        )
        print("[PRESENCE] Set to online with activity")
    except Exception as e:
        print(f"[PRESENCE ERROR] {e}")

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
