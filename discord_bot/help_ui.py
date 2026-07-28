import discord
import math

HELP_PAGES = [
    {
        "name": "📚 Study Help",
        "description": "View all study commands.",
        "commands": [
            ("!startchallenge", "Initialises new challenge"),
            ("!endchallenge", "Ends the current challenge"),
           ("!startstudy", "Start a study session."),
            ("!endstudy", "End the current study session."),
            ("!pause", "Pause/resume the current study session."),
            ("!stats", "View your overall lifetime study statistics."),
            ("!challengestats", "View your current challenge statistics."),
            ("leaderboard", "Uploads/updates the study leaderboard in the #leaderboard chat."),
            ("!challengeleaderboard", "Uploads/updates the challenge leaderboard in the #leaderboard chat."),
        ]
 
    }
]
PAGE_SIZE = 4


def create_help_embed(page):
    section = HELP_PAGES[0]
    all_commands = section["commands"]
    start = page * PAGE_SIZE
    page_commands = all_commands[start:start + PAGE_SIZE]

    embed = discord.Embed(title = section["name"], description=section["description"], color=discord.Color.blue())


    for command, description in page_commands:
        embed.add_field(name=command, value=description, inline=False)

    return embed

class HelpView(discord.ui.View):
    def __init__(self, page=0):
        super().__init__()
        self.page = page

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        embed = create_help_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        total_commands = len(HELP_PAGES[0]["commands"])
        total_pages = math.ceil(total_commands / PAGE_SIZE)
        if self.page < total_pages - 1:
            self.page += 1
        embed = create_help_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)
