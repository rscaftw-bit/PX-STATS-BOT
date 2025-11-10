# =========================================================
# PXstats v3.8.1 • parser.py
# Detects all encounter types & shiny properly
# + Pokédex ID → Name mapping (p###)
# =========================================================

import re
import unicodedata
from typing import Tuple, Optional
import discord

# ===== IV pattern =====
IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)


# ===== Normalizers =====
def _norm(s: str) -> str:
    """Lowercase + ASCII normalize"""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


# ===== Extractors =====
def _extract_name(desc: str) -> str:
    """Extract Pokémon name or p### ID from text"""
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .-]+|p\s*\d+)", desc, re.I)
    if m:
        return m.group(1).strip()
    return "?"


def _extract_iv(desc: str):
    """Extract IV triple (A/D/S)"""
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# ===== Main Parser =====
def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """Parses a PolygonX embed and returns (event_type, data)"""
    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full_norm = _norm(full)

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None
    }

    # ===== Pokédex ID → Name mapping =====
    from PXstats.pokedex import get_name_from_id
    if data["name"]:
        match = re.search(r"\bp\s*(\d+)\b", data["name"], re.IGNORECASE)
        if match:
            pid = int(match.group(1))
            data["name"] = get_name_from_id(pid)

    # ===== Shiny detection =====
    shiny_triggers = [" shiny", "✨", "⭐", "★", "🌟"]
    if any(t in full.lower() for t in shiny_triggers):
        data["shiny"] = True

    # ===== Catch / Shiny =====
    if "caught successfully" in full_norm or "pokemon caught" in full_norm:
        if data.get("shiny"):
            return "Shiny", data
        return "Catch", data

    # ===== Quest encounter =====
    if "quest" in full_norm:
        return "Quest", data

    # ===== Rocket encounters =====
    if any(k in full_norm for k in ["rocket", "invasion", "grunt", "leader", "giovanni"]):
        return "Rocket", data

    # ===== Raid / Max battle =====
    if "raid" in full_norm:
        return "Raid", data
    if "max battle" in full_norm:
        return "MaxBattle", data

    # ===== Hatch =====
    if "hatch" in full_norm:
        return "Hatch", data

    # ===== Wild / Incense / Lure encounter =====
    if "encounter" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"
        return "Encounter", {"name": data["name"], "source": src}

    # ===== Fled =====
    if any(k in full_norm for k in ["fled", "flee", "ran away"]):
        return "Fled", data

    # ===== Default =====
    return None, {}
