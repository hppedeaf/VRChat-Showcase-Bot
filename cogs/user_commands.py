"""
User-facing commands for the VRChat World Showcase Bot.
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import config as config
from utils.embed_builders import build_about_embed, build_help_embed
from ui.buttons import WorldButton

class UserCommands(commands.Cog):
    """User-facing commands for the bot."""
    
    def __init__(self, bot: commands.Bot):
        """
        Initialize the cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
    
    @app_commands.command(name="test", description="Test if the bot is online")
    async def test_slash(self, interaction: discord.Interaction):
        """
        Test if the bot is online.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.send_message("Bot is online!")
    
    @app_commands.command(name="world", description="Create a new VRChat world post button")
    async def world_slash(self, interaction: discord.Interaction):
        """
        Create a world submission button.
        
        Args:
            interaction: Discord interaction
        """
        view = WorldButton(allowed_user_id=interaction.user.id)  # Only allow the command user
        embed = discord.Embed(
            description="Hiya! \n\nWelcome! Do you want to share amazing VRChat worlds with everyone?\n\nIt's super easy! Just click the button below and paste the VRChat world's URL! You can copy the URL from the VRChat website. \n\nYou'll get to pick tags in the next step, so people who love things like horror or games or chatting can easily find worlds they'll enjoy! We'll make it look super pretty with all the details!\n\nPlease don't share every VRChat world you see. Let's focus on the special ones, the ones you think are really cool or maybe even a little hidden and deserve some love! ❤️",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="about", description="Learn what this bot does and how to use it")
    async def about_slash(self, interaction: discord.Interaction):
        """
        Display information about the bot.
        
        Args:
            interaction: Discord interaction
        """
        embed = build_about_embed()
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="help", description="Show a list of available commands")
    async def help_slash(self, interaction: discord.Interaction):
        """
        Display a list of all available commands.
        
        Args:
            interaction: Discord interaction
        """
        embed = build_help_embed()
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    """
    Set up the cog.
    
    Args:
        bot: The bot instance
    """
    await bot.add_cog(UserCommands(bot))