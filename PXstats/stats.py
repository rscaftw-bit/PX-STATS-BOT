from datetime import datetime
from typing import List, Dict, Any

import discord

from PXstats.utils import last_24h, TZ

STATS_VERSION = "v4.4"


def _format_event_line(e: Dict[str, Any]) -> str:
    """Format a single event for the latest lists."""
    name = e.get("name", "?")
    iv = e.get("iv")
    ts: datetime = e.get("timestamp")

    if isinstance(iv, (list, tuple)) and len(iv) == 3:
        iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}"
    else:
        iv_str = "-"

    if isinstance(ts, datetime):
        ts_str = ts.astimezone(TZ).strftime("%d %B %Y %H:%M")
    else:
        ts_str = "?"

    return f"{name} {iv_str} ({ts_str})"


def _compute_stats(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute all counters for the last 24h window.

    Belangrijk:
    - Encounters = alle outcomes (catch + flee), dus runaways tellen mee.
    - Runaways komen uit echte 'Fled'-events.
    """
    rows = last_24h(events)

    wild = incense = lure = quest = raid = rocket = maxb = 0
    catches = shinies = runaways = 0

    latest_catches: List[Dict[str, Any]] = []
    latest_shinies: List[Dict[str, Any]] = []

    for e in rows:
        etype = e.get("type")
        src = (e.get("source") or "").lower()

        if etype in ("Catch", "Shiny"):
            catches += 1
            if etype == "Shiny":
                shinies += 1
                latest_shinies.append(e)

            latest_catches.append(e)

            # Bron breakdown (fallback = wild)
            if src == "incense":
                incense += 1
            elif src == "lure":
                lure += 1
            elif src == "quest":
                quest += 1
            elif src == "raid":
                raid += 1
            elif src == "rocket":
                rocket += 1
            elif src == "max":
                maxb += 1
            else:
                wild += 1

        elif etype == "Fled":
            # Pure runaway; we kennen de bron niet, dus enkel "Runaways".
            runaways += 1

    # Totaal encounters = alle outcomes (catch of flee)
    encounters = wild + incense + lure + quest + raid + rocket + maxb + runaways

    # Catch rate op basis van echte outcomes
    catch_rate = (catches / encounters * 100.0) if encounters > 0 else 0.0

    # Geen schatting meer, gewoon echte flee-count
    runaways_est = runaways

    # Perfect 100 IV (alleen catches / shinies)
    perfect_100 = 0
    for e in rows:
        if e.get("type") not in ("Catch", "Shiny"):
            continue
        iv = e.get("iv")
        if isinstance(iv, (list, tuple)) and tuple(iv) == (15, 15, 15):
            perfect_100 += 1

    # Laatste 5
    latest_catches = sorted(
        latest_catches,
        key=lambda x: x.get("timestamp", datetime.min),
        reverse=True,
    )[:5]
    latest_shinies = sorted(
        latest_shinies,
        key=lambda x: x.get("timestamp", datetime.min),
        reverse=True,
    )[:5]

    return {
        "rows": rows,
        "encounters": encounters,
        "catches": catches,
        "shinies": shinies,
        "wild": wild,
        "incense": incense,
        "lure": lure,
        "quest": quest,
        "raid": raid,
        "rocket": rocket,
        "max": maxb,
        "runaways": runaways,
        "catch_rate": catch_rate,
        "runaways_est": runaways_est,
        "perfect_100": perfect_100,
        "latest_catches": latest_catches,
        "latest_shinies": latest_shinies,
    }


def build_embed(events: List[Dict[str, Any]]) -> discord.Embed:
    """Build the Discord embed for /summary."""
    s = _compute_stats(events)

    embed = discord.Embed(
        title="📊 Today’s Stats (Last 24h)",
        colour=discord.Colour.blue(),
    )

    # Bovenste rij
    embed.add_field(name="🕵️ Encounters", value=str(s["encounters"]), inline=True)
    embed.add_field(name="🎯 Catches", value=str(s["catches"]), inline=True)
    embed.add_field(name="✨ Shinies", value=str(s["shinies"]), inline=True)

    # Event breakdown
    breakdown_lines = [
        f"🐾 Wild: {s['wild']}",
        f"🧪 Incense: {s['incense']}",
        f"🎣 Lure: {s['lure']}",
        f"📜 Quest: {s['quest']}",
        f"⚔️ Raid: {s['raid']}",
        f"🚀 Rocket: {s['rocket']}",
        f"⭕ Max: {s['max']}",
        f"🏃 Runaways: {s['runaways']}",
    ]
    embed.add_field(
        name="📦 Event breakdown",
        value="\n".join(breakdown_lines),
        inline=False,
    )

    # Rates
    embed.add_field(
        name="🎯 Catch rate",
        value=f"{s['catch_rate']:.1f}%",
        inline=True,
    )
    embed.add_field(
        name="🏃 Runaways (est.)",
        value=str(s["runaways_est"]),
        inline=True,
    )
    embed.add_field(
        name="🏆 Perfect 100 IV",
        value=str(s["perfect_100"]),
        inline=True,
    )

    # Laatste catches
    if s["latest_catches"]:
        latest_catches_str = "\n".join(_format_event_line(e) for e in s["latest_catches"])
    else:
        latest_catches_str = "—"
    embed.add_field(
        name="🕒 Latest Catches",
        value=latest_catches_str,
        inline=False,
    )

    # Laatste shinies
    if s["latest_shinies"]:
        latest_shinies_str = "\n".join(_format_event_line(e) for e in s["latest_shinies"])
    else:
        latest_shinies_str = "—"
    embed.add_field(
        name="✨ Latest Shinies",
        value=latest_shinies_str,
        inline=False,
    )

    # Footer
    rate_base = len(s["rows"])
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    embed.set_footer(text=f"Rate base: {rate_base} • stats-{STATS_VERSION} • {today}")

    return embed
