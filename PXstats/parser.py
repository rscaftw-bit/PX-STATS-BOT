# parser.py — v3.4 (2025-11-09)
"""
Zet PolygonX embeds om naar (event_type, data).

Event types:
- Catch, Shiny
- Encounter (wild)
- Quest
- Raid
- MaxBattle  (incl. 'Complete Bread Battle Encounter!')
- Rocket     (Invasion/Grunt/Leader/Giovanni)
- Hatch
- Fled

Data bevat minimaal: name, iv (tuple of None), level, cp, (optioneel) source.
"""

import re
import unicodedata
from typing import Tuple, Optional, Dict, Any
from utils import translate_pnumber


# ---------- helpers ----------
def _norm(s: Optional[str]) -> str:
    return unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode().lower().strip()

def _extract_basic_fields(text: str) -> Dict[str, Any]:
    """Zoekt naam, IV, Level, CP in de vrije tekst (title+description+fields)."""
    data: Dict[str, Any] = {"name": None, "iv": None, "level": None, "cp": None}

    # Pokémon naam (knip alles na '(' af). Voorbeelden:
    # - "Pokemon: p861 (861:3195:0:1)" -> 'p861' (wordt vertaald)
    # - "Pokemon: Grimer (88:73:0:2)"  -> 'Grimer'
    m = re.search(r"pokemon:\s*([^\n\r(]+)", text, re.I)
    if m:
        raw = m.group(1).strip()
        data["name"] = translate_pnumber(raw)

    m = re.search(r"\biv\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", text, re.I)
    if m:
        try:
            data["iv"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass

    m = re.search(r"\blevel\s*:\s*(\d{1,2})\b", text, re.I)
    if m:
        try:
            data["level"] = int(m.group(1))
        except Exception:
            pass

    m = re.search(r"\bcp\s*:\s*(\d{1,5})\b", text, re.I)
    if m:
        try:
            data["cp"] = int(m.group(1))
        except Exception:
            pass

    return data


# ---------- main ----------
def parse_polygonx_embed(e) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Retourneert (event_type, data) of (None, None) als het geen relevant PolygonX-event lijkt.
    """
    title_raw = getattr(e, "title", "") or ""
    desc = getattr(e, "description", "") or ""
    fields_blob = "\n".join(f"{(f.name or '')}\n{(f.value or '')}" for f in getattr(e, "fields", []))

    title = _norm(title_raw)
    full_text = f"{title_raw}\n{desc}\n{fields_blob}"
    full_norm = _norm(full_text)

    data = _extract_basic_fields(full_text)

    # --- Shiny detectie: robuust, kijkt in 'raw' zodat emoji niet wegvallen ---
    shiny_triggers = [" shiny", "shiny ✨", "shiny!", "⭐", "✨"]
    is_shiny = any(t in full_text.lower() for t in shiny_triggers)

    # 1) Catch / Shiny
    # PolygonX: "Pokemon caught successfully!"
    if "pokemon caught successfully" in title:
        return ("Shiny" if is_shiny else "Catch", data)

    # 2) Rocket / Invasion
    # "Invasion Encounter!" of tekst bevat rocket/leader/giovanni/grunt
    if ("invasion encounter" in title) or any(k in full_norm for k in [" rocket", "grunt", "leader", "giovanni"]):
        data["source"] = "rocket"
        return ("Rocket", data)

    # 3) Quest
    # "Quest Encounter!"
    if "quest encounter" in title or " quest " in full_norm:
        data["source"] = "quest"
        return ("Quest", data)

    # 4) Raid
    # "Complete Raid Battle Encounter!"
    if ("complete raid battle encounter" in title) or (" raid " in full_norm and "battle encounter" in full_norm):
        data["source"] = "raid"
        return ("Raid", data)

    # 5) Max Battle (incl. Bread Battle variant van PolygonX)
    # "Complete Max Battle Encounter!" of "Complete Bread Battle Encounter!"
    if (
        "complete max battle encounter" in title
        or "complete bread battle encounter" in title
        or ("complete" in full_norm and "battle encounter" in full_norm and "raid" not in full_norm)
    ):
        data["source"] = "maxbattle"
        return ("MaxBattle", data)

    # 6) Wild encounter
    # "Encounter Ping!" / "Wild Encounter!" / generieke "… Encounter!" zonder raid/quest/battle
    if (
        "encounter ping" in title
        or "wild encounter" in full_norm
        or (" encounter!" in title and all(k not in full_norm for k in ["quest", "raid", "battle"]))
    ):
        data["source"] = "wild"
        return ("Encounter", data)

    # 7) Hatch
    if " hatch" in full_norm or "hatched" in full_norm:
        return ("Hatch", data)

    # 8) Fled
    if any(k in full_norm for k in [" flee", " fled", " run away"]):
        return ("Fled", data)

    return (None, None)
