import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio
import functools
import db

STATUS_CHOICES = [
    app_commands.Choice(name="Backlog", value="backlog"),
    app_commands.Choice(name="Watching", value="watching"),
    app_commands.Choice(name="Completed", value="completed"),
    app_commands.Choice(name="Dropped", value="dropped"),
    app_commands.Choice(name="On Hold", value="on_hold"),
]

PRIORITY_CHOICES = [
    app_commands.Choice(name="1 - Low", value=1),
    app_commands.Choice(name="2 - Below Average", value=2),
    app_commands.Choice(name="3 - Normal", value=3),
    app_commands.Choice(name="4 - High", value=4),
    app_commands.Choice(name="5 - Must Watch", value=5),
]

STATUS_EMOJI = {
    "backlog": "\U0001f5c2\ufe0f",
    "watching": "\U0001f4fa",
    "completed": "\u2705",
    "dropped": "\u274c",
    "on_hold": "\u23f8\ufe0f",
}

NO_PROFILE_MSG = "\u274c No profile linked. Use `!createprofile <name>` first, or specify a profile name."


# -- TVMaze search result picker view ----------------------------------------

class TVMazePickButton(discord.ui.Button):
    def __init__(self, profile, show_id, name, index, status, priority):
        year_label = ""
        super().__init__(label=f"{index}. {name}"[:80], style=discord.ButtonStyle.primary)
        self.profile = profile
        self.show_id = show_id
        self.show_name = name
        self.status = status
        self.priority = priority

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        loop = asyncio.get_event_loop()
        tv_data = await loop.run_in_executor(None, db.tvmaze_lookup, self.show_id)
        if not tv_data:
            await interaction.followup.send("\u274c Could not fetch show data.", ephemeral=True)
            return

        title = tv_data["name"]
        kwargs = {
            "genre": tv_data.get("genre", ""),
            "platform": tv_data.get("platform", ""),
            "premiere_date": tv_data.get("premiere_date", ""),
            "total_episodes": tv_data.get("total_episodes") or None,
        }
        if self.status:
            kwargs["status"] = self.status.value
        if self.priority:
            kwargs["priority"] = self.priority.value

        if db.add_item(self.profile, "shows", title, **kwargs):
            show = db.get_item(self.profile, "shows", title)
            embed = _show_embed(title, show)
            if tv_data.get("image_url"):
                embed.set_thumbnail(url=tv_data["image_url"])
            embed.set_footer(text=f"Added to {self.profile}'s shows from TVMaze")
            await interaction.edit_original_response(embed=embed, view=None)
        else:
            await interaction.edit_original_response(
                content=f"\u274c **{title}** already exists in **{self.profile}**.",
                embed=None, view=None
            )


class TVMazeSearchView(discord.ui.View):
    def __init__(self, profile, results, status, priority):
        super().__init__(timeout=120)
        for i, r in enumerate(results[:5]):
            label = r["name"]
            if r.get("year"):
                label += f" ({r['year']})"
            btn = TVMazePickButton(profile, r["id"], r["name"], i + 1, status, priority)
            btn.label = f"{i + 1}. {label}"[:80]
            self.add_item(btn)


def _resolve_profile(user_id: int, profile: str = None) -> str | None:
    if profile:
        return profile
    return db.get_profile_for_user(user_id)


def _show_embed(title, show, color=0x5865F2):
    embed = discord.Embed(title=f"\U0001f4fa {title}", color=color)
    status_emoji = STATUS_EMOJI.get(show.get("status", "backlog"), "\u2753")
    embed.add_field(name="Status", value=f"{status_emoji} {show.get('status', 'backlog').replace('_', ' ').title()}", inline=True)
    embed.add_field(name="Priority", value=f"{'\u2b50' * show.get('priority', 3)} ({show.get('priority', 3)}/5)", inline=True)
    embed.add_field(name="Genre", value=show.get("genre") or "\u2014", inline=True)
    embed.add_field(name="Platform", value=show.get("platform") or "\u2014", inline=True)
    if show.get("premiere_date"):
        embed.add_field(name="Premiere Date", value=show["premiere_date"], inline=True)
    ep = show.get("current_episode", 0)
    total = show.get("total_episodes")
    season = show.get("current_season", 1)
    ep_str = f"S{season:02d}E{ep:02d}"
    if total:
        ep_str += f" / {total} eps"
    embed.add_field(name="Progress", value=ep_str, inline=True)
    embed.add_field(name="Rating", value=f"{show.get('rating')}/10" if show.get("rating") is not None else "\u2014", inline=True)
    embed.add_field(name="Notes", value=show.get("notes") or "\u2014", inline=False)
    return embed


