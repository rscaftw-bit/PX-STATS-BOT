# PXstats v3.8 – stats.py
# Handles summaries, shiny/catch rates and embeds

import time, discord
from PXstats.utils import last_24h, _fmt_when

def build_stats():
    rows = last_24h()
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    def count(t): return by_type.get(t, 0)

    catches = count("Catch")
    shinies = count("Shiny")
    encounters = sum(count(t) for t in ["Encounter","Quest","Raid","Rocket","MaxBattle"])
    rate_base = max(encounters, catches)

    perfect = sum(1 for r in rows if r["type"]=="Catch" and r["data"].get("iv")==(15,15,15))
    fled = count("Fled")

    s = {
        "encounters": encounters,
        "catches": catches,
        "shinies": shinies,
        "catch_rate": (catches / rate_base * 100) if rate_base > 0 else 0.0,
        "shiny_rate": (shinies / catches * 100) if catches > 0 else 0.0,
        "perfect": perfect,
        "fled": fled,
        "rows": rows,
        "latest_catches": [r for r in rows if r["type"]=="Catch"][-5:],
        "latest_shinies": [r for r in rows if r["type"]=="Shiny"][-5:]
    }
    s["runaways"] = max(0, s["encounters"] - s["catches"])
    s["since"] = min((r["ts"] for r in rows), default=time.time())
    return s

def build_embed(mode="catch"):
    s = build_stats()
    emb = discord.Embed(title="📊 Today’s Stats (Last 24h)", color=discord.Color.blurple())
    emb.add_field(name="Encounters", value=str(s["encounters"]), inline=True)
    emb.add_field(name="Catches", value=str(s["catches"]), inline=True)
    emb.add_field(name="Shinies", value=str(s["shinies"]), inline=True)

    breakdown = (
        f"Wild/Quest/Raid/Rocket/Max: {s['encounters']}\n"
        f"Runaways: {s['runaways']}\n"
        f"Fled: {s['fled']}"
    )
    emb.add_field(name="**Event breakdown**", value=breakdown, inline=False)

    if mode == "catch":
        emb.add_field(name="🎯 Catch rate", value=f"{s['catch_rate']:.1f}%", inline=True)
    else:
        emb.add_field(name="✨ Shiny rate", value=f"{s['shiny_rate']:.3f}%", inline=True)

    emb.add_field(name="🏃 Runaways (est.)", value=str(s["runaways"]), inline=True)
    emb.add_field(name="🏆 Perfect 100 IV", value=str(s["perfect"]), inline=True)

    def fmt_list(lst, shiny=False):
        if not lst: return "—"
        lines = []
        for r in lst[-5:]:
            name = r["data"].get("name") or "?"
            iv = r["data"].get("iv")
            ivt = f" {iv[0]}/{iv[1]}/{iv[2]}" if iv else ""
            prefix = "✨ " if shiny else ""
            lines.append(f"{prefix}{name}{ivt} ({_fmt_when(r['ts'],'f')})")
        return "\n".join(lines)

    emb.add_field(name="🕓 Latest Catches", value=fmt_list(s["latest_catches"]), inline=False)
    emb.add_field(name="✨ Latest Shinies", value=fmt_list(s["latest_shinies"], True), inline=False)
    emb.set_footer(text=f"Rate base: {s['encounters']} • stats-v3.8 • {time.strftime('%Y-%m-%d')}")
    return emb
