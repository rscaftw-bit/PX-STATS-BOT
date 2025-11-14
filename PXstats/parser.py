# PXstats v4 – parser.py (fix shiny)
# - Shiny detection op ruwe tekst (met/zonder emoji)
# - Correct encounter vs catch
# - Correct Pokédex mapping (p###, p###-FORM)
# - Handles PolygonX "p 7/9/10" glitch
# - Betere name-extractie

import re
import unicodedata
from typing import Tuple, Optional
import discord

from PXstats.pokedex import get_name_from_id

# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------

IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)


def _norm(s: str) -> str:
    """Normalize text to ASCII lowercase (voor algemene detectie)."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _extract_name(desc: str) -> str:
    """Extract Pokémon name of p### ID uit tekst."""
    # “Pokemon: Necrozma (800:2717:0:3)”
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .0-9:-]+)", desc, re.I)
    if m:
        return m.group(1).strip()

    # Fallback: p### of p 123 of p123-XYZ
    m = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", desc, re.I)
    if m:
        return f"p{m.group(1)}"

    return "?"


def _extract_iv(desc: str):
    """IV-triple eruit halen."""
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# -------------------------------------------------------------
# MAIN PARSER
# -------------------------------------------------------------

def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """Parses een PolygonX embed en geeft (event_type, data) terug."""

    title = (e.title or "")
    desc = (e.description or "")

    field_chunks = []
    for f in e.fields:
        if f.name:
            field_chunks.append(f.name)
        if f.value:
            field_chunks.append(f.value)

    full = "\n".join([title, desc] + field_chunks)
    full_norm = _norm(full)              # genormaliseerd (zonder emoji)
    full_lower = (full or "").lower()    # ruwe tekst, alleen lowercase

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None,
    }

    raw = data["name"].strip().lower()

    # ---------------------------------------------------------
    # Pokédex mapping: p### of p###-FORM → echte naam
    # ---------------------------------------------------------
    m_id = re.match(r"p\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)", raw)
    if m_id:
        pid = m_id.group(1)  # kan bv. "785" of "1017-c" zijn
        resolved = get_name_from_id(pid)
        print(f"[Pokédex-map] {data['name']} → {resolved}")
        data["name"] = resolved

    # PolygonX glitch: "p 7/9/10" etc.
    elif re.match(r"p\s*[0-9]{1,2}/[0-9]{1,2}/[0-9]{1,2}", raw):
        data["name"] = f"Unknown ({raw})"

    # ---------------------------------------------------------
    # SHINY-detectie (BELANGRIJK)
    # ---------------------------------------------------------
    shiny = False

    # 1) op ruwe tekst naar 'shiny' zoeken
    if "shiny" in full_lower:
        shiny = True
    # 2) emoji-check op ongenormaliseerde tekst
    elif any(sym in full for sym in ("✨", "⭐", "★", "🌟")):
        shiny = True

    if shiny:
        data["shiny"] = True

    # ---------------------------------------------------------
    # EVENT TYPE DETECTIE
    # ---------------------------------------------------------

    # CATCH (moet vóór Encounter komen)
    if "pokemon caught" in full_norm or "caught successfully" in full_norm:
        if data.get("shiny"):
            # één log met type "Shiny"
            return "Shiny", data
        return "Catch", data

    # QUEST
    if "quest" in full_norm:
        return "Quest", data

    # ROCKET
    if any(x in full_norm for x in ("rocket", "invasion", "grunt", "leader", "giovanni")):
        return "Rocket", data

    # RAID / MAX
    if "raid" in full_norm:
        return "Raid", data
    if "max battle" in full_norm:
        return "MaxBattle", data

    # HATCH
    if "hatch" in full_norm:
        return "Hatch", data

    # ENCOUNTER (wild/incense/lure)
    if "encounter" in full_norm or "encounter ping" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"

        return "Encounter", {
            "name": data["name"],
            "source": src,
        }

    # FLED
    if any(x in full_norm for x in ("fled", "flee", "ran away")):
        return "Fled", data

    # Onbekend type → negeren
    return None, {}
