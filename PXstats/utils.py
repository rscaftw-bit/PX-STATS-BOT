# ======================================================
# PXstats • utils.py • Final Stable Build • 14-11-2025
# ======================================================

import json
from datetime import datetime
from zoneinfo import ZoneInfo
import os

# Timezone
TZ = ZoneInfo("Europe/Brussels")

# Data storage
EVENTS_FILE = "events.json"
EVENTS = []

# ------------------------------------------------------
# POKEDEX LOADER
# ------------------------------------------------------

_pokedex_cache = None

def load_pokedex():
    """Load and cache the pokedex.json file."""
    global _pokedex_cache

    if _pokedex_cache is not None:
        return _pokedex_cache

    path = os.path.join("PXstats", "pokedex.json")

    try:
        with open(path, "r", encoding="utf-8") as f:
            _pokedex_cache = json.load(f)
            print(f"[POKEDEX] Loaded {len(_pokedex_cache)} entries")
            return _pokedex_cache
    except Exception as e:
        print("[POKEDEX ERROR]", e)
        _pokedex_cache = {}
        return _pokedex_cache


def get_pokedex():
    """Return the cached Pokédex."""
    return load_pokedex()


# ------------------------------------------------------
# EVENT STORAGE
# ------------------------------------------------------

def load_events():
    """Load events from events.json."""
    global EVENTS

    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        EVENTS = []
        for e in raw:
            try:
                ts = datetime.fromisoformat(e["timestamp"])
            except:
                ts = datetime.now(TZ)

            EVENTS.append({
                "timestamp": ts,
                "type": e.get("type"),
                "name": e.get("name"),
                "iv": e.get("iv"),
                "source": e.get("source")
            })

    except FileNotFoundError:
        EVENTS = []
    except Exception as e:
        print("[LOAD EVENTS ERROR]", e)
        EVENTS = []


def save_events():
    """Save all events to JSON."""
    try:
        out = []
        for e in EVENTS:
            out.append({
                "timestamp": e["timestamp"].isoformat(),
                "type": e["type"],
                "name": e["name"],
                "iv": e.get("iv"),
                "source": e.get("source"),
            })

        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)

    except Exception as e:
        print("[SAVE EVENTS ERROR]", e)


def add_event(event):
    """Add an event to memory."""
    global EVENTS

    if not isinstance(event["timestamp"], datetime):
        try:
            event["timestamp"] = datetime.fromisoformat(event["timestamp"])
        except:
            event["timestamp"] = datetime.now(TZ)

    EVENTS.append(event)


# Load events on import
load_events()
