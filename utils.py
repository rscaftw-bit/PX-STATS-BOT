# utils.py
import os, json, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo
from collections import deque
from urllib.request import urlopen

TIMEZONE = os.getenv("TIMEZONE", "Europe/Brussels")
TZ = ZoneInfo(TIMEZONE)

# ------------------ KEEPALIVE ------------------
class _Healthz(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self,*a,**k): return

def start_keepalive():
    port=int(os.getenv("PORT","10000"))
    s=HTTPServer(("",port),_Healthz)
    threading.Thread(target=s.serve_forever,daemon=True).start()
    print(f"[KEEPALIVE] active on :{port}")

# ------------------ EVENTS / STORAGE ------------------
EVENTS = deque(maxlen=10000)
SAVE_PATH = os.getenv("SAVE_PATH","events.json")

def add_event(t, p, ts=None):
    """Voegt een event toe, met anti-duplicate check binnen 60s."""
    now = ts or time.time()
    name = (p or {}).get("name")
    if name:
        for e in list(EVENTS)[-50:]:  # check laatste 50 events
            if e["type"] == t and e["data"].get("name") == name and abs(now - e["ts"]) < 60:
                return  # negeer duplicate binnen 60s
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

# ------------------ POKEDEX ------------------
POKEDEX_FILE = "pokedex.json"

def _load_pokedex():
    """Laadt volledige Pokédex (1-1025). Cachet lokaal."""
    if os.path.exists(POKEDEX_FILE):
        with open(POKEDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    mapping = {}
    try:
        with urlopen("https://raw.githubusercontent.com/fanzeyi/pokemon.json/master/pokedex.json", timeout=10) as r:
            data = json.load(r)
        mapping = {str(p["id"]): p["name"]["english"] for p in data}
    except Exception as e:
        print("[POKEDEX DL ERR]", e)

    # Aanvulling tot 1025 (Gen 8-9)
    extra = {
        810:"Grookey",811:"Thwackey",812:"Rillaboom",813:"Scorbunny",814:"Raboot",815:"Cinderace",
        816:"Sobble",817:"Drizzile",818:"Inteleon",819:"Skwovet",820:"Greedent",
        894:"Regieleki",895:"Regidrago",896:"Glastrier",897:"Spectrier",898:"Calyrex",
        999:"Gimmighoul",1000:"Gholdengo",1025:"Pecharunt"
    }
    mapping.update({str(k):v for k,v in extra.items()})
    with open(POKEDEX_FILE,"w",encoding="utf-8") as f: json.dump(mapping,f,ensure_ascii=False)
    print(f"[POKEDEX] created local file with {len(mapping)} entries")
    return mapping

POKEDEX = _load_pokedex()

def translate_pnumber(name:str)->str:
    """Converteert 'p###' of 'p ### (...)' naar naam."""
    if not name: return name
    name = name.strip().split("(")[0].strip()
    import re
    m = re.search(r"\b[pP]\s*(\d{1,4})\b", name)
    if m:
        num = m.group(1)
        return POKEDEX.get(num, f"#{num}")
    return name
