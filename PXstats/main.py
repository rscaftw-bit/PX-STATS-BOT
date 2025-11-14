@bot.event
async def on_message(msg: discord.Message):

    # Eigen bot negeren
    if msg.author == bot.user:
        return

    if not msg.embeds:
        return

    processed = 0

    for e in msg.embeds:
        etype, data = parse_polygonx_embed(e)
        if not etype:
            continue

        ts = e.timestamp or datetime.now(TZ)

        # basis event
        base = dict(data)
        base["timestamp"] = ts
        base["type"] = etype
        add_event(base)
        processed += 1

        # Shiny-catch: extra "Shiny"-event toevoegen
        if etype == "Catch" and data.get("shiny"):
            shiny_evt = dict(base)
            shiny_evt["type"] = "Shiny"
            add_event(shiny_evt)
            processed += 1

    if processed > 0:
        print(f"[INGEST] processed embeds from {msg.author} ({processed} events)")
        save_events()
