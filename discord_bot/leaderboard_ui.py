import discord
import math

PAGE_SIZE = 10

async def build_leaderboard_embed(bot, ranked, page, viewer_id, title="📚 Study Leaderboard"):
    start = page * PAGE_SIZE
    page_entries = ranked[start:start + PAGE_SIZE]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for rank, (user_id, stats_data) in enumerate(page_entries, start=start + 1):
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        prefix = medals.get(rank, f"{rank}.")
        lines.append(f"{prefix} {user.name}: {stats_data['points']:.0f} points, {stats_data['strikes']} strikes")

    embed = discord.Embed(title=title, color=discord.Color.gold())
    embed.description = "\n".join(lines)

    total_pages = math.ceil(len(ranked) / PAGE_SIZE)
    viewer_rank = None
    for i, (user_id, _) in enumerate(ranked, start=1):
        if user_id == viewer_id:
            viewer_rank = i
            break
    if viewer_rank is not None:
        footer_text = f"Page {page + 1}/{total_pages}  Your leaderboard rank: {viewer_rank}"
    else:
        footer_text = f"Page {page + 1}/{total_pages}  You are not on the leaderboard yet"
    embed.set_footer(text=footer_text)
    embed.timestamp = discord.utils.utcnow()
    return embed

class LeaderboardView(discord.ui.View):
    def __init__(self, bot, ranked, page=0, title="📚 Study Leaderboard"):
        super().__init__(timeout=None)
        self.bot = bot
        self.ranked = ranked
        self.page = page
        self.title = title

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        embed = await build_leaderboard_embed(self.bot, self.ranked, self.page, interaction.user.id, self.title)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (self.page + 1) * PAGE_SIZE < len(self.ranked):
            self.page += 1
        embed = await build_leaderboard_embed(self.bot, self.ranked, self.page, interaction.user.id, self.title)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📍 My Page", style=discord.ButtonStyle.primary)
    async def my_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        viewer_rank = None
        for i, (user_id, _) in enumerate(self.ranked, start=1):
            if user_id == interaction.user.id:
                viewer_rank = i
                break
        if viewer_rank is None:
            await interaction.response.send_message("You're not on the leaderboard yet!", ephemeral=True)
            return
        self.page = (viewer_rank - 1) // PAGE_SIZE
        embed = await build_leaderboard_embed(self.bot, self.ranked, self.page, interaction.user.id, self.title)
        await interaction.response.edit_message(embed=embed, view=self)

