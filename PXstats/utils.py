# PXstats v3.8 — utils.py
# Storage (events.json), 24h filter, Pokédex loader, timezone

import os, json, time
from collections import deque
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

# ----- Timezone -----
TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Brussels"))

# ----- In-memory events buffer + persistence -----
SAVE_PATH = os.getenv("EVENTS_FILE", "events.json")
EVENTS: deque = deque(maxlen=100000)

def _coerce_event(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one event record loaded from disk."""
    d = rec.get("data") or {}
    iv = d.get("iv")
    if isinstance(iv, list) and len(iv) == 3:
        d["iv"] = (iv[0], iv[1], iv[2])  # tuple for consistency
    return {
        "ts": float(rec.get("ts", time.time())),
        "type": rec.get("type"),
        "data": d,
    }

def load_events() -> None:
    """Load events from SAVE_PATH into EVENTS (append)."""
    if not os.path.exists(SAVE_PATH):
        print("[LOAD] no events.json, starting fresh")
        return
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cnt = 0
        for rec in raw:
            EVENTS.append(_coerce_event(rec))
            cnt += 1
        print(f"[LOAD] {cnt} events restored")
    except Exception as e:
        print("[LOAD ERR]", e)

def save_events() -> None:
    """Persist EVENTS to SAVE_PATH."""
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(list(EVENTS), f, ensure_ascii=False)
        # Optional: uncomment to log every save (can be noisy)
        # print(f"[SAVE] {len(EVENTS)} events -> {SAVE_PATH}")
    except Exception as e:
        print("[SAVE ERR]", e)

def add_event(evt_type: str, data: dict, ts: Optional[float] = None) -> None:
    """Append an event and immediately persist (simple & safe)."""
    EVENTS.append({
        "ts": ts if ts is not None else time.time(),
        "type": evt_type,
        "data": data or {},
    })
    save_events()

def last_24h(hours: int = 24) -> List[Dict[str, Any]]:
    """Return a list of events within the last N hours (default 24)."""
    cutoff = time.time() - hours * 3600
    # Copy to list to avoid iterator invalidation
    return [e for e in list(EVENTS) if float(e.get("ts", 0)) >= cutoff]

# ----- Pokédex -----
# We store pokedex.json alongside this file (PXstats/pokedex.json)
POKEDEX_PATH = os.path.join(os.path.dirname(__file__), "pokedex.json")
POKEDEX: Dict[str, str] = {}

def _seed_pokedex() -> Dict[str, str]:
    """
    Create a full 1..1025 skeleton so 'p###' nooit in de UI blijft staan.
    Placeholder-naam 'Pokemon N' waar we geen echte naam hebben.
    (Je kunt later je volledige officiële mapping committen; deze wordt dan geladen.)
    """
    base = {str(i): f"Pokemon {i}" for i in range(1, 1026)}
    # Enkele bekende late entries die we wél juist invullen:
    base["808"] = "Meltan"; base["809"] = "Melmetal"
    base["999"] = "Gimmighoul"; base["1000"] = "Gholdengo"; base["1025"] = "Pecharunt"
    return base

def load_pokedex() -> Dict[str, str]:
    """
    Load pokedex.json if present; otherwise create a 1..1025 skeleton mapping.
    Returns the in-memory dict for optional use elsewhere.
    """
    global POKEDEX
    if os.path.exists(POKEDEX_PATH):
        try:
            with open(POKEDEX_PATH, "r", encoding="utf-8") as f:
                POKEDEX = json.load(f)
            print(f"[POKEDEX] loaded {len(POKEDEX)} entries")
            return POKEDEX
        except Exception as e:
            print("[POKEDEX LOAD ERR]", e)

    # Create and persist a default full skeleton
    POKEDEX = _seed_pokedex()
    try:
        with open(POKEDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(POKEDEX, f, ensure_ascii=False)
        print(f"[POKEDEX] created local file with {len(POKEDEX)} entries")
    except Exception as e:
        print("[POKEDEX SAVE ERR]", e)
    return POKEDEX

# (Optional) Helper als je ergens 'p###' naar naam wil vertalen in je UI/parser:
def dex_name(raw_name: str) -> str:
    """
    Convert strings als 'p816' of 'P 816' naar een Pokédex-naam (indien gekend).
    Laat gewone namen ongemoeid.
    """
    if not raw_name:
        return "?"
    s = str(raw_name).strip()
    # p ### varianten normaliseren
    # bv. "p816", "P 816", "p 007"
    import re
    m = re.match(r"(?i)^\s*p\s*(\d{1,4})\s*$", s)
    if m:
        pid = m.group(1).lstrip("0")
        name = POKEDEX.get(pid)
        return name if name else f"p{pid}"
    return s
