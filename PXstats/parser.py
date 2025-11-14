# PXstats • parser.py • v4.2

import re
import unicodedata
from typing import Tuple, Optional
import discord

from PXstats.pokedex import get_name_from_id

IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)


def _norm(s: str) -> str:
    """ASCII-lower, handig voor keyword detectie (maar niet voor emoji!)."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _extract_name(desc: str) -> str:
    """Probeer de Pokémon naam of p### te pakken uit de tekst."""
    # Normale lijn: "Pokemon: Necrozma (800:2717:0:3)"
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .0-9:-]+)", desc, re.I)
    if m:
        return m.group(1).strip()

    # Fallback op p### (of p ###, p785-A, ...)
    m = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", desc, re.I)
    if m:
        return f"p{m.group(1)}"

    return "?"


def _extract_iv(desc: str):
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """
    Parse een PolygonX / Spidey embed → (event_type, data)

    Event types:
    - Encounter (wild/incense/lure via data["source"])
    - Quest
    - Raid
    - Rocket
    - Max
    - Catch
    - Fled
    - Hatch
    """
    title = (e.title or "")
    desc = (e.description or "")
    fields_text = "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full = f"{title}\n{desc}\n{fields_text}"

    full_norm = _norm(full)
    full_lower = (full or "").lower()

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None,
    }

    # ---------- Pokédex ID → naam ----------
    raw = data["name"].strip().lower()

    # p### of p###-FORM
    m_id = re.match(r"p\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)", raw)
    if m_id:
        pid = m_id.group(1)
        resolved = get_name_from_id(pid)
        print(f"[POKEDEX-MAP] {data['name']} → {resolved}")
        data["name"] = resolved
    # Glitch: "p 7/9/10" (niet te mappen)
    elif re.match(r"p\s*[0-9]{1,2}/[0-9]{1,2}/[0-9]{1,2}", raw):
        data["name"] = f"Unknown ({raw})"

    # ---------- Shiny detectie ----------
    shiny_triggers = [" shiny", "✨", "⭐", "★", "🌟"]
    if any(t in full_lower for t in shiny_triggers):
        data["shiny"] = True
    else:
        data["shiny"] = False

    # ---------- Event type detectie ----------

    # Catch (altijd eerst: deze embed heeft geen 'Encounter' in titel)
    if "pokemon caught successfully" in full_lower or "pokemon caught" in full_lower:
        return "Catch", data

    # Rocket / Invasion
    if "invasion encounter" in full_lower or "team go rocket" in full_lower or "grunt" in full_lower:
        return "Rocket", data

    # Raid
    if "complete raid battle encounter" in full_lower or "raid battle" in full_lower or "raid encounter" in full_lower:
        return "Raid", data

    # Quest
    if "quest encounter" in full_lower or "field research encounter" in full_lower:
        return "Quest", data

    # Max battle
    if "max battle" in full_lower or "max raid" in full_lower:
        return "Max", data

    # Hatch
    if "hatched" in full_lower or "egg hatch" in full_lower:
        return "Hatch", data

    # Encounter (wild / incense / lure)
    if "encounter ping" in full_lower or "encounter!" in full_lower:
        src = "wild"
        if "incense" in full_lower:
            src = "incense"
        elif "lure" in full_lower:
            src = "lure"
        data["source"] = src
        return "Encounter", data

    # Fled
    if "fled" in full_lower or "ran away" in full_lower:
        return "Fled", data

    # Geen match → negeren
    return None, {}
