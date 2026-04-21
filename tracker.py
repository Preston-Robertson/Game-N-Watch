import discord
from discord.ext import commands
import db

NO_PROFILE_MSG = "\u274c No profile linked. Use `!createprofile <name>` first, or specify a profile name."


def _resolve_profile(user_id: int, profile: str = None) -> str | None:
    if profile:
        return profile
    return db.get_profile_for_user(user_id)


class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="summary")
    async def summary(self, ctx, *, profile: str = None):
        """Show a full summary. Usage: !summary [profile]"""
        profile = _resolve_profile(ctx.author.id, profile)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        if not db.profile_exists(profile):
            await ctx.send(f"\u274c Profile **{profile}** not found.")
            return

        games = db.get_items(profile, "games")
        shows = db.get_items(profile, "shows")

        embed = discord.Embed(title=f"\U0001f4ca Summary: {profile}", color=0xFAA81A)

        def g_count(s):
            return sum(1 for v in games.values() if v.get("status") == s)

        rated_games = [v["rating"] for v in games.values() if v.get("rating") is not None]
        avg_game_rating = round(sum(rated_games) / len(rated_games), 1) if rated_games else None

        game_lines = (
            f"\U0001f5c2\ufe0f Backlog: **{g_count('backlog')}**\n"
            f"\U0001f3ae Playing: **{g_count('playing')}**\n"
            f"\u2705 Completed: **{g_count('completed')}**\n"
            f"\u274c Dropped: **{g_count('dropped')}**"
        )
        if avg_game_rating:
            game_lines += f"\n\U0001f4c8 Avg Rating: **{avg_game_rating}/10**"
        embed.add_field(name=f"\U0001f3ae Games ({len(games)} total)", value=game_lines, inline=True)

        def s_count(s):
            return sum(1 for v in shows.values() if v.get("status") == s)

        rated_shows = [v["rating"] for v in shows.values() if v.get("rating") is not None]
        avg_show_rating = round(sum(rated_shows) / len(rated_shows), 1) if rated_shows else None

        show_lines = (
            f"\U0001f5c2\ufe0f Backlog: **{s_count('backlog')}**\n"
            f"\U0001f4fa Watching: **{s_count('watching')}**\n"
            f"\u2705 Completed: **{s_count('completed')}**\n"
            f"\u23f8\ufe0f On Hold: **{s_count('on_hold')}**\n"
            f"\u274c Dropped: **{s_count('dropped')}**"
        )
        if avg_show_rating:
            show_lines += f"\n\U0001f4c8 Avg Rating: **{avg_show_rating}/10**"
        embed.add_field(name=f"\U0001f4fa Shows ({len(shows)} total)", value=show_lines, inline=True)

        top_games = sorted(
            [(t, v) for t, v in games.items() if v.get("rating") is not None],
            key=lambda x: -x[1]["rating"]
        )[:3]
        top_shows = sorted(
            [(t, v) for t, v in shows.items() if v.get("rating") is not None],
            key=lambda x: -x[1]["rating"]
        )[:3]

        if top_games:
            embed.add_field(
                name="\U0001f3c6 Top Rated Games",
                value="\n".join(f"`{v['rating']}/10` {t}" for t, v in top_games),
                inline=False,
            )
        if top_shows:
            embed.add_field(
                name="\U0001f3c6 Top Rated Shows",
                value="\n".join(f"`{v['rating']}/10` {t}" for t, v in top_shows),
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(name="currently")
    async def currently(self, ctx, *, profile: str = None):
        """Show what is currently being played/watched. Usage: !currently [profile]"""
        profile = _resolve_profile(ctx.author.id, profile)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        if not db.profile_exists(profile):
            await ctx.send(f"\u274c Profile **{profile}** not found.")
            return

        games = db.get_items(profile, "games")
        shows = db.get_items(profile, "shows")

        active_games = {t: v for t, v in games.items() if v.get("status") == "playing"}
        active_shows = {t: v for t, v in shows.items() if v.get("status") == "watching"}

        embed = discord.Embed(title=f"\u25b6\ufe0f Currently Active: {profile}", color=0xED4245)

        if active_games:
            lines = []
            for t, v in active_games.items():
                todos = v.get("todos", [])
                pending = sum(1 for td in todos if not td["done"])
                todo_str = f" \u2014 \U0001f4dd {pending} pending to-do(s)" if pending else ""
                lines.append(f"\U0001f3ae **{t}**{todo_str}")
            embed.add_field(name="Games", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Games", value="Nothing currently playing.", inline=False)

        if active_shows:
            lines = []
            for t, v in active_shows.items():
                ep = v.get("current_episode", 0)
                season = v.get("current_season", 1)
                total = v.get("total_episodes")
                prog = f"S{season:02d}E{ep:02d}"
                if total:
                    prog += f"/{total}"
                lines.append(f"\U0001f4fa **{t}** \u2014 {prog}")
            embed.add_field(name="Shows", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Shows", value="Nothing currently watching.", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="completed")
    async def completed(self, ctx, *, profile: str = None):
        """Review all completed games and shows. Usage: !completed [profile]"""
        profile = _resolve_profile(ctx.author.id, profile)
        if not profile:
            await ctx.send(NO_PROFILE_MSG)
            return
        if not db.profile_exists(profile):
            await ctx.send(f"\u274c Profile **{profile}** not found.")
            return

        games = db.get_items(profile, "games")
        shows = db.get_items(profile, "shows")

        done_games = {t: v for t, v in games.items() if v.get("status") == "completed"}
        done_shows = {t: v for t, v in shows.items() if v.get("status") == "completed"}

        embed = discord.Embed(title=f"\u2705 Completed: {profile}", color=0x57F287)

        if done_games:
            sorted_g = sorted(done_games.items(), key=lambda x: -(x[1].get("rating") or 0))
            lines = [
                f"**{t}**{' \u2014 ' + str(v['rating']) + '/10' if v.get('rating') is not None else ''}"
                for t, v in sorted_g[:15]
            ]
            embed.add_field(name=f"\U0001f3ae Games ({len(done_games)})", value="\n".join(lines) or "None", inline=False)
        else:
            embed.add_field(name="\U0001f3ae Games (0)", value="None completed yet.", inline=False)

        if done_shows:
            sorted_s = sorted(done_shows.items(), key=lambda x: -(x[1].get("rating") or 0))
            lines = [
                f"**{t}**{' \u2014 ' + str(v['rating']) + '/10' if v.get('rating') is not None else ''}"
                for t, v in sorted_s[:15]
            ]
            embed.add_field(name=f"\U0001f4fa Shows ({len(done_shows)})", value="\n".join(lines) or "None", inline=False)
        else:
            embed.add_field(name="\U0001f4fa Shows (0)", value="None completed yet.", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="search")
    async def search(self, ctx, *, query: str):
        """Search for a title across all profiles. Usage: !search <query>"""
        profiles = db.get_profiles()
        results = []

        for pname, pdata in profiles.items():
            for section in ("games", "shows"):
                for title in pdata.get(section, {}):
                    if query.lower() in title.lower():
                        results.append((pname, section, title))

        if not results:
            await ctx.send(f"\U0001f50d No results for `{query}`.")
            return

        embed = discord.Embed(title=f"\U0001f50d Search: {query}", color=0xFEE75C)
        for pname, section, title in results[:20]:
            icon = "\U0001f3ae" if section == "games" else "\U0001f4fa"
            embed.add_field(name=f"{icon} {title}", value=f"Profile: **{pname}**", inline=False)

        if len(results) > 20:
            embed.set_footer(text=f"Showing 20 of {len(results)} results")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Tracker(bot))
