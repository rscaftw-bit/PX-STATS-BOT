# ======================================================
# PXstats • parser.py • 2025-11-13
# Shiny-proof, Raid-proof, Rocket-proof, Pokedex-proof
# ======================================================

import re
import unicodedata
from typing import Tuple, Optional
import discord

from PXstats.pokedex import get_name_from_id


# ======================================================
# Helpers
# ======================================================

IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()

def _extract_iv(desc: str):
    m = IV_TRIPLE.search(desc)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _extract_name(desc: str) -> str:
    # Normale lijn: "Pokemon: Necrozma (800:2717:0:3)"
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .0-9:-]+)", desc, re.I)
    if m:
        return m.group(1).strip()

    # Fallback: p### of p123-Form
    m = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", desc, re.I)
    if m:
        return f"p{m.group(1)}"

    return "?"


# ======================================================
# MAIN PARSER
# ======================================================

def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """
    Neemt één PolygonX embed en retourneert:
    (event_type, data: dict)
    event_type ∈ {Catch, Encounter, Raid, Rocket, MaxBattle, Quest, Hatch, Fled}
    """

    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full_norm = _norm(full)

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None,
        "shiny": False
    }

    # ===== Pokédex mapping (p### -> echte naam) =====
    raw_name = data["name"].strip().lower()
    pid_match = re.match(r"p\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)", raw_name)
    if pid_match:
        pid = pid_match.group(1)
        resolved = get_name_from_id(pid)
        if resolved:
            data["name"] = resolved

    # ===== SHINY detection (agressief, werkt voor alle formats) =====
    # Voorbeelden: "SHINY ✨", "Shiny ✨", "(Shiny)", alleen "✨", ...
    if any(k in full.upper() for k in ["SHINY", "✨", "⭐", "★", "🌟"]):
        data["shiny"] = True

    # ==================================================
    # TYPE DETECTIE
    # ==================================================

    # CATCH (altijd puur catch, shiny zit in data["shiny"])
    if "pokemon caught" in full_norm or "caught successfully" in full_norm:
        return "Catch", data

    # ROCKET / INVASION
    if any(x in full_norm for x in ["rocket", "invasion", "grunt", "leader", "giovanni"]):
        return "Rocket", data

    # RAID encounter
    if "complete raid battle encounter" in full_norm or "raid battle" in full_norm:
        return "Raid", data

    # MAX BATTLE encounter
    if "max battle" in full_norm:
        return "MaxBattle", data

    # QUEST encounter
    if "quest" in full_norm:
        return "Quest", data

    # HATCH
    if "hatch" in full_norm:
        return "Hatch", data

    # ENCOUNTER (wild/incense/lure)
    if "encounter ping" in full_norm or "encounter" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"
        return "Encounter", {**data, "source": src}

    # FLED
    if any(x in full_norm for x in ["fled", "flee", "ran away"]):
        return "Fled", data

    return None, {}