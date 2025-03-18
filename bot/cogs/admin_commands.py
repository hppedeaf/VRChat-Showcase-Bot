"""
Admin commands for the VRChat World Showcase Bot.
"""
import time
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import re
from typing import Optional, List, Dict, Tuple
import bot.config as config
from database.models import ServerChannels, ServerTags
from database.db import log_activity
from utils.api import extract_world_id, VRChatAPI
from ui.buttons import WorldButton
import bot.config as config
from database.models import ServerChannels, WorldPosts, ServerTags

class AdminCommands(commands.Cog):
    """Administrative commands for the bot."""
    
    def __init__(self, bot: commands.Bot):
        """
        Initialize the cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
    
    # Add a command to view bot stats
    @app_commands.command(name="stats", description="View bot statistics")
    @app_commands.default_permissions(administrator=True)
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
            color=discord.Color.blue()
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
    @app_commands.default_permissions(administrator=True)
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
                color=discord.Color.yellow()
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
                color=discord.Color.yellow()
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
        name="world-set", 
        description="Set up an existing forum channel for VRChat world posts"
    )
    @app_commands.describe(forum_channel="The forum channel to set up for VRChat world posts")
    @app_commands.default_permissions(administrator=True)
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
        await interaction.response.defer(thinking=True)
        
        try:
            server_id = interaction.guild.id
            
            # First, check if this is the same channel that's already configured
            forum_config = ServerChannels.get_forum_channel(server_id)

            if forum_config and forum_config[0] == forum_channel.id:
                # This is the same channel, check if the thread still exists
                old_thread_id = forum_config[1]
                existing_thread = forum_channel.get_thread(old_thread_id)
                
                if existing_thread:
                    # Check if we want to delete the old thread and create a new one
                    try:
                        await existing_thread.delete()
                        await interaction.followup.send(f"🗑️ Deleted old control thread: {existing_thread.name}")
                    except Exception as e:
                        config.logger.error(f"Error deleting old thread: {e}")
                        await interaction.followup.send(f"⚠️ Could not delete old thread: {e}")
                    
                    # Continue to create a new thread below
                else:
                    # Thread doesn't exist anymore
                    await interaction.followup.send(
                        f"⚠️ Forum channel {forum_channel.mention} was already set, " +
                        "but the control thread is missing. Creating a new thread..."
                    )
                    
                # Don't delete existing world data, just proceed to create a new thread
                
            else:
                # This is a different channel or first setup
                if forum_config:
                    # Clean up old thread references but not world data
                    # This lets users switch forum channels without losing world links
                    await interaction.followup.send(
                        f"🔄 Switching from previous forum channel to {forum_channel.mention}. " +
                        "Preserved world data but you'll need to re-scan for threads."
                    )
                
                # Send initial progress message
                progress_message = await interaction.followup.send("🔍 **Scanning VRChat Worlds**: Initializing scan...")
                
                # Scan active threads in the forum and add them to the database
                import time
                start_time = time.time()
                
                # Call the scanning function with the progress message
                worlds_found, unknown_threads = await self._scan_forum_threads(
                    interaction.guild.id, 
                    forum_channel,
                    progress_message
                )
                
                # Calculate scan duration
                duration = time.time() - start_time
                
                # Send a summary message with the scan results
                await interaction.followup.send(
                    f"✅ **Scan Summary**:\n" +
                    f"• Found and indexed **{worlds_found}** VRChat worlds\n" +
                    f"• **{len(unknown_threads)}** threads without identifiable worlds were skipped\n" +
                    f"• All world IDs have been added to the database\n" +
                    f"• Scan completed in **{duration:.1f}** seconds"
                )
            
            # Create the welcome embed first
            embed = discord.Embed(
                title="Share your favorite VRChat worlds here!",
                color=discord.Color.yellow()
            )
            embed.set_image(url=config.WELCOME_IMAGE_URL)

            # Now create the thread with the embed
            thread_info = await forum_channel.create_thread(
                name="Share Your VRChat World Here!", 
                reason="New World Thread", 
                embed=embed
            )
            thread = thread_info.thread
            
            # Add the world button 
            view = WorldButton()
            button_embed = discord.Embed(
                description="Hiya! \n\nWelcome! Do you want to share amazing VRChat worlds with everyone?\n\nIt's super easy! Just click the button below and paste the VRChat world's URL! You can copy the URL from the VRChat website. \n\nYou'll get to pick tags in the next step, so people who love things like horror or games or chatting can easily find worlds they'll enjoy! We'll make it look super pretty with all the details!\n\nPlease don't share every VRChat world you see. Let's focus on the special ones, the ones you think are really cool or maybe even a little hidden and deserve some love! ❤️",
                color=discord.Color.yellow()
            )
            await thread.send(embed=button_embed, view=view)

            # Add missing tags to the database
            added_tags = await self._sync_forum_tags(server_id, forum_channel)
            tag_msg = f"\n{added_tags} new tags added to database." if added_tags > 0 else ""
            
            # Update the database with the channel and thread ID
            ServerChannels.set_forum_channel(server_id, forum_channel.id, thread.id)
            
            # Log activity
            log_activity(
                server_id, 
                "world_set", 
                f"Set forum channel to {forum_channel.id} with thread {thread.id}"
            )

            await interaction.followup.send(
                f"✅ Forum channel set to {forum_channel.mention}\n" +
                f"Created world submission thread: {thread.mention}{tag_msg}"
            )
            
        except Exception as e:
            config.logger.error(f"Error in world_set_slash: {e}")
            await interaction.followup.send(f"❌ An error occurred: {e}")
    
    @app_commands.command(
    name="world-remove", 
    description="Remove a specific VRChat world post"
    )
    @app_commands.describe(
        world_id_or_url="The world ID or URL to remove (e.g., wrld_123... or https://vrchat.com/home/world/...)",
        thread="Or select the thread to remove"
    )
    @app_commands.default_permissions(administrator=True)
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
        name="sync", 
        description="Sync slash commands (admin only)"
    )
    @app_commands.default_permissions(administrator=True)
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
    
    async def _scan_forum_threads(self, server_id: int, forum_channel: discord.ForumChannel, progress_message=None) -> Tuple[int, List[Dict]]:
        """
        Scan forum threads for VRChat worlds with improved accuracy and real-time updates.
        
        Args:
            server_id: Discord server ID
            forum_channel: Discord forum channel
            progress_message: Discord message to update with progress
                
        Returns:
            Tuple of (worlds_found, unknown_threads_data)
        """
        worlds_found = 0
        unknown_threads = []
        duplicates_found = 0
        threads_processed = 0
        
        # Get all threads in the forum
        threads = [thread for thread in forum_channel.threads]
        try:
            # Also get archived threads
            archived_threads = [thread async for thread in forum_channel.archived_threads(limit=None)]
            threads.extend(archived_threads)
        except Exception as e:
            config.logger.error(f"Error fetching archived threads: {e}")
        
        total_threads = len(threads)
        
        # Import APIs
        from utils.api import extract_world_id, VRChatAPI
        vrchat_api = VRChatAPI(config.AUTH)
        
        # Log the scanning process
        config.logger.info(f"Scanning {total_threads} threads in forum channel {forum_channel.id} for server {server_id}")
        
        # Initialize progress message if not provided
        if progress_message:
            await progress_message.edit(content=f"🔍 **Scanning VRChat Worlds**: 0/{total_threads} threads processed, 0 worlds found...")
        
        # Update interval (update message every X threads to avoid rate limits)
        update_interval = max(1, min(total_threads // 10, 10))  # Update at most 10 times during scan
        last_update_time = time.time()
        
        # Process each thread
        for index, thread in enumerate(threads):
            try:
                # Skip the control thread
                if thread.name == "Please post here to provide information and display it to the world" or thread.name == "Share Your VRChat World Here!":
                    threads_processed += 1
                    continue
                    
                # Check if this thread already has a world ID in our database
                existing_world_id = WorldPosts.get_world_for_thread(server_id, thread.id)
                if existing_world_id:
                    # This thread already has a world entry - count it and skip
                    worlds_found += 1
                    threads_processed += 1
                    
                    # Update progress message periodically
                    if progress_message and (index % update_interval == 0 or index == total_threads - 1) and time.time() - last_update_time > 1.5:
                        await progress_message.edit(
                            content=f"🔍 **Scanning VRChat Worlds**: {threads_processed}/{total_threads} threads processed, {worlds_found} worlds found..."
                        )
                        last_update_time = time.time()
                        
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
                        duplicates_found += 1
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
                        
                        # Also try to fetch VRChat world details to store them in our VRChatWorlds table
                        try:
                            from database.models import VRChatWorlds
                            world_details = vrchat_api.get_world_info(world_id)
                            if world_details:
                                VRChatWorlds.add_world(
                                    world_id=world_id,
                                    world_name=world_details.get('name', 'Unknown World'),
                                    author_name=world_details.get('authorName', 'Unknown Author'),
                                    image_url=world_details.get('imageUrl', None)
                                )
                        except Exception as e:
                            config.logger.error(f"Error fetching world details for {world_id}: {e}")
                else:
                    # No world ID found - check if it might be a valid thread we just can't parse
                    # This would be a candidate for manual review
                    unknown_threads.append({
                        "thread_id": thread.id,
                        "thread_name": thread.name,
                        "issue_type": "no_world_link", 
                        "message_sample": first_message.content[:100] if messages and messages[0].content else "No content"
                    })
                
                threads_processed += 1
                
                # Update progress message periodically
                if progress_message and (index % update_interval == 0 or index == total_threads - 1) and time.time() - last_update_time > 1.5:
                    await progress_message.edit(
                        content=f"🔍 **Scanning VRChat Worlds**: {threads_processed}/{total_threads} threads processed, {worlds_found} worlds found..."
                    )
                    last_update_time = time.time()
                    
            except Exception as e:
                config.logger.error(f"Error processing thread {thread.id}: {e}")
                threads_processed += 1
                continue
        
        # Final update for the progress message
        if progress_message:
            await progress_message.edit(
                content=f"✅ **Scan Complete**: {threads_processed}/{total_threads} threads processed, {worlds_found} worlds found, {duplicates_found} duplicates, {len(unknown_threads)} issues detected."
            )
        
        # Log the scan results
        config.logger.info(f"Scan completed: Found {worlds_found} worlds, {duplicates_found} duplicates, and {len(unknown_threads)} threads with issues")
        
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
        for tag in forum_channel.available_tags:
            forum_tags.append({
                'id': tag.id,
                'name': tag.name,
                'emoji': str(tag.emoji) if tag.emoji else None
            })
        
        # Sync tags with database
        added, updated, removed = ServerTags.sync_tags(server_id, forum_tags)
        return added

    @app_commands.command(
        name="repair-threads", 
        description="Repair threads that don't have proper world links"
    )
    @app_commands.default_permissions(administrator=True)
    async def repair_threads_slash(self, interaction: discord.Interaction):
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
            from database.models import WorldPosts
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
                color=discord.Color.green()
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