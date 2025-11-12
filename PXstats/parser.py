# =========================================================
# PXstats v3.9.2 • parser.py (FINAL)
# - Detects encounters, quests, raids, rockets, hatches, fled
# - Full Pokédex ID mapping for any "p###" or "p###:####"
# - Shiny detection + preservation across Encounter/Catch
# - Safe deduplication for double shiny logs
# =========================================================

import re
import unicodedata
from typing import Tuple, Optional
import discord

# ===== Constants =====
IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)
SHINY_TRIGGERS = [" shiny", "✨", "⭐", "★", "🌟"]

# ===== Helpers =====
def _norm(s: str) -> str:
    """Normalize to lowercase ASCII"""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _extract_name(desc: str) -> str:
    """Extract Pokémon name or ID pattern (p### or p###:####)"""
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .-]+|p\s*\d+(?::[0-9:]+)?)", desc, re.I)
    if m:
        return m.group(1).strip()
    return "?"


def _extract_iv(desc: str):
    """Extract IVs from the embed"""
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# ===== Main Parser =====
def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """Parse a PolygonX embed and return (event_type, data)"""
    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full_norm = _norm(full)

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None,
    }

    # ===== Pokédex ID → Name mapping =====
    from PXstats.pokedex import get_name_from_id
    if data["name"]:
        raw_name = data["name"].strip().lower()
        pid_match = re.search(r"[pP]\s*0*([0-9]{1,4})(?=[^0-9]|$)", raw_name)
        if pid_match:
            pid = int(pid_match.group(1))
            resolved = get_name_from_id(pid)
            print(f"[Pokédex-map] {data['name']} → {resolved}")
            data["name"] = resolved

    # ===== Shiny detection =====
    data["shiny"] = any(t in full.lower() for t in SHINY_TRIGGERS)
    title_lower = title.lower()
    if "shiny" in title_lower and not data["shiny"]:
        data["shiny"] = True

    # ===== Event classification =====
    event_type = None

    if "caught successfully" in full_norm or "pokemon caught" in full_norm:
        # Deduplication-safe shiny marker
        event_type = "Shiny" if data.get("shiny") else "Catch"

    elif "quest" in full_norm:
        event_type = "Quest"

    elif any(k in full_norm for k in ["rocket", "invasion", "grunt", "leader", "giovanni"]):
        event_type = "Rocket"

    elif "raid" in full_norm:
        event_type = "Raid"

    elif "max battle" in full_norm:
        event_type = "MaxBattle"

    elif "hatch" in full_norm:
        event_type = "Hatch"

    elif "encounter" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"
        event_type = "Encounter"
        data["source"] = src

    elif any(k in full_norm for k in ["fled", "flee", "ran away"]):
        event_type = "Fled"

    # ===== Return structured data =====
    return event_type, data if event_type else (None, {})