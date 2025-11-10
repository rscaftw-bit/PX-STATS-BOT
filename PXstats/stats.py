import time, json, os
from datetime import datetime
import discord

# ========== Load Pokédex ==========
POKEDEX = {}
try:
    with open(os.path.join(os.path.dirname(__file__), "pokedex.json"), "r", encoding="utf-8") as f:
        POKEDEX = json.load(f)
        print(f"[POKEDEX] loaded {len(POKEDEX)} entries")
except Exception as e:
    print("[POKEDEX] could not load:", e)

def dex_name(pname: str) -> str:
    """Convert p### placeholders to Pokémon names if possible."""
    pname = str(pname or "").strip()
    if pname.lower().startswith("p"):
        pid = pname.lower().replace("p", "").strip()
        if pid.isdigit():
            return POKEDEX.get(pid, f"p{pid}")
    return pname

# ========== Stats Builder ==========
def build_stats(rows):
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    # Filter encounters by source
    enc_wild   = sum(1 for r in rows if r["type"] == "Encounter" and r["data"].get("source") == "wild")
    enc_quest  = sum(1 for r in rows if r["type"] == "Encounter" and r["data"].get("source") == "quest")
    enc_raid   = sum(1 for r in rows if r["type"] == "Encounter" and r["data"].get("source") == "raid")
    enc_rocket = sum(1 for r in rows if r["type"] == "Encounter" and r["data"].get("source") == "rocket")
    enc_max    = sum(1 for r in rows if r["type"] == "Encounter" and r["data"].get("source") == "maxbattle")
    fled       = by_type.get("Fled", 0)
    catches    = by_type.get("Catch", 0)

    enc_total = enc_wild + enc_quest + enc_raid + enc_rocket + enc_max
    rate_base = max(enc_total, catches)

    # Perfect IV
    perfect = sum(1 for r in rows if r["type"] == "Catch" and r["data"].get("iv") == (15, 15, 15))

    # Shinies
    shiny_rows = [
        r for r in rows if r["type"] == "Shiny" or (r["type"] == "Catch" and r["data"].get("shiny"))
    ]
    shinies = len(shiny_rows)

    # Catch rate
    runaways = max(0, rate_base - catches)
    catch_rate = (catches / rate_base * 100) if rate_base > 0 else 0.0
    shiny_rate = (shinies / catches * 100) if catches > 0 else 0.0

    # Latest
    latest_catches = sorted(
        [r for r in rows if r["type"] == "Catch"],
        key=lambda x: x["ts"],
        reverse=True
    )[:5]
    latest_shinies = sorted(shiny_rows, key=lambda x: x["ts"], reverse=True)[:5]

    return {
        "enc_total": rate_base,
        "wild": enc_wild, "quest": enc_quest, "raid": enc_raid,
        "rocket": enc_rocket, "max": enc_max, "fled": fled,
        "catches": catches, "shinies": shinies, "perfect": perfect,
        "runaways": runaways, "catch_rate": catch_rate, "shiny_rate": shiny_rate,
        "latest_catches": latest_catches, "latest_shinies": latest_shinies,
        "since": min((r["ts"] for r in rows), default=time.time()),
    }

# ========== Embed Builder ==========
def _fmt_when(ts: float, style="f"):
    return f"<t:{int(ts)}:{style}>"

def build_embed(rows, mode="catch"):
    s = build_stats(rows)
    emb = discord.Embed(title="📊 Today’s Stats (Last 24h)", color=discord.Color.blurple())

    emb.add_field(name="Encounters", value=str(s["enc_total"]), inline=True)
    emb.add_field(name="Catches", value=str(s["catches"]), inline=True)
    emb.add_field(name="Shinies", value=str(s["shinies"]), inline=True)

    # Breakdown now separate
    breakdown = (
        f"Wild: {s['wild']}\n"
        f"Quest: {s['quest']}\n"
        f"Raid: {s['raid']}\n"
        f"Rocket: {s['rocket']}\n"
        f"Max: {s['max']}\n"
        f"Runaways: {s['fled']}"
    )
    emb.add_field(name="**Event breakdown**", value=breakdown, inline=False)

    # Rate section
    if mode == "catch":
        emb.add_field(name="🎯 Catch rate", value=f"{s['catch_rate']:.1f}%", inline=True)
    else:
        emb.add_field(name="✨ Shiny rate", value=f"{s['shiny_rate']:.3f}%", inline=True)
    emb.add_field(name="🏃 Runaways (est.)", value=str(s["runaways"]), inline=True)
    emb.add_field(name="🏆 Perfect 100 IV", value=str(s["perfect"]), inline=True)

    def fmt_list(lst, shiny=False):
        if not lst: return "—"
        lines = []
        for it in lst:
            n = dex_name(it["data"].get("name") or "?")
            iv = it["data"].get("iv")
            ivtxt = f" {iv[0]}/{iv[1]}/{iv[2]}" if iv else ""
            prefix = "✨ " if shiny else ""
            lines.append(f"{prefix}{n}{ivtxt} ({_fmt_when(it['ts'], 'f')})")
        return "\n".join(lines)

    emb.add_field(name="🕓 Latest Catches", value=fmt_list(s["latest_catches"]), inline=False)
    emb.add_field(name="✨ Latest Shinies", value=fmt_list(s["latest_shinies"], shiny=True), inline=False)

    emb.set_footer(text=f"Rate base: {s['enc_total']} • stats-v3.9.2 • {datetime.now().strftime('%Y-%m-%d')}")
    return emb
