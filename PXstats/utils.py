# PXstats • utils.py • v4.2
import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any

TZ = ZoneInfo(os.getenv("TZ", "Europe/Brussels"))

EVENTS: List[Dict[str, Any]] = []


def load_events(path: str = "events.json"):
    """Laad events.json in geheugen (EVENTS)."""
    global EVENTS
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        EVENTS = []
        for e in raw:
            item = dict(e)
            ts = item.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts_dt = datetime.fromisoformat(ts)
                except Exception:
                    ts_dt = datetime.now(TZ)
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=TZ)
                item["timestamp"] = ts_dt
            EVENTS.append(item)

        print(f"[EVENTS] geladen: {len(EVENTS)} records")
    except FileNotFoundError:
        print("[EVENTS] events.json niet gevonden, start leeg.")
        EVENTS = []
    except Exception as e:
        print("[EVENT LOAD ERROR]", e)
        EVENTS = []

    return EVENTS


def save_events(path: str = "events.json"):
    """Schrijf EVENTS terug naar disk."""
    try:
        raw = []
        for e in EVENTS:
            item = dict(e)
            ts = item.get("timestamp")
            if isinstance(ts, datetime):
                item["timestamp"] = ts.isoformat()
            raw.append(item)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
    except Exception as e:
        print("[EVENT SAVE ERROR]", e)


def add_event(event: Dict[str, Any]):
    """Event toevoegen aan globale lijst."""
    EVENTS.append(event)


def last_24h(events):
    """Filter: enkel laatste 24 uur."""
    cutoff = datetime.now(TZ) - timedelta(hours=24)
    return [e for e in events if isinstance(e.get("timestamp"), datetime) and e["timestamp"] >= cutoff]


# ---- Pokédex wrapper -------------------------------------------------

def load_pokedex():
    """Doorgeefluik naar pokedex.load_pokedex, zodat main hierop kan blijven leunen."""
    try:
        from PXstats.pokedex import load_pokedex as _lp
        return _lp()
    except Exception as e:
        print("[POKEDEX WRAP ERROR]", e)
        return {}
