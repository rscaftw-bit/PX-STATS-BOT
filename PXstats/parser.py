# PXstats • parser.py (FINAL)
# - p### & p###-FORM mapping via pokedex.py
# - Detects shiny and stores data["shiny"] = True
# - Returns ONE event for shiny catches: type = "Catch", shiny = True
# - Supports: Wild / Quest / Raid / Rocket / MaxBattle / Hatch / Fled / Encounter Ping

import re
import unicodedata
from typing import Tuple, Optional
import discord

# Regex for IV triple
IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)


# =============== Helpers ===============

def _norm(s: str) -> str:
    """Normalize to lowercase ASCII string."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _extract_name(desc: str) -> str:
    """
    Extract Pokémon name or p### ID pattern from the raw embed text.

    Examples it catches:
      Pokemon: Turtwig (387:688:0:1)
      Pokemon: p785:3130:0:3
      Pokemon: p487-O
    """
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .-]+|p\s*\d+[A-Za-z0-9\-:]*)", desc, re.I)
    if m:
        return m.group(1).strip()
    return "?"


def _extract_iv(desc: str):
    """Extract IV triple (A/D/S) if present."""
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# =============== Main parser ===============

def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """
    Parse a PolygonX embed into (event_type, data).

    event_type is one of:
      "Catch", "Quest", "Rocket", "Raid", "MaxBattle",
      "Hatch", "Encounter", "Fled"
    For shiny catches:
      type = "Catch" AND data["shiny"] = True
    """
    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full_norm = _norm(full)

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None  # nog niet gebruikt, maar kan later
    }

    # -------- Pokédex ID → Name mapping (incl. forms) --------
    # uses pokedex_full.json via PXstats.pokedex.get_name_from_id
    from PXstats.pokedex import get_name_from_id

    if data["name"]:
        raw = data["name"].strip().lower()
        # matches:
        #   p785
        #   p 785
        #   p487-o
        #   p1024-t
        #   p785:3130:0:3   (pakt "785" stuk)
        pid_match = re.search(r"[pP]\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)", raw)
        if pid_match:
            pid = pid_match.group(1)
            resolved = get_name_from_id(pid)
            print(f"[Pokedex-map] {data['name']} → {resolved}")
            data["name"] = resolved

    # -------- Shiny detection (flag only) --------
    shiny = False
    lower_full = full.lower()
    if (
        "shiny" in lower_full
        or "shiny" in title.lower()
        or any(sym in full for sym in ["✨", "⭐", "★", "🌟"])
    ):
        shiny = True

    data["shiny"] = shiny

    # -------- Event classification --------
    event_type: Optional[str] = None

    # Catch (shiny of niet) → altijd type "Catch"
    if "caught successfully" in full_norm or "pokemon caught" in full_norm:
        event_type = "Catch"

    # Encounter Ping! (wordt ook Encounter, maar met shiny-flag indien shiny)
    elif "encounter ping" in full_norm or "encounter!" in full_norm:
        event_type = "Encounter"

    # Quest
    elif "quest" in full_norm:
        event_type = "Quest"

    # Rocket encounters (grunt / leader / giovanni / invasion)
    elif any(k in full_norm for k in ["rocket", "grunt", "leader", "invasion", "giovanni"]):
        event_type = "Rocket"

    # Raid / Max battle
    elif "raid" in full_norm:
        event_type = "Raid"
    elif "max battle" in full_norm:
        event_type = "MaxBattle"

    # Egg hatch
    elif "hatch" in full_norm:
        event_type = "Hatch"

    # Generic encounter (wild / incense / lure)
    elif "encounter" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"
        data["source"] = src
        event_type = "Encounter"

    # Fled / ran away
    elif any(k in full_norm for k in ["fled", "flee", "ran away"]):
        event_type = "Fled"

    if not event_type:
        return None, {}

    return event_type, data