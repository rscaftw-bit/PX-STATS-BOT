# PXstats • parser.py • v4.1
# -----------------------------------------------
# - Parse PolygonX / Spidey embeds
# - Detects:
#   • Encounter / Quest / Raid / Rocket / Max / Hatch / Fled
#   • Catches (strikt op titel)
#   • Shiny flag
#   • Pokédex mapping voor p### en p###-FORM
# -----------------------------------------------

import re
import unicodedata
from typing import Tuple, Optional
import discord

from PXstats.pokedex import get_name_from_id


# ---------- helpers ----------

IV_TRIPLE = re.compile(r"IV\s*[:：]?\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", re.I)


def _norm(s: str) -> str:
    """Normalize text to ASCII lowercase."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _extract_name(text: str) -> str:
    """
    Haal de pokémonnaam of p###-id uit de tekst.
    Werkt met bv:
      Pokemon: Necrozma (800:2717:0:3)
      Pokemon: p785 (785:3130:0:3)
    """

    # Standaard "Pokemon: X" lijn
    m = re.search(r"pokemon:\s*([A-Za-z0-9À-ÿ' .:\-()]+)", text, re.I)
    if m:
        return m.group(1).strip()

    # Fallback voor "p 123" of "p123" of "p123-form"
    m = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", text, re.I)
    if m:
        return f"p{m.group(1)}"

    return "?"


def _extract_iv(text: str):
    """Return (atk, def, sta) of None."""
    m = IV_TRIPLE.search(text)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# ---------- main parser ----------

def parse_polygonx_embed(e: discord.Embed) -> Tuple[Optional[str], dict]:
    """
    Parse één PolygonX embed en geef (event_type, data) terug.

    Mogelijke event_type values:
      - "Encounter"
      - "Quest"
      - "Raid"
      - "Rocket"
      - "MaxBattle"
      - "Hatch"
      - "Catch"
      - "Fled"
      - None (onherkenbaar)
    """

    title = (e.title or "")
    desc = (e.description or "")
    full = f"{title}\n{desc}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields)

    full_norm = _norm(full)
    title_norm = _norm(title)
    full_lower = (full or "").lower()

    data = {
        "name": _extract_name(full),
        "iv": _extract_iv(full),
        "level": None
    }

    # ----- Pokédex mapping -----
    raw_name = data["name"].strip()
    raw_lower = raw_name.lower()

    # p### of p###-FORM
    m_id = re.search(r"\bp\s*0*([0-9]{1,4}(?:-[A-Za-z0-9]+)?)\b", raw_lower)
    if m_id:
        pid = m_id.group(1)  # bv "785" of "1017-c"
        resolved = get_name_from_id(pid)
        if resolved:
            print(f"[Pokédex-map] {data['name']} -> {resolved}")
            data["name"] = resolved
    # Glitch "p 7/9/10" enz
    elif re.match(r"p\s*[0-9]{1,2}/[0-9]{1,2}/[0-9]{1,2}", raw_lower):
        data["name"] = f"Unknown ({raw_name})"

    # ----- shiny detection -----
    if "shiny" in full_lower:
        data["shiny"] = True

    # ----- event type detection -----

    # 1) Fled / runaway
    if any(x in full_norm for x in ["fled", "ran away", "flee"]):
        return "Fled", data

    # 2) CATCH – strikt op titel, zodat encounters niet als catch tellen
    if title_norm.startswith("pokemon caught successfully"):
        return "Catch", data
    if "pokemon caught successfully" in title_norm:
        return "Catch", data
    if title_norm.strip() == "pokemon caught successfully":
        return "Catch", data

    # 3) Specifieke encounter types op titel
    if "complete raid battle encounter" in title_norm or (
        "raid" in title_norm and "encounter" in title_norm
    ):
        return "Raid", data

    if "invasion encounter" in title_norm:
        # Rocket encounter
        return "Rocket", data

    if "encounter ping" in title_norm:
        # gewone wild encounter (met evt incense/lure)
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"
        return "Encounter", {"name": data["name"], "source": src}

    # 4) Quest / Research
    if "quest" in full_norm or "research" in full_norm:
        return "Quest", data

    # 5) Rocket keywords buiten titel
    if any(x in full_norm for x in ["rocket", "grunt", "leader", "giovanni"]):
        return "Rocket", data

    # 6) Max battle
    if "max battle" in full_norm or "max raid" in full_norm:
        return "MaxBattle", data

    # 7) Hatch
    if "hatch" in full_norm:
        return "Hatch", data

    # 8) Generieke "encounter" fallback
    if "encounter" in full_norm:
        src = "wild"
        if "incense" in full_norm:
            src = "incense"
        elif "lure" in full_norm:
            src = "lure"
        return "Encounter", {"name": data["name"], "source": src}

    # Onbekend
    return None, {}
