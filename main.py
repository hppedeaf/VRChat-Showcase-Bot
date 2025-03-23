"""
Main entry point for the VRChat World Showcase Bot.
"""
import asyncio
import discord
from discord.ext import commands
import os
import sys
import time
from datetime import datetime

# Add the bot directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

import config as config
from database.db import setup_database, check_postgres_availability
from database.pg_handler import add_missing_columns

# Track bot uptime
start_time = datetime.now()
guild_count = 0
worlds_count = 0

# Create bot with proper intents
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
        
        # Load cogs - make sure each cog is loaded only once
        await self.load_extension("cogs.user_commands")
        await self.load_extension("cogs.admin_commands")
        await self.load_extension("cogs.maintenance")
        config.logger.info("Cogs loaded")
        
        # If PostgreSQL is available, make sure the schema is up-to-date
        if check_postgres_availability():
            try:
                add_missing_columns()
                config.logger.info("PostgreSQL schema updated with any missing columns")
            except Exception as e:
                config.logger.error(f"Failed to update PostgreSQL schema: {e}")
    
    async def on_ready(self):
        """Handle bot ready event."""
        global guild_count, worlds_count, start_time
        
        config.logger.info(f'Logged in as {self.user.name}')
        
        # Update stats
        guild_count = len(self.guilds)
        
        # Count worlds across all servers - use a more efficient approach
        try:
            # Use a direct database count instead of loading all records
            from database.models import WorldPosts
            from database.db import get_connection, IS_POSTGRES
            
            total_worlds = 0
            with get_connection() as conn:
                cursor = conn.cursor()
                
                if IS_POSTGRES:
                    # Use a simpler query that avoids loading all records
                    cursor.execute("SELECT COUNT(*) FROM thread_world_links")
                else:
                    cursor.execute("SELECT COUNT(*) FROM thread_world_links")
                    
                result = cursor.fetchone()
                if result:
                    total_worlds = result[0]
                    
            worlds_count = total_worlds
            config.logger.info(f"Counted {worlds_count} worlds across all servers")
        except Exception as e:
            config.logger.error(f"Error counting worlds: {e}")
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            config.logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            config.logger.error(f"Failed to sync commands: {e}")
        
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
                            color=discord.Color.dark_red()
                        )
                        await channel.send(embed=embed, view=view)
                        config.logger.info(f"Added world button to thread {thread_id}, allowed user: {admin_id}")
                        
                except Exception as e:
                    config.logger.error(f"Error checking thread {thread_id}: {e}")

        config.logger.info("All threads have been checked and world buttons added where needed.")
        
        # Update guild tracking in the database
        await self.update_guild_stats()
        
    async def on_guild_join(self, guild):
        """Handle bot joining a new guild."""
        global guild_count
        guild_count += 1
        
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
                    color=discord.Color.dark_red()
                )
                
                try:
                    await channel.send(embed=embed)
                    break
                except:
                    continue

    async def on_guild_remove(self, guild):
        """Handle bot leaving a guild."""
        global guild_count
        guild_count -= 1
        
        config.logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
        
        # Update the database
        from database.models import GuildTracking
        GuildTracking.remove_guild(guild.id)

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
        
        # Start periodic task to update guild stats every hour
        self.bg_task = self.loop.create_task(self._periodic_guild_update())
    
    async def _periodic_guild_update(self):
        """Periodically update guild statistics with improved error handling and non-blocking design."""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                # Process each guild with individual error handling and proper async handling
                update_tasks = []
                for guild in self.guilds:
                    # Use a separate task for each guild update to avoid blocking
                    task = asyncio.create_task(self._update_single_guild(guild))
                    update_tasks.append(task)
                
                # Wait for all update tasks with a timeout
                if update_tasks:
                    done, pending = await asyncio.wait(update_tasks, timeout=30)
                    
                    # Cancel any pending tasks that didn't complete within timeout
                    for task in pending:
                        task.cancel()
                        config.logger.warning(f"Guild update task timed out and was cancelled")
                
                # Update global stats using a non-blocking approach
                await self._update_global_stats()
                
                config.logger.info(f"Updated guild stats: {len(self.guilds)} guilds, {worlds_count} worlds")
                
                # Check PostgreSQL availability using a separate task
                asyncio.create_task(self._check_database_availability())
                
            except Exception as e:
                config.logger.error(f"Error in periodic guild update: {e}")
                
            # Sleep for 1 hour
            await asyncio.sleep(3600)

    async def _update_single_guild(self, guild):
        """Update stats for a single guild in a non-blocking way."""
        try:
            # Use a thread pool executor for database operations
            from concurrent.futures import ThreadPoolExecutor
            from database.models import GuildTracking, ServerChannels
            
            # Run database operations in a thread pool to avoid blocking the event loop
            with ThreadPoolExecutor(max_workers=1) as executor:
                # Update member count
                await self.loop.run_in_executor(
                    executor, 
                    GuildTracking.update_member_count, 
                    guild.id, 
                    guild.member_count
                )
                
                # Check if this guild has a forum channel set up (also in thread pool)
                forum_config = await self.loop.run_in_executor(
                    executor,
                    ServerChannels.get_forum_channel,
                    guild.id
                )
                has_forum = forum_config is not None
                
                # Update forum status
                await self.loop.run_in_executor(
                    executor,
                    GuildTracking.update_guild_status,
                    guild.id,
                    has_forum
                )
        except Exception as e:
            config.logger.error(f"Error updating guild {guild.id}: {e}")

    async def _update_global_stats(self):
        """Update global statistics in a non-blocking way."""
        try:
            # Use a thread pool executor for database operations
            from concurrent.futures import ThreadPoolExecutor
            from database.db import get_connection, IS_POSTGRES
            
            # Update worlds count
            global worlds_count
            
            def count_worlds():
                try:
                    with get_connection() as conn:
                        cursor = conn.cursor()
                        
                        # Set a short timeout
                        if IS_POSTGRES:
                            cursor.execute("SET statement_timeout = 3000")  # 3 second timeout
                            cursor.execute("SELECT COUNT(*) FROM thread_world_links")
                        else:
                            cursor.execute("SELECT COUNT(*) FROM thread_world_links")
                            
                        result = cursor.fetchone()
                        if result:
                            return result[0]
                        return 0
                except Exception as e:
                    config.logger.error(f"Error counting worlds: {e}")
                    return worlds_count  # Return existing count on error
            
            # Run in thread pool
            with ThreadPoolExecutor(max_workers=1) as executor:
                new_count = await self.loop.run_in_executor(executor, count_worlds)
                worlds_count = new_count
                
        except Exception as e:
            config.logger.error(f"Error updating global stats: {e}")

    async def _check_database_availability(self):
        """Check database availability in a non-blocking way."""
        try:
            from concurrent.futures import ThreadPoolExecutor
            from database.db import check_postgres_availability
            
            # Run database check in thread pool
            with ThreadPoolExecutor(max_workers=1) as executor:
                await self.loop.run_in_executor(executor, check_postgres_availability)
        except Exception as e:
            config.logger.error(f"Error checking database availability: {e}")

