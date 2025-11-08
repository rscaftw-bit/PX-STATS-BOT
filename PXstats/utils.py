# utils.py
import os, json, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

# ---------- TIMEZONE (met fallback) ----------
try:
    from zoneinfo import ZoneInfo
    _tzkey = os.getenv("TIMEZONE", "Europe/Brussels")
    TZ = ZoneInfo(_tzkey)
except Exception as e:
    # Fallback op UTC als tzdata ontbreekt of key niet gevonden
    class _UTC:
        def __init__(self): pass
        def utcoffset(self, dt): return None
        def tzname(self, dt): return "UTC"
        def dst(self, dt): return None
    TZ = _UTC()
    print(f"[TZ] Warning: {e}. Falling back to UTC. Install 'tzdata' for '{os.getenv('TIMEZONE','Europe/Brussels')}'.")

# ---------- KEEPALIVE ----------
class _Healthz(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self,*a,**k): return

def start_keepalive():
    port = int(os.getenv("PORT","10000"))
    srv  = HTTPServer(("",port), _Healthz)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[KEEPALIVE] active on :{port}")

# ---------- EVENTS / STORAGE ----------
EVENTS    = deque(maxlen=10000)
SAVE_PATH = os.getenv("SAVE_PATH","events.json")

def add_event(t, p, ts=None):
    """Voegt event toe met anti-duplicate binnen 60s (zelfde type + naam)."""
    now  = ts or time.time()
    name = (p or {}).get("name")
    if name:
        # check laatste 50 events voor duplicaten
        for e in list(EVENTS)[-50:]:
            if e["type"] == t and e["data"].get("name") == name and abs(now - e["ts"]) < 60:
                return  # negeer duplicate
    EVENTS.append({"ts": now, "type": t, "data": p or {}})

def last_24h():
    cutoff = time.time() - 86400
    return [e for e in EVENTS if e["ts"] >= cutoff]

def save_events():
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(list(EVENTS), f, ensure_ascii=False)
        print(f"[SAVE] {len(EVENTS)} events -> {SAVE_PATH}")
    except Exception as e:
        print("[SAVE ERR]", e)

def load_events():
    try:
        if os.path.exists(SAVE_PATH):
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for e in data[-EVENTS.maxlen:]:
                    EVENTS.append(e)
            print(f"[LOAD] restored {len(EVENTS)} events")
    except Exception as e:
        print("[LOAD ERR]", e)

# ---------- POKEDEX (1–1025) ----------
POKEDEX_FILE = "pokedex.json"

def _titleize_pokeapi(name: str) -> str:
    """
    Converteer PokeAPI-naam naar nette weergave:
    - 'mr-rime' -> 'Mr. Rime'
    - 'sirfetchd' -> 'Sirfetch’d'
    - hyphens -> spaties, Title Case
    """
    if not name: return name
    raw = name.replace("-", " ").strip().title()

    # Uitzonderingen / speciale cases (minimaal gehouden, vooral Gen8+)
    exceptions = {
        "Mr Rime": "Mr. Rime",
        "Mr Mime": "Mr. Mime",
        "Mime Jr": "Mime Jr.",
        "Type Null": "Type: Null",
        "Sirfetchd": "Sirfetch’d",
        "Jangmo O": "Jangmo-o",
        "Hakamo O": "Hakamo-o",
        "Kommo O": "Kommo-o",
        "Porygon Z": "Porygon-Z",
        "Ho Oh": "Ho-Oh",
        "Flabebe": "Flabébé",
        "Farfetchd": "Farfetch’d",
        # Gen 9 speciale casing (chemische notatie blijft “Naclstack” oké)
    }
    return exceptions.get(raw, raw)

def _fetch_json(url: str, timeout: int = 12):
    try:
        with urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except (URLError, HTTPError) as e:
        print(f"[HTTP] {url} -> {e}")
        return None
    except Exception as e:
        print(f"[HTTP] {url} -> {e}")
        return None

def _augment_with_pokeapi(mapping: dict, upto: int = 1025) -> dict:
    """
    Vult ontbrekende IDs aan t/m 'upto' via PokeAPI (namen in nette vorm).
    Gebruikt 1 call naar de paginated listing, geen honderden per-ID calls.
    """
    data = _fetch_json("https://pokeapi.co/api/v2/pokemon?limit=10250")
    if not data or "results" not in data: 
        return mapping

    for item in data["results"]:
        name = item["name"]              # bv. 'mr-rime'
        url  = item["url"]               # bv. .../pokemon/866/
        # ID uit url parsen
        try:
            pid = int(url.strip("/").split("/")[-1])
        except:
            continue
        if pid <= upto and str(pid) not in mapping:
            mapping[str(pid)] = _titleize_pokeapi(name)
    return mapping

def _load_pokedex():
    """Laadt volledige Pokédex (1–1025) en cachet lokaal in pokedex.json."""
    # 1) Lokaal bestand eerst
    if os.path.exists(POKEDEX_FILE):
        try:
            with open(POKEDEX_FILE, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            # Zorg dat keys strings zijn
            mapping = {str(k): v for k, v in mapping.items()}
            print(f"[POKEDEX] Loaded {len(mapping)} entries")
            return mapping
        except Exception as e:
            print("[POKEDEX] Local load failed:", e)

    mapping: dict[str, str] = {}

    # 2) Gen1–7 (1..809) via fanzeyi (mooie Engelse namen)
    fj = _fetch_json("https://raw.githubusercontent.com/fanzeyi/pokemon.json/master/pokedex.json")
    if fj and isinstance(fj, list):
        for p in fj:
            try:
                pid = int(p.get("id"))
                if 1 <= pid <= 809:
                    mapping[str(pid)] = p["name"]["english"]
            except:
                continue

    # 3) Aanvullen met PokeAPI tot 1025 (namen netjes)
    mapping = _augment_with_pokeapi(mapping, upto=1025)

    # 4) Minimale “zekerheidjes” (mochten endpoints ooit haperen)
    safety_overrides = {
        "808": "Meltan",
        "809": "Melmetal",
        "810": "Grookey", "811": "Thwackey", "812": "Rillaboom",
        "813": "Scorbunny", "814": "Raboot", "815": "Cinderace",
        "816": "Sobble", "817": "Drizzile", "818": "Inteleon",
        "819": "Skwovet", "820": "Greedent",
        "898": "Calyrex",
        "899": "Wyrdeer", "900": "Kleavor", "901": "Ursaluna",
        "902": "Basculegion", "903": "Sneasler", "904": "Overqwil",
        "905": "Enamorus",
        "999": "Gimmighoul", "1000": "Gholdengo",
        "1025": "Pecharunt",
    }
    for k, v in safety_overrides.items():
        mapping.setdefault(k, v)

    # 5) Bewaren en loggen
    try:
        with open(POKEDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False)
        print(f"[POKEDEX] created local file with {len(mapping)} entries")
    except Exception as e:
        print("[POKEDEX] Save failed:", e)

    print(f"[POKEDEX] Loaded {len(mapping)} entries")
    return mapping

POKEDEX = _load_pokedex()

def translate_pnumber(name: str) -> str:
    """Converteert 'p###' (in welke spatie-/haakjesvariant dan ook) naar een nette naam."""
    if not name: return name
    # strip alles na '(' (bv. 'p755 (755:...)' -> 'p755')
    base = name.strip().split("(")[0].strip()
    import re
    m = re.search(r"\b[pP]\s*(\d{1,4})\b", base)
    if m:
        pid = m.group(1)
        return POKEDEX.get(pid, f"#{pid}")
    return name
