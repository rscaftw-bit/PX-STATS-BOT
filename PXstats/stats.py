# ================================================================
# PXstats – stats.py • v4.2 • 2025-11-13
# Tellers voor encounters/catches/shinies + breakdown + latest
# ================================================================

from datetime import datetime, timedelta
import discord

from PXstats.utils import TZ


def build_embed(all_events):
    """Bouwt de /summary embed op basis van EVENTS list."""

    now = datetime.now(TZ)
    rows = [e for e in all_events if (now - e["timestamp"]) <= timedelta(hours=24)]

    # counters
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

    latest_catches = []
    latest_shinies = []

    for e in rows:
        et = e.get("type", "").lower()

        # ===== ENCOUNTERS =====
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

        # ===== RUNAWAYS =====
        if et == "fled":
            runaways += 1

        # ===== CATCHES & SHINIES =====
        if et == "catch":
            catches += 1
            latest_catches.append(e)
            if e.get("shiny"):
                shinies += 1
                latest_shinies.append(e)

    # ===== RATES =====
    effective_encounters = max(encounters - runaways, 1)
    catch_rate = (catches / effective_encounters) * 100

    # ===== Latest Catches (max 5) =====
    latest_catches = sorted(
        latest_catches, key=lambda x: x["timestamp"], reverse=True
    )[:5]

    txt_latest_catches = (
        "\n".join(
            f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
            f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
            for e in latest_catches
        )
        if latest_catches
        else "—"
    )

    # ===== Latest Shinies (max 5) =====
    latest_shinies = sorted(
        latest_shinies, key=lambda x: x["timestamp"], reverse=True
    )[:5]

    txt_latest_shinies = (
        "\n".join(
            f"{e['name']} {e['iv'][0]}/{e['iv'][1]}/{e['iv'][2]} "
            f"({e['timestamp'].strftime('%d %B %Y %H:%M')})"
            for e in latest_shinies
        )
        if latest_shinies
        else "—"
    )

    # ===== BUILD EMBED =====
    emb = discord.Embed(
        title="📊 Today’s Stats (Last 24h)",
        color=0x5865F2
    )

    emb.add_field(name="🕵️ Encounters", value=str(encounters), inline=True)
    emb.add_field(name="🎯 Catches", value=str(catches), inline=True)
    emb.add_field(name="✨ Shinies", value=str(shinies), inline=True)

    breakdown = (
        f"🐾 Wild: {wild}\n"
        f"🧪 Incense: {incense}\n"
        f"🎣 Lure: {lure}\n"
        f"📜 Quest: {quest}\n"
        f"⚔️ Raid: {raid}\n"
        f"🚀 Rocket: {rocket}\n"
        f"🌀 Max: {maxb}\n"
        f"🏃 Runaways: {runaways}"
    )
    emb.add_field(name="📌 Event breakdown", value=breakdown, inline=False)

    emb.add_field(name="🎯 Catch rate", value=f"{catch_rate:.1f}%", inline=True)
    emb.add_field(name="🏃 Runaways (est.)", value=str(runaways), inline=True)
    emb.add_field(
        name="🏆 Perfect 100 IV",
        value=str(len([e for e in rows if e.get("iv") == (15, 15, 15)])),
        inline=True
    )

    emb.add_field(name="🕒 Latest Catches", value=txt_latest_catches, inline=False)
    emb.add_field(name="✨ Latest Shinies", value=txt_latest_shinies, inline=False)

    return emb