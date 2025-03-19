"""
Admin commands for the VRChat World Showcase Bot.
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import re
from typing import Optional, List, Dict, Tuple
import os
from dotenv import load_dotenv

# Define the creator user ID
CREATOR_USER_ID = os.getenv("CREATOR_USER_ID")
import config as config
from database.models import ServerChannels, ServerTags
from database.db import log_activity
from utils.api import extract_world_id
from ui.buttons import WorldButton
from database.models import WorldPosts, ThreadWorldLinks



class AdminCommands(commands.Cog):
    """Administrative commands for the bot."""
    
    def __init__(self, bot: commands.Bot):
        """
        Initialize the cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
    
    # Add this as a helper method in the class
    def _is_creator_or_admin(self, interaction: discord.Interaction) -> bool:
        """
        Check if the user is the bot creator or has administrator permissions.
        
        Args:
            interaction: Discord interaction
            
        Returns:
            True if user is creator or has admin permissions, False otherwise
        """
        # Check if user is the creator
        if interaction.user.id == CREATOR_USER_ID:
            return True
        
        # Check for administrator permissions
        return interaction.user.guild_permissions.administrator

    # Modify the default_permissions decorator to use a custom check
    def creator_or_admin():
        """
        A custom decorator to check if the user is the creator or an admin.
        """
        async def predicate(interaction: discord.Interaction) -> bool:
            # Use the method from the cog
            cog = interaction.client.get_cog('AdminCommands')
            if cog:
                return cog._is_creator_or_admin(interaction)
            
            # Fallback check if something goes wrong
            return interaction.user.id == CREATOR_USER_ID or interaction.user.guild_permissions.administrator
        
        return app_commands.check(predicate)

    # Create a specific creator-only check
    def creator_only():
        """
        A decorator that only allows the bot creator to use the command.
        """
        async def predicate(interaction: discord.Interaction) -> bool:
            # Check if user is the creator
            return interaction.user.id == CREATOR_USER_ID
        
        return app_commands.check(predicate)

    @app_commands.command(name="sync-db", description="Synchronize SQLite and PostgreSQL databases")
    @creator_only()  # Use creator_only instead of creator_or_admin
    async def sync_db_slash(self, interaction):
        """
        Force synchronization between SQLite and PostgreSQL databases.
        Only available to the bot creator.
        """
        await interaction.response.defer(thinking=True)
        
        try:
            from database.sync import sync_now
            
            # Execute sync and time it
            import time
            start_time = time.time()
            results = sync_now()
            end_time = time.time()
            
            # Prepare response embed
            embed = discord.Embed(
                title="Database Synchronization Results",
                description="Synchronized data between SQLite and PostgreSQL",
                color=discord.Color.dark_red()
            )
            
            # Add summary field
            total_sqlite_to_pg = sum([r['sqlite_to_pg'] for r in results.values()])
            total_pg_to_sqlite = sum([r['pg_to_sqlite'] for r in results.values()])
            
            embed.add_field(
                name="Summary",
                value=(
                    f"**SQLite → PostgreSQL:** {total_sqlite_to_pg} rows\n"
                    f"**PostgreSQL → SQLite:** {total_pg_to_sqlite} rows\n"
                    f"**Time taken:** {end_time - start_time:.2f} seconds"
                ),
                inline=False
            )
            
            # Add detailed results
            details = []
            for table, counts in results.items():
                if counts['sqlite_to_pg'] > 0 or counts['pg_to_sqlite'] > 0:
                    details.append(f"**{table}**: {counts['sqlite_to_pg']} to PG, {counts['pg_to_sqlite']} to SQLite")
            
            if details:
                embed.add_field(
                    name="Details",
                    value="\n".join(details),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            config.logger.error(f"Error in sync_db_slash: {e}")
            await interaction.followup.send(f"❌ An error occurred: {e}")
            
    # Add a command to view bot stats
    @app_commands.command(name="stats", description="View bot statistics")
    @creator_or_admin()
    async def stats_slash(self, interaction: discord.Interaction):
        """
        View bot statistics.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(thinking=True)
        
        from database.models import GuildTracking
        
        # Get stats
        guild_count = GuildTracking.get_guild_count()
        forums_count = GuildTracking.get_forums_count()
        all_stats = GuildTracking.get_stats()
        
        # Create embed
        embed = discord.Embed(
            title="VRChat World Showcase Bot - Statistics",
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name="Server Stats",
            value=(
                f"Total Servers: **{guild_count}**\n"
                f"Servers with Forums: **{forums_count}**\n"
                f"Current Server: **{interaction.guild.name}**"
            ),
            inline=False
        )
        
        # Add extra stats if available
        if all_stats:
            extra_stats = []
            for name, data in all_stats.items():
                if name not in ['total_guilds', 'guilds_with_forums']:
                    extra_stats.append(f"{name.replace('_', ' ').title()}: **{data['value']}**")
            
            if extra_stats:
                embed.add_field(
                    name="Additional Stats",
                    value="\n".join(extra_stats),
                    inline=False
                )
        
        # Add this server's info
        from database.models import WorldPosts
        
        # Count world posts for this server
        server_posts = len(WorldPosts.get_all_posts(interaction.guild.id))
        
        embed.add_field(
            name="This Server",
            value=(
                f"World Posts: **{server_posts}**\n"
                f"Members: **{interaction.guild.member_count}**\n"
                f"Server ID: `{interaction.guild.id}`"
            ),
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="world-create", description="Create a forum channel for VRChat world posts")
    @creator_or_admin()
    async def world_create_slash(self, interaction: discord.Interaction):
        """
        Create a new forum channel for VRChat worlds.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(thinking=True)
        
        try:
            # Create the forum channel
            forum_channel = await interaction.guild.create_forum(
                name=config.FORUM_NAME, 
                reason="To host VRChat world threads"
            )
            
            # Set up permissions for the forum channel
            everyone_role = interaction.guild.default_role
            
            # Set permissions for @everyone: completely read-only access
            await forum_channel.set_permissions(
                everyone_role,
                # General channel permissions
                view_channel=True,  # Can see the channel
                send_messages=False,  # Can't send regular messages
                
                # Thread permissions
                create_public_threads=False,  # Cannot create forum posts
                create_private_threads=False,  # Cannot create private threads
                send_messages_in_threads=False,  # Can't chat in the threads
                read_messages=True,  # Can read messages
                
                # Other restrictions
                add_reactions=False,  # Can't add reactions
                embed_links=False,  # Can't embed links
                attach_files=False,  # Can't attach files
                use_external_emojis=False,  # Can't use external emojis
                mention_everyone=False,  # Can't mention everyone
                manage_messages=False,  # Can't manage messages
                manage_threads=False,  # Can't manage threads
            )
            
            # Create tags for the forum
            created_tags = 0
            for emoji, name in config.DEFAULT_TAGS.items():
                try:
                    new_tag = await forum_channel.create_tag(name=name, emoji=emoji)
                    created_tags += 1
                    
                    # Add to database
                    ServerTags.add_tag(interaction.guild.id, new_tag.id, name, emoji)
                    
                    await asyncio.sleep(0.5)  # Avoid rate limits
                except Exception as e:
                    config.logger.error(f"Error creating tag {name}: {e}")
            
            config.logger.info(f"Created {created_tags} tags for server {interaction.guild.id}")
            
            # Try to modify forum settings using HTTP API
            try:
                # Get the bot's HTTP adapter to make direct API calls
                http = self.bot.http
                
                # Set forum settings
                await http.request(
                    discord.http.Route(
                        'PATCH', 
                        '/channels/{channel_id}', 
                        channel_id=forum_channel.id
                    ),
                    json={
                        'default_forum_layout': config.FORUM_LAYOUT_GALLERY,
                        'default_reaction_emoji': {
                            'emoji_id': None,
                            'emoji_name': config.DEFAULT_REACTION
                        },
                        'default_sort_order': 0,  # 0 = LATEST_ACTIVITY
                        'default_thread_rate_limit_per_user': 0  # No slowmode
                    }
                )
                config.logger.info(f"Successfully set forum settings for {forum_channel.id}")
                
            except Exception as api_error:
                config.logger.error(f"Failed to set forum settings: {api_error}")
                await interaction.followup.send(
                    "⚠️ Note: Some forum settings could not be applied. " +
                    "You may need to set them manually in Discord settings."
                )
            
            # Create the welcome embed first
            thread_embed = discord.Embed(
                title="Share your favorite VRChat worlds here!",
                color=discord.Color.dark_red()
            )
            thread_embed.set_image(url=config.WELCOME_IMAGE_URL)

            # Now create the thread with the embed
            thread_info = await forum_channel.create_thread(
                name="Share Your VRChat World Here!", 
                reason="New World Thread", 
                embed=thread_embed
            )
            thread = thread_info.thread
            
            # Add the world button
            view = WorldButton(allowed_user_id=interaction.user.id)  # Only allow the admin who created it
            button_embed = discord.Embed(
                description="Hiya! \n\nWelcome! Do you want to share amazing VRChat worlds with everyone?\n\nIt's super easy! Just click the button below and paste the VRChat world's URL! You can copy the URL from the VRChat website. \n\nYou'll get to pick tags in the next step, so people who love things like horror or games or chatting can easily find worlds they'll enjoy! We'll make it look super pretty with all the details!\n\nPlease don't share every VRChat world you see. Let's focus on the special ones, the ones you think are really cool or maybe even a little hidden and deserve some love! ❤️",
                color=discord.Color.dark_red()
            )
            await thread.send(embed=button_embed, view=view)

            # Update the database
            server_id = interaction.guild.id
            forum_channel_id = forum_channel.id
            thread_id = thread.id

            ServerChannels.set_forum_channel(server_id, forum_channel_id, thread_id)
            
            # Log activity
            log_activity(
                server_id, 
                "world_create", 
                f"Created forum channel {forum_channel_id} with thread {thread_id}"
            )

            await interaction.followup.send(
                f"World forum created with strict read-only permissions for everyone! " +
                f"Check out: {thread.mention}\n\n" +
                "Note: Regular users cannot create forum posts directly. " +
                "They must use the button in the pinned thread."
            )
                
        except Exception as e:
            config.logger.error(f"Error in world_create_slash: {e}")
            await interaction.followup.send(f"An error occurred: {e}")
    
    @app_commands.command(
    name="world-remove", 
    description="Remove a specific VRChat world post"
    )
    @app_commands.describe(
        world_id_or_url="The world ID or URL to remove (e.g., wrld_123... or https://vrchat.com/home/world/...)",
        thread="Or select the thread to remove"
    )
    @creator_or_admin()
    async def world_remove_slash(
        self, 
        interaction: discord.Interaction, 
        world_id_or_url: Optional[str] = None,
        thread: Optional[discord.Thread] = None
    ):
        """
        Remove a specific VRChat world post.
        """
        await interaction.response.defer(thinking=True)
        server_id = interaction.guild_id

        # Make sure at least one parameter is provided
        if not world_id_or_url and not thread:
            await interaction.followup.send(
                "⚠️ Please provide either a world ID/URL or select a thread to remove."
            )
            return

        try:
            # First, check if a forum channel is configured for this server
            forum_config = ServerChannels.get_forum_channel(server_id)
            if not forum_config:
                await interaction.followup.send("❌ No forum channel configuration found for this server.")
                return
            
            forum_channel_id = forum_config[0]
            
            # Import WorldPosts
            from database.models import WorldPosts
            
            # If thread is provided directly, use that
            if thread:
                thread_id = thread.id
                
                # Find the world associated with this thread
                world_id = WorldPosts.get_world_for_thread(server_id, thread_id)
                
                if world_id:
                    # Remove the thread-world link
                    WorldPosts.remove_post_by_thread(server_id, thread_id)
                    
                    await interaction.followup.send(
                        f"✅ Successfully removed thread {thread.mention} from the database. " +
                        f"World ID: `{world_id}`"
                    )
                    
                    # Try to delete the thread if it exists
                    try:
                        await thread.delete()
                        await interaction.followup.send(f"✅ Thread has been deleted from Discord.")
                    except Exception as e:
                        config.logger.error(f"Could not delete thread {thread_id}: {e}")
                        await interaction.followup.send(f"⚠️ Note: Could not delete the Discord thread: {e}")
                else:
                    await interaction.followup.send(
                        f"❌ No world associated with thread {thread.mention} found in the database."
                    )
                return
            
            # If we get here, we're using world_id_or_url
            world_id = None
            
            # Check if the input is a URL
            if world_id_or_url.startswith("http"):
                # Extract world ID from URL
                world_id = extract_world_id(world_id_or_url)
                if not world_id:
                    await interaction.followup.send("❌ Could not extract a valid world ID from the URL.")
                    return
            elif world_id_or_url.startswith("wrld_"):
                # This is already a world ID
                world_id = world_id_or_url
            else:
                await interaction.followup.send(
                    "❌ Invalid input. Please provide either a valid world ID (starting with 'wrld_') or a URL."
                )
                return
                
            # Now process with the extracted or provided world ID
            thread_id = WorldPosts.get_thread_for_world(server_id, world_id)
            
            if thread_id:
                # Remove the thread-world link
                WorldPosts.remove_post_by_world(server_id, world_id)
                
                await interaction.followup.send(
                    f"✅ Successfully removed world `{world_id}` from the database. " +
                    f"Thread ID: <#{thread_id}>"
                )
                
                # Try to delete the thread if it exists
                try:
                    forum_channel = interaction.client.get_channel(forum_channel_id)
                    if forum_channel:
                        thread = forum_channel.get_thread(thread_id)
                        if thread:
                            await thread.delete()
                            await interaction.followup.send(f"✅ Thread has been deleted from Discord.")
                except Exception as e:
                    config.logger.error(f"Could not delete thread {thread_id}: {e}")
                    await interaction.followup.send(f"⚠️ Note: Could not delete the Discord thread: {e}")
            else:
                await interaction.followup.send(f"❌ No world with ID `{world_id}` found in the database.")
            
        except Exception as e:
            config.logger.error(f"Error in world_remove_slash: {e}")
            await interaction.followup.send(f"❌ An error occurred: {e}")
    
    @app_commands.command(
        name="world-set", 
        description="Set up an existing forum channel for VRChat world posts"
    )
    @app_commands.describe(forum_channel="The forum channel to set up for VRChat world posts")
    @creator_or_admin()
    async def world_set_slash(
        self, 
        interaction: discord.Interaction,
        forum_channel: discord.ForumChannel
    ):
        """
        Set up an existing forum channel for VRChat worlds.
        
        Args:
            interaction: Discord interaction
            forum_channel: Discord forum channel to set up
        """
        # Log the start of the command
        config.logger.info(f"Starting world-set for server {interaction.guild_id}")
        
        # Use a more explicit try-except block
        try:
            # Ensure we have a valid interaction response
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=False)
            
            server_id = interaction.guild.id
            
            # Perform initial checks and configurations
            forum_config = ServerChannels.get_forum_channel(server_id)

            # Prepare an initial status message
            status_message = "Preparing to set up forum channel..."
            try:
                # Try to send an initial message
                status_msg = await interaction.followup.send(status_message, ephemeral=False)
            except Exception as initial_error:
                config.logger.error(f"Error sending initial status message: {initial_error}")
                # If sending fails, we'll continue and rely on error logging
                status_msg = None

            # Get all threads in the forum
            threads = list(forum_channel.threads)
            try:
                # Also get archived threads
                archived_threads = [thread async for thread in forum_channel.archived_threads(limit=None)]
                threads.extend(archived_threads)
            except Exception as archive_error:
                config.logger.error(f"Error fetching archived threads: {archive_error}")
            
            # Track processing
            total_threads = len(threads)
            processed_count = 0
            worlds_found = 0
            unknown_threads = []
            
            # Import APIs
            from utils.api import extract_world_id, VRChatAPI
            
            # Update status periodically
            async def update_status():
                try:
                    if status_msg:
                        await status_msg.edit(
                            content=f"⌛ Scanning existing forum posts for VRChat worlds... "
                                    f"({processed_count}/{total_threads} threads processed, "
                                    f"{worlds_found} worlds found)"
                        )
                except Exception as status_error:
                    config.logger.error(f"Error updating status message: {status_error}")
            
            # Process each thread
            for thread in threads:
                try:
                    # Skip control threads
                    if thread.name in ["Please post here to provide information and display it to the world", 
                                    "Share Your VRChat World Here!"]:
                        processed_count += 1
                        continue
                    
                    # Get messages
                    messages = []
                    async for message in thread.history(limit=3, oldest_first=True):
                        messages.append(message)
                    
                    # Skip if no messages
                    if not messages:
                        processed_count += 1
                        continue
                    
                    first_message = messages[0]
                    world_id = None
                    world_url = None
                    
                    # Check embeds first
                    if first_message.embeds:
                        for embed in first_message.embeds:
                            if embed.url and "vrchat.com/home/world" in embed.url:
                                world_url = embed.url
                                world_id = extract_world_id(world_url)
                                break
                    
                    # Check message content if no world ID from embeds
                    if not world_id and first_message.content:
                        urls = re.findall(
                            r'https://vrchat\.com/home/world/wrld_[a-zA-Z0-9_-]+(?:/info)?', 
                            first_message.content
                        )
                        if urls:
                            world_url = urls[0]
                            world_id = extract_world_id(world_url)
                    
                    # Process found world
                    if world_id:
                        existing_thread = WorldPosts.get_thread_for_world(server_id, world_id)
                        
                        if existing_thread and existing_thread != thread.id:
                            # Duplicate world
                            unknown_threads.append({
                                "thread_id": thread.id,
                                "thread_name": thread.name,
                                "world_id": world_id,
                                "world_url": world_url,
                                "issue_type": "duplicate",
                                "duplicate_thread_id": existing_thread
                            })
                        elif not existing_thread:
                            # New world to add
                            WorldPosts.add_world_post(
                                server_id=server_id,
                                user_id=first_message.author.id if first_message.author else 0,
                                thread_id=thread.id,
                                world_id=world_id,
                                world_link=world_url or f"https://vrchat.com/home/world/{world_id}"
                            )
                            worlds_found += 1
                    else:
                        # No world found
                        unknown_threads.append({
                            "thread_id": thread.id,
                            "thread_name": thread.name,
                            "issue_type": "no_world_link", 
                            "message_sample": first_message.content[:100] if first_message.content else "No content"
                        })
                    
                    # Update processed count
                    processed_count += 1
                    
                    # Update status periodically
                    if processed_count % 5 == 0:
                        await update_status()
                
                except Exception as thread_error:
                    config.logger.error(f"Error processing thread {thread.id}: {thread_error}")
                    processed_count += 1
            
            # Final status update
            try:
                if status_msg:
                    await status_msg.edit(
                        content=f"✅ Scan complete! Processed {total_threads} threads, found {worlds_found} VRChat worlds."
                    )
            except Exception as final_status_error:
                config.logger.error(f"Error updating final status: {final_status_error}")
            
            # Check if a "Share Your VRChat World Here!" thread already exists
            existing_welcome_thread = None
            for thread in threads:
                if thread.name == "Share Your VRChat World Here!":
                    existing_welcome_thread = thread
                    break
            
            if existing_welcome_thread:
                # Use the existing welcome thread
                config.logger.info(f"Using existing welcome thread: {existing_welcome_thread.id}")
                thread = existing_welcome_thread
                
                # Check if it already has the button message
                has_button = False
                async for message in thread.history(limit=10):
                    if message.author.id == self.bot.user.id and message.embeds:
                        for embed in message.embeds:
                            if embed.description and "Hiya! \n\nWelcome! Do you want to share amazing VRChat worlds with everyone?" in embed.description:
                                has_button = True
                                break
                        if has_button:
                            break
                
                # If no button exists, add one
                if not has_button:
                    view = WorldButton()
                    button_embed = discord.Embed(
                        description="Hiya! \n\nWelcome! Do you want to share amazing VRChat worlds with everyone?\n\nIt's super easy! Just click the button below and paste the VRChat world's URL! You can copy the URL from the VRChat website. \n\nYou'll get to pick tags in the next step, so people who love things like horror or games or chatting can easily find worlds they'll enjoy! We'll make it look super pretty with all the details!\n\nPlease don't share every VRChat world you see. Let's focus on the special ones, the ones you think are really cool or maybe even a little hidden and deserve some love! ❤️",
                        color=discord.Color.dark_red()
                    )
                    await thread.send(embed=button_embed, view=view)
                    config.logger.info(f"Added world button to existing welcome thread {thread.id}")
            else:
                # Create a new welcome thread
                embed = discord.Embed(
                    title="Share your favorite VRChat worlds here!",
                    color=discord.Color.dark_red()
                )
                embed.set_image(url=config.WELCOME_IMAGE_URL)

                thread_info = await forum_channel.create_thread(
                    name="Share Your VRChat World Here!", 
                    reason="New World Thread", 
                    embed=embed
                )
                thread = thread_info.thread
                
                # Add world button
                view = WorldButton()
                button_embed = discord.Embed(
                    description="Hiya! \n\nWelcome! Do you want to share amazing VRChat worlds with everyone?\n\nIt's super easy! Just click the button below and paste the VRChat world's URL! You can copy the URL from the VRChat website. \n\nYou'll get to pick tags in the next step, so people who love things like horror or games or chatting can easily find worlds they'll enjoy! We'll make it look super pretty with all the details!\n\nPlease don't share every VRChat world you see. Let's focus on the special ones, the ones you think are really cool or maybe even a little hidden and deserve some love! ❤️",
                    color=discord.Color.dark_red()
                )
                await thread.send(embed=button_embed, view=view)

            # Add tags
            added_tags = await self._sync_forum_tags(server_id, forum_channel)
            tag_msg = f"\n{added_tags} new tags added to database." if added_tags > 0 else ""
            
            # Update database
            ServerChannels.set_forum_channel(server_id, forum_channel.id, thread.id)
            
            # Log activity
            log_activity(
                server_id, 
                "world_set", 
                f"Set forum channel to {forum_channel.id} with thread {thread.id}"
            )

            # Send final confirmation
            try:
                await interaction.followup.send(
                    f"✅ Forum channel set to {forum_channel.mention}\n" +
                    f"Using world submission thread: {thread.mention}{tag_msg}\n" +
                    f"Total worlds indexed: **{worlds_found}**"
                )
            except Exception as final_error:
                config.logger.error(f"Error sending final confirmation: {final_error}")
                # Fallback logging if sending fails
                config.logger.info(
                    f"Forum channel set to {forum_channel.id}, "
                    f"thread created {thread.id}, "
                    f"worlds indexed: {worlds_found}"
                )
            
        except Exception as main_error:
            # Comprehensive error logging
            config.logger.error(f"Critical error in world_set_slash: {main_error}", exc_info=True)
            
            # Multiple attempts to communicate the error
            error_message = f"❌ An error occurred: {main_error}"
            try:
                # First attempt: use followup
                await interaction.followup.send(error_message)
            except:
                try:
                    # Second attempt: use response
                    if not interaction.response.is_done():
                        await interaction.response.send_message(error_message)
                except:
                    # Last resort: log the error
                    config.logger.critical(f"Could not send error message: {error_message}")
    
    @app_commands.command(
        name="sync", 
        description="Sync bot commands (admin only)"
    )
    @creator_or_admin()
    async def sync_slash(self, interaction: discord.Interaction):
        """
        Sync slash commands with Discord.
        
        Args:
            interaction: Discord interaction
        """
        if interaction.user.guild_permissions.administrator:
            await interaction.response.defer(thinking=True)
            try:
                synced = await self.bot.tree.sync()
                await interaction.followup.send(f"Synced {len(synced)} command(s)")
            except Exception as e:
                await interaction.followup.send(f"Failed to sync commands: {e}")
        else:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.", 
                ephemeral=True
            )
    
    async def _scan_forum_threads(self, server_id: int, forum_channel: discord.ForumChannel) -> Tuple[int, List[Dict]]:
        """
        Scan forum threads for VRChat worlds with improved accuracy.
        
        Args:
            server_id: Discord server ID
            forum_channel: Discord forum channel
                
        Returns:
            Tuple of (worlds_found, unknown_threads_data)
        """
        worlds_found = 0
        unknown_threads = []
        
        # Get all threads in the forum
        threads = [thread for thread in forum_channel.threads]
        try:
            # Also get archived threads
            archived_threads = [thread async for thread in forum_channel.archived_threads(limit=None)]
            threads.extend(archived_threads)
        except Exception as e:
            config.logger.error(f"Error fetching archived threads: {e}")
        
        # Import APIs
        from utils.api import extract_world_id, VRChatAPI
        vrchat_api = VRChatAPI(config.AUTH)
        
        # Process each thread
        for thread in threads:
            try:
                # Skip the control thread
                if thread.name == "Please post here to provide information and display it to the world":
                    continue
                    
                # Get the first 3 messages (original post + possible follow-ups)
                world_id = None
                world_url = None
                messages = []
                
                async for message in thread.history(limit=3, oldest_first=True):
                    messages.append(message)
                
                # Get the first message (original post)
                if messages:
                    first_message = messages[0]
                    
                    # Check if the message has embeds with a URL
                    if first_message.embeds:
                        for embed in first_message.embeds:
                            # Look for VRChat world URL in the embed url
                            if embed.url and "vrchat.com/home/world" in embed.url:
                                world_url = embed.url
                                world_id = extract_world_id(embed.url)
                                break
                    
                    # Check message content for VRChat links if we didn't find one in embeds
                    if not world_id and first_message.content:
                        # Look for VRChat world URLs in the message
                        urls = re.findall(
                            r'https://vrchat\.com/home/world/wrld_[a-zA-Z0-9_-]+(?:/info)?', 
                            first_message.content
                        )
                        if urls:
                            world_url = urls[0]
                            world_id = extract_world_id(world_url)
                
                # If we found a valid world ID
                if world_id:
                    # Check if this world already exists in the database
                    existing_thread = WorldPosts.get_thread_for_world(server_id, world_id)
                    
                    if existing_thread and existing_thread != thread.id:
                        # This is a duplicate - the same world exists in another thread
                        unknown_threads.append({
                            "thread_id": thread.id,
                            "thread_name": thread.name,
                            "world_id": world_id,
                            "world_url": world_url,
                            "issue_type": "duplicate",
                            "duplicate_thread_id": existing_thread
                        })
                    elif not existing_thread:
                        # This is a valid world that's not in our database yet - add it
                        WorldPosts.add_world_post(
                            server_id=server_id,
                            user_id=first_message.author.id if first_message.author else 0,
                            thread_id=thread.id,
                            world_id=world_id,
                            world_link=world_url or f"https://vrchat.com/home/world/{world_id}"
                        )
                        worlds_found += 1
                else:
                    # No world ID found - check if it might be a valid thread we just can't parse
                    # This would be a candidate for manual review
                    unknown_threads.append({
                        "thread_id": thread.id,
                        "thread_name": thread.name,
                        "issue_type": "no_world_link", 
                        "message_sample": first_message.content[:100] if messages and messages[0].content else "No content"
                    })
            except Exception as e:
                config.logger.error(f"Error processing thread {thread.id}: {e}")
                continue
        
        return worlds_found, unknown_threads
    
    async def _sync_forum_tags(self, server_id: int, forum_channel: discord.ForumChannel) -> int:
        """
        Synchronize forum tags with database.
        
        Args:
            server_id: Discord server ID
            forum_channel: Discord forum channel
            
        Returns:
            Number of tags added
        """
        # If there are no tags in the forum, create default ones
        if not forum_channel.available_tags:
            config.logger.info(f"No tags found in forum channel for server {server_id}. Creating default tags...")
            created_count = 0
            
            # Create default tags in the forum
            for emoji, name in config.DEFAULT_TAGS.items():
                try:
                    new_tag = await forum_channel.create_tag(name=name, emoji=emoji)
                    
                    # Add to database
                    ServerTags.add_tag(server_id, new_tag.id, name, emoji)
                    
                    created_count += 1
                    await asyncio.sleep(0.5)  # Avoid rate limits
                except Exception as e:
                    config.logger.error(f"Error creating tag {name}: {e}")
            
            config.logger.info(f"Created {created_count} tags for server {server_id}")
            return created_count
        
        # Convert forum tags to a format compatible with ServerTags.sync_tags
        forum_tags = []
        moderated_tags = []
        
        for tag in forum_channel.available_tags:
            # Check if this tag has the moderator-only setting
            is_moderated = False
            try:
                # Try accessing the moderated attribute directly
                is_moderated = getattr(tag, "moderated", False)
            except AttributeError:
                # If that fails, try the __dict__ approach
                if hasattr(tag, "__dict__"):
                    is_moderated = tag.__dict__.get("moderated", False)
            
            if is_moderated:
                moderated_tags.append((tag.id, tag.name))
                config.logger.info(f"Skipping moderated tag '{tag.name}' (ID: {tag.id}) from database sync")
            else:
                forum_tags.append({
                    'id': tag.id,
                    'name': tag.name,
                    'emoji': str(tag.emoji) if tag.emoji else None
                })
        
        if moderated_tags:
            config.logger.info(f"Skipped {len(moderated_tags)} moderated tags during sync: {', '.join(name for _, name in moderated_tags)}")
        
        # Sync tags with database
        added, updated, removed = ServerTags.sync_tags(server_id, forum_tags)
        return added

    @app_commands.command(
        name="repair-threads", 
        description="Repair threads that don't have proper world links"
    )
    @creator_or_admin()
    async def repair_threads_slash(self, interaction):
        """
        Repair forum threads that don't have proper world links.
        """
        await interaction.response.defer(thinking=True)
        server_id = interaction.guild_id
        
        try:
            # First, check if a forum channel is configured for this server
            forum_config = ServerChannels.get_forum_channel(server_id)
            if not forum_config:
                await interaction.followup.send("❌ No forum channel configuration found for this server.")
                return
            
            forum_channel_id = forum_config[0]
            forum_channel = interaction.client.get_channel(forum_channel_id)
            
            if not forum_channel:
                await interaction.followup.send("❌ Could not find the configured forum channel. It may have been deleted.")
                return
            
            # Step 1: Try to repair threads with the repair function
            fixed_count = WorldPosts.repair_missing_threads(server_id)
            
            # Step 2: Scan forum for threads without world links
            threads = [thread for thread in forum_channel.threads]
            try:
                # Also get archived threads
                archived_threads = [thread async for thread in forum_channel.archived_threads(limit=100)]
                threads.extend(archived_threads)
            except Exception as e:
                config.logger.error(f"Error fetching archived threads: {e}")
            
            # Create a list to store threads that still don't have world links
            no_world_threads = []
            
            # Process each thread
            added_count = 0
            for thread in threads:
                try:
                    # Skip the control thread
                    if thread.name == "Please post here to provide information and display it to the world" or thread.name == "Share Your VRChat World Here!":
                        continue
                    
                    # Check if this thread already has a world link
                    thread_id = thread.id
                    world_id = WorldPosts.get_world_for_thread(server_id, thread_id)
                    
                    if not world_id:
                        # Thread doesn't have a world link, try to find one in the messages
                        world_found = False
                        
                        # Check the first message for VRChat links
                        async for message in thread.history(limit=3, oldest_first=True):
                            # Check embed URLs
                            if message.embeds:
                                for embed in message.embeds:
                                    if embed.url and "vrchat.com/home/world" in embed.url:
                                        found_world_id = extract_world_id(embed.url)
                                        if found_world_id:
                                            # Make sure this world ID isn't assigned to another thread
                                            existing_thread = WorldPosts.get_thread_for_world(server_id, found_world_id)
                                            if not existing_thread:
                                                # Add to database
                                                WorldPosts.add_world_post(
                                                    server_id=server_id,
                                                    user_id=message.author.id if message.author else 0,
                                                    thread_id=thread_id,
                                                    world_id=found_world_id,
                                                    world_link=embed.url
                                                )
                                                added_count += 1
                                                world_found = True
                                                break
                            
                            # Check message content for VRChat links
                            if not world_found and message.content:
                                urls = re.findall(
                                    r'https://vrchat\.com/home/world/wrld_[a-zA-Z0-9_-]+(?:/info)?', 
                                    message.content
                                )
                                for url in urls:
                                    found_world_id = extract_world_id(url)
                                    if found_world_id:
                                        # Make sure this world ID isn't assigned to another thread
                                        existing_thread = WorldPosts.get_thread_for_world(server_id, found_world_id)
                                        if not existing_thread:
                                            # Add to database
                                            WorldPosts.add_world_post(
                                                server_id=server_id,
                                                user_id=message.author.id if message.author else 0,
                                                thread_id=thread_id,
                                                world_id=found_world_id,
                                                world_link=url
                                            )
                                            added_count += 1
                                            world_found = True
                                            break
                            
                            if world_found:
                                break
                        
                        # If still no world found, add to the list of threads without worlds
                        if not world_found:
                            no_world_threads.append((thread_id, thread.name))
                            
                except Exception as e:
                    config.logger.error(f"Error processing thread {thread.id}: {e}")
                    continue
            
            # Create response message
            embed = discord.Embed(
                title="Thread Repair Results",
                description="",
                color=discord.Color.dark_red()
            )
            
            embed.description += f"✅ Fixed {fixed_count} threads with database repairs\n"
            embed.description += f"✅ Added {added_count} world links from thread content\n"
            
            if no_world_threads:
                embed.description += f"\n⚠️ Still found {len(no_world_threads)} threads without VRChat worlds:\n"
                
                # Only show up to 10 to avoid making the embed too long
                for i, (thread_id, thread_name) in enumerate(no_world_threads[:10]):
                    embed.description += f"- {thread_name} (ID: {thread_id})\n"
                    
                if len(no_world_threads) > 10:
                    embed.description += f"...and {len(no_world_threads) - 10} more threads\n"
                    
                embed.description += "\nYou can use `/scan` to find and remove these empty threads."
            else:
                embed.description += "\n✅ All threads now have proper world links!"
                
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            config.logger.error(f"Error in repair_threads_slash: {e}")
            await interaction.followup.send(f"❌ An error occurred: {e}")
        
async def setup(bot: commands.Bot):
    """
    Set up the cog.
    
    Args:
        bot: The bot instance
    """
    await bot.add_cog(AdminCommands(bot))