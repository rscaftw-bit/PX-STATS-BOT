# ======================================================
# PXstats • utils.py • 2025-11-13
# Event storage + timezone
# ======================================================

from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Timezone (Brussels)
TZ = ZoneInfo("Europe/Brussels")

# Padjes
BASE_DIR = os.path.dirname(__file__)
EVENT_FILE = os.path.join(BASE_DIR, "events.json")

# Globale event-list
EVENTS: list[dict] = []


# ======================================================
# EVENTS LADEN / OPSLAAN
# ======================================================

def load_events() -> list[dict]:
    """Laad events.json in de globale EVENTS-list (in-place)."""
    EVENTS.clear()

    if not os.path.exists(EVENT_FILE):
        print("[EVENTS] Geen events.json gevonden, start leeg.")
        return EVENTS

    try:
        with open(EVENT_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        for e in raw:
            ts_str = e.get("timestamp")
            if ts_str:
                try:
                    e["timestamp"] = datetime.fromisoformat(ts_str)
                except Exception:
                    # fallback: strip timezone als er iets raars in zit
                    e["timestamp"] = datetime.fromisoformat(ts_str.split("+")[0])
            else:
                e["timestamp"] = datetime.now(TZ)

            EVENTS.append(e)

        print(f"[EVENTS] Loaded {len(EVENTS)} events.")
    except Exception as exc:
        print(f"[EVENTS ERROR] {exc}")

    return EVENTS


def save_events() -> None:
    """Schrijf EVENTS terug naar events.json."""
    try:
        to_save: list[dict] = []
        for e in EVENTS:
            d = dict(e)
            ts = d.get("timestamp")
            if isinstance(ts, datetime):
                d["timestamp"] = ts.isoformat()
            to_save.append(d)

        with open(EVENT_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2)

        print(f"[EVENTS] Saved {len(EVENTS)} events.")
    except Exception as exc:
        print(f"[EVENTS SAVE ERROR] {exc}")


def add_event(ev: dict) -> None:
    """Voeg één event toe aan de globale lijst."""
    EVENTS.append(ev)
