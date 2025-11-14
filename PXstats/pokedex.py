# PXstats • pokedex.py • v4.2
# Leest pokedex.json en mapt ID → naam.

import os
import json
from functools import lru_cache


@lru_cache()
def load_pokedex():
    path = os.path.join(os.path.dirname(__file__), "pokedex.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[POKEDEX] geladen: {len(data)} entries")
        return data
    except Exception as e:
        print("[POKEDEX ERROR]", e)
        return {}


def get_name_from_id(pid):
    """
    pid kan zijn:
    - int: 785
    - str: "785" of "785-A"
    """
    dex = load_pokedex()

    key = str(pid)
    name = dex.get(key)

    if not name and "-" in key:
        base, _ = key.split("-", 1)
        name = dex.get(key) or dex.get(base)

    if not name:
        return f"p{key}"
    return name
