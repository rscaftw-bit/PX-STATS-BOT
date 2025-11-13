# ===============================================================
# PXstats • utils.py • v4.0 (FINAL)
# Core storage, events manager, time utilities
# ===============================================================

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Timezone
TZ = ZoneInfo("Europe/Brussels")

# Path to event storage
EVENTS_FILE = os.path.join(os.path.dirname(__file__), "events.json")

# In-memory storage
EVENTS = []


# ===============================================================
# LOAD EVENTS
# ===============================================================
def load_events():
    """Load events from events.json into EVENTS list."""
    global EVENTS

    if not os.path.exists(EVENTS_FILE):
        EVENTS = []
        print("[EVENTS] No events.json found → starting fresh")
        return EVENTS

    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        EVENTS = []
        for e in raw:
            # ensure timestamps convert to datetime
            if isinstance(e.get("timestamp"), str):
                try:
                    e["timestamp"] = datetime.fromisoformat(e["timestamp"])
                except:
                    # fallback: treat as UTC
                    e["timestamp"] = datetime.fromtimestamp(0, TZ)

            EVENTS.append(e)

        print(f"[EVENTS] Loaded {len(EVENTS)} events")

    except Exception as e:
        print(f"[ERROR] Could not load events: {e}")
        EVENTS = []

    return EVENTS


# ===============================================================
# SAVE EVENTS
# ===============================================================
def save_events():
    """Save all events to events.json."""
    try:
        serial = []
        for e in EVENTS:
            evt = dict(e)
            # convert datetime to ISO8601 string
            if isinstance(evt["timestamp"], datetime):
                evt["timestamp"] = evt["timestamp"].isoformat()
            serial.append(evt)

        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(serial, f, indent=2, ensure_ascii=False)

        print(f"[EVENTS] Saved ({len(EVENTS)} events)")

    except Exception as e:
        print(f"[SAVE ERROR] {e}")


# ===============================================================
# ADD EVENT
# ===============================================================
def add_event(data: dict):
    """
    Add event (Catch, Shiny, Encounter, Rocket, Raid, etc.)
    Events look like:
    {
        "timestamp": datetime,
        "type": "Catch",
        "name": "...",
        "iv": [a,d,s]
    }
    """

    # Ensure timestamp exists
    if "timestamp" not in data:
        data["timestamp"] = datetime.now(TZ)

    EVENTS.append(data)
    return data


# ===============================================================
# FILTER: LAST 24 HOURS
# ===============================================================
def last_24h():
    """Return events from last 24 hours."""
    cutoff = datetime.now(TZ).timestamp() - 24 * 3600
    rows = []

    for e in EVENTS:
        ts = e["timestamp"]
        if isinstance(ts, datetime):
            tstamp = ts.timestamp()
        else:
            try:
                tstamp = datetime.fromisoformat(ts).timestamp()
            except:
                continue

        if tstamp >= cutoff:
            rows.append(e)

    return rows