# PXstats • pokedex.py
# Lightweight helper around pokedex.json

from __future__ import annotations

from PXstats.utils import get_pokedex


def get_name_from_id(code: str | int) -> str:
    """Resolve a Pokédex id like '785' or '1017-C' to a Pokémon name.

    Falls back to 'p<code>' if not found, so the UI still shows something.
    """
    dex = get_pokedex()
    key = str(code).upper()

    # Exact key
    if key in dex:
        return dex[key]

    # Try without form suffix (e.g. '1017-C' -> '1017')
    if "-" in key:
        base = key.split("-", 1)[0]
        if base in dex:
            return dex[base]

    return f"p{code}"
