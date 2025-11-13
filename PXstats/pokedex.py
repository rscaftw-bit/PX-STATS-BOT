# ======================================================
# PXstats • pokedex.py • 2025-11-13
# Laadt pokedex.json en mapt ID -> naam
# ======================================================

from __future__ import annotations

import json
import os

BASE_DIR = os.path.dirname(__file__)
POKEDEX_PATH = os.path.join(BASE_DIR, "pokedex.json")

POKEDEX: dict[str, str] = {}


def load_pokedex() -> dict[str, str]:
    """Laad pokedex.json in globale POKEDEX dict."""
    global POKEDEX
    try:
        with open(POKEDEX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # keys altijd strings
        POKEDEX = {str(k): v for k, v in data.items()}
        print(f"[POKEDEX] Loaded {len(POKEDEX)} entries.")
    except Exception as exc:
        print(f"[POKEDEX ERROR] {exc}")
        POKEDEX = {}
    return POKEDEX


def get_name_from_id(pid: int | str) -> str:
    """Geef officiële naam voor ID of vorm-ID (bvb '1012-A')."""
    key = str(pid)
    return POKEDEX.get(key, f"p{key}")
