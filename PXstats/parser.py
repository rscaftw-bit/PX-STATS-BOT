# parser.py — v3.2 (2025-11-09)
import re, unicodedata
from typing import Tuple, Optional, Dict, Any
from utils import translate_pnumber

def _norm(s: Optional[str]) -> str:
    return unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode().lower().strip()

def _lines(s: Optional[str]):
    return [ln.strip() for ln in (s or "").splitlines() if ln.strip()]

def _extract_basic_fields(text: str) -> Dict[str, Any]:
    """Zoekt naam, IV, Level, CP in de tekst."""
    data: Dict[str, Any] = {"name": None, "iv": None, "level": None, "cp": None}

    # Pokémon naam
    m = re.search(r"pokemon:\s*([^) \n\r]+(?:[^\n\r]*?)?)", text, re.I)
    if m:
        raw = m.group(1).split("(")[0].strip()
        data["name"] = translate_pnumber(raw)

    # IV
    m = re.search(r"\biv\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", text, re.I)
    if m:
        try:
            data["iv"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except:
            pass

    # Level
    m = re.search(r"\blevel\s*:\s*(\d{1,2})\b", text, re.I)
    if m:
        try:
            data["level"] = int(m.group(1))
        except:
            pass

    # CP
    m = re.search(r"\bcp\s*:\s*(\d{1,5})\b", text, re.I)
    if m:
        try:
            data["cp"] = int(m.group(1))
        except:
            pass

    return data

def parse_polygonx_embed(e) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Zet PolygonX embed om naar (event_type, data)
    Mogelijke events: Catch, Shiny, Encounter, Quest, Raid, MaxBattle, Rocket, Hatch, Fled
    """
    title = _norm(getattr(e, "title", ""))
    desc  = getattr(e, "description", "") or ""
    fields_blob = "\n".join(f"{(f.name or '')}\n{(f.value or '')}" for f in getattr(e, "fields", []))
    full_text = f"{e.title or ''}\n{desc}\n{fields_blob}"
    full_norm = _norm(full_text)

    data = _extract_basic_fields(full_text)

    # Detect shiny
    is_shiny = (" shiny" in full_norm) or ("✨" in full_text)

    # 1️⃣ Catch / Shiny
    if "pokemon caught successfully" in title:
        return ("Shiny" if is_shiny else "Catch", data)

    # 2️⃣ Rocket / Invasion
    if ("invasion encounter" in title) or any(k in full_norm for k in [" rocket", "grunt", "leader", "giovanni"]):
        data["source"] = "rocket"
        return ("Rocket", data)

    # 3️⃣ Quest
    if "quest encounter" in title or " quest " in full_norm:
        data["source"] = "quest"
        return ("Quest", data)

    # 4️⃣ Raid
    # Voorbeelden:
    # - "Complete Raid Battle Encounter!"
    if "complete raid battle encounter" in title or (" raid " in full_norm and "battle encounter" in full_norm):
        data["source"] = "raid"
        return ("Raid", data)

    # 5️⃣ Max Battle (incl. Bread Battle)
    if (
        "complete max battle encounter" in title
        or "complete bread battle encounter" in title
        or ("complete" in full_norm and "battle encounter" in full_norm and "raid" not in full_norm)
    ):
        data["source"] = "maxbattle"
        return ("MaxBattle", data)

    # 6️⃣ Wild encounter
    if "encounter ping" in title or "wild encounter" in full_norm or (" encounter!" in title and "quest" not in full_norm and "raid" not in full_norm and "battle" not in full_norm):
        data["source"] = "wild"
        return ("Encounter", data)

    # 7️⃣ Hatch
    if " hatch" in full_norm or "hatched" in full_norm:
        return ("Hatch", data)

    # 8️⃣ Fled
    if any(k in full_norm for k in [" flee", " fled", " run away"]):
        return ("Fled", data)

    return (None, None)
