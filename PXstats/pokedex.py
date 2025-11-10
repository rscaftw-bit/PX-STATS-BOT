import json, os

POKEDEX_PATH = os.path.join(os.path.dirname(__file__), "pokedex.json")

def load_pokedex():
    pokedex = {}
    if os.path.exists(POKEDEX_PATH):
        try:
            with open(POKEDEX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Jouw JSON is een dict {"1":"Bulbasaur", "2":"Ivysaur", ...}
                for k, v in data.items():
                    pokedex[int(k)] = v
            print(f"[Pokédex] Loaded (dict mode) with {len(pokedex)} entries")
            return pokedex
        except Exception as e:
            print(f"[Pokédex] Failed to parse JSON: {e}")

    # Fallback
    for i in range(1, 1026):
        pokedex[i] = f"Pokémon {i}"
    print(f"[Pokédex] Fallback generated: {len(pokedex)} generic entries")
    return pokedex


def get_name_from_id(pid: int):
    if pid in POKEDEX:
        return POKEDEX[pid]
    return f"Pokémon {pid}"


POKEDEX = load_pokedex()
