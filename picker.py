import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import random
import db


STATUS_EMOJI_GAMES = {
    "backlog": "\U0001f5c2\ufe0f",
    "playing": "\U0001f3ae",
    "completed": "\u2705",
    "dropped": "\u274c",
}

STATUS_EMOJI_SHOWS = {
    "backlog": "\U0001f5c2\ufe0f",
    "watching": "\U0001f4fa",
    "completed": "\u2705",
    "dropped": "\u274c",
    "on_hold": "\u23f8\ufe0f",
}

NO_PROFILE_MSG = "\u274c No profile linked. Use `!createprofile <name>` first, or specify a profile name."


def _resolve_profile(user_id: int, profile: str = None) -> str | None:
    if profile:
        return profile
    return db.get_profile_for_user(user_id)


def weighted_pick(pool):
    if not pool:
        return None
    weights = [item.get("priority", 3) for item in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def _random_embed(pick, section):
    icon = "\U0001f3ae" if section == "games" else "\U0001f4fa"
    color = 0x43B581 if section == "games" else 0x5865F2
    embed = discord.Embed(
        title=f"{icon} You should {'play' if section == 'games' else 'watch'}...",
        description=f"# {pick['title']}",
        color=color,
    )
    embed.add_field(name="Priority", value=f"{'\u2b50' * pick.get('priority', 3)} ({pick.get('priority', 3)}/5)", inline=True)
    embed.add_field(name="Status", value=pick.get("status", "backlog").title(), inline=True)
    if section == "games" and pick.get("platform"):
        embed.add_field(name="Platform", value=pick["platform"], inline=True)
    if section == "shows":
        ep = pick.get("current_episode", 0)
        season = pick.get("current_season", 1)
        embed.add_field(name="At", value=f"S{season:02d}E{ep:02d}", inline=True)
    return embed


def _top_embed(pool, profile, section):
    total_weight = sum(item.get("priority", 3) for item in pool)
    sorted_pool = sorted(pool, key=lambda x: -x.get("priority", 3))[:5]
    icon = "\U0001f3ae" if section == "games" else "\U0001f4fa"
    color = 0x43B581 if section == "games" else 0x5865F2
    embed = discord.Embed(
        title=f"{icon} Top Backlog Picks for {profile}",
        description="Sorted by priority \u2014 higher priority = more likely to be picked.",
        color=color,
    )
    for i, item in enumerate(sorted_pool, 1):
        chance = round((item.get("priority", 3) / total_weight) * 100, 1)
        embed.add_field(
            name=f"#{i} {item['title']}",
            value=f"{'\u2b50' * item.get('priority', 3)} | ~{chance}% pick chance",
            inline=False,
        )
    embed.set_footer(text=f"From {len(pool)} backlog item(s)")
    return embed


def _battle_embed(first, second, section):
    icon = "\U0001f3ae" if section == "games" else "\U0001f4fa"
    embed = discord.Embed(
        title=f"\u2694\ufe0f {icon} Battle! Which will you {'play' if section == 'games' else 'watch'} next?",
        color=0xED4245,
    )

    def item_value(item):
        lines = [f"Priority: {'\u2b50' * item.get('priority', 3)}"]
        if section == "shows":
            ep = item.get("current_episode", 0)
            season = item.get("current_season", 1)
            lines.append(f"At: S{season:02d}E{ep:02d}")
        if section == "games" and item.get("platform"):
            lines.append(f"Platform: {item['platform']}")
        return "\n".join(lines)

    embed.add_field(name=f"\U0001f170\ufe0f {first['title']}", value=item_value(first), inline=True)
    embed.add_field(name="vs", value="\u200b", inline=True)
    embed.add_field(name=f"\U0001f171\ufe0f {second['title']}", value=item_value(second), inline=True)
    return embed


# -- /random button views ---------------------------------------------------

class RandomMethodView(discord.ui.View):
    def __init__(self, profile, section):
        super().__init__(timeout=120)
        self.profile = profile
        self.section = section

    @discord.ui.button(label="Random Pick", style=discord.ButtonStyle.primary, emoji="\U0001f3b2")
    async def random_pick(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = db.get_weighted_pool(self.profile, self.section, ["backlog", "playing" if self.section == "games" else "watching"])
        if not pool:
            await interaction.response.edit_message(content="\U0001f4ed No items to pick from.", embed=None, view=None)
            return
        pick = weighted_pick(pool)
        embed = _random_embed(pick, self.section)
        embed.set_footer(text=f"Picked from {len(pool)} eligible item(s)")
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Top 5", style=discord.ButtonStyle.secondary, emoji="\U0001f3c6")
    async def top_five(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = db.get_weighted_pool(self.profile, self.section, ["backlog"])
        if not pool:
            await interaction.response.edit_message(content="\U0001f4ed Backlog is empty.", embed=None, view=None)
            return
        embed = _top_embed(pool, self.profile, self.section)
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Battle", style=discord.ButtonStyle.danger, emoji="\u2694\ufe0f")
    async def battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = db.get_weighted_pool(self.profile, self.section, ["backlog"])
        if len(pool) < 2:
            await interaction.response.edit_message(content="\U0001f4ed Need at least 2 backlog items for a battle.", embed=None, view=None)
            return
        first = weighted_pick(pool)
        remaining = [p for p in pool if p["title"] != first["title"]]
        second = weighted_pick(remaining)
        embed = _battle_embed(first, second, self.section)
        await interaction.response.edit_message(embed=embed, view=None)


class RandomTypeView(discord.ui.View):
    def __init__(self, profile):
        super().__init__(timeout=120)
        self.profile = profile

    @discord.ui.button(label="Game", style=discord.ButtonStyle.primary, emoji="\U0001f3ae")
    async def pick_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RandomMethodView(self.profile, "games")
        await interaction.response.edit_message(content="How should I pick?", view=view)

    @discord.ui.button(label="Show", style=discord.ButtonStyle.primary, emoji="\U0001f4fa")
    async def pick_show(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RandomMethodView(self.profile, "shows")
        await interaction.response.edit_message(content="How should I pick?", view=view)


# -- /list button views -----------------------------------------------------

class ListTypeView(discord.ui.View):
    def __init__(self, profile):
        super().__init__(timeout=120)
        self.profile = profile

    @discord.ui.button(label="Games", style=discord.ButtonStyle.primary, emoji="\U0001f3ae")
    async def list_games(self, interaction: discord.Interaction, button: discord.ui.Button):
        games = db.get_items(self.profile, "games")
        if not games:
            await interaction.response.edit_message(content="\U0001f4ed No games found.", embed=None, view=None)
            return
        sorted_games = sorted(games.items(), key=lambda x: -x[1].get("priority", 3))
        embed = discord.Embed(title=f"\U0001f3ae {self.profile}'s Games", color=0x43B581)
        for title, info in sorted_games[:25]:
            emoji = STATUS_EMOJI_GAMES.get(info.get("status", "backlog"), "\u2753")
            stars = "\u2b50" * info.get("priority", 3)
            rating = f" | \u2b50{info['rating']}/10" if info.get("rating") is not None else ""
            todos = info.get("todos", [])
            todo_done = sum(1 for t in todos if t["done"])
            todo_str = f" | \U0001f4dd{todo_done}/{len(todos)}" if todos else ""
            embed.add_field(name=f"{emoji} {title}", value=f"{stars}{rating}{todo_str}", inline=False)
        if len(sorted_games) > 25:
            embed.set_footer(text=f"Showing 25 of {len(sorted_games)} games")
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Shows", style=discord.ButtonStyle.primary, emoji="\U0001f4fa")
    async def list_shows(self, interaction: discord.Interaction, button: discord.ui.Button):
        shows = db.get_items(self.profile, "shows")
        if not shows:
            await interaction.response.edit_message(content="\U0001f4ed No shows found.", embed=None, view=None)
            return
        sorted_shows = sorted(shows.items(), key=lambda x: -x[1].get("priority", 3))
        embed = discord.Embed(title=f"\U0001f4fa {self.profile}'s Shows", color=0x5865F2)
        for title, info in sorted_shows[:25]:
            emoji = STATUS_EMOJI_SHOWS.get(info.get("status", "backlog"), "\u2753")
            stars = "\u2b50" * info.get("priority", 3)
            rating = f" | \u2b50{info['rating']}/10" if info.get("rating") is not None else ""
            ep = info.get("current_episode", 0)
            season = info.get("current_season", 1)
            total = info.get("total_episodes")
            prog = f" | S{season:02d}E{ep:02d}"
            if total:
                prog += f"/{total}"
            embed.add_field(name=f"{emoji} {title}", value=f"{stars}{rating}{prog}", inline=False)
        if len(sorted_shows) > 25:
            embed.set_footer(text=f"Showing 25 of {len(sorted_shows)} shows")
        await interaction.response.edit_message(embed=embed, view=None)


class Picker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="random", description="Pick a random game or show from your backlog")
    @app_commands.describe(profile="Profile name (optional if linked)")
    async def random_cmd(self, interaction: discord.Interaction, profile: Optional[str] = None):
        profile = _resolve_profile(interaction.user.id, profile)
        if not profile:
            await interaction.response.send_message(NO_PROFILE_MSG, ephemeral=True)
            return
        if not db.profile_exists(profile):
            await interaction.response.send_message(f"\u274c Profile **{profile}** not found.", ephemeral=True)
            return
        view = RandomTypeView(profile)
        await interaction.response.send_message("Pick a **Game** or **Show**?", view=view)

    @app_commands.command(name="list", description="View your games or shows list")
    @app_commands.describe(profile="Profile name (optional if linked)")
    async def list_cmd(self, interaction: discord.Interaction, profile: Optional[str] = None):
        profile = _resolve_profile(interaction.user.id, profile)
        if not profile:
            await interaction.response.send_message(NO_PROFILE_MSG, ephemeral=True)
            return
        if not db.profile_exists(profile):
            await interaction.response.send_message(f"\u274c Profile **{profile}** not found.", ephemeral=True)
            return
        view = ListTypeView(profile)
        await interaction.response.send_message("View **Games** or **Shows**?", view=view)


async def setup(bot):
    await bot.add_cog(Picker(bot))
