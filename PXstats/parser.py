# PXstats v4.6 – parser.py
# -------------------------------------------------------------
# Fixes:
# - Shiny detection: match "shiny" in normalized text (newline-safe)
# - Keeps correct encounter vs catch
# - Correct Pokédex mapping (p###, p###-FORM)
# - Handles PolygonX "p 7/9/10" glitch
# -------------------------------------------------------------

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
    """Normalize text to ASCII lowercase."""
    return unicodedata.normalize("NFKD", s or "").encode(
        "ascii", "ignore"
    ).decode().lower().strip()


def _extract_name(desc: str) -> str:
    """Extract Pokémon name or p### ID from text."""
    # Normaal: "Pokemon: Necrozma (800:2717:0:3)"
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .0-9:-]+)", desc, re.I)
    if m:
        return m.group(1).strip()

    # Fallback: losse "p###" of "p 785" enz.
    m = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", desc, re.I)
    if m:
        return f"p{m.group(1)}"

    return "?"


def _extract_iv(desc: str):
    """Extract IV triple as (atk, def, sta) or None."""
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# -------------------------------------------------------------
# MAIN PARSER
# -------------------------------------------------------------

def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """
    Parse a PolygonX/Spidey embed en return (event_type, data)

    Mogelijke event_type:
      - "Encounter"  (wild / incense / lure)
      - "Catch"
      - "Raid"
      - "Rocket"
      - "Quest"
      - "MaxBattle"
      - "Hatch"
      - "Fled"
    data bevat minstens:
      - name
      - iv: (a,d,s) of None
      - level (nu nog None)
      - shiny: bool (optioneel, alleen bij shiny)
    """

    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full_norm = _norm(full)

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None,
    }

    raw = data["name"].strip().lower()

    # ---------------------------------------------------------
    # Pokédex mapping: p### of p###-FORM → officiële naam
    # ---------------------------------------------------------
    m_id = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", raw)
    if m_id:
        pid = m_id.group(1)          # bv "859" of "1017-C"
        resolved = get_name_from_id(pid)
        print(f"[Pokédex-map] {data['name']} → {resolved}")
        data["name"] = resolved

    # PolygonX glitch: "p 7/9/10"
    elif re.match(r"p\s*[0-9]{1,2}/[0-9]{1,2}/[0-9]{1,2}", raw):
        data["name"] = f"Unknown ({raw})"

    # ---------------------------------------------------------
    # SHINY detection – **FIXED**
    # We kijken gewoon of 'shiny' ergens in de genormaliseerde tekst zit.
    # (De lijn "SHINY ✨" wordt genormaliseerd naar "shiny")
    # ---------------------------------------------------------
    if "shiny" in full_norm:
        data["shiny"] = True

    # ---------------------------------------------------------
    # EVENT TYPE DETECTION
    # ---------------------------------------------------------

    # CATCH (moet vóór "encounter", want de tekst bevat ook "Encounter" in titles soms)
    if "pokemon caught successfully" in full_norm or "pokemon caught" in full_norm:
        # Shiny-catch blijft type "Catch", maar met data["shiny"] = True
        return "Catch", data

    # HATCH
    if "hatched egg" in full_norm or "hatch" in full_norm:
        return "Hatch", data

    # QUEST
    if "quest" in full_norm:
        return "Quest", data

    # ROCKET (invasion / grunt / leader / giovanni)
    if any(x in full_norm for x in ["rocket", "invasion encounter", "invasion", "grunt", "leader", "giovanni"]):
        return "Rocket", data

    # RAID / MAX
    if "raid battle encounter" in full_norm or "raid" in full_norm:
        return "Raid", data
    if "max battle" in full_norm:
        return "MaxBattle", data

    # FLED
    if any(x in full_norm for x in ["pokemon flee", "pokemon fled", "ran away", "fleed"]):
        return "Fled", data

    # ENCOUNTER (wild, incense, lure)
    if "encounter ping" in full_norm or "encounter!" in full_norm or "encounter" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure encounter" in full_norm or "lure" in full_norm:
            src = "lure"

        return "Encounter", {
            "name": data["name"],
            "source": src,
            "iv": data["iv"],
            "level": data["level"],
            "shiny": data.get("shiny", False),
        }

    # Onbekend / niet relevant → negeren
    return None, {}
