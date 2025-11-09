# stats.py
VERSION = "stats-v3.7 • 2025-11-09"

import time, csv, io, discord
from discord.ui import View, Button
from utils import last_24h

def build_stats():
    rows = last_24h()  # filter: laatste 24u
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    # Encounters per bron (geflagd in data["source"])
    def enc(src):
        return sum(1 for r in rows if r["type"] == "Encounter" and r["data"].get("source") == src)

    s = dict(
        wild   = enc("wild"),
        lure   = enc("lure"),
        inc    = enc("incense"),
        max    = enc("maxbattle"),
        quest  = enc("quest"),
        rocket = enc("rocket"),
        raid   = enc("raid"),

        hatch   = by_type.get("Hatch", 0),
        fled    = by_type.get("Fled", 0),
        catches = by_type.get("Catch", 0),
    )

    # Shinies: 'Shiny' events + Catch(shiny=True)
    shiny_rows = [r for r in rows if r["type"] == "Shiny" or (r["type"] == "Catch" and r["data"].get("shiny"))]
    s["shinies"] = len(shiny_rows)

    # Rate-base = encounters via bronnen (excl. hatch) of #catches (whichever is larger)
    rate_base = s["wild"] + s["lure"] + s["inc"] + s["max"] + s["quest"] + s["rocket"] + s["raid"]
    s["enc_total"] = max(rate_base, s["catches"])
    s["runaways"]  = max(0, s["enc_total"] - s["catches"])

    s["catch_rate"] = (s["catches"] / s["enc_total"] * 100) if s["enc_total"] else 0.0
    s["shiny_rate"] = (s["shinies"] / max(s["catches"], 1) * 100)

    # 100% perfect
    s["perfect"] = sum(1 for r in rows if r["type"] == "Catch" and r["data"].get("iv") == (15, 15, 15))

    # Latest lists
    catches = [r for r in rows if r["type"] == "Catch"]
    catches.sort(key=lambda x: x["ts"], reverse=True)
    shiny_rows.sort(key=lambda x: x["ts"], reverse=True)
    s["latest_catches"] = catches[:5]
    s["latest_shinies"] = shiny_rows[:5]

    s["since"] = min((r["ts"] for r in rows), default=time.time())
    s["rows"]  = rows
    return s

def _fmt_when(ts, style="f"):
    return f"<t:{int(ts)}:{style}>"

def _fmt_iv(iv):
    return f"{iv[0]}/{iv[1]}/{iv[2]}" if (isinstance(iv, (list, tuple)) and len(iv) == 3) else ""

def _fmt_list(items, shiny=False):
    if not items:
        return "—"
    out = []
    for it in items:
        name = it["data"].get("name") or "?"
        iv   = _fmt_iv(it["data"].get("iv"))
        when = _fmt_when(it["ts"], "f")
        star = "✨ " if shiny else ""
        spacer = f" {iv}" if iv else ""
        out.append(f"{star}{name}{spacer} ({when})")
    return "\n".join(out)

def build_embed(mode="catch"):
    s = build_stats()
    emb = discord.Embed(title="📊 Today’s Stats (Last 24h)", color=discord.Color.blurple())

    # Top row
    emb.add_field(name="Encounters", value=str(s["enc_total"]), inline=True)
    emb.add_field(name="Catches",   value=str(s["catches"]),    inline=True)
    emb.add_field(name="Shinies",   value=str(s["shinies"]),    inline=True)

    # Breakdown per bron
    breakdown = (
        f"Wild: {s['wild']}\n"
        f"Lure: {s['lure']}\n"
        f"Incense: {s['inc']}\n"
        f"Max Battle: {s['max']}\n"
        f"Quest: {s['quest']}\n"
        f"Rocket Battle: {s['rocket']}\n"
        f"Raid: {s['raid']}\n"
        f"Runaways: {s['fled']}\n"
        f"Hatch: {s['hatch']}"
    )
    emb.add_field(name="**Event breakdown**", value=breakdown, inline=False)

    # Rates + perfect
    if mode == "catch":
        emb.add_field(name="🎯 Catch rate", value=f"{s['catch_rate']:.1f}%", inline=True)
    else:
        emb.add_field(name="✨ Shiny rate", value=f"{s['shiny_rate']:.3f}%", inline=True)
    emb.add_field(name="🏃 Runaways (est.)", value=str(s["runaways"]), inline=True)
    emb.add_field(name="🏆 Perfect 100 IV", value=str(s["perfect"]), inline=True)

    # Latest lists
    emb.add_field(name="🕓 Latest Catches", value=_fmt_list(s["latest_catches"]), inline=False)
    emb.add_field(name="✨ Latest Shinies", value=_fmt_list(s["latest_shinies"], shiny=True), inline=False)

    emb.set_footer(text=f"Now {_fmt_when(time.time(),'t')} • Rate base: {s['enc_total']} • {VERSION}")
    return emb

class SummaryView(View):
    def __init__(self, mode="catch"):
        super().__init__(timeout=180)
        self.mode = mode

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(embed=build_embed(self.mode), view=self)

    @discord.ui.button(label="Toggle Rate", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, button: Button):
        self.mode = "shiny" if self.mode == "catch" else "catch"
        await interaction.response.edit_message(embed=build_embed(self.mode), view=self)

# CSV export helper (slash command roept deze aan)
async def export_csv(interaction: discord.Interaction):
    rows = last_24h()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "type", "pokemon", "iv", "shiny"])
    for r in rows:
        iv = r["data"].get("iv")
        w.writerow([
            int(r["ts"]),
            r["type"],
            r["data"].get("name","?"),
            _fmt_iv(iv),
            "yes" if r["data"].get("shiny") else ""
        ])
    data = buf.getvalue().encode()
    await interaction.followup.send(
        file=discord.File(io.BytesIO(data), filename="pxstats_last24h.csv"),
        ephemeral=True
    )
