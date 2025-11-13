# ================================================================
# PXstats – stats.py • v4.1 • 2025-11-13
# Nieuwe teller-engine gebaseerd op Kjell zijn regels
# Inclusief Latest Shinies block
# ================================================================

from datetime import datetime, timedelta
from PXstats.utils import TZ

# EVENTS wordt beheerd door utils
EVENTS = []

def add_event(ev):
    """Log één event in EVENTS"""
    EVENTS.append(ev)

def last_24h():
    """Filter events van laatste 24 uur"""
    now = datetime.now(TZ)
    return [e for e in EVENTS if (now - e["timestamp"]) <= timedelta(hours=24)]


# ================================================================
# BUILD EMBED
# ================================================================
import discord

def build_embed(all_events):

    rows = last_24h()

    # ----------------------------------------------------------
    # COUNTERS
    # ----------------------------------------------------------

    encounters = 0
    catches = 0
    shinies = 0
    runaways = 0

    # breakdown
    wild = 0
    incense = 0
    lure = 0
    quest = 0
    raid = 0
    rocket = 0
    maxb = 0

    # lists
    latest_catches = []
    latest_shinies = []

    for e in rows:

        et = e["type"].lower()

        # ------------------------------------------------------
        # ENCOUNTERS
        # ------------------------------------------------------
        if et == "encounter":
            encounters += 1

            src = e.get("source", "wild")
            if src == "wild":
                wild += 1
            elif src == "incense":
                incense += 1
            elif src == "lure":
                lure += 1

        elif et == "quest":
            encounters += 1
            quest += 1

        elif et == "raid":
            encounters += 1
            raid += 1

        elif et == "rocket":
            encounters += 1
            rocket += 1

        elif et == "maxbattle":
            encounters += 1
            maxb += 1

        # ------------------------------------------------------
        # FLED
        # ------------------------------------------------------
        elif et == "fled":
            runaways += 1

        # ------------------------------------------------------
        # CATCH
        # ------------------------------------------------------
        if et == "catch":
            catches += 1
            latest_catches.append(e)

        # ------------------------------------------------------
        # SHINY (telt als catch + shiny)
        # ------------------------------------------------------
        if et == "shiny":
            shinies += 1
            catches += 1
            latest_catches.append(e)
            latest_shinies.append(e)

    # ----------------------------------------------------------
    # RATE
    # ----------------------------------------------------------

    effective_encounters = max(1, encounters - runaways)
    catch_rate = (catches / effective_encounters) * 100

    # laatste 5 catches
    latest_catches = sorted(
        latest_catches, key=lambda x: x["timestamp"], reverse=True
    )[:5]

    latest_catches_txt = "\n".join(
        f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
        f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
        for e in latest_catches
    ) if latest_catches else "—"

    # laatste 5 shinies
    latest_shinies = sorted(
        latest_shinies, key=lambda x: x["timestamp"], reverse=True
    )[:5]

    latest_shinies_txt = "\n".join(
        f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
        f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
        for e in latest_shinies
    ) if latest_shinies else "—"

    # ----------------------------------------------------------
    # BUILD EMBED
    # ----------------------------------------------------------

    emb = discord.Embed(
        title="📊 Today’s Stats (Last 24h)",
        color=0x5865F2
    )

    emb.add_field(name="Encounters", value=str(encounters))
    emb.add_field(name="Catches", value=str(catches))
    emb.add_field(name="Shinies", value=str(shinies))
    emb.add_field(name="\u200b", value="\u200b")

    breakdown = (
        f"Wild: {wild}\n"
        f"Incense: {incense}\n"
        f"Lure: {lure}\n"
        f"Quest: {quest}\n"
        f"Raid: {raid}\n"
        f"Rocket: {rocket}\n"
        f"Max: {maxb}\n"
        f"Runaways: {runaways}"
    )

    emb.add_field(name="Event breakdown", value=breakdown, inline=False)

    emb.add_field(name="🎯 Catch rate", value=f"{catch_rate:.1f}%", inline=True)
    emb.add_field(name="🏃 Runaways (est.)", value=str(runaways), inline=True)
    emb.add_field(name="🏆 Perfect 100 IV", value=str(len([e for e in rows if e.get('iv') == (15,15,15)])), inline=True)

    # ----------------------------------------------------------
    # Latest Catches
    # ----------------------------------------------------------
    emb.add_field(name="🕒 Latest Catches", value=latest_catches_txt, inline=False)

    # ----------------------------------------------------------
    # Latest Shinies
    # ----------------------------------------------------------
    emb.add_field(name="✨ Latest Shinies", value=latest_shinies_txt, inline=False)

    return emb