# utils.py — core utils: keepalive, storage, time, pokedex translation
import os, json, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

# ---------- time / tz ----------
TIMEZONE = os.getenv("TIMEZONE", "Europe/Brussels")
try:
    TZ = ZoneInfo(TIMEZONE)
except Exception:
    TZ = ZoneInfo("UTC")

# ---------- keepalive (Render) ----------
class _Healthz(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def log_message(self, *a, **k): return

def start_keepalive():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("", port), _Healthz)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[KEEPALIVE] active on :{port}")

# ---------- events storage ----------
SAVE_PATH = "events.json"
EVENTS: deque = deque(maxlen=100000)

def add_event(evt_type: str, data: dict, ts: Optional[float] = None):
    EVENTS.append({"ts": ts if ts is not None else time.time(), "type": evt_type, "data": data or {}})

def load_events():
    if not os.path.exists(SAVE_PATH):
        print("[LOAD] no events.json, starting fresh"); return
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cnt = 0
        for r in raw:
            d = r.get("data") or {}
            iv = d.get("iv")
            if isinstance(iv, list) and len(iv) == 3:
                d["iv"] = (iv[0], iv[1], iv[2])  # tuple-ize
            EVENTS.append({"ts": float(r.get("ts", time.time())), "type": r.get("type"), "data": d})
            cnt += 1
        print(f"[LOAD] {cnt} events from {SAVE_PATH}")
    except Exception as e:
        print("[LOAD ERR]", e)

def save_events():
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(list(EVENTS), f, ensure_ascii=False)
        print(f"[SAVE] {len(EVENTS)} events -> {SAVE_PATH}")
    except Exception as e:
        print("[SAVE ERR]", e)

def last_24h(hours: int = 24) -> List[Dict[str, Any]]:
    cutoff = time.time() - hours * 3600
    return [e for e in list(EVENTS) if float(e.get("ts", 0)) >= cutoff]

# ---------- Pokédex translation ----------
POKEDEX_PATH = "pokedex.json"
_PDEX: Dict[str, str] = {}

def _default_pokedex() -> Dict[str, str]:
    # Minimale basis; bestand wordt automatisch aangemaakt en je kan het zelf aanvullen
    base = {
        "808": "Meltan", "809": "Melmetal",
        "810": "Grookey","811":"Thwackey","812":"Rillaboom",
        "813":"Scorbunny","814":"Raboot","815":"Cinderace",
        "816":"Sobble","817":"Drizzile","818":"Inteleon",
        "819":"Skwovet","820":"Greedent",
        "894":"Regieleki","895":"Regidrago","896":"Glastrier","897":"Spectrier","898":"Calyrex",
        "999":"Gimmighoul","1000":"Gholdengo","1025":"Pecharunt"
    }
    return base

def _load_pokedex():
    global _PDEX
    if os.path.exists(POKEDEX_PATH):
        try:
            with open(POKEDEX_PATH, "r", encoding="utf-8") as f:
                _PDEX = json.load(f)
            print(f"[POKEDEX] loaded {len(_PDEX)} entries")
            return
        except Exception as e:
            print("[POKEDEX ERR]", e)
    _PDEX = _default_pokedex()
    try:
        with open(POKEDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(_PDEX, f, ensure_ascii=False)
        print(f"[POKEDEX] created local file with {len(_PDEX)} entries")
    except Exception as e:
        print("[POKEDEX SAVE ERR]", e)

_load_pokedex()

def translate_pnumber(raw: str) -> str:
    """
    - Laat normale namen ongemoeid (Pikachu -> Pikachu)
    - Converteert 'p861' / 'P 861' naar dex-naam indien bekend (anders 'p861' laten staan)
    """
    if not raw:
        return "?"
    s = raw.strip()
    m = None
    # p ### of P### varianten
    import re
    m = re.match(r"(?i)^\s*p\s*(\d{1,4})\s*$", s)
    if m:
        dex = m.group(1).lstrip("0")
        return _PDEX.get(dex, f"p{dex}")
    return s
