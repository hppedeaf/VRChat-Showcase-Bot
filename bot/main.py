"""
Main entry point for the VRChat World Showcase Bot.
"""
import asyncio
import discord
from discord.ext import commands
import config
from database.db import setup_database

# Add these imports for Flask
from flask import Flask, request, jsonify
import threading
import os

# Flask app setup
app = Flask(__name__)

@app.route('/api/interactions', methods=['POST'])
def interactions():
    # Handle Discord interactions
    return jsonify({"type": 1})

@app.route('/api/verify', methods=['GET', 'POST'])
def verify():
    # Handle role verification
    return jsonify({"success": True})

# Add this route to serve your website's main page
@app.route('/')
def index():
    return app.send_static_file('index.html')

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    
# Discord Bot setup
intents = discord.Intents.default()
intents.message_content = True

class VRChatBot(commands.Bot):
    """Main bot class."""
    
    def __init__(self):
        """Initialize the bot."""
        super().__init__(command_prefix="&", intents=intents)
        
    async def setup_hook(self):
        """Set up the bot hooks."""
        # Register UI components that need to persist
        from ui.buttons import WorldButton
        self.add_view(WorldButton())
        config.logger.info("Persistent views registered")
        
        # Load cogs
        await self.load_extension("cogs.user_commands")
        await self.load_extension("cogs.admin_commands")
        await self.load_extension("cogs.maintenance")
        config.logger.info("Cogs loaded")
    
    async def on_ready(self):
        """Handle bot ready event."""
        config.logger.info(f'Logged in as {self.user.name}')
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            config.logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            config.logger.error(f"Failed to sync commands: {e}")
            
        # Set up the database
        setup_database()
        
        # Check threads based on thread ID and add world button if needed
        from database.models import ServerChannels
        
        servers = {}
        for guild in self.guilds:
            forum_config = ServerChannels.get_forum_channel(guild.id)
            if forum_config:
                forum_channel_id, thread_id = forum_config
                servers[guild.id] = {"forum_channel_id": forum_channel_id, "thread_id": thread_id}
        
        for server_id, data in servers.items():
            thread_id = data["thread_id"]
            guild = self.get_guild(server_id)
            channel = self.get_channel(thread_id)  # Get the channel using the thread ID
            
            if channel:
                try:
                    # Check if there's already a button message in the thread
                    button_found = False
                    async for message in channel.history(limit=25):
                        # Check if the message is from the bot and has an embed
                        if message.author == self.user and message.embeds:
                            for embed in message.embeds:
                                if embed.description and "Hiya! \n\nWelcome! Do you want to share amazing VRChat worlds with everyone?" in embed.description:
                                    config.logger.info(f"Button already exists in thread {thread_id}")
                                    button_found = True
                                    break
                            if button_found:
                                break
                    
                    if not button_found:
                        # No button found, add one
                        # Find an admin user to assign as the allowed user
                        admin_id = None
                        try:
                            # Try to find a server admin
                            for member in guild.members:
                                if member.guild_permissions.administrator:
                                    admin_id = member.id
                                    break
                        except:
                            # If we can't find an admin, we'll create a button with no user restriction
                            pass
                        
                        from ui.buttons import WorldButton
                        view = WorldButton(allowed_user_id=admin_id)  # Allow only an admin if found
                        embed = discord.Embed(
                            description="Hiya! \n\nWelcome! Do you want to share amazing VRChat worlds with everyone?\n\nIt's super easy! Just click the button below and paste the VRChat world's URL! You can copy the URL from the VRChat website. \n\nYou'll get to pick tags in the next step, so people who love things like horror or games or chatting can easily find worlds they'll enjoy! We'll make it look super pretty with all the details!\n\nPlease don't share every VRChat world you see. Let's focus on the special ones, the ones you think are really cool or maybe even a little hidden and deserve some love! ❤️",
                            color=discord.Color.yellow()
                        )
                        await channel.send(embed=embed, view=view)
                        config.logger.info(f"Added world button to thread {thread_id}, allowed user: {admin_id}")
                        
                except Exception as e:
                    config.logger.error(f"Error checking thread {thread_id}: {e}")

        config.logger.info("All threads have been checked and world buttons added where needed.")
        
    async def on_guild_join(self, guild):
        """Handle bot joining a new guild."""
        config.logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        
        # Send welcome message to the first available text channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                embed = discord.Embed(
                    title="VRChat World Showcase Bot",
                    description=(
                        "Thanks for adding me to your server! I help you create and manage a showcase " +
                        "of VRChat worlds in a forum channel.\n\n" +
                        "To get started, run `/world-create` to create a new forum channel " +
                        "or `/world-set` to use an existing one.\n\n" +
                        "For more information, run `/about` or `/help`."
                    ),
                    color=discord.Color.blue()
                )
                
                try:
                    await channel.send(embed=embed)
                    break
                except:
                    continue
                
    async def on_guild_join(self, guild):
        """Handle bot joining a new guild."""
        config.logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        
        # Track the guild in the database
        from database.models import GuildTracking
        GuildTracking.add_guild(guild.id, guild.name, guild.member_count)
        
        # Send welcome message to the first available text channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                embed = discord.Embed(
                    title="VRChat World Showcase Bot",
                    description=(
                        "Thanks for adding me to your server! I help you create and manage a showcase " +
                        "of VRChat worlds in a forum channel.\n\n" +
                        "To get started, run `/world-create` to create a new forum channel " +
                        "or `/world-set` to use an existing one.\n\n" +
                        "For more information, run `/about` or `/help`."
                    ),
                    color=discord.Color.blue()
                )
                
                try:
                    await channel.send(embed=embed)
                    break
                except:
                    continue

    async def on_guild_remove(self, guild):
        """Handle bot leaving a guild."""
        config.logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
        
        # Update the database
        from database.models import GuildTracking
        GuildTracking.remove_guild(guild.id)

    # Add this to your periodic task or create a new maintenance cog
    async def update_guild_stats(self):
        """Update guild statistics periodically."""
        from database.models import GuildTracking, ServerChannels
        
        for guild in self.guilds:
            # Update member count
            GuildTracking.update_member_count(guild.id, guild.member_count)
            
            # Check if this guild has a forum channel set up
            forum_config = ServerChannels.get_forum_channel(guild.id)
            has_forum = forum_config is not None
            
            # Update forum status
            GuildTracking.update_guild_status(guild.id, has_forum)

async def main():
    """Main function to start the bot."""
    # Initialize the bot
    bot = VRChatBot()
    
    # Run the bot with the token from config
    try:
        await bot.start(config.TOKEN)
    except discord.errors.LoginFailure:
        config.logger.critical("Invalid Discord token. Please check your token and try again.")
        print("ERROR: Invalid Discord token. Please check your .env file.")
    except Exception as e:
        config.logger.critical(f"Failed to start bot: {e}")
        print(f"ERROR: Failed to start bot: {e}")

if __name__ == "__main__":
    # Check if token exists
    if not config.TOKEN:
        config.logger.critical("Discord token not found! Please add your bot token to a .env file.")
        print("ERROR: Discord token not found! Please create a .env file with DISCORD_TOKEN=your_token")
        exit(1)
    
    # Run the bot
    asyncio.run(main())