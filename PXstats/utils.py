# PXstats v3.8 – utils.py
# Shared helpers + Pokedex

import os, json, time
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Brussels")

def _fmt_when(ts: float, style="f"):
    return f"<t:{int(ts)}:{style}>"

def last_24h():
    if not os.path.exists("events.json"): return []
    with open("events.json","r",encoding="utf-8") as f:
        data = json.load(f)
    cutoff = time.time() - 86400
    return [e for e in data if e["ts"] >= cutoff]

# ===== POKEDEX =====
POKEDEX_FILE = "pokedex.json"

def init_pokedex():
    dex = {}
    if os.path.exists(POKEDEX_FILE):
        with open(POKEDEX_FILE,"r",encoding="utf-8") as f:
            dex = json.load(f)
    if len(dex) < 1025:
        print("[POKEDEX] generating full 1–1025")
        for n in range(1, 1026):
            if str(n) not in dex:
                dex[str(n)] = f"Pokemon {n}"
        dex["808"] = "Meltan"; dex["809"] = "Melmetal"; dex["999"] = "Gimmighoul"; dex["1000"] = "Gholdengo"; dex["1025"] = "Pecharunt"
        with open(POKEDEX_FILE,"w",encoding="utf-8") as f:
            json.dump(dex,f,indent=2,ensure_ascii=False)
    return dex

