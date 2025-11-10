import json
import os

POKEDEX_PATH = os.path.join(os.path.dirname(__file__), "pokedex.json")

def load_pokedex():
    """
    Load Pokédex from pokedex.json or create a fallback with generic names.
    Returns dict: {id: name}
    """
    pokedex = {}

    # 1️⃣ Eerst proberen het JSON-bestand te laden
    if os.path.exists(POKEDEX_PATH):
        try:
            with open(POKEDEX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # verwacht structuur: [{"id":1,"name":"Bulbasaur"}, ...]
                for entry in data:
                    pokedex[int(entry["id"])] = entry.get("name", f"Pokémon {entry['id']}")
            print(f"[Pokédex] Loaded from {POKEDEX_PATH} ({len(pokedex)} entries)")
            return pokedex
        except Exception as e:
            print(f"[Pokédex] Failed to parse JSON: {e}")

    # 2️⃣ Fallback als bestand ontbreekt of fout
    for i in range(1, 1026):
        pokedex[i] = f"Pokémon {i}"
    print(f"[Pokédex] Fallback generated: {len(pokedex)} generic entries")

    return pokedex


def get_name_from_id(pid: int):
    """Return Pokémon name by ID."""
    if pid in POKEDEX:
        return POKEDEX[pid]
    return f"Pokémon {pid}"


# Initialise global on import
POKEDEX = load_pokedex()
