# ======================================================
# PXstats • stats.py • 2025-11-13
# Correct shiny counting & breakdown
# ======================================================

from __future__ import annotations

from datetime import datetime, timedelta

from PXstats.utils import TZ

ICONS = {
    "enc": "🕵️",
    "catch": "🎯",
    "shiny": "✨",
    "event": "🥋",
    "wild": "🐾",
    "incense": "🧪",
    "lure": "🎣",
    "quest": "📜",
    "raid": "⚔️",
    "rocket": "🚀",
    "max": "🌀",
    "run": "🏃",
    "100": "🏆",
    "clock": "🕒",
}


def build_embed(events: list[dict]):
    """Bouw de 24u samenvatting-embed op basis van EVENTS."""

    now = datetime.now(TZ)
    cutoff = now - timedelta(hours=24)
    last24 = [e for e in events if e["timestamp"] >= cutoff]

    # ----- Counts -----
    encounters = sum(1 for e in last24 if e["type"] == "Encounter")
    catches = sum(1 for e in last24 if e["type"] == "Catch")

    shiny_count = sum(
        1
        for e in last24
        if e.get("type") == "Catch" and e.get("shiny") is True
    )

    perfect100 = sum(
        1
        for e in last24
        if e.get("type") == "Catch"
        and e.get("iv") is not None
        and tuple(e["iv"]) == (15, 15, 15)
    )

    # ----- Breakdown -----
    breakdown = {
        "Wild": sum(1 for e in last24 if e.get("source") == "wild"),
        "Incense": sum(1 for e in last24 if e.get("source") == "incense"),
        "Lure": sum(1 for e in last24 if e.get("source") == "lure"),
        "Quest": sum(1 for e in last24 if e["type"] == "Quest"),
        "Raid": sum(1 for e in last24 if e["type"] == "Raid"),
        "Rocket": sum(1 for e in last24 if e["type"] == "Rocket"),
        "Max": sum(1 for e in last24 if e["type"] == "MaxBattle"),
        "Runaways": sum(1 for e in last24 if e["type"] == "Fled"),
    }

    run_est = max(0, encounters - catches)
    catch_rate = (catches / encounters * 100) if encounters > 0 else 0.0

    # ----- Latest catches -----
    latest_catches = [e for e in last24 if e["type"] == "Catch"][-5:]

    # ----- Latest shinies (catch + shiny=True) -----
    shinies = [
        e for e in last24
        if e.get("type") == "Catch" and e.get("shiny") is True
    ][-5:]

    # ==================================================
    import discord

    embed = discord.Embed(
        title="📊 Today’s Stats (Last 24h)",
        color=0x3498DB,
    )

    embed.add_field(name=f"{ICONS['enc']} Encounters", value=str(encounters), inline=True)
    embed.add_field(name=f"{ICONS['catch']} Catches", value=str(catches), inline=True)
    embed.add_field(name=f"{ICONS['shiny']} Shinies", value=str(shiny_count), inline=True)

    breakdown_text = (
        f"{ICONS['wild']} Wild: {breakdown['Wild']}\n"
        f"{ICONS['incense']} Incense: {breakdown['Incense']}\n"
        f"{ICONS['lure']} Lure: {breakdown['Lure']}\n"
        f"{ICONS['quest']} Quest: {breakdown['Quest']}\n"
        f"{ICONS['raid']} Raid: {breakdown['Raid']}\n"
        f"{ICONS['rocket']} Rocket: {breakdown['Rocket']}\n"
        f"{ICONS['max']} Max: {breakdown['Max']}\n"
        f"{ICONS['run']} Runaways: {breakdown['Runaways']}"
    )

    embed.add_field(name=f"{ICONS['event']} Event breakdown", value=breakdown_text, inline=False)

    embed.add_field(
        name=f"{ICONS['catch']} Catch rate",
        value=f"{catch_rate:.1f}%",
        inline=True,
    )
    embed.add_field(
        name=f"{ICONS['run']} Runaways (est.)",
        value=str(run_est),
        inline=True,
    )
    embed.add_field(
        name=f"{ICONS['100']} Perfect 100 IV",
        value=str(perfect100),
        inline=True,
    )

    if latest_catches:
        txt = "\n".join(
            f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
            f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
            for e in reversed(latest_catches)
        )
    else:
        txt = "—"

    embed.add_field(
        name=f"{ICONS['clock']} Latest Catches",
        value=txt,
        inline=False,
    )

    if shinies:
        shiny_txt = "\n".join(
            f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
            f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
            for e in reversed(shinies)
        )
    else:
        shiny_txt = "—"

    embed.add_field(
        name=f"{ICONS['shiny']} Latest Shinies",
        value=shiny_txt,
        inline=False,
    )

    return embed
