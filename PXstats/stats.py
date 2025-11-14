# PXstats • stats-v4.5 • 2025-11-14
# ---------------------------------
# - Encounters / Catches / Shinies
# - Event breakdown (Wild / Incense / Lure / Quest / Raid / Rocket / Max / Runaways)
# - Runaways (est.) = max(Fled, Encounters - Catches)
# - Perfect 100 IV counter
# - Latest Catches
# - Latest Shinies (uit catches met shiny=True)
# - NIEUW: Latest 100 IV (uit catches met IV 15/15/15)
# ---------------------------------

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict, Any

import discord

from PXstats.utils import TZ


def _last_24h(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter events van de laatste 24 uur."""
    cutoff = datetime.now(TZ) - timedelta(hours=24)
    out = []
    for e in events:
        ts = e.get("timestamp")
        if isinstance(ts, datetime) and ts >= cutoff:
            out.append(e)
    return out


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%d %B %Y %H:%M")


def build_embed(all_events: List[Dict[str, Any]]) -> discord.Embed:
    # Window = laatste 24h
    window = _last_24h(all_events)

    # -------------------------------------------------
    # Counters
    # -------------------------------------------------
    wild = incense = lure = quest = raid = rocket = max_b = runaways = 0
    catches = 0

    shinies_from_catches: List[Dict[str, Any]] = []
    perfect_from_catches: List[Dict[str, Any]] = []

    for e in window:
        etype = e.get("type")
        src = e.get("source")
        iv = e.get("iv")
        shiny_flag = bool(e.get("shiny"))

        # Encounter breakdown
        if etype == "Encounter":
            if src == "wild":
                wild += 1
            elif src == "incense":
                incense += 1
            elif src == "lure":
                lure += 1

        elif etype == "Quest":
            quest += 1
        elif etype == "Raid":
            raid += 1
        elif etype == "Rocket":
            rocket += 1
        elif etype == "MaxBattle":
            max_b += 1
        elif etype == "Fled":
            runaways += 1

        # Catches & flags
        if etype == "Catch":
            catches += 1

            if shiny_flag:
                shinies_from_catches.append(e)

            if iv and len(iv) == 3 and iv[0] == 15 and iv[1] == 15 and iv[2] == 15:
                perfect_from_catches.append(e)

    # Encounters = alles wat je effectief gezien hebt
    encounters = wild + incense + lure + quest + raid + rocket + max_b + runaways

    # Shinies = aantal shiny catches
    shinies = len(shinies_from_catches)

    # Perfect 100 IV = aantal perfect catches
    perfect_100 = len(perfect_from_catches)

    # Runaways (est.) = max(gezien flee-events, Enc - Catches)
    runaways_est = max(runaways, max(0, encounters - catches))

    # Catch rate
    denom = catches + runaways_est
    if denom > 0:
        catch_rate = round(100.0 * catches / denom, 1)
    else:
        catch_rate = 0.0

    # -------------------------------------------------
    # Embed opbouwen
    # -------------------------------------------------
    embed = discord.Embed(
        title="📊 Today’s Stats (Last 24h)",
        colour=discord.Colour.blurple()
    )

    # Top counters
    embed.add_field(name="🧑‍✈️ Encounters", value=str(encounters), inline=True)
    embed.add_field(name="🎯 Catches", value=str(catches), inline=True)
    embed.add_field(name="✨ Shinies", value=str(shinies), inline=True)

    # Event breakdown
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
        value="\n".join(breakdown_lines) if breakdown_lines else "—",
        inline=False,
    )

    # Catch rate, runaways (est.), perfect
    embed.add_field(name="🎯 Catch rate", value=f"{catch_rate:.1f}%", inline=True)
    embed.add_field(name="🏃 Runaways (est.)", value=str(runaways_est), inline=True)
    embed.add_field(name="🏆 Perfect 100 IV", value=str(perfect_100), inline=True)

    # -------------------------------------------------
    # Latest catches
    # -------------------------------------------------
    latest_catches = [e for e in window if e.get("type") == "Catch"][-5:]
    if latest_catches:
        lines = []
        for e in reversed(latest_catches):
            name = e.get("name", "?")
            iv = e.get("iv") or (None, None, None)
            ts = e.get("timestamp")
            iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}"
            ts_str = _fmt_ts(ts) if isinstance(ts, datetime) else "?"
            lines.append(f"{name} {iv_str} ({ts_str})")
        latest_catches_text = "\n".join(lines)
    else:
        latest_catches_text = "—"

    embed.add_field(
        name="🕒 Latest Catches",
        value=latest_catches_text,
        inline=False,
    )

    # -------------------------------------------------
    # Latest shinies (uit catches)
    # -------------------------------------------------
    latest_shinies = shinies_from_catches[-5:]
    if latest_shinies:
        lines = []
        for e in reversed(latest_shinies):
            name = e.get("name", "?")
            iv = e.get("iv") or (None, None, None)
            ts = e.get("timestamp")
            iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}"
            ts_str = _fmt_ts(ts) if isinstance(ts, datetime) else "?"
            lines.append(f"{name} {iv_str} ({ts_str})")
        latest_shinies_text = "\n".join(lines)
    else:
        latest_shinies_text = "—"

    embed.add_field(
        name="✨ Latest Shinies",
        value=latest_shinies_text,
        inline=False,
    )

    # -------------------------------------------------
    # NIEUW: Latest 100 IV
    # -------------------------------------------------
    latest_perfect = perfect_from_catches[-5:]
    if latest_perfect:
        lines = []
        for e in reversed(latest_perfect):
            name = e.get("name", "?")
            iv = e.get("iv") or (None, None, None)
            ts = e.get("timestamp")
            iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}"
            ts_str = _fmt_ts(ts) if isinstance(ts, datetime) else "?"
            lines.append(f"{name} {iv_str} ({ts_str})")
        latest_perfect_text = "\n".join(lines)
    else:
        latest_perfect_text = "—"

    embed.add_field(
        name="🏅 Latest 100 IV",
        value=latest_perfect_text,
        inline=False,
    )

    # Footer
    embed.set_footer(
        text=f"Rate base: {encounters} • stats-v4.5 • {datetime.now(TZ).date()}"
    )

    return embed