# parser.py
import re, unicodedata
from utils import translate_pnumber

def _norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower().strip()

def _normalize_pname(name:str)->str:
    return re.sub(r"^p\s*(\d+)", r"p\1", name.strip(), flags=re.I)

def extract_name(embed):
    for f in getattr(embed, "fields", []):
        if "pokemon" in _norm(f.name):
            val = f.value.split("(")[0].strip()
            return translate_pnumber(_normalize_pname(val))
    if embed.description:
        m = re.search(r"Pokemon:\s*([A-Za-zÀ-ÿ' .-]+|p\s*\d+)", embed.description, re.I)
        if m:
            return translate_pnumber(_normalize_pname(m.group(1)))
    return "?"

def extract_iv(embed):
    text = (embed.description or "") + "".join(f"{f.name}{f.value}" for f in embed.fields)
    m = re.search(r"IV\s*:\s*(\d{1,2})/(\d{1,2})/(\d{1,2})", text)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None

def parse_polygonx_embed(e):
    """Geeft (type, data) terug voor PolygonX-embeds."""
    full = "\n".join([e.title or "", e.description or ""] + [f"{f.name}\n{f.value}" for f in e.fields]).lower()
    if not any(k in full for k in ["pokemon","caught","encounter","fled","flee","invasion","rocket"]):
        return (None,None)
    name, iv = extract_name(e), extract_iv(e)
    if any(k in full for k in ["rocket","invasion","grunt","giovanni","leader"]):
        return ("Rocket",{"name":name})
    if "shiny" in full and "caught" in full:
        return ("Shiny",{"name":name,"iv":iv})
    if "caught" in full:
        return ("Catch",{"name":name,"iv":iv})
    if "flee" in full or "fled" in full:
        return ("Fled",{"name":name})
    if "quest" in full:
        return ("Quest",{"name":name})
    if "raid" in full:
        return ("Raid",{"name":name})
    if "battle" in full and "encounter" in full and "rocket" not in full:
        return ("MaxBattle",{"name":name})
    if "hatch" in full:
        return ("Hatch",{"name":name})
    if "encounter" in full:
        src="wild"
        if "lure" in full: src="lure"
        elif "incense" in full: src="incense"
        return ("Encounter",{"name":name,"source":src})
    return (None,None)
