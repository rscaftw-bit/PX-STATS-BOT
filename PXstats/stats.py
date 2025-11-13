# PXstats • stats.py (FINAL)
# Compatible with new shiny-flag parser

from datetime import datetime, timedelta
from discord import Embed
from PXstats.utils import TZ

# ---------------------------------------------------------
# Internal: Format timestamp
# ---------------------------------------------------------

def fmt(ts: float) -> str:
    """Format UNIX timestamp to readable EU datetime."""
    return datetime.fromtimestamp(ts, TZ).strftime("%d %B %Y %H:%M")

# ---------------------------------------------------------
# Internal: CSV helper
# ---------------------------------------------------------

def make_csv_rows(events):
    """Return a list of dicts for CSV export."""
    rows = []
    for ev in events:
        data = ev["data"]
        rows.append({
            "timestamp": fmt(ev["ts"]),
            "type": ev["type"],
            "name": data.get("name"),
            "iv": "/".join(map(str, data["iv"])) if data.get("iv") else "",
            "shiny": "YES" if data.get("shiny") else "NO",
            "source": data.get("source", "")
        })
    return rows

# ---------------------------------------------------------
# Main embed builder
# ---------------------------------------------------------

def build_embed(events):
    """
    Build the Discord embed for /summary.
    """
    # ========== Counters ==========
    catches = 0
    shinies = 0
    runaways = 0

    wild = quest = raid = rocket = maxb = 0

    latest_catches = []
    latest_shinies = []

    for ev in events:
        etype = ev.get("type")
        data = ev.get("data", {})
        ts = ev.get("ts")

        # ------- Count catches -------
        if etype == "Catch":
            catches += 1
            latest_catches.append(ev)

            if data.get("shiny"):
                shinies += 1
                latest_shinies.append(ev)

        # ------- Count shiny Encounter Ping -------
        if etype == "Encounter" and data.get("shiny"):
            shinies += 1
            latest_shinies.append(ev)

        # ------- Event breakdown -------
        if etype == "Encounter":
            src = data.get("source", "wild")
            if src == "wild":
                wild += 1
        elif etype == "Quest":
            quest += 1
        elif etype == "Raid":
            raid += 1
        elif etype == "Rocket":
            rocket += 1
        elif etype == "MaxBattle":
            maxb += 1
        elif etype == "Fled":
            runaways += 1

    # Sort newest first
    latest_catches = sorted(latest_catches, key=lambda e: e["ts"], reverse=True)[:5]
    latest_shinies = sorted(latest_shinies, key=lambda e: e["ts"], reverse=True)[:5]

    total_enc = len(events)

    # ---------------------------------------------------------
    # Build embed
    # ---------------------------------------------------------
    e = Embed(
        title="📊 Today's Stats (Last 24h)",
        color=0x3498DB
    )

    # Top line numbers
    e.add_field(name="Encounters", value=str(total_enc), inline=True)
    e.add_field(name="Catches", value=str(catches), inline=True)
    e.add_field(name="Shinies", value=str(shinies), inline=True)

    # Breakdown
    breakdown = (
        f"Wild: {wild}\n"
        f"Quest: {quest}\n"
        f"Raid: {raid}\n"
        f"Rocket: {rocket}\n"
        f"Max: {maxb}\n"
        f"Runaways: {runaways}"
    )
    e.add_field(name="Event breakdown", value=breakdown, inline=False)

    # Catch rate
    catch_rate = (catches / total_enc * 100) if total_enc else 0
    e.add_field(name="🎯 Catch rate", value=f"{catch_rate:.1f}%", inline=True)
    e.add_field(name="🏃 Runaways (est.)", value=str(runaways), inline=True)

    # 100% IV
    perfect = 0
    for ev in events:
        data = ev["data"]
        if data.get("iv") == (15, 15, 15):
            perfect += 1
    e.add_field(name="🏆 Perfect 100 IV", value=str(perfect), inline=True)

    # Latest Catches
    if latest_catches:
        txt = "\n".join(
            f"{ev['data']['name']} {ev['data']['iv'][0]}/{ev['data']['iv'][1]}/{ev['data']['iv'][2]}  "
            f"({fmt(ev['ts'])})"
            for ev in latest_catches
        )
    else:
        txt = "—"
    e.add_field(name="🕒 Latest Catches", value=txt, inline=False)

    # Latest Shinies
    if latest_shinies:
        s_txt = "\n".join(
            f"{ev['data']['name']} {ev['data']['iv'][0]}/{ev['data']['iv'][1]}/{ev['data']['iv'][2]}  "
            f"({fmt(ev['ts'])})"
            for ev in latest_shinies
        )
    else:
        s_txt = "—"

    e.add_field(name="✨ Latest Shinies", value=s_txt, inline=False)

    # Footer (stats version)
    e.set_footer(text=f"Rate base: {total_enc} • stats-v3.9.2 • {datetime.now(TZ).strftime('%Y-%m-%d')}")

    return e