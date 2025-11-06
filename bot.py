# --- keep-alive voor Render ---
import threading, http.server, socketserver

PORT = 8080
Handler = http.server.SimpleHTTPRequestHandler

def run_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_server, daemon=True).start()
# --- end keep-alive ---

import os, time, json
from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from discord.ui import View, Button

# 🔹 Laad tokens vanuit Render environment
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
DATA_FILE = "stats.json"

# --- Helpers ---
def load_data():
    return json.load(open(DATA_FILE, "r", encoding="utf-8")) if os.path.exists(DATA_FILE) else {"events":[]}

def save_data(d):
    json.dump(d, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ✅ Belangrijk: intents toestaan om berichten te lezen
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def now(): return datetime.now(timezone.utc)
def last24(): return now()-timedelta(hours=24), now()
def link(gid,cid,mid): return f"https://discord.com/channels/{gid}/{cid}/{mid}"
def fmd(dt): return dt.strftime("%m/%d/%y %H:%M")

# --- Data & Embed functies ---
def gather():
    s,e = last24(); S,E = s.timestamp(), e.timestamp()
    ev = [x for x in load_data()["events"] if S<=x["ts"]<=E]
    encounters = sum(1 for x in ev if x["type"]!="Catch")
    catches = sum(1 for x in ev if x["type"]=="Catch")
    shinies = sum(1 for x in ev if x.get("is_shiny"))
    latest_c = [x for x in sorted(ev,key=lambda x:x["ts"],reverse=True) if x["type"]=="Catch"][:5]
    latest_s = [x for x in sorted(ev,key=lambda x:x["ts"],reverse=True) if x.get("is_shiny")][:5]
    bd_keys = ["Encounter","Lure","Incense","Max Battle","Quest","Rocket Battle","Raid","Hatch"]
    bd = {k:0 for k in bd_keys}
    for x in ev:
        if x["type"] in bd: bd[x["type"]]+=1
    since = fmd(datetime.fromtimestamp(min([x["ts"] for x in ev]), tz=timezone.utc)) if ev else "—"
    return encounters,catches,shinies,bd,latest_c,latest_s,since,fmd(e)

def lines(items):
    if not items: return "—"
    out=[]
    for x in items:
        nm=x.get("name") or "Unknown"
        iv=x.get("iv"); ivtxt=f"{int(round(iv*100))}%" if isinstance(iv,(int,float)) else ""
        dt=datetime.fromtimestamp(x["ts"], tz=timezone.utc)
        lnk = link(x["gid"],x["cid"],x["mid"]) if x.get("mid") else ""
        stamp=f"[{fmd(dt)}]({lnk})" if lnk else fmd(dt)
        shiny=" ✨" if x.get("is_shiny") else ""
        out.append(f"{nm} {ivtxt}{shiny} ({stamp})".strip())
    return "\n".join(out)

def build_embed():
    encounters,catches,shinies,bd,lc,ls,since,until = gather()
    em = discord.Embed(title="📊 Today’s Stats (Last 24h)", colour=discord.Colour.from_rgb(43,45,49))
    em.description = f"**Encounters**\n{encounters}\n\n**Catches**\n{catches}\n\n**Shinies**\n{shinies}"
    em.add_field(
        name="Event breakdown",
        value="\n".join([f"{k}: {bd[k]}" for k in ["Encounter","Lure","Incense","Max Battle","Quest","Rocket Battle","Raid","Hatch"]]),
        inline=False
    )
    em.add_field(name="🕓 Latest Catches", value=lines(lc), inline=False)
    em.add_field(name="✨ Latest Shinies", value=lines(ls), inline=False)
    em.set_footer(text=f"Since {since} • Today at {until}")
    return em

# --- Discord Commands ---
class SummaryView(View):
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, custom_id="refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await interaction.message.edit(embed=build_embed(), view=self)

@tree.command(name="log", description="Log een mock event")
@app_commands.describe(type="Encounter/Lure/Incense/Quest/Rocket Battle/Raid/Hatch/Max Battle/Catch",
                       name="Naam (bv. Pokémon)", iv="IV in % (0-100) bij Catch", shiny="Shiny ja/nee")
async def log(inter: discord.Interaction, type: str, name: str=None, iv: float=None, shiny: bool=False):
    await inter.response.defer(ephemeral=True)
    msg = await inter.channel.send(
        f"Logged: **{type}**{f' • {name}' if name else ''}{f' • IV {iv:.0f}%' if (iv and type=='Catch') else ''}{' • ✨Shiny' if shiny else ''}"
    )
    d = load_data()
    d["events"].append({
        "type": type, "name": name,
        "iv": (iv/100.0) if (iv and type=="Catch") else None,
        "is_shiny": bool(shiny),
        "ts": time.time(),
        "gid": inter.guild_id, "cid": inter.channel_id, "mid": msg.id
    })
    save_data(d)
    await inter.followup.send("✅ Event gelogd.", ephemeral=True)

@tree.command(name="summary", description="Toon/refresh de 24u stats")
async def summary(inter: discord.Interaction):
    await inter.response.defer()
    ch = client.get_channel(CHANNEL_ID) if CHANNEL_ID else inter.channel
    await ch.send(embed=build_embed(), view=SummaryView())
    await inter.followup.send("📊 Summary geplaatst.", ephemeral=True)

# --- Events ---
@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user} | Slash commands gesynchroniseerd.")

@client.event
async def on_message(msg):
    # Enkel reageren op berichten van de PolygonX webhook
    if msg.author.bot and "caught Pokémon" in msg.content.lower():
        name = "Unknown"
        iv = None
        shiny = "✨" in msg.content or "shiny" in msg.content.lower()

        # probeer naam & IV te ontleden
        try:
            parts = msg.content.split("caught Pokémon: ")[1]
            name = parts.split("•")[0].strip()
            if "IV" in msg.content:
                iv_part = msg.content.split("IV")[1].split("%")[0]
                iv = float(iv_part.strip()) / 100
        except Exception as e:
            print("⚠️ Kon bericht niet parsen:", e)

        # opslaan in stats.json
        d = load_data()
        d["events"].append({
            "type": "Catch",
            "name": name,
            "iv": iv,
            "is_shiny": shiny,
            "ts": time.time(),
            "gid": msg.guild.id if msg.guild else 0,
            "cid": msg.channel.id,
            "mid": msg.id
        })
        save_data(d)
        print(f"✅ Auto-logged catch: {name} ({iv*100 if iv else '?'}%) {'✨' if shiny else ''}")

# --- Start de bot ---
client.run(TOKEN)
