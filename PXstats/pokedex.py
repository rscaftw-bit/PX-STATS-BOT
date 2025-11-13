# PXstats • pokedex.py
# Loads the Ultra Full Pokédex (Option C)
# Supports forms like 487-O, 479-W, 1024-T
# Fallbacks safely if entry not found

import json
import os

# Path to full Pokédex JSON file
POKEDEX_FILE = os.path.join(os.path.dirname(__file__), "pokedex_full.json")

# Loaded data
_POKEDEX = {}

# ============================
# LOAD POKEDEX
# ============================
def load_pokedex() -> dict:
    global _POKEDEX

    if _POKEDEX:
        return _POKEDEX  # already loaded

    try:
        with open(POKEDEX_FILE, "r", encoding="utf-8") as f:
            _POKEDEX = json.load(f)

        print(f"[Pokédex] Loaded {len(_POKEDEX)} entries from pokedex_full.json")

    except Exception as e:
        print(f"[Pokédex ERROR] Failed to load pokedex_full.json: {e}")
        _POKEDEX = {}

    return _POKEDEX


# ============================
# GET NAME FROM POKÉDEX ID
# ============================
def get_name_from_id(pid: str) -> str:
    """
    pid examples:
       "785"
       "487-O"
       "479-W"
       "1024-T"
    """
    pokedex = load_pokedex()

    # direct match
    if pid in pokedex:
        return pokedex[pid]

    # safety: strip leading zeros ("p0025" -> "25")
    pid_clean = pid.lstrip("0")
    if pid_clean in pokedex:
        return pokedex[pid_clean]

    # Try uppercase for form keys
    pid_upper = pid.upper()
    if pid_upper in pokedex:
        return pokedex[pid_upper]

    # fallback unknown
    return f"Unknown #{pid}"