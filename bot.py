import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

# Load token from environment or config
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
# intents.message_content = True  # Enable this after turning it on in the Developer Portal

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[OK] Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[OK] Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"[FAIL] Sync error: {e}")

    # Initialize Google Sheet (creates tabs + headers if needed)
    try:
        import db
        db._get_sheet()
        print("[OK] Google Sheet connected")
    except Exception as e:
        import traceback
        print(f"[FAIL] Google Sheet error: {type(e).__name__}: {e}")
        traceback.print_exc()

    # Send startup message
    channel_id = os.getenv("STARTUP_CHANNEL_ID")
    if channel_id:
        channel = bot.get_channel(int(channel_id))
        if channel:
            embed = discord.Embed(
                title="🎮📺 Game'N'Watch is online!",
                description="Your game & show tracker is ready. Here's what I can do:",
                color=0x43B581,
            )
            embed.add_field(
                name="⚡ Slash Commands",
                value=(
                    "`/newgame <search>` — Add a game (Steam URL, name, or manual)\n"
                    "`/newshow <search>` — Add a show (TVMaze search or manual)\n"
                    "`/random` — Pick a random game/show (Random, Top 5, Battle)\n"
                    "`/list` — View your games or shows list\n"
                    "`/todo <game>` — View & toggle to-do items for a game"
                ),
                inline=False,
            )
            embed.add_field(
                name="👤 Profile Commands",
                value=(
                    "`!createprofile <name>` — Create a profile (auto-links to you)\n"
                    "`!deleteprofile <name>` — Delete a profile\n"
                    "`!renameprofile <old> <new>` — Rename a profile\n"
                    "`!profiles` — List all profiles\n"
                    "`!profileinfo <name>` — Detailed profile stats"
                ),
                inline=False,
            )
            embed.add_field(
                name="🎮 Game Commands",
                value=(
                    "`!viewgame <title>` — View a game\n"
                    "`!updategame <title> <field> <value>` — Update a game\n"
                    "`!removegame <title>` — Remove a game\n"
                    "`!addtodo <game> | <task>` — Add a to-do\n"
                    "`!removetodo <game> <id>` — Remove a to-do"
                ),
                inline=False,
            )
            embed.add_field(
                name="📺 Show Commands",
                value=(
                    "`!viewshow <title>` — View a show\n"
                    "`!updateshow <title> <field> <value>` — Update a show\n"
                    "`!removeshow <title>` — Remove a show\n"
                    "`!progress <title> <ep> [season]` — Log episode progress"
                ),
                inline=False,
            )
            embed.add_field(
                name="📊 Tracker Commands",
                value=(
                    "`!summary` — Full profile summary\n"
                    "`!currently` — Currently playing/watching\n"
                    "`!completed` — All completed items\n"
                    "`!search <query>` — Search across all profiles"
                ),
                inline=False,
            )
            embed.set_footer(text="Tip: Profile is optional on all commands if you've used !createprofile")
            await channel.send(embed=embed)
            print("[OK] Startup message sent")

async def load_cogs():
    for cog in ["profiles", "games", "shows", "tracker", "picker"]:
        try:
            await bot.load_extension(cog)
            print(f"[OK] Loaded {cog}")
        except Exception as e:
            print(f"[FAIL] Failed to load {cog}: {e}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
