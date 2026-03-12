import discord
from bot.claude import get_reply

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    print(f"MiniClaw online as {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    # DM: always respond. Channel: only on @mention.
    if message.guild is not None:
        if bot.user not in message.mentions:
            return
        # Strip the mention prefix
        content = message.content
        for mention_str in [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]:
            content = content.replace(mention_str, "").strip()
    else:
        content = message.content

    if not content:
        return

    session_key = f"{message.channel.id}:{message.author.id}"

    async with message.channel.typing():
        try:
            reply = await get_reply(session_key, content)
        except Exception as e:
            await message.reply(f"Error: {e}")
            return

    # Split long messages (Discord 2000 char limit)
    for i in range(0, len(reply), 2000):
        chunk = reply[i : i + 2000]
        await message.reply(chunk)
