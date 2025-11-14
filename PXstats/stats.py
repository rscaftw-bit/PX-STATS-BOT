# PXstats • stats.py • v4.3
# - Runaways = echte 'Fled' events
# - Runaways (est.) = Encounters - Catches

from datetime import datetime
from typing import List, Dict, Any

import discord

from PXstats.utils import last_24h, TZ


def _fmt_iv(e: Dict[str, Any]) -> str:
    iv = e.get("iv")
    if not iv:
        return "?"
    try:
        return f"{iv[0]}/{iv[1]}/{iv[2]}"
    except Exception:
        return "?"


def build_embed(events: List[Dict[str, Any]]) -> discord.Embed:
    now = datetime.now(TZ)
    window = last_24h(events)

    # --- Totalen ---
    encounters = sum(
        1
        for e in window
        if e.get("type") in ("Encounter", "Quest", "Raid", "Rocket", "MaxBattle")
    )

    catches = sum(
        1
        for e in window
        if e.get("type") in ("Catch", "Shiny")
    )

    shinies = sum(1 for e in window if e.get("type") == "Shiny")

    # ECHTE runaways: Pokemon flee!
    runaways_real = sum(1 for e in window if e.get("type") == "Fled")

    # Perfect 100 IV (alleen catches/shinies)
    perfect_100 = sum(
        1
        for e in window
        if e.get("type") in ("Catch", "Shiny")
        and e.get("iv") == (15, 15, 15)
    )

    # --- Event breakdown per bron ---
    wild = sum(1 for e in window if e.get("source") == "wild")
    incense = sum(1 for e in window if e.get("source") == "incense")
    lure = sum(1 for e in window if e.get("source") == "lure")
    quest = sum(1 for e in window if e.get("type") == "Quest")
    raid = sum(1 for e in window if e.get("type") == "Raid")
    rocket = sum(1 for e in window if e.get("type") == "Rocket")
    max_b = sum(1 for e in window if e.get("type") == "MaxBattle")

    # Catch rate & estimated runaways
    catch_rate = (catches / encounters * 100.0) if encounters > 0 else 0.0
    runaways_est = max(encounters - catches, 0)

    # --- Laatste catches/shinies ---
    recent_catches = [
        e for e in window if e.get("type") in ("Catch", "Shiny")
    ]
    recent_catches.sort(key=lambda x: x.get("timestamp", datetime.min), reverse=True)
    recent_catches = recent_catches[:5]

    if recent_catches:
        latest_catches_txt = "\n".join(
            f"{e.get('name', '?')} {_fmt_iv(e)} "
            f"({e.get('timestamp').strftime('%d %B %Y %H:%M')})"
            for e in recent_catches
            if isinstance(e.get("timestamp"), datetime)
        )
    else:
        latest_catches_txt = "—"

    recent_shinies = [e for e in window if e.get("type") == "Shiny"]
    recent_shinies.sort(key=lambda x: x.get("timestamp", datetime.min), reverse=True)
    recent_shinies = recent_shinies[:5]

    if recent_shinies:
        latest_shinies_txt = "\n".join(
            f"{e.get('name', '?')} {_fmt_iv(e)} "
            f"({e.get('timestamp').strftime('%d %B %Y %H:%M')})"
            for e in recent_shinies
            if isinstance(e.get("timestamp"), datetime)
        )
    else:
        latest_shinies_txt = "—"

    # --- Embed bouwen ---
    embed = discord.Embed(
        title="📊 Today's Stats (Last 24h)",
        colour=discord.Colour.blurple(),
    )

    # Top stats
    embed.add_field(name="🕵️‍♂️ Encounters", value=str(encounters), inline=True)
    embed.add_field(name="🎯 Catches", value=str(catches), inline=True)
    embed.add_field(name="✨ Shinies", value=str(shinies), inline=True)

    # Breakdown
    breakdown_txt = (
        f"🐾 Wild: {wild}\n"
        f"🧪 Incense: {incense}\n"
        f"🎣 Lure: {lure}\n"
        f"📋 Quest: {quest}\n"
        f"⚔️ Raid: {raid}\n"
        f"🚀 Rocket: {rocket}\n"
        f"⭕ Max: {max_b}\n"
        f"🏃‍♂️ Runaways: {runaways_real}"
    )
    embed.add_field(name="📦 Event breakdown", value=breakdown_txt, inline=False)

    # Rates
    embed.add_field(name="🎯 Catch rate", value=f"{catch_rate:.1f}%", inline=True)
    embed.add_field(
        name="🕺 Runaways (est.)", value=str(runaways_est), inline=True
    )
    embed.add_field(
        name="🏆 Perfect 100 IV", value=str(perfect_100), inline=True
    )

    # Latest catches & shinies
    embed.add_field(name="🕒 Latest Catches", value=latest_catches_txt, inline=False)
    embed.add_field(name="✨ Latest Shinies", value=latest_shinies_txt, inline=False)

    embed.set_footer(
        text=f"Rate base: {encounters} • stats-v4.3 • {now.strftime('%Y-%m-%d')}"
    )

    return embed
