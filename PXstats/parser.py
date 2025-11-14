# PXstats v4.1 • parser.py
# Robust PolygonX embed parser:
#  - Distinguishes Encounter / Catch / Fled
#  - Detects shiny from text + emojis
#  - Maps Pokédex ids (p###, p###-FORM) to names
#  - Extracts IV triples

from __future__ import annotations

import re
import unicodedata
from typing import Tuple, Optional

import discord

from PXstats.pokedex import get_name_from_id

IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def _norm(s: str) -> str:
    """Normalize to ASCII lowercase for easy matching."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _extract_name(full: str) -> str:
    """Extract Pokémon name or p### code from the raw embed text."""
    # Typical line: 'Pokemon: Necrozma (800:2717:0:3)'
    m = re.search(r"Pokemon:\s*([A-Za-zÀ-ÿ' .0-9:-]+)", full, re.I)
    if m:
        name = m.group(1).strip()
        # cut off after '(' or newline
        name = name.split("\n")[0]
        if "(" in name:
            name = name.split("(")[0].strip()
        return name

    # Fallback: look for 'p123' style ids
    m = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", full, re.I)
    if m:
        return f"p{m.group(1)}"

    return "?"


def _extract_iv(full: str):
    m = IV_TRIPLE.search(full)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _is_shiny(full: str) -> bool:
    # Raw text check keeps emojis
    if "✨" in full or "⭐" in full or "★" in full or "🌟" in full:
        return True
    low = full.lower()
    if "shiny" in low:
        return True
    return False


# --------------------------------------------------
# Main parser
# --------------------------------------------------
def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """Parse a PolygonX embed and return (event_type, data).

    event_type is one of: 'Encounter', 'Catch', 'Fled', or None.
    data always at least contains: name, iv, source?, shiny?
    """
    title = e.title or ""
    desc = e.description or ""
    field_text = "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full = f"{title}\n{desc}\n{field_text}"

    title_norm = _norm(title)
    full_norm = _norm(full)

    # Base data
    name_raw = _extract_name(full)
    iv = _extract_iv(full)
    shiny = _is_shiny(full)

    # Pokédex mapping for p### names
    resolved_name = name_raw
    m_id = re.match(r"p\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)", name_raw.strip(), re.I)
    if m_id:
        code = m_id.group(1)
        resolved_name = get_name_from_id(code)
    elif re.match(r"p\s*[0-9]{1,2}/[0-9]{1,2}/[0-9]{1,2}", name_raw.strip(), re.I):
        # PolygonX glitch: 'p 7/9/10'
        resolved_name = f"Unknown ({name_raw})"

    data = {
        "name": resolved_name,
        "iv": iv,
    }
    if shiny:
        data["shiny"] = True

    # Determine basic event type from the title
    event_type: Optional[str] = None

    if "pokemon caught successfully" in title_norm or "pokemon caught" in title_norm:
        event_type = "Catch"
    elif "encounter" in title_norm:
        event_type = "Encounter"
    elif any(k in full_norm for k in ["fled", "ran away", "flee"]):
        event_type = "Fled"

    if not event_type:
        return None, {}

    # For encounters, determine the source
    if event_type == "Encounter":
        source = "wild"
        if "incense" in full_norm:
            source = "incense"
        elif "lure" in full_norm:
            source = "lure"
        elif "quest" in full_norm:
            source = "quest"
        elif "raid" in full_norm:
            source = "raid"
        elif any(k in full_norm for k in ["rocket", "invasion", "grunt", "leader", "giovanni"]):
            source = "rocket"
        elif "max battle" in full_norm or "max raid" in full_norm:
            source = "max"
        data["source"] = source

    return event_type, data
