import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import db
import asyncio
import functools

STATUS_CHOICES = [
    app_commands.Choice(name="Backlog", value="backlog"),
    app_commands.Choice(name="Playing", value="playing"),
    app_commands.Choice(name="Completed", value="completed"),
    app_commands.Choice(name="Dropped", value="dropped"),
]

PRIORITY_CHOICES = [
    app_commands.Choice(name="1 - Low", value=1),
    app_commands.Choice(name="2 - Below Average", value=2),
    app_commands.Choice(name="3 - Normal", value=3),
    app_commands.Choice(name="4 - High", value=4),
    app_commands.Choice(name="5 - Must Play", value=5),
]

STATUS_EMOJI = {
    "backlog": "\U0001f5c2\ufe0f",
    "playing": "\U0001f3ae",
    "completed": "\u2705",
    "dropped": "\u274c",
}


def _resolve_profile(user_id: int, profile: str = None) -> str | None:
    if profile:
        return profile
    return db.get_profile_for_user(user_id)


def _game_embed(title, game, color=0x43B581):
    embed = discord.Embed(title=f"\U0001f3ae {title}", color=color)
    status_emoji = STATUS_EMOJI.get(game.get("status", "backlog"), "\u2753")
    embed.add_field(name="Status", value=f"{status_emoji} {game.get('status', 'backlog').title()}", inline=True)
    embed.add_field(name="Priority", value=f"{'\u2b50' * game.get('priority', 3)} ({game.get('priority', 3)}/5)", inline=True)
    embed.add_field(name="Platform", value=game.get("platform") or "\u2014", inline=True)
    embed.add_field(name="Rating", value=f"{game.get('rating')}/10" if game.get("rating") is not None else "\u2014", inline=True)
    if game.get("release_date"):
        embed.add_field(name="Release Date", value=game["release_date"], inline=True)
    if game.get("price"):
        embed.add_field(name="Price", value=game["price"], inline=True)
    if game.get("developers"):
        embed.add_field(name="Developers", value=game["developers"], inline=True)
    mp_val = game.get("is_multiplayer", False)
    embed.add_field(name="Multiplayer", value="\u2705 Yes" if mp_val else "\u274c No", inline=True)
    embed.add_field(name="Notes", value=game.get("notes") or "\u2014", inline=False)
    todos = game.get("todos", [])
    if todos:
        todo_lines = []
        for t in todos:
            check = "\u2705" if t["done"] else "\u2b1c"
            todo_lines.append(f"{check} `#{t['id']}` {t['task']}")
        embed.add_field(name=f"To-Dos ({len(todos)})", value="\n".join(todo_lines[:10]), inline=False)
    return embed


NO_PROFILE_MSG = "\u274c No profile linked. Use `!createprofile <name>` first, or specify a profile name."


# -- Steam search result picker view ----------------------------------------

class SteamPickButton(discord.ui.Button):
    def __init__(self, profile, app_id, name, index, status, priority, platform):
        super().__init__(label=f"{index}. {name}"[:80], style=discord.ButtonStyle.primary)
        self.profile = profile
        self.app_id = app_id
        self.game_name = name
        self.status = status
        self.priority = priority
        self.platform = platform

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        loop = asyncio.get_event_loop()
        steam_data = await loop.run_in_executor(None, db.steam_lookup, self.app_id)
        if not steam_data:
            await interaction.followup.send(f"\u274c Could not fetch Steam data.", ephemeral=True)
            return

        title = steam_data["name"]
        kwargs = {
            "release_date": steam_data.get("release_date", ""),
            "price": steam_data.get("price", ""),
            "developers": steam_data.get("developers", ""),
            "is_multiplayer": steam_data.get("is_multiplayer", False),
        }
        if self.platform:
            kwargs["platform"] = self.platform
        elif steam_data.get("platform"):
            kwargs["platform"] = steam_data["platform"]
        if self.status:
            kwargs["status"] = self.status.value
        if self.priority:
            kwargs["priority"] = self.priority.value

        if db.add_item(self.profile, "games", title, **kwargs):
            game = db.get_item(self.profile, "games", title)
            embed = _game_embed(title, game)
            if steam_data.get("header_image"):
                embed.set_thumbnail(url=steam_data["header_image"])
            embed.set_footer(text=f"Added to {self.profile}'s games from Steam")
            await interaction.edit_original_response(embed=embed, view=None)
        else:
            await interaction.edit_original_response(
                content=f"\u274c **{title}** already exists in **{self.profile}**.",
                embed=None, view=None
            )


