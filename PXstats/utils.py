# PXstats • utils.py
# Shared storage & helpers

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List, Dict, Any
from zoneinfo import ZoneInfo

# Timezone (Belgium default)
TZ = ZoneInfo("Europe/Brussels")

# Path for events and pokedex JSON
BASE_DIR = os.path.dirname(__file__)
EVENTS_FILE = os.path.join(BASE_DIR, "events.json")
POKEDEX_FILE = os.path.join(BASE_DIR, "pokedex.json")

# In-memory stores
EVENTS: List[Dict[str, Any]] = []
_POKEDEX_CACHE: Dict[str, str] | None = None


# --------------------------------------------------
# Event persistence
# --------------------------------------------------
def _serialize_event(e: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(e)
    ts = out.get("timestamp")
    if isinstance(ts, datetime):
        out["timestamp"] = ts.astimezone(TZ).isoformat()
    return out


def _deserialize_event(e: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(e)
    ts = out.get("timestamp")
    if isinstance(ts, str):
        try:
            out["timestamp"] = datetime.fromisoformat(ts)
        except Exception:
            out["timestamp"] = datetime.now(TZ)
    return out


def load_events() -> List[Dict[str, Any]]:
    """Load events from disk into EVENTS and return the list."""
    global EVENTS
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        EVENTS = [_deserialize_event(e) for e in raw]
        print(f"[EVENTS] loaded {len(EVENTS)} events")
    except FileNotFoundError:
        EVENTS = []
        print("[EVENTS] no existing events file, starting fresh")
    except Exception as e:
        EVENTS = []
        print(f"[EVENTS] error loading events: {e}")
    return EVENTS


def save_events() -> None:
    """Persist EVENTS list to disk."""
    try:
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump([_serialize_event(e) for e in EVENTS], f, ensure_ascii=False)
        print(f"[EVENTS] saved {len(EVENTS)} events")
    except Exception as e:
        print(f"[EVENTS] error saving events: {e}")


def add_event(data: Dict[str, Any]) -> None:
    """Append a single event to the in-memory store."""
    from datetime import datetime as _dt

    if "timestamp" not in data:
        data["timestamp"] = _dt.now(TZ)
    EVENTS.append(data)


# --------------------------------------------------
# Pokédex loading
# --------------------------------------------------
def load_pokedex() -> Dict[str, str]:
    """Load pokedex.json into a dict (cached)."""
    global _POKEDEX_CACHE
    if _POKEDEX_CACHE is not None:
        return _POKEDEX_CACHE

    try:
        with open(POKEDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Normalize keys to upper-case strings
        _POKEDEX_CACHE = {str(k).upper(): v for k, v in data.items()}
        print(f"[POKEDEX] loaded {len(_POKEDEX_CACHE)} entries")
    except FileNotFoundError:
        _POKEDEX_CACHE = {}
        print("[POKEDEX] pokedex.json not found, running with empty Pokédex")
    except Exception as e:
        _POKEDEX_CACHE = {}
        print(f"[POKEDEX] error loading pokedex.json: {e}")
    return _POKEDEX_CACHE


def get_pokedex() -> Dict[str, str]:
    """Public accessor for Pokédex cache."""
    return load_pokedex()
