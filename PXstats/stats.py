# PXstats • stats.py
# Build Discord embeds from the in-memory EVENTS list.

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict, Any

import discord

from PXstats.utils import TZ


def _last_24h(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cutoff = datetime.now(TZ) - timedelta(hours=24)
    return [e for e in events if e.get("timestamp") and e["timestamp"] >= cutoff]


def _format_iv(iv):
    if not iv:
        return "?"
    return f"{iv[0]}/{iv[1]}/{iv[2]}"


def build_embed(events: List[Dict[str, Any]]) -> discord.Embed:
    """Create the main summary embed for the last 24 hours."""
    recent = _last_24h(events)

    # Totals
    encounters = sum(1 for e in recent if e.get("type") == "Encounter")
    catches = sum(1 for e in recent if e.get("type") == "Catch")
    shinies = sum(1 for e in recent if e.get("shiny") is True)

    # Breakdown (based on encounters only)
    breakdown = {
        "wild": 0,
        "incense": 0,
        "lure": 0,
        "quest": 0,
        "raid": 0,
        "rocket": 0,
        "max": 0,
    }
    for e in recent:
        if e.get("type") != "Encounter":
            continue
        src = e.get("source", "wild")
        if src in breakdown:
            breakdown[src] += 1
        else:
            breakdown["wild"] += 1

    # Runaways are estimated: encounters - catches
    runaways = max(encounters - catches, 0)

    # Catch rate
    if encounters > 0:
        catch_rate = catches / encounters * 100.0
    else:
        catch_rate = 0.0

    # Perfect IV: only on catches with 15/15/15
    perfect = sum(
        1
        for e in recent
        if e.get("type") == "Catch"
        and e.get("iv") is not None
        and tuple(e["iv"]) == (15, 15, 15)
    )

    # Latest catches & shinies
    latest_catches = [e for e in recent if e.get("type") == "Catch"]
    latest_catches.sort(key=lambda x: x["timestamp"], reverse=True)
    latest_catches = latest_catches[:5]

    latest_shinies = [e for e in recent if e.get("shiny") is True]
    latest_shinies.sort(key=lambda x: x["timestamp"], reverse=True)
    latest_shinies = latest_shinies[:5]

    # --------------------------------------------------
    # Build embed
    # --------------------------------------------------
    embed = discord.Embed(
        title="📊 Today’s Stats (Last 24h)",
        colour=discord.Colour.blurple(),
    )

    # Header lines
    embed.add_field(
        name="👮‍♂️ Encounters",
        value=str(encounters),
        inline=True,
    )
    embed.add_field(
        name="🎯 Catches",
        value=str(catches),
        inline=True,
    )
    embed.add_field(
        name="✨ Shinies",
        value=str(shinies),
        inline=True,
    )

    # Event breakdown
    bd_lines = [
        f"🐾 Wild: {breakdown['wild']}",
        f"🪄 Incense: {breakdown['incense']}",
        f"🧲 Lure: {breakdown['lure']}",
        f"📜 Quest: {breakdown['quest']}",
        f"⚔ Raid: {breakdown['raid']}",
        f"🚀 Rocket: {breakdown['rocket']}",
        f"⭕ Max: {breakdown['max']}",
        f"🏃 Runaways: {runaways}",
    ]
    embed.add_field(
        name="🧱 Event breakdown",
        value="\n".join(bd_lines),
        inline=False,
    )

    # Catch rate & perfects
    embed.add_field(
        name="🎯 Catch rate",
        value=f"{catch_rate:.1f}%",
        inline=True,
    )
    embed.add_field(
        name="🏃 Runaways (est.)",
        value=str(runaways),
        inline=True,
    )
    embed.add_field(
        name="🏆 Perfect 100 IV",
        value=str(perfect),
        inline=True,
    )

    # Latest catches
    if latest_catches:
        lines = []
        for e in latest_catches:
            ts = e["timestamp"].strftime("%d %B %Y %H:%M")
            iv_str = _format_iv(e.get("iv"))
            lines.append(f"{e['name']} {iv_str} ({ts})")
        value = "\n".join(lines)
    else:
        value = "—"
    embed.add_field(name="🕒 Latest Catches", value=value, inline=False)

    # Latest shinies
    if latest_shinies:
        lines = []
        for e in latest_shinies:
            ts = e["timestamp"].strftime("%d %B %Y %H:%M")
            iv_str = _format_iv(e.get("iv"))
            lines.append(f"{e['name']} {iv_str} ({ts})")
        value = "\n".join(lines)
    else:
        value = "—"
    embed.add_field(name="✨ Latest Shinies", value=value, inline=False)

    # Footer with version & base
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    embed.set_footer(
        text=f"Rate base: {encounters} • stats-v4.1 • {today_str}"
    )

    return embed