class SteamSearchView(discord.ui.View):
    def __init__(self, profile, results, status, priority, platform):
        super().__init__(timeout=120)
        for i, r in enumerate(results[:5]):
            self.add_item(SteamPickButton(profile, r["app_id"], r["name"], i + 1, status, priority, platform))


# -- Todo toggle button view ------------------------------------------------

class TodoToggleButton(discord.ui.Button):
    def __init__(self, profile, game_title, todo):
        done = todo["done"]
        label = f"{'[x]' if done else '[ ]'} #{todo['id']}: {todo['task']}"
        style = discord.ButtonStyle.success if done else discord.ButtonStyle.secondary
        super().__init__(label=label[:80], style=style, custom_id=f"todo_{profile}_{game_title}_{todo['id']}")
        self.profile = profile
        self.game_title = game_title
        self.todo_id = todo["id"]

    async def callback(self, interaction: discord.Interaction):
        db.toggle_todo(self.profile, self.game_title, self.todo_id)
        game = db.get_item(self.profile, "games", self.game_title)
        if not game:
            await interaction.response.send_message("\u274c Game not found.", ephemeral=True)
            return
        todos = game.get("todos", [])
        if not todos:
            await interaction.response.edit_message(content="\U0001f4ed No to-dos.", view=None, embed=None)
            return
        view = TodoView(self.profile, self.game_title, todos)
        embed = discord.Embed(title=f"\U0001f4dd To-Dos: {self.game_title}", color=0x43B581)
        pending = [t for t in todos if not t["done"]]
        done_list = [t for t in todos if t["done"]]
        if pending:
            embed.add_field(name="\u2b1c Pending", value="\n".join(f"`#{t['id']}` {t['task']}" for t in pending), inline=False)
        if done_list:
            embed.add_field(name="\u2705 Done", value="\n".join(f"`#{t['id']}` ~~{t['task']}~~" for t in done_list), inline=False)
        await interaction.response.edit_message(embed=embed, view=view)


class TodoView(discord.ui.View):
    def __init__(self, profile, game_title, todos):
        super().__init__(timeout=300)
        for todo in todos[:25]:
            self.add_item(TodoToggleButton(profile, game_title, todo))


