# stats.py
import time, csv, io, discord
from discord.ui import View, Button
from utils import last_24h, TZ

def build_stats():
    rows = last_24h()
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    enc=lambda s:sum(1 for r in rows if r["type"]=="Encounter" and r["data"].get("source")==s)
    data=dict(
        wild=enc("wild"),lure=enc("lure"),inc=enc("incense"),max=enc("maxbattle"),
        raid=enc("raid"),quest=enc("quest"),rocket=enc("rocket"),
        fled=by_type.get("Fled",0),hatch=by_type.get("Hatch",0),
        catches=by_type.get("Catch",0),shinies=by_type.get("Shiny",0)
    )
    base=sum([data[k] for k in ["wild","lure","inc","max","raid","quest","rocket"]])
    data["enc_total"]=max(base,data["catches"])
    data["catch_rate"]=(data["catches"]/data["enc_total"]*100) if data["enc_total"] else 0
    data["shiny_rate"]=(data["shinies"]/max(data["catches"],1)*100)
    data["rows"]=rows
    return data

def build_embed(mode="catch"):
    s=build_stats()
    e=discord.Embed(title="📊 Today’s Stats (Last 24h)",color=discord.Color.blurple())
    e.add_field(name="Encounters",value=s["enc_total"])
    e.add_field(name="Catches",value=s["catches"])
    e.add_field(name="Shinies",value=s["shinies"])
    e.add_field(name="Breakdown",value=f"Wild {s['wild']} • Rocket {s['rocket']} • Raid {s['raid']}",inline=False)
    if mode=="catch": e.add_field(name="🎯 Catch rate",value=f"{s['catch_rate']:.1f}%")
    else: e.add_field(name="✨ Shiny rate",value=f"{s['shiny_rate']:.3f}%")
    e.set_footer(text=f"Now <t:{int(time.time())}:t> · Base {s['enc_total']}")
    return e

class SummaryView(View):
    def __init__(self, mode="catch"):
        super().__init__(timeout=180); self.mode=mode
    @discord.ui.button(label="Refresh",style=discord.ButtonStyle.primary)
    async def refresh(self,i,b): await i.response.edit_message(embed=build_embed(self.mode),view=self)
    @discord.ui.button(label="Toggle Rate",style=discord.ButtonStyle.secondary)
    async def toggle(self,i,b):
        self.mode="shiny" if self.mode=="catch" else "catch"
        await i.response.edit_message(embed=build_embed(self.mode),view=self)

async def export_csv(inter):
    rows=last_24h(); buf=io.StringIO(); w=csv.writer(buf)
    w.writerow(["timestamp","type","pokemon"])
    for r in rows: w.writerow([int(r["ts"]),r["type"],r["data"].get("name","?")])
    buf.seek(0)
    await inter.response.send_message(file=discord.File(io.BytesIO(buf.getvalue().encode()),"pxstats.csv"),ephemeral=True)
