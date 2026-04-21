import discord
from discord.ext import commands
import db


class Profiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="createprofile")
    async def create(self, ctx: commands.Context, *, name: str):
        """Create a new profile. Usage: !createprofile <name>"""
        if db.create_profile(name):
            db.link_user(ctx.author.id, name)
            await ctx.send(f"\u2705 Profile **{name}** created and linked to you!")
        else:
            await ctx.send(f"\u274c Profile **{name}** already exists.")

    @commands.command(name="deleteprofile")
    async def delete(self, ctx: commands.Context, *, name: str):
        """Delete a profile. Usage: !deleteprofile <name>"""
        if db.delete_profile(name):
            # Unlink if this user was linked to it
            linked = db.get_profile_for_user(ctx.author.id)
            if linked and linked.lower() == name.lower():
                db.unlink_user(ctx.author.id)
            await ctx.send(f"\U0001f5d1\ufe0f Profile **{name}** deleted.")
        else:
            await ctx.send(f"\u274c Profile **{name}** not found.")

    @commands.command(name="renameprofile")
    async def rename(self, ctx: commands.Context, old_name: str, *, new_name: str):
        """Rename a profile. Usage: !renameprofile <old> <new>"""
        if db.rename_profile(old_name, new_name):
            # Update link if this user was linked to the old name
            linked = db.get_profile_for_user(ctx.author.id)
            if linked and linked.lower() == old_name.lower():
                db.link_user(ctx.author.id, new_name)
            await ctx.send(f"\u270f\ufe0f Profile **{old_name}** renamed to **{new_name}**.")
        else:
            await ctx.send(f"\u274c Rename failed. Check that the old name exists and the new name is unused.")

    @commands.command(name="profiles")
    async def list_profiles(self, ctx: commands.Context):
        """List all profiles. Usage: !profiles"""
        profiles = db.get_profiles()
        if not profiles:
            await ctx.send("\U0001f4ed No profiles found. Create one with `!createprofile <name>`.")
            return

        embed = discord.Embed(title="\U0001f464 Profiles", color=0x7289DA)
        for name, data in profiles.items():
            game_count = len(data.get("games", {}))
            show_count = len(data.get("shows", {}))
            embed.add_field(
                name=name,
                value=f"\U0001f3ae {game_count} game(s)  |  \U0001f4fa {show_count} show(s)",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="profileinfo")
    async def info(self, ctx: commands.Context, *, name: str):
        """Show detailed stats for a profile. Usage: !profileinfo <name>"""
        if not db.profile_exists(name):
            await ctx.send(f"\u274c Profile **{name}** not found.")
            return

        games = db.get_items(name, "games")
        shows = db.get_items(name, "shows")

        def count_status(items, status):
            return sum(1 for v in items.values() if v.get("status") == status)

        embed = discord.Embed(title=f"\U0001f4ca Profile: {name}", color=0x7289DA)

        g_statuses = ["backlog", "playing", "completed", "dropped"]
        s_statuses = ["backlog", "watching", "completed", "dropped", "on_hold"]

        g_lines = "\n".join(f"`{s}`: {count_status(games, s)}" for s in g_statuses)
        s_lines = "\n".join(f"`{s}`: {count_status(shows, s)}" for s in s_statuses)

        embed.add_field(name=f"\U0001f3ae Games ({len(games)} total)", value=g_lines or "None", inline=True)
        embed.add_field(name=f"\U0001f4fa Shows ({len(shows)} total)", value=s_lines or "None", inline=True)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Profiles(bot))
