# PXstats • stats.py • v4.2

from datetime import datetime
from typing import List, Dict, Any

import discord

from PXstats.utils import TZ


def _fmt_iv(e: Dict[str, Any]) -> str:
    iv = e.get("iv")
    if not iv:
        return "?"
    try:
        return f"{iv[0]}/{iv[1]}/{iv[2]}"
    except Exception:
        return "?"


def build_embed(events: List[Dict[str, Any]]) -> discord.Embed:
    """Bouw de 'Today's Stats (Last 24h)' embed op basis van gefilterde events."""

    # -------- Counters initialiseren --------
    wild = incense = lure = 0
    quest = raid = rocket = max_b = 0
    runaways = 0
    catches = 0
    shinies = 0
    perfect_100 = 0

    latest_catches: List[Dict[str, Any]] = []
    latest_shinies: List[Dict[str, Any]] = []

    for e in events:
        et = e.get("type")
        if et == "Encounter":
            src = e.get("source", "wild")
            if src == "incense":
                incense += 1
            elif src == "lure":
                lure += 1
            else:
                wild += 1

        elif et == "Quest":
            quest += 1
        elif et == "Raid":
            raid += 1
        elif et == "Rocket":
            rocket += 1
        elif et == "Max":
            max_b += 1
        elif et == "Fled":
            runaways += 1

        elif et == "Catch":
            catches += 1
            latest_catches.append(e)

            iv = e.get("iv")
            if iv and all(v == 15 for v in iv):
                perfect_100 += 1

            if e.get("shiny"):
                shinies += 1
                latest_shinies.append(e)

    encounters = wild + incense + lure + quest + raid + rocket + max_b

    # Catch rate
    if encounters > 0:
        catch_rate = (catches / encounters) * 100.0
    else:
        catch_rate = 0.0

    # Runaways (est): max(logged, encounters - catches)
    est_runaways = max(runaways, encounters - catches, 0)

    # Laatste 5 catches/shinies (recentste eerst)
    latest_catches = sorted(latest_catches, key=lambda x: x["timestamp"], reverse=True)[:5]
    latest_shinies = sorted(latest_shinies, key=lambda x: x["timestamp"], reverse=True)[:5]

    def _fmt_line(e: Dict[str, Any]) -> str:
        ts = e.get("timestamp")
        if isinstance(ts, datetime):
            ts_s = ts.strftime("%d %B %Y %H:%M")
        else:
            ts_s = "?"
        return f"{e.get('name', '?')} {_fmt_iv(e)} ({ts_s})"

    latest_catches_text = "\n".join(_fmt_line(e) for e in latest_catches) or "—"
    latest_shinies_text = "\n".join(_fmt_line(e) for e in latest_shinies) or "—"

    # -------- Embed opbouwen --------
    now = datetime.now(TZ)

    embed = discord.Embed(
        title="📊 Today's Stats (Last 24h)",
        colour=discord.Colour.blurple(),
    )

    embed.add_field(name="👮 Encounters", value=str(encounters), inline=True)
    embed.add_field(name="🎯 Catches", value=str(catches), inline=True)
    embed.add_field(name="✨ Shinies", value=str(shinies), inline=True)

    breakdown_lines = [
        f"🐾 Wild: {wild}",
        f"🧪 Incense: {incense}",
        f"🎣 Lure: {lure}",
        f"📜 Quest: {quest}",
        f"⚔️ Raid: {raid}",
        f"🚀 Rocket: {rocket}",
        f"⭕ Max: {max_b}",
        f"🏃 Runaways: {runaways}",
    ]
    embed.add_field(
        name="📦 Event breakdown",
        value="\n".join(breakdown_lines),
        inline=False,
    )

    embed.add_field(
        name="🎯 Catch rate",
        value=f"{catch_rate:.1f}%",
        inline=True,
    )
    embed.add_field(
        name="🏃 Runaways (est.)",
        value=str(est_runaways),
        inline=True,
    )
    embed.add_field(
        name="🏆 Perfect 100 IV",
        value=str(perfect_100),
        inline=True,
    )

    embed.add_field(
        name="🕒 Latest Catches",
        value=latest_catches_text,
        inline=False,
    )
    embed.add_field(
        name="✨ Latest Shinies",
        value=latest_shinies_text,
        inline=False,
    )

    embed.set_footer(text=f"Rate base: {encounters} • stats-v4.2 • {now.date().isoformat()}")
    return embed