class Shows(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -- Slash: /newshow ----------------------------------------------------

    @app_commands.command(name="newshow", description="Add a show — search by name or enter manually")
    @app_commands.describe(
        search="Show name to search TVMaze, or manual title",
        status="Current status",
        priority="Priority (1-5)",
        profile="Profile name (optional if linked)"
    )
    @app_commands.choices(status=STATUS_CHOICES, priority=PRIORITY_CHOICES)
    async def newshow(
        self,
        interaction: discord.Interaction,
        search: str,
        status: app_commands.Choice[str] = None,
        priority: app_commands.Choice[int] = None,
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

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, db.tvmaze_search, search)

        if not results:
            # No results — add manually
            await self._add_manual(interaction, profile, search, status, priority)
        elif len(results) == 1:
            # Single match — look it up
            tv_data = await loop.run_in_executor(None, db.tvmaze_lookup, results[0]["id"])
            if tv_data:
                await self._add_from_tvmaze(interaction, profile, tv_data, status, priority)
            else:
                await self._add_manual(interaction, profile, results[0]["name"], status, priority)
        else:
            # Multiple results — let the user pick
            view = TVMazeSearchView(profile, results, status, priority)
            desc = "\n".join(
                f"**{i+1}.** {r['name']}{f' ({r["year"]})' if r.get('year') else ''} — {r['network'] or 'Unknown network'}"
                for i, r in enumerate(results)
            )
            embed = discord.Embed(
                title="\U0001f50e TVMaze Search Results",
                description=desc + "\n\nPick one, or the show will be added manually if none match.",
                color=0x3DB4F2,
            )
            await interaction.followup.send(embed=embed, view=view)

    async def _add_from_tvmaze(self, interaction, profile, tv_data, status, priority):
        title = tv_data["name"]
        kwargs = {
            "genre": tv_data.get("genre", ""),
            "platform": tv_data.get("platform", ""),
            "premiere_date": tv_data.get("premiere_date", ""),
            "total_episodes": tv_data.get("total_episodes") or None,
        }
        if status:
            kwargs["status"] = status.value
        if priority:
            kwargs["priority"] = priority.value

        if db.add_item(profile, "shows", title, **kwargs):
            show = db.get_item(profile, "shows", title)
            embed = _show_embed(title, show)
            if tv_data.get("image_url"):
                embed.set_thumbnail(url=tv_data["image_url"])
            embed.set_footer(text=f"Added to {profile}'s shows from TVMaze")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"\u274c **{title}** already exists in **{profile}**.", ephemeral=True)

    async def _add_manual(self, interaction, profile, title, status, priority):
        kwargs = {}
        if status:
            kwargs["status"] = status.value
        if priority:
            kwargs["priority"] = priority.value

        if db.add_item(profile, "shows", title, **kwargs):
            await interaction.followup.send(f"\u2705 Added **{title}** to **{profile}**'s shows! (no TVMaze data found)")
        else:
            await interaction.followup.send(f"\u274c **{title}** already exists in **{profile}**.", ephemeral=True)

    # -- ! commands ---------------------------------------------------------

    @commands.command(name="removeshow")
    async def remove(self, ctx, *, title: str):
        """Remove a show. Usage: !removeshow <title>"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        if db.remove_item(profile, "shows", title):
            await ctx.send(f"\U0001f5d1\ufe0f Removed **{title}** from **{profile}**.")
        else:
            await ctx.send(f"\u274c Show not found.")

    @commands.command(name="updateshow")
    async def update(self, ctx, title: str, field: str, *, value: str):
        """Update a show field. Usage: !updateshow <title> <field> <value>
        Fields: status, priority, genre, rating, notes, episode, season, total_episodes, platform, premiere_date"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        kwargs = {}
        field = field.lower()
        valid_statuses = ("backlog", "watching", "completed", "dropped", "on_hold")
        if field == "status" and value.lower() in valid_statuses:
            kwargs["status"] = value.lower()
        elif field == "priority" and value.isdigit() and 1 <= int(value) <= 5:
            kwargs["priority"] = int(value)
        elif field == "genre":
            kwargs["genre"] = value
        elif field == "rating" and value.isdigit() and 0 <= int(value) <= 10:
            kwargs["rating"] = int(value)
        elif field == "notes":
            kwargs["notes"] = value
        elif field == "episode" and value.isdigit():
            kwargs["current_episode"] = int(value)
        elif field == "season" and value.isdigit():
            kwargs["current_season"] = int(value)
        elif field == "total_episodes" and value.isdigit():
            kwargs["total_episodes"] = int(value)
        elif field == "platform":
            kwargs["platform"] = value
        elif field == "premiere_date":
            kwargs["premiere_date"] = value
        else:
            await ctx.send(f"\u274c Invalid field or value. Fields: `status`, `priority`, `genre`, `rating`, `notes`, `episode`, `season`, `total_episodes`, `platform`, `premiere_date`")
            return
        if db.update_item(profile, "shows", title, **kwargs):
            await ctx.send(f"\u270f\ufe0f Updated **{title}** `{field}` \u2192 `{value}`.")
        else:
            await ctx.send(f"\u274c Show not found.")

    @commands.command(name="viewshow")
    async def view(self, ctx, *, title: str):
        """View a show. Usage: !viewshow <title>"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        show = db.get_item(profile, "shows", title)
        if not show:
            await ctx.send(f"\u274c Show not found.")
            return
        embed = _show_embed(title, show)
        await ctx.send(embed=embed)

    @commands.command(name="progress")
    async def progress(self, ctx, title: str, episode: int, season: int = None):
        """Log episode progress. Usage: !progress <title> <episode> [season]"""
        profile = _resolve_profile(ctx.author.id)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        show = db.get_item(profile, "shows", title)
        if not show:
            await ctx.send(f"\u274c Show not found.")
            return
        kwargs = {"current_episode": episode}
        if season is not None:
            kwargs["current_season"] = season
        db.update_item(profile, "shows", title, **kwargs)
        s = season or show.get("current_season", 1)
        await ctx.send(f"\U0001f4fa Updated **{title}** \u2192 S{s:02d}E{episode:02d}")


async def setup(bot):
    await bot.add_cog(Shows(bot))
