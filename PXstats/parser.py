# PXstats • parser.py (FULL FINAL VERSION)
# Supports:
# - p### and p###-F forms
# - All PolygonX Catch/Encounter types
# - Shiny detection
# - Wild / Quest / Raid / Rocket / MaxBattle
# - Handles accents and normalizes fields

import re
import unicodedata
from typing import Tuple, Optional
import discord

# Regex for IV triple
IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)

# ================================
# Normalizer
# ================================
def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower().strip()


# ================================
# Extract name (raw)
# ================================
def _extract_name(desc: str) -> str:
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .-]+|p\s*\d+[A-Za-z0-9\-]*)", desc, re.I)
    if m:
        return m.group(1).strip()
    return "?"


# ================================
# Extract IV
# ================================
def _extract_iv(desc: str):
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# ================================
# MAIN PARSER
# ================================
def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """Parses a PolygonX embed into (event_type, data)"""

    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)

    full_norm = _norm(full)

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None
    }

    # -----------------------------------------
    # Pokédex ID → NAME mapping (supports forms)
    # -----------------------------------------
    from PXstats.pokedex import get_name_from_id

    if data["name"]:
        raw = data["name"].strip().lower()

        # Matches:
        # p785
        # p 785
        # p487-o
        # p1024-t
        pid_match = re.search(r"[pP]\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)", raw)
        if pid_match:
            pid = pid_match.group(1)
            resolved = get_name_from_id(pid)
            print(f"[Pokedex-map] {data['name']} → {resolved}")
            data["name"] = resolved

    # -----------------------------------------
    # SHINY detection
    # -----------------------------------------
    shiny_triggers = [" shiny", "✨", "⭐", "★", "🌟"]
    if any(t in full.lower() for t in shiny_triggers):
        data["shiny"] = True

    # -----------------------------------------
    # Catch / Shiny
    # -----------------------------------------
    if "caught successfully" in full_norm or "pokemon caught" in full_norm:
        if data.get("shiny"):
            return "Shiny", data
        return "Catch", data

    # -----------------------------------------
    # Quest
    # -----------------------------------------
    if "quest" in full_norm:
        return "Quest", data

    # -----------------------------------------
    # Rocket
    # -----------------------------------------
    if any(k in full_norm for k in ["rocket", "grunt", "leader", "invasion", "giovanni"]):
        return "Rocket", data

    # -----------------------------------------
    # Raid / Max battle
    # -----------------------------------------
    if "raid" in full_norm:
        return "Raid", data
    if "max battle" in full_norm:
        return "MaxBattle", data

    # -----------------------------------------
    # Hatch
    # -----------------------------------------
    if "hatch" in full_norm:
        return "Hatch", data

    # -----------------------------------------
    # Encounter (wild/lure/incense)
    # -----------------------------------------
    if "encounter" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"
        return "Encounter", {"name": data["name"], "source": src}

    # -----------------------------------------
    # Flee / fled
    # -----------------------------------------
    if any(k in full_norm for k in ["fled", "flee", "ran away"]):
        return "Fled", data

    return None, {}