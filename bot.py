# --- keep-alive voor Render (web service free tier) ---
import threading, http.server, socketserver

PORT = 8080
Handler = http.server.SimpleHTTPRequestHandler
def run_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
threading.Thread(target=run_server, daemon=True).start()
# --- end keep-alive ---

import os, time, json, re
from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from discord.ui import View, Button

# -------- Environment / constants --------
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
DATA_FILE = "stats.json"

# -------- Helpers: storage --------
def load_data():
    return json.load(open(DATA_FILE, "r", encoding="utf-8")) if os.path.exists(DATA_FILE) else {"events": []}

def save_data(d):
    json.dump(d, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# -------- Discord setup (intents incl. message content) --------
intents = discord.Intents.default()
intents.message_content = True  # vereist + geactiveerd in Dev Portal
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# -------- Time / formatting --------
def now(): return datetime.now(timezone.utc)
def last24(): return now() - timedelta(hours=24), now()
def link(gid, cid, mid): return f"https://discord.com/channels/{gid}/{cid}/{mid}"
def fmd(dt): return dt.strftime("%m/%d/%y %H:%M")

# -------- Aggregation for embed --------
def gather():
    s, e = last24(); S, E = s.timestamp(), e.timestamp()
    ev = [x for x in load_data()["events"] if S <= x["ts"] <= E]

    encounters = sum(1 for x in ev if x["type"] not in ["Catch", "Reward"])
    catches    = sum(1 for x in ev if x["type"] == "Catch")
    shinies    = sum(1 for x in ev if x.get("is_shiny"))

    rewards    = [x for x in ev if x["type"] == "Reward"]
    total_candy = sum(x.get("count", 0) for x in rewards if "candy" in (x.get("name") or "").lower())

    latest_c = [x for x in sorted(ev, key=lambda x: x["ts"], reverse=True) if x["type"] == "Catch"][:5]
    latest_s = [x for x in sorted(ev, key=lambda x: x["ts"], reverse=True) if x.get("is_shiny")][:5]
    latest_r = sorted(rewards, key=lambda x: x["ts"], reverse=True)[:5]

    bd_keys = ["Encounter","Lure","Incense","Max Battle","Quest","Rocket Battle","Raid","Hatch","Reward"]
    bd = {k: 0 for k in bd_keys}
    for x in ev:
        if x["type"] in bd:
            bd[x["type"]] += 1

    since = fmd(datetime.fromtimestamp(min([x["ts"] for x in ev]), tz=timezone.utc)) if ev else "—"
    return encounters, catches, shinies, total_candy, bd, latest_c, latest_s, latest_r, since, fmd(e)

# -------- Embed builders --------
def lines(items):
    if not items:
        return "—"
    out = []
    for x in items:
        nm = x.get("name") or "Unknown"
        iv = x.get("iv"); ivtxt = f"{int(round(iv*100))}%" if isinstance(iv, (int, float)) else ""
        cnt = x.get("count"); cnttxt = f"x{cnt}" if cnt else ""
        dt = datetime.fromtimestamp(x["ts"], tz=timezone.utc)
        lnk = link(x["gid"], x["cid"], x["mid"]) if x.get("mid") else ""
        stamp = f"[{fmd(dt)}]({lnk})" if lnk else fmd(dt)
        shiny = " ✨" if x.get("is_shiny") else ""
        out.append(f"{nm} {ivtxt}{cnttxt}{shiny} ({stamp})".strip())
    return "\n".join(out)

def build_embed():
    encounters,catches,shinies,total_candy,bd,lc,ls,lr,since,until = gather()
    em = discord.Embed(title="📊 Today’s Stats (Last 24h)", colour=discord.Colour.from_rgb(43,45,49))
    em.description = (
        f"**Encounters**\n{encounters}\n\n"
        f"**Catches**\n{catches}\n\n"
        f"**Shinies**\n{shinies}\n\n"
        f"🍬 **Rare Candy earned**\n{total_candy}"
    )
    em.add_field(
        name="Event breakdown",
        value="\n".join([f"{k}: {bd[k]}" for k in bd.keys()]),
        inline=False
    )
    em.add_field(name="🕓 Latest Catches", value=lines(lc), inline=False)
    em.add_field(name="✨ Latest Shinies", value=lines(ls), inline=False)
    em.add_field(name="🍬 Recent Rewards", value=lines(lr), inline=False)
    em.set_footer(text=f"Since {since} • Today at {until}")
    return em

# -------- Commands --------
class SummaryView(View):
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, custom_id="refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        # Direct bijwerken; geen defer om double-ack te voorkomen
        try:
            await interaction.response.edit_message(embed=build_embed(), view=self)
        except discord.InteractionResponded:
            await interaction.message.edit(embed=build_embed(), view=self)

@tree.command(name="summary", description="Toon/refresh de 24u stats")
async def summary(inter: discord.Interaction):
    # Meteen ephemeral ack (voorkomt Unknown/Already acknowledged)
    try:
        await inter.response.send_message("📊 Summary wordt geplaatst…", ephemeral=True)
    except discord.InteractionResponded:
        pass

    ch = client.get_channel(CHANNEL_ID) if CHANNEL_ID else inter.channel
    await ch.send(embed=build_embed(), view=SummaryView())

# -------- Events --------
@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user} | Slash commands gesynchroniseerd.")

