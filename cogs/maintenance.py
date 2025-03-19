"""
Maintenance commands for the VRChat World Showcase Bot.
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import config as config
from database.models import ServerChannels, WorldPosts, ServerTags
from utils.formatters import chunk_text
from utils.embed_builders import build_scan_results_embed
from ui.buttons import ScanActionButtons


class MaintenanceCommands(commands.Cog):
    """Maintenance commands for the bot."""
    
    def __init__(self, bot: commands.Bot):
        """
        Initialize the cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
    
    @app_commands.command(name="clean-db", description="Clean database entries for deleted channels")
    @app_commands.default_permissions(administrator=True)
    async def clean_db_slash(self, interaction):
        """
        Clean the database by removing references to deleted channels and threads.
        """
        await interaction.response.defer(thinking=True)
        
        server_id = interaction.guild.id
        cleaned_entries = []
        
        try:
            # Check for the forum channel record
            forum_config = ServerChannels.get_forum_channel(server_id)
            
            if forum_config:
                forum_channel_id = forum_config[0]
                forum_channel = interaction.guild.get_channel(forum_channel_id)
                
                if not forum_channel:
                    # Forum channel doesn't exist anymore, remove all related entries
                    ServerChannels.clear_forum_channel(server_id)
                    cleaned_entries.append(f"Removed forum channel configuration (ID: {forum_channel_id})")
                    
                    # Don't delete thread_world_links or tags - these can be migrated to a new forum
                else:
                    # Forum exists, but check for deleted threads
                    thread_world_links = WorldPosts.get_all_threads(server_id)
                    
                    deleted_threads = 0
                    for thread_id, world_id in thread_world_links:
                        thread = forum_channel.get_thread(thread_id)
                        
                        if not thread:
                            # Thread doesn't exist anymore
                            WorldPosts.remove_thread(server_id, thread_id)
                            deleted_threads += 1
                    
                    if deleted_threads > 0:
                        cleaned_entries.append(f"Removed {deleted_threads} deleted threads from database")
            
            # Create a response message
            if cleaned_entries:
                embed = discord.Embed(
                    title="Database Cleanup Results",
                    description="✅ Successfully cleaned the database:",
                    color=discord.Color.dark_red()
                )
                
                for entry in cleaned_entries:
                    embed.description += f"\n• {entry}"
                    
                embed.add_field(
                    name="Next Steps",
                    value="You can now set up a new forum channel using `/world-create` or `/world-set`.",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("✅ Database is clean. No deleted channels or threads found.")
                
        except Exception as e:
            config.logger.error(f"Error in clean_db_slash: {e}")
            await interaction.followup.send(f"❌ An error occurred: {e}")
    
    @app_commands.command(name="scan", description="Comprehensive scan of forum with auto-fix options")
    @app_commands.default_permissions(administrator=True)
    async def scan_slash(self, interaction):
        """
        Perform a comprehensive scan of the forum channel with interactive buttons to fix issues.
        """
        await interaction.response.defer(thinking=True)
        
        server_id = interaction.guild.id
        
        # First check if we have a forum channel set up
        forum_config = ServerChannels.get_forum_channel(server_id)
        if not forum_config:
            await interaction.followup.send(
                "❌ No forum channel set up for this server. Use `/world-create` or `/world-set` first."
            )
            return
        
        forum_channel_id = forum_config[0]
        forum_channel = interaction.guild.get_channel(forum_channel_id)
        
        if not forum_channel:
            await interaction.followup.send(
                "❌ Could not find the configured forum channel. It may have been deleted."
            )
            return
        
        # Send initial progress message
        progress_message = await interaction.followup.send("🔍 **Starting VRChat World Showcase Scan**: Initializing...")
        
        # STEP 1: Scan forum channel for available tags
        await progress_message.edit(content="🔍 **Scanning Tags**: Checking forum channel tags...")
        
        forum_tags = forum_channel.available_tags
        
        # STEP 2: Check database for existing tags
        server_tags = ServerTags.get_all_tags(server_id)
        db_tags = {tag['tag_id']: tag['tag_name'] for tag in server_tags}
        
        # STEP 3: Update database tags
        added = 0
        updated = 0
        removed = 0
        
        # Convert forum tags to a format compatible with ServerTags.sync_tags
        forum_tag_data = []
        for tag in forum_tags:
            # Add a check for moderated tags
            is_moderated = getattr(tag, "moderated", False)
            
            # Only include in forum_tag_data if not moderated
            if not is_moderated:
                forum_tag_data.append({
                    'id': tag.id,
                    'name': tag.name,
                    'emoji': str(tag.emoji) if tag.emoji else None
                })
            else:
                # Log that we're skipping a moderated tag
                config.logger.info(f"Skipping moderated tag '{tag.name}' (ID: {tag.id}) from database sync")

        # Sync tags with database
        added, updated, removed = ServerTags.sync_tags(server_id, forum_tag_data)
        
        # Update progress message with tag results
        tag_results = f"🔍 **Tag Scan Complete**:\n• Added: {added}\n• Updated: {updated}\n• Removed: {removed}\n\nStarting thread scan..."
        await progress_message.edit(content=tag_results)
        
        # STEP 4: Scan forum threads for world posts using our scanning function with real-time updates
        worlds_found, unknown_threads = await self._scan_forum_threads(server_id, forum_channel, progress_message)
        
        # STEP 5: Check threads for missing tags
        await progress_message.edit(content="🔍 **Checking Tags**: Verifying tags on all world threads...")
        
        # Create a map of world_id to thread_id to detect duplicates
        world_thread_map = {}
        duplicate_worlds = []
        
        # First, get existing world_id to thread_id mappings from database
        thread_worlds = WorldPosts.get_all_threads(server_id)
        for thread_id, world_id in thread_worlds:
            if world_id in world_thread_map:
                # Found a duplicate - same world ID linked to multiple threads
                duplicate_worlds.append((world_id, world_thread_map[world_id], thread_id))
            else:
                world_thread_map[world_id] = thread_id
        
        # Track threads that exist in Discord but don't have valid world links
        threads_without_worlds = []
        
        # Track threads with missing tags
        threads_with_missing_tags = []
        tags_to_fix = 0
        
        # Scan each thread for missing tags
        thread_count = 0
        processed_count = 0
        
        # Get all threads - both active and archived
        all_threads = list(forum_channel.threads)
        try:
            # Get archived threads
            archived_threads = [thread async for thread in forum_channel.archived_threads(limit=None)]
            all_threads.extend(archived_threads)
        except Exception as e:
            config.logger.error(f"Error fetching archived threads: {e}")
        
        thread_count = len(all_threads)
        update_interval = max(1, min(thread_count // 5, 10))
        
        # Scan each thread for tag issues
        for i, thread in enumerate(all_threads):
            try:
                # Skip the control thread
                if thread.name == "Please post here to provide information and display it to the world" or thread.name == "Share Your VRChat World Here!":
                    processed_count += 1
                    continue
                
                # Check if this thread has a world in our database
                world_id = WorldPosts.get_world_for_thread(server_id, thread.id)
                
                if world_id:
                    # This thread has a valid world link - check for missing tags
                    
                    # Get thread tags
                    thread_tags = []
                    try:
                        # Try the most common attribute first
                        thread_tags = thread.applied_tags
                    except AttributeError:
                        try:
                            # Try alternative attribute names
                            thread_tags = getattr(thread, "tags", []) or getattr(thread, "applied_tags", [])
                        except:
                            config.logger.warning(f"Could not retrieve tags for thread {thread.id}")
                    
                    # Convert thread tags to a set of IDs for easier comparison
                    thread_tag_ids = set()
                    for tag in thread_tags:
                        # Handle different ways tag IDs might be stored
                        if isinstance(tag, int):
                            thread_tag_ids.add(tag)
                        elif hasattr(tag, 'id'):
                            thread_tag_ids.add(tag.id)
                        elif isinstance(tag, str) and tag.isdigit():
                            thread_tag_ids.add(int(tag))
                    
                    # Check if we need to add tags to this thread
                    # Get user choices from the database for this world
                    from database.models import UserWorldLinks
                    users = UserWorldLinks.find_by_world_id(world_id)
                    
                    if users:
                        for user in users:
                            user_choices = user.get('user_choices', '')
                            if user_choices:
                                user_tags = user_choices.split(',')
                                
                                # Get tag IDs for these tag names
                                expected_tag_ids = ServerTags.get_tag_ids(server_id, user_tags)
                                
                                # Check which tags are missing
                                missing_tag_ids = []
                                for tag_id in expected_tag_ids:
                                    # Convert to int for comparison if needed
                                    if isinstance(tag_id, str) and tag_id.isdigit():
                                        tag_id = int(tag_id)
                                        
                                    # Check if this tag ID is missing
                                    if tag_id not in thread_tag_ids:
                                        missing_tag_ids.append(tag_id)
                                
                                if missing_tag_ids:
                                    # Store the data for the fix button
                                    threads_with_missing_tags.append((thread.id, missing_tag_ids))
                                    tags_to_fix += len(missing_tag_ids)
                else:
                    # This thread doesn't have a world in our database - add to the list
                    threads_without_worlds.append((thread.id, thread.name))
                    
                processed_count += 1
                
                # Update progress message periodically
                if i % update_interval == 0 or i == len(all_threads) - 1:
                    await progress_message.edit(
                        content=f"🔍 **Checking Tags**: Processing thread {processed_count}/{thread_count}, found {tags_to_fix} missing tags so far..."
                    )
                    
            except Exception as e:
                config.logger.error(f"Error processing thread {thread.id}: {e}")
                processed_count += 1
        
        # STEP 6: Generate final results message
        await progress_message.edit(
            content=f"✅ **Scan Complete**: Found {len(duplicate_worlds)} duplicates, {len(threads_without_worlds)} threads without worlds, and {tags_to_fix} missing tags."
        )
        
        # Create a data structure to store info for the action buttons
        scan_data = {
            'forum_channel_id': forum_channel_id,
            'server_id': server_id,
            'duplicate_worlds': duplicate_worlds,
            'missing_threads': threads_without_worlds,
            'tag_fix_data': threads_with_missing_tags,
            'tags_to_fix': tags_to_fix
        }
        
        progress_completion = (
            "# ✅ **Scan Complete!**\n\n"
            f"**📊 Summary:**\n"
            f"• 🔄 **Duplicates:** {len(duplicate_worlds)} worlds\n"
            f"• ⚠️ **Threads without worlds:** {len(threads_without_worlds)} threads\n"
            f"• 🏷️ **Missing tags:** {tags_to_fix} tags\n\n"
            "📝 Preparing detailed results..."
        )
        await progress_message.edit(content=progress_completion)

        # Then, further down the method, modify the scan result messages:
        # Create scan result messages with more visual appeal
        results = []
        results.append(f"# 🔍 **VRCHAT WORLD SHOWCASE SCAN RESULTS**")

        # Add tag results with emojis
        results.append(f"\n## 🏷️ **TAG SCAN:**")
        results.append(f"• ✅ Added {added} new tags")
        results.append(f"• 🔄 Updated {updated} existing tags")
        results.append(f"• 🗑️ Removed {removed} unused tags")

        # Add thread results with emojis
        results.append(f"\n## 🌐 **THREAD SCAN:**")
        results.append(f"• ✅ Valid VRChat world threads: {worlds_found}")
        results.append(f"• 🏷️ Threads with missing tags: {tags_to_fix}")

        # Report on threads without VRChat worlds
        if scan_data['missing_threads']:
            results.append(f"\n## ⚠️ **Found {len(scan_data['missing_threads'])} threads needing review:**")
            results.append("These threads don't have detectable VRChat world links. They may need manual inspection or cleanup.")
            # Only show up to 10 to avoid making the message too long
            for i, (thread_id, thread_name) in enumerate(scan_data['missing_threads'][:10]):
                results.append(f"• 📎 {thread_name} (ID: {thread_id})")
            if len(scan_data['missing_threads']) > 10:
                results.append(f"...and {len(scan_data['missing_threads']) - 10} more threads")
                    
        # Report on duplicate worlds
        if duplicate_worlds:
            results.append(f"\n## ⚠️ **Found {len(duplicate_worlds)} duplicate VRChat worlds:**")
            results.append("These threads contain worlds that already exist in other threads:")
            for world_id, thread_id1, thread_id2 in duplicate_worlds[:10]:
                results.append(f"• 🔄 World: {world_id}")
                results.append(f"  └─ Original thread: <#{thread_id1}>")
                results.append(f"  └─ Duplicate thread: <#{thread_id2}>")
            if len(duplicate_worlds) > 10:
                results.append(f"...and {len(duplicate_worlds) - 10} more duplicates")
        
        # Send results with action buttons
        from utils.formatters import chunk_text
        
        # STEP 7: Send results in chunks if needed
        chunked_results = chunk_text("\n".join(results), 4000)  # Discord embed limit is 4096
        
        # Send results
        for i, chunk in enumerate(chunked_results):
            embed = build_scan_results_embed(
                "VRChat World Showcase Scan", 
                chunk.split("\n"), 
                i + 1, 
                len(chunked_results)
            )
            
            # Add buttons to the last chunk
            if i == len(chunked_results) - 1:
                view = ScanActionButtons(scan_data)
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        
        # If there were no results (unlikely), send a fallback message
        if not chunked_results:
            embed = discord.Embed(
                title="🔍 VRChat World Showcase Scan",
                description="# ✅ Perfect Showcase!\n\nYour VRChat World Showcase is in excellent condition.\n\n**No issues were found during the scan.**",
                color=discord.Color.dark_red()
            )
            
            # Add a celebratory image
            embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1049421057178079262.webp?size=96&quality=lossless")
            
            # Add some stats fields
            embed.add_field(
                name="💯 Perfect Score",
                value="All worlds have proper tags and links",
                inline=True
            )
            
            embed.add_field(
                name="🏆 Showcase Status",
                value="Perfectly maintained",
                inline=True
            )
            
            embed.set_footer(
                text=f"Scan completed on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}",
                icon_url="https://cdn.discordapp.com/avatars/1156538533876613121/8acb3d0ce2c328987ad86355e0d0b528.png"
            )
            
            await interaction.followup.send(embed=embed)

    async def _scan_forum_threads(self, server_id, forum_channel, progress_message=None):
        """
        Scan forum threads for VRChat worlds with improved accuracy and real-time updates.
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


async def setup(bot: commands.Bot):
    """
    Set up the cog.
    
    Args:
        bot: The bot instance
    """
    await bot.add_cog(MaintenanceCommands(bot))