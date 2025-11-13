# PXstats • stats.py
# ------------------------------------------------------------
# Builds summary embed + handles last 24h stats
# Fully supports: Catch, Shiny, Raid, Rocket, Quest, MaxBattle
# Shiny = double log (Catch + Shiny)
# ------------------------------------------------------------

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord

TZ = ZoneInfo("Europe/Brussels")


# ------------------------------------------------------------
# FILTER EVENTS (LAST 24H)
# ------------------------------------------------------------
def last_24h(events):
    """Return all events from the last 24 hours."""
    now = datetime.now(TZ)
    cutoff = now - timedelta(hours=24)
    return [e for e in events if e["timestamp"] >= cutoff]


# ------------------------------------------------------------
# EMBED BUILDER
# ------------------------------------------------------------
def build_embed(events):
    """Builds the Daily Summary embed."""
    
    # Filter for last 24h
    ev24 = last_24h(events)

    encounters = sum(1 for e in ev24 if e["type"] == "Encounter")
    catches    = sum(1 for e in ev24 if e["type"] == "Catch")
    shinies    = sum(1 for e in ev24 if e["type"] == "Shiny")
    rockets    = sum(1 for e in ev24 if e["type"] == "Rocket")
    raids      = sum(1 for e in ev24 if e["type"] == "Raid")
    quests     = sum(1 for e in ev24 if e["type"] == "Quest")
    maxb       = sum(1 for e in ev24 if e["type"] == "MaxBattle")
    runaways   = sum(1 for e in ev24 if e["type"] == "Fled")

    # Latest catches
    latest_catches = [
        e for e in reversed(ev24) if e["type"] == "Catch"
    ][:5]

    # Latest shinies
    latest_shinies = [
        e for e in reversed(ev24) if e["type"] == "Shiny"
    ][:5]

    # Perfect IV (15/15/15)
    hundos = [
        e for e in ev24
        if e["type"] in ("Catch", "Shiny")
        and e.get("iv") == [15, 15, 15]
    ]
    hundos_count = len(hundos)

    # Catch rate
    try:
        catch_rate = (catches / encounters) * 100
    except ZeroDivisionError:
        catch_rate = 0.0

    # BUILD EMBED
    embed = discord.Embed(
        title="📊 Today’s Stats (Last 24h)",
        color=0x5865F2
    )

    embed.add_field(name="Encounters", value=str(encounters), inline=True)
    embed.add_field(name="Catches", value=str(catches), inline=True)
    embed.add_field(name="Shinies", value=str(shinies), inline=True)

    embed.add_field(
        name="Event breakdown",
        value=(
            f"Wild: {encounters}\n"
            f"Quest: {quests}\n"
            f"Raid: {raids}\n"
            f"Rocket: {rockets}\n"
            f"Max: {maxb}\n"
            f"Runaways: {runaways}"
        ),
        inline=False
    )

    embed.add_field(
        name="🎯 Catch rate",
        value=f"{catch_rate:.1f}%",
        inline=True
    )
    embed.add_field(
        name="🏃 Runaways (est.)",
        value=str(runaways),
        inline=True
    )
    embed.add_field(
        name="🏆 Perfect 100 IV",
        value=str(hundos_count),
        inline=True
    )

    # Latest catches
    if latest_catches:
        txt = "\n".join(
            f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
            f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
            for e in latest_catches
        )
    else:
        txt = "—"
    embed.add_field(name="🕒 Latest Catches", value=txt, inline=False)

    # Latest shinies
    if latest_shinies:
        txt2 = "\n".join(
            f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
            f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
            for e in latest_shinies
        )
    else:
        txt2 = "—"
    embed.add_field(name="✨ Latest Shinies", value=txt2, inline=False)

    embed.set_footer(
        text=f"Rate base: {encounters} • stats-v3.9.2 • {datetime.now(TZ).date()}"
    )

    return embed