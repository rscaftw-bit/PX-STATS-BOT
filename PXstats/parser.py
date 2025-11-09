# parser.py — v3.7 (2025-11-09) — shiny-proof + alle PolygonX varianten
from __future__ import annotations
import re, unicodedata
from typing import Tuple, Optional, Dict, Any
from utils import translate_pnumber

def _norm(s: Optional[str]) -> str:
    return unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode().lower().strip()

def _extract_basic_fields(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {"name": None, "iv": None, "level": None, "cp": None}

    m = re.search(r"pokemon:\s*([^\n\r(]+)", text, re.I)
    if m:
        raw = m.group(1).strip()
        data["name"] = translate_pnumber(raw)

    m = re.search(r"\biv\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", text, re.I)
    if m:
        try: data["iv"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except: pass

    m = re.search(r"\blevel\s*:\s*(\d{1,2})\b", text, re.I)
    if m:
        try: data["level"] = int(m.group(1))
        except: pass

    m = re.search(r"\bcp\s*:\s*(\d{1,5})\b", text, re.I)
    if m:
        try: data["cp"] = int(m.group(1))
        except: pass

    return data

def parse_polygonx_embed(e) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    title_raw: str = getattr(e, "title", "") or ""
    desc: str = getattr(e, "description", "") or ""
    fields_blob = "\n".join(f"{(f.name or '')}\n{(f.value or '')}" for f in getattr(e, "fields", []))

    title = _norm(title_raw)
    full_text_raw = f"{title_raw}\n{desc}\n{fields_blob}"
    full_norm = _norm(full_text_raw)

    data = _extract_basic_fields(full_text_raw)


    # 1) CATCH / SHINY
    if "pokemon caught successfully" in title:
        # behoud emoji's – niet normaliseren
        blob = (title_raw + " " + desc + " " + fields_blob)
        lower_blob = blob.lower()
        shiny_triggers = [" shiny", "shiny ✨", "shiny!", "⭐", "✨", "✦", "★", "🌟"]
        is_shiny = any(t in blob or t in lower_blob for t in shiny_triggers)

        if is_shiny:
            data["shiny"] = True
            print(f"[PARSE] SHINY DETECTED: {data.get('name')} IV={data.get('iv')} • L={data.get('level')}")
            return "Shiny", data

        print(f"[PARSE] CATCH: {data.get('name')} IV={data.get('iv')}")
        return "Catch", data


    # 2) ROCKET / INVASION
    if ("invasion encounter" in title) or any(k in full_norm for k in [" rocket", "grunt", "leader", "giovanni"]):
        data["source"] = "rocket"
        print(f"[PARSE] ROCKET: {data.get('name')}")
        return "Rocket", data

    # 3) QUEST
    if "quest encounter" in title or " quest " in full_norm:
        data["source"] = "quest"
        print(f"[PARSE] QUEST: {data.get('name')}")
        return "Quest", data

    # 4) RAID
    if ("complete raid battle encounter" in title) or (" raid " in full_norm and "battle encounter" in full_norm):
        data["source"] = "raid"
        print(f"[PARSE] RAID: {data.get('name')}")
        return "Raid", data

    # 5) MAX BATTLE (incl. Bread Battle)
    if (
        "complete max battle encounter" in title
        or "complete bread battle encounter" in title
        or ("complete" in full_norm and "battle encounter" in full_norm and "raid" not in full_norm)
    ):
        data["source"] = "maxbattle"
        print(f"[PARSE] MAXBATTLE: {data.get('name')}")
        return "MaxBattle", data

    # 6) WILD ENCOUNTER
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

    return None, None