@client.event
async def on_message(msg):
    # Alleen bot/webhook-berichten analyseren (PolygonX webhook post als 'bot')
    if not msg.author.bot:
        return

    text = msg.content.lower()
    # Snel filtertje voor performance
    if not any(x in text for x in ["caught","encounter","hatch","raid","quest","battle","reward","candy","lure","incense","rocket"]):
        return

    # --- type-detectie op basis van PolygonX zinsdelen ---
    type_map = {
        "caught":               "Catch",
        "wild encounter":       "Encounter",
        "tappable encounter":   "Encounter",
        "incense encounter":    "Incense",
        "lure encounter":       "Lure",
        "quest encounter":      "Quest",
        "pokéstop encounter":   "Quest",
        "invasion encounter":   "Rocket Battle",
        "rocket":               "Rocket Battle",
        "raid battle":          "Raid",
        "battle rewards":       "Reward",
        "hatch":                "Hatch"
    }
    ev_type = next((v for k, v in type_map.items() if k in text), "Encounter")

    # --- naam/iv/shiny detectie ---
    name, iv, shiny = "Unknown", None, False
    shiny = ("✨" in msg.content) or ("shiny" in text)

    m_name = re.search(r"caught\s+pokémon:\s*([^\n•]*)", msg.content, re.I)
    if m_name:
        name = m_name.group(1).strip()

    m_iv = re.search(r"IV[:\s]+(\d{1,2}\.\d+|\d{1,3})%", msg.content)
    if m_iv:
        try:
            iv = float(m_iv.group(1)) / 100.0
        except:
            iv = None

    # --- Candy/Reward detectie ---
    # Voorbeelden die we willen vangen:
    # "Reward: 3 Rare Candy", "Reward: 1 Rare Candy XL", "You received 2x Rare Candy"
    if any(kw in text for kw in ["rare candy", "rare candy xl", "battle rewards", "reward:"]):
        # Forceer type Reward
        ev_type = "Reward"
        # Tel alle candy (Rare en XL)
        counts = re.findall(r"(\d+)\s*(?:x\s*)?(rare candy(?:\s*xl)?)", text)
        total = 0
        last_label = None
        for num, label in counts:
            total += int(num)
            last_label = label  # onthoud laatste label voor naam
        if total == 0:
            # fallback: losse “rare candy” zonder getal -> tel 1
            if "rare candy xl" in text:
                total, last_label = 1, "rare candy xl"
            elif "rare candy" in text:
                total, last_label = 1, "rare candy"

        name = "Rare Candy XL" if (last_label and "xl" in last_label) else "Rare Candy"

        d = load_data()
        d["events"].append({
            "type":  "Reward",
            "name":  name,
            "count": total,
            "ts":    time.time(),
            "gid":   msg.guild.id if msg.guild else 0,
            "cid":   msg.channel.id,
            "mid":   msg.id
        })
        save_data(d)
        print(f"🍬 Logged reward: {total}x {name}")
        return

    # --- Standaard event loggen ---
    d = load_data()
    d["events"].append({
        "type": ev_type,
        "name": name,
        "iv": iv,
        "is_shiny": shiny,
        "ts": time.time(),
        "gid": msg.guild.id if msg.guild else 0,
        "cid": msg.channel.id,
        "mid": msg.id
    })
    save_data(d)
    print(f"✅ Auto-logged {ev_type}: {name} ({(iv*100 if iv else '?')}%) {'✨' if shiny else ''}")

# -------- Start bot --------
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN ontbreekt. Zet deze in Render → Environment.")

client.run(TOKEN)
