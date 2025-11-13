# PXstats v4 – FULL PARSER (13-11-2025)
# -------------------------------------------------------------
# Fixes:
# - Shiny detection
# - Correct encounter vs catch
# - Correct Pokédex mapping (p###, p###-FORM)
# - Handles PolygonX "p 7/9/10" glitch
# - Better name extraction
# -------------------------------------------------------------

import re
import unicodedata
from typing import Tuple, Optional
import discord

# Import Pokédex resolver
from PXstats.pokedex import get_name_from_id

# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------

IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)

def _norm(s: str) -> str:
    """Normalize text to ASCII lowercase."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()

def _extract_name(desc: str) -> str:
    """Extract Pokémon name or p### ID from text."""
    # Pokémon: Necrozma (...)
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .0-9:-]+)", desc, re.I)
    if m:
        return m.group(1).strip()

    # Fallback to p### or p 123
    m = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", desc, re.I)
    if m:
        return f"p{m.group(1)}"

    return "?"

def _extract_iv(desc: str):
    """Extract IV triple."""
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# -------------------------------------------------------------
# MAIN PARSER
# -------------------------------------------------------------

def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:

    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full_norm = _norm(full)

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None
    }

    raw = data["name"].strip().lower()

    # ---------------------------------------------------------
    # Pokédex mapping: p### or p###-FORM
    # ---------------------------------------------------------
    m_id = re.match(r"p\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)", raw)
    if m_id:
        pid = m_id.group(1)
        resolved = get_name_from_id(pid)
        print(f"[Pokédex-map] {data['name']} → {resolved}")
        data["name"] = resolved

    # PolygonX glitch: "p 7/9/10"
    elif re.match(r"p\s*[0-9]{1,2}/[0-9]{1,2}/[0-9]{1,2}", raw):
        data["name"] = f"Unknown ({raw})"

    # ---------------------------------------------------------
    # SHINY detection
    # ---------------------------------------------------------
    shiny_triggers = [" shiny", "✨", "⭐", "★", "🌟"]
    if any(t in full_norm for t in shiny_triggers):
        data["shiny"] = True

    # ---------------------------------------------------------
    # EVENT TYPE DETECTION
    # ---------------------------------------------------------

    # CATCH (must be before encounter)
    if "pokemon caught" in full_norm or "caught successfully" in full_norm:
        if data.get("shiny"):
            return "Shiny", data
        return "Catch", data

    # QUEST
    if "quest" in full_norm:
        return "Quest", data

    # ROCKET
    if any(x in full_norm for x in ["rocket", "invasion", "grunt", "leader", "giovanni"]):
        return "Rocket", data

    # RAID / MAX
    if "raid" in full_norm:
        return "Raid", data
    if "max battle" in full_norm:
        return "MaxBattle", data

    # HATCH
    if "hatch" in full_norm:
        return "Hatch", data

    # ENCOUNTER
    if "encounter" in full_norm or "encounter ping" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"

        return "Encounter", {
            "name": data["name"],
            "source": src
        }

    # FLED
    if any(x in full_norm for x in ["fled", "flee", "ran away"]):
        return "Fled", data

    return None, {}