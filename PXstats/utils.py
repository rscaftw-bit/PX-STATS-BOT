# ======================================================
# PXstats • utils.py • 2025-11-13
# Includes: load_pokedex(), save_pokedex(), event storage
# ======================================================

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Timezone
TZ = ZoneInfo("Europe/Brussels")

# File locations
EVENT_FILE = "events.json"
POKEDEX_FILE = os.path.join(os.path.dirname(__file__), "pokedex.json")

# In-memory storage
EVENTS = []
POKEDEX = {}


# ======================================================
# EVENTS LOADING
# ======================================================

def load_events():
    global EVENTS
    if not os.path.exists(EVENT_FILE):
        EVENTS = []
        return EVENTS
    
    try:
        with open(EVENT_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Convert timestamps to datetime
        EVENTS = [
            {
                **e,
                "timestamp": datetime.fromisoformat(e["timestamp"])
            }
            for e in raw
        ]
        print(f"[LOAD] {len(EVENTS)} events geladen.")
        return EVENTS

    except Exception as e:
        print("[LOAD ERROR]", e)
        EVENTS = []
        return EVENTS


def save_events():
    try:
        data = [
            {
                **e,
                "timestamp": e["timestamp"].isoformat()
            }
            for e in EVENTS
        ]

        with open(EVENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"[SAVE] {len(EVENTS)} events opgeslagen.")

    except Exception as e:
        print("[SAVE ERROR]", e)


def add_event(e):
    EVENTS.append(e)


# ======================================================
# POKEDEX LOADING
# ======================================================

def load_pokedex():
    """Load pokedex.json and store it globally."""
    global POKEDEX

    try:
        with open(POKEDEX_FILE, "r", encoding="utf-8") as f:
            POKEDEX = json.load(f)

        print(f"[POKEDEX] Loaded {len(POKEDEX)} entries.")
        return POKEDEX

    except Exception as e:
        print(f"[POKEDEX ERROR] {e}")
        POKEDEX = {}
        return POKEDEX


def save_pokedex(data):
    """Optional: if you ever rewrite the Pokédex."""
    try:
        with open(POKEDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("[POKEDEX] Saved.")
    except Exception as e:
        print("[POKEDEX SAVE ERROR]", e)