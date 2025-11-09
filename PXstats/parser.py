# parser.py — v3.6 (2025-11-09)
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

'data' bevat minstens: name, iv (tuple of None), level, cp, optioneel 'source' en 'shiny'.
"""

from __future__ import annotations
import re
import unicodedata
from typing import Tuple, Optional, Dict, Any
from utils import translate_pnumber


# ---------------- helpers ----------------

def _norm(s: Optional[str]) -> str:
    """Lowercase, strip en verwijder accenten voor robuuste matching."""
    return unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode().lower().strip()

def _extract_basic_fields(text: str) -> Dict[str, Any]:
    """
    Parse vrijetekst voor velden:
    - Pokemon: <naam> (…)
    - IV: a/b/c
    - Level: n
    - CP: nnnn
    """
    data: Dict[str, Any] = {"name": None, "iv": None, "level": None, "cp": None}

    # Pokemon-naam (knip alles na '(' af)
    m = re.search(r"pokemon:\s*([^\n\r(]+)", text, re.I)
    if m:
        raw = m.group(1).strip()
        data["name"] = translate_pnumber(raw)

    # IV
    m = re.search(r"\biv\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", text, re.I)
    if m:
        try:
            data["iv"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass

    # Level
    m = re.search(r"\blevel\s*:\s*(\d{1,2})\b", text, re.I)
    if m:
        try:
            data["level"] = int(m.group(1))
        except Exception:
            pass

    # CP
    m = re.search(r"\bcp\s*:\s*(\d{1,5})\b", text, re.I)
    if m:
        try:
            data["cp"] = int(m.group(1))
        except Exception:
            pass

    return data


# ---------------- main ----------------

def parse_polygonx_embed(e) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Retourneert (event_type, data) of (None, None) als het geen relevant PolygonX-event lijkt.
    """
    # Ruwe velden
    title_raw: str = getattr(e, "title", "") or ""
    desc: str = getattr(e, "description", "") or ""
    fields_blob = "\n".join(f"{(f.name or '')}\n{(f.value or '')}" for f in getattr(e, "fields", []))

    # Voor matching
    title = _norm(title_raw)
    full_text_raw = f"{title_raw}\n{desc}\n{fields_blob}"
    full_norm = _norm(full_text_raw)

    data = _extract_basic_fields(full_text_raw)

    # --- sterke shiny-detectie op RAW tekst (emoji blijven behouden) ---
    shiny_triggers = [" shiny", "shiny ✨", "shiny!", "⭐", "✨"]
    is_shiny = any(t in full_text_raw.lower() for t in shiny_triggers)
    if is_shiny:
        data["shiny"] = True

    # 1) CATCH / SHINY
    # PolygonX: "Pokemon caught successfully!"
    if "pokemon caught successfully" in title:
        evt = "Shiny" if is_shiny else "Catch"
        if is_shiny:
            print(f"[PARSE] SHINY DETECTED: {data.get('name')} IV={data.get('iv')}")
        else:
            print(f"[PARSE] CATCH: {data.get('name')} IV={data.get('iv')}")
        return evt, data

    # 2) ROCKET / INVASION
    # "Invasion Encounter!" of tekst bevat rocket/leader/giovanni/grunt
    if ("invasion encounter" in title) or any(k in full_norm for k in [" rocket", "grunt", "leader", "giovanni"]):
        data["source"] = "rocket"
        print(f"[PARSE] ROCKET: {data.get('name')}")
        return "Rocket", data

    # 3) QUEST
    # "Quest Encounter!"
    if "quest encounter" in title or " quest " in full_norm:
        data["source"] = "quest"
        print(f"[PARSE] QUEST: {data.get('name')}")
        return "Quest", data

    # 4) RAID
    # "Complete Raid Battle Encounter!"
    if ("complete raid battle encounter" in title) or (" raid " in full_norm and "battle encounter" in full_norm):
        data["source"] = "raid"
        print(f"[PARSE] RAID: {data.get('name')}")
        return "Raid", data

    # 5) MAX BATTLE (incl. Bread Battle variant)
    # "Complete Max Battle Encounter!" of "Complete Bread Battle Encounter!"
    if (
        "complete max battle encounter" in title
        or "complete bread battle encounter" in title
        or ("complete" in full_norm and "battle encounter" in full_norm and "raid" not in full_norm)
    ):
        data["source"] = "maxbattle"
        print(f"[PARSE] MAXBATTLE: {data.get('name')}")
        return "MaxBattle", data

    # 6) WILD ENCOUNTER
    # "Encounter Ping!" / "Wild Encounter!" / generieke "<…> Encounter!" zonder raid/quest/battle
    if (
        "encounter ping" in title
        or "wild encounter" in full_norm
        or (" encounter!" in title and all(k not in full_norm for k in ["quest", "raid", "battle"]))
    ):
        data["source"] = "wild"
        print(f"[PARSE] ENCOUNTER (wild): {data.get('name')}")
        return "Encounter", data

    # 7) HATCH
    if " hatch" in full_norm or "hatched" in full_norm:
        print(f"[PARSE] HATCH: {data.get('name')}")
        return "Hatch", data

    # 8) FLED
    if any(k in full_norm for k in [" flee", " fled", " run away"]):
        print(f"[PARSE] FLED: {data.get('name')}")
        return "Fled", data

    # Geen match
    return None, None