async def main():
    """Main function to start the bot."""
    # Initialize the bot
    bot = VRChatBot()
    
    # Create the bot as a global variable
    global bot_instance
    bot_instance = bot
    
    # Run the bot with the token from config
    try:
        await bot.start(config.TOKEN)
    except discord.errors.LoginFailure:
        config.logger.critical("Invalid Discord token. Please check your token and try again.")
        print("ERROR: Invalid Discord token. Please check your .env file.")
    except Exception as e:
        config.logger.critical(f"Failed to start bot: {e}")
        print(f"ERROR: Failed to start bot: {e}")

# Define the uptime property
def uptime() -> str:
    """Calculate the bot's uptime."""
    delta = datetime.now() - start_time
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    days = delta.days
    
    if days:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    else:
        return f"{hours}h {minutes}m {seconds}s"

if __name__ == "__main__":
    # Check if token exists
    if not config.TOKEN:
        config.logger.critical("Discord token not found! Please add your bot token to a .env file.")
        print("ERROR: Discord token not found! Please create a .env file with DISCORD_TOKEN=your_token")
        exit(1)
    
    # Set up the database
    try:
        setup_database()
    except Exception as e:
        config.logger.error(f"Database setup error: {e}")
        print(f"WARNING: Database setup error: {e}")
    
    # Run the bot
    asyncio.run(main())