# PXstats • pokedex.py
# -------------------------------------------------------------
# Full Pokédex loader with p### and p###-FORMID support.
# Works with complete pokedex.json (1–1025 + variants).
# -------------------------------------------------------------

import json
import os

POKEDEX = {}


# -------------------------------------------------------------
# LOAD POKEDEX FROM JSON
# -------------------------------------------------------------
def load_pokedex():
    """Load pokedex.json from PXstats folder."""
    global POKEDEX

    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "pokedex.json")

    try:
        with open(json_path, "r", encoding="utf8") as f:
            POKEDEX = json.load(f)

        print(f"[POKÉDEX] Loaded {len(POKEDEX)} entries")

    except Exception as e:
        print(f"[ERROR] Could not load pokedex.json: {e}")
        POKEDEX = {}

    return POKEDEX


# -------------------------------------------------------------
# RESOLVE NAME FROM ID
# -------------------------------------------------------------
def get_name_from_id(raw):
    """
    Accepts:
        "785"
        "p785"
        "p0785"
        "p785-h"
        "785-h"
        "1024-T"
        "1012-A"
    Returns:
        Pokémon name (string) or "Unknown (raw)"
    """

    if raw is None:
        return "Unknown"

    key = str(raw).lower().replace(" ", "").replace("p", "")

    # Example:
    # raw = "p1017-H" → key = "1017-h"
    # raw = "785" → key = "785"

    # Direct match
    if key in POKEDEX:
        return POKEDEX[key]

    # Form-ID case-insensitive
    # Example: "1017-h" → try "1017-H"
    # Example: "1017-h" → try "1017-H"
    upper_key = key.upper()
    if upper_key in POKEDEX:
        return POKEDEX[upper_key]

    # Remove leading zeroes "0007" → "7"
    nozero = key.lstrip("0")
    if nozero in POKEDEX:
        return POKEDEX[nozero]

    # Try upper-case variant for forms without zero
    if nozero.upper() in POKEDEX:
        return POKEDEX[nozero.upper()]

    # If still not found:
    return f"Unknown ({raw})"