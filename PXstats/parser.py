# ======================================================
# PXstats • parser.py • 2025-11-13
# Detects encounter / catch / quest / raid / rocket / max
# + IV + shiny + Pokédex mapping
# ======================================================

from __future__ import annotations

import re
import unicodedata
from typing import Tuple, Optional

import discord

from PXstats.pokedex import get_name_from_id

IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _extract_name(desc: str) -> str:
    # Eerst: "Pokemon: Necrozma (xxx)"
    m = re.search(r"pokemon:\s*([A-Za-zÀ-ÿ' .0-9:-]+)", desc, re.I)
    if m:
        return m.group(1).strip()

    # Fallback: p### of p ###-FORM
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
    """Parses a PolygonX embed and returns (event_type, data)."""

    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)
    full_norm = _norm(full)

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None,
        "shiny": False,
    }

    # ---- Pokédex mapping p### → naam ----
    raw = data["name"].strip().lower()
    m_id = re.match(r"p\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)", raw)
    if m_id:
        pid = m_id.group(1)
        resolved = get_name_from_id(pid)
        print(f"[POKEDEX MAP] {data['name']} -> {resolved}")
        data["name"] = resolved

    # ---- Shiny detectie ----
    shiny_triggers_text = [" shiny"]
    shiny_triggers_emoji = ["✨", "⭐", "★", "🌟"]

    if any(t in full_norm for t in shiny_triggers_text) or any(t in full for t in shiny_triggers_emoji):
        data["shiny"] = True

    # ---- EVENT TYPE ----

    # Catch
    if "pokemon caught successfully" in full_norm or "pokemon caught" in full_norm:
        return "Catch", data

    # Quest
    if "quest" in full_norm:
        return "Quest", data

    # Rocket (invasion, grunt, leader, giovanni)
    if any(k in full_norm for k in ["rocket", "invasion", "grunt", "leader", "giovanni"]):
        return "Rocket", data

    # Raid / Max battle
    if "raid battle" in full_norm or "raid" in full_norm:
        return "Raid", data
    if "max battle" in full_norm:
        return "MaxBattle", data

    # Hatch
    if "hatch" in full_norm:
        return "Hatch", data

    # Encounter (wild/incense/lure)
    if "encounter ping" in full_norm or "encounter" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"
        return "Encounter", {"name": data["name"], "source": src}

    # Fled
    if any(k in full_norm for k in ["fled", "flee", "ran away"]):
        return "Fled", data

    return None, {}