class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -- Slash: /newgame ----------------------------------------------------

    @app_commands.command(name="newgame", description="Add a game — paste a Steam link, search by name, or enter manually")
    @app_commands.describe(
        search="Steam store URL, game name to search, or manual title",
        status="Current status",
        priority="Priority (1-5)",
        platform="Platform (overrides Steam data)",
        profile="Profile name (optional if linked)"
    )
    @app_commands.choices(status=STATUS_CHOICES, priority=PRIORITY_CHOICES)
    async def newgame(
        self,
        interaction: discord.Interaction,
        search: str,
        status: app_commands.Choice[str] = None,
        priority: app_commands.Choice[int] = None,
        platform: str = "",
        profile: Optional[str] = None
    ):
        profile = _resolve_profile(interaction.user.id, profile)
        if not profile:
            await interaction.response.send_message(NO_PROFILE_MSG, ephemeral=True)
            return
        if not db.profile_exists(profile):
            await interaction.response.send_message(f"\u274c Profile **{profile}** not found.", ephemeral=True)
            return

        await interaction.response.defer()

        # Try to parse as Steam URL or app ID
        app_id = db.parse_steam_input(search)

        if app_id:
            # Direct lookup
            loop = asyncio.get_event_loop()
            steam_data = await loop.run_in_executor(None, db.steam_lookup, app_id)
            if not steam_data:
                await interaction.followup.send(f"\u274c Could not fetch Steam data for app ID `{app_id}`.", ephemeral=True)
                return
            await self._add_from_steam(interaction, profile, steam_data, status, priority, platform)
        else:
            # Search by name
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, db.steam_search, search)

            if not results:
                # No results — add manually with the search text as the title
                await self._add_manual(interaction, profile, search, status, priority, platform)
            elif len(results) == 1:
                # Single match — look it up
                steam_data = await loop.run_in_executor(None, db.steam_lookup, results[0]["app_id"])
                if steam_data:
                    await self._add_from_steam(interaction, profile, steam_data, status, priority, platform)
                else:
                    await self._add_manual(interaction, profile, results[0]["name"], status, priority, platform)
            else:
                # Multiple results — let the user pick
                view = SteamSearchView(profile, results, status, priority, platform)
                desc = "\n".join(f"**{i+1}.** {r['name']}" for i, r in enumerate(results))
                embed = discord.Embed(
                    title="\U0001f50e Steam Search Results",
                    description=desc + "\n\nPick one, or click **Manual** to add with your search text as-is.",
                    color=0x1B2838,
                )
                await interaction.followup.send(embed=embed, view=view)

    async def _add_from_steam(self, interaction, profile, steam_data, status, priority, platform):
        title = steam_data["name"]
        kwargs = {
            "release_date": steam_data.get("release_date", ""),
            "price": steam_data.get("price", ""),
            "developers": steam_data.get("developers", ""),
            "is_multiplayer": steam_data.get("is_multiplayer", False),
        }
        if platform:
            kwargs["platform"] = platform
        elif steam_data.get("platform"):
            kwargs["platform"] = steam_data["platform"]
        if status:
            kwargs["status"] = status.value
        if priority:
            kwargs["priority"] = priority.value

        if db.add_item(profile, "games", title, **kwargs):
            game = db.get_item(profile, "games", title)
            embed = _game_embed(title, game)
            if steam_data.get("header_image"):
                embed.set_thumbnail(url=steam_data["header_image"])
            embed.set_footer(text=f"Added to {profile}'s games from Steam")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"\u274c **{title}** already exists in **{profile}**.", ephemeral=True)

    async def _add_manual(self, interaction, profile, title, status, priority, platform):
        kwargs = {}
        if status:
            kwargs["status"] = status.value
        if priority:
            kwargs["priority"] = priority.value
        if platform:
            kwargs["platform"] = platform

        if db.add_item(profile, "games", title, **kwargs):
            await interaction.followup.send(f"\u2705 Added **{title}** to **{profile}**'s games! (no Steam data found)")
        else:
            await interaction.followup.send(f"\u274c **{title}** already exists in **{profile}**.", ephemeral=True)

    # -- Slash: /todo -------------------------------------------------------

    @app_commands.command(name="todo", description="View and toggle to-dos for a game")
    @app_commands.describe(game="Game title", profile="Profile name (optional if linked)")
    async def todo(self, interaction: discord.Interaction, game: str, profile: Optional[str] = None):
        profile = _resolve_profile(interaction.user.id, profile)
        if not profile:
            await interaction.response.send_message(NO_PROFILE_MSG, ephemeral=True)
            return
        item = db.get_item(profile, "games", game)
        if not item:
            await interaction.response.send_message(f"\u274c Game **{game}** not found in **{profile}**.", ephemeral=True)
            return
        todos = item.get("todos", [])
        if not todos:
            await interaction.response.send_message(f"\U0001f4ed No to-dos for **{game}**. Add one with `!addtodo <game> | <task>`.", ephemeral=True)
            return
        view = TodoView(profile, game, todos)
        embed = discord.Embed(title=f"\U0001f4dd To-Dos: {game}", color=0x43B581)
        pending = [t for t in todos if not t["done"]]
        done_list = [t for t in todos if t["done"]]
        if pending:
            embed.add_field(name="\u2b1c Pending", value="\n".join(f"`#{t['id']}` {t['task']}" for t in pending), inline=False)
        if done_list:
            embed.add_field(name="\u2705 Done", value="\n".join(f"`#{t['id']}` ~~{t['task']}~~" for t in done_list), inline=False)
        await interaction.response.send_message(embed=embed, view=view)

    # -- ! commands ---------------------------------------------------------

    @commands.command(name="removegame")
    async def remove(self, ctx, *, title: str):
        """Remove a game. Usage: !removegame <title>"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        if db.remove_item(profile, "games", title):
            await ctx.send(f"\U0001f5d1\ufe0f Removed **{title}** from **{profile}**.")
        else:
            await ctx.send(f"\u274c Game not found.")

    @commands.command(name="updategame")
    async def update(self, ctx, title: str, field: str, *, value: str):
        """Update a game field. Usage: !updategame <title> <field> <value>
        Fields: status, priority, platform, rating, notes, release_date, price, developers, multiplayer"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        kwargs = {}
        field = field.lower()
        if field == "status" and value.lower() in ("backlog", "playing", "completed", "dropped"):
            kwargs["status"] = value.lower()
        elif field == "priority" and value.isdigit() and 1 <= int(value) <= 5:
            kwargs["priority"] = int(value)
        elif field == "platform":
            kwargs["platform"] = value
        elif field == "rating" and value.isdigit() and 0 <= int(value) <= 10:
            kwargs["rating"] = int(value)
        elif field == "notes":
            kwargs["notes"] = value
        elif field == "release_date":
            kwargs["release_date"] = value
        elif field == "price":
            kwargs["price"] = value
        elif field == "developers":
            kwargs["developers"] = value
        elif field == "multiplayer":
            kwargs["is_multiplayer"] = value.lower() in ("true", "yes", "1")
        else:
            await ctx.send(f"\u274c Invalid field or value. Fields: `status`, `priority`, `platform`, `rating`, `notes`, `release_date`, `price`, `developers`, `multiplayer`")
            return
        if db.update_item(profile, "games", title, **kwargs):
            await ctx.send(f"\u270f\ufe0f Updated **{title}** `{field}` \u2192 `{value}`.")
        else:
            await ctx.send(f"\u274c Game not found.")

    @commands.command(name="viewgame")
    async def view(self, ctx, *, title: str):
        """View a game. Usage: !viewgame <title>"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        game = db.get_item(profile, "games", title)
        if not game:
            await ctx.send(f"\u274c Game not found.")
            return
        embed = _game_embed(title, game)
        await ctx.send(embed=embed)

    @commands.command(name="addtodo")
    async def addtodo(self, ctx, *, args: str):
        """Add a to-do. Usage: !addtodo <game> | <task>"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        if "|" not in args:
            await ctx.send("\u274c Usage: `!addtodo <game> | <task>`")
            return
        game, task = args.split("|", 1)
        game = game.strip()
        task = task.strip()
        todo_id = db.add_todo(profile, game, task)
        if todo_id is not None:
            await ctx.send(f"\u2705 Added to-do `#{todo_id}` to **{game}**: {task}")
        else:
            await ctx.send(f"\u274c Game **{game}** not found in **{profile}**.")

    @commands.command(name="removetodo")
    async def removetodo(self, ctx, game: str, todo_id: int):
        """Remove a to-do. Usage: !removetodo <game> <id>"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        if db.remove_todo(profile, game, todo_id):
            await ctx.send(f"\U0001f5d1\ufe0f Removed to-do `#{todo_id}` from **{game}**.")
        else:
            await ctx.send(f"\u274c To-do not found.")


async def setup(bot):
    await bot.add_cog(Games(bot))
