"""
Maintenance commands for the VRChat World Showcase Bot.
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import bot.config as config
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
    async def clean_db_slash(self, interaction: discord.Interaction):
        """
        Clean the database by removing references to deleted channels and threads.
        
        Args:
            interaction: Discord interaction
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
                    color=discord.Color.green()
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
    async def scan_slash(self, interaction: discord.Interaction):
        """
        Perform a comprehensive scan of the forum channel with interactive buttons to fix issues.
        
        Args:
            interaction: Discord interaction
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
        
        # Start building a results message
        results = []
        
        # Create a data structure to store info for the action buttons
        scan_data = {
            'forum_channel_id': forum_channel_id,
            'server_id': server_id,
            'duplicate_worlds': [],
            'missing_threads': [],
            'tag_fix_data': [],
            'tags_to_fix': 0
        }
        
        # STEP 1: Scan forum channel for available tags
        results.append(f"🔍 **SCANNING FORUM CHANNEL: {forum_channel.name}**")
        
        forum_tags = forum_channel.available_tags
        results.append(f"Found {len(forum_tags)} tags in the forum channel")
        
        # STEP 2: Check database for existing tags
        server_tags = ServerTags.get_all_tags(server_id)
        db_tags = {tag['tag_id']: tag['tag_name'] for tag in server_tags}
        
        results.append(f"Found {len(db_tags)} tags in the database")
        
        # STEP 3: Update database tags
        added = 0
        updated = 0
        removed = 0
        
        # Convert forum tags to a format compatible with ServerTags.sync_tags
        forum_tag_data = []
        for tag in forum_tags:
            forum_tag_data.append({
                'id': tag.id,
                'name': tag.name,
                'emoji': str(tag.emoji) if tag.emoji else None
            })
        
        # Sync tags with database
        added, updated, removed = ServerTags.sync_tags(server_id, forum_tag_data)
        
        # Log tag changes
        if added > 0:
            results.append(f"➕ Added {added} new tags to database")
        if updated > 0:
            results.append(f"📝 Updated {updated} tags in database")
        if removed > 0:
            results.append(f"➖ Removed {removed} tags from database")
        
        results.append(f"\n**TAG RESULTS:**\n➕ Added: {added}\n📝 Updated: {updated}\n➖ Removed: {removed}")
        
        # STEP 4: Scan forum threads for world posts
        results.append(f"\n🔍 **SCANNING THREADS FOR VRCHAT WORLDS**")
        
        # Get all active and archived threads
        all_threads = []
        try:
            # Get active threads
            all_threads.extend([thread for thread in forum_channel.threads])
            
            # Get archived threads
            archived_threads = [thread async for thread in forum_channel.archived_threads(limit=None)]
            all_threads.extend(archived_threads)
            
            results.append(f"Found {len(all_threads)} total threads")
        except Exception as e:
            results.append(f"⚠️ Error fetching threads: {e}")
            config.logger.error(f"Error fetching threads: {e}")
        
        # STEP 5: Check threads for VRChat world links and update tags
        world_threads_found = 0
        worlds_added = 0
        
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
        
        # Import API helpers for thread scanning
        from utils.api import extract_world_id
        import re
        
        # Scan threads for missing tags and try to identify world links
        for thread in all_threads:
            try:
                # Skip the control thread
                if thread.name == "Please post here to provide information and display it to the world":
                    continue
                
                # Check if this thread has a world in our database
                world_id = WorldPosts.get_world_for_thread(server_id, thread.id)
                
                if world_id:
                    # This thread has a valid world link in our database
                    world_threads_found += 1
                    
                    # Now check for missing tags
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
                                    scan_data['tag_fix_data'].append((thread.id, missing_tag_ids))
                                    scan_data['tags_to_fix'] += 1
                                    
                                    # Get the tag names for the log
                                    missing_tag_names = ServerTags.get_tag_names(server_id, missing_tag_ids)
                                    
                                    results.append(
                                        f"🏷️ Thread missing tags: {thread.name} - " +
                                        f"Missing: {', '.join(missing_tag_names)}"
                                    )
                else:
                    # This thread doesn't have a world link in our database
                    # Let's try to find a VRChat world link in the thread messages
                    
                    found_world_id = None
                    found_world_url = None
                    
                    # Check the first message (thread starter)
                    try:
                        # Get first message
                        async for message in thread.history(limit=1, oldest_first=True):
                            # Check for embeds with URL
                            if message.embeds:
                                for embed in message.embeds:
                                    if embed.url and "vrchat.com/home/world" in embed.url:
                                        found_world_url = embed.url
                                        found_world_id = extract_world_id(found_world_url)
                                        break
                            
                            # Check content for VRChat links
                            if not found_world_id and message.content:
                                urls = re.findall(
                                    r'https://vrchat\.com/home/world/wrld_[a-zA-Z0-9_-]+(?:/info)?', 
                                    message.content
                                )
                                if urls:
                                    found_world_url = urls[0]
                                    found_world_id = extract_world_id(found_world_url)
                    except Exception as e:
                        config.logger.error(f"Error checking thread messages: {e}")
                    
                    if found_world_id:
                        # We found a world ID in the thread, check if it's already in another thread
                        existing_thread = WorldPosts.get_thread_for_world(server_id, found_world_id)
                        
                        if existing_thread and existing_thread != thread.id:
                            # This is a duplicate world
                            duplicate_worlds.append((found_world_id, existing_thread, thread.id))
                        else:
                            # This is a new world we should add to the database
                            try:
                                # Get first message author for user ID
                                user_id = 0
                                async for message in thread.history(limit=1, oldest_first=True):
                                    user_id = message.author.id if message.author else 0
                                
                                # Add to database
                                WorldPosts.add_world_post(
                                    server_id=server_id,
                                    user_id=user_id,
                                    thread_id=thread.id,
                                    world_id=found_world_id,
                                    world_link=found_world_url or f"https://vrchat.com/home/world/{found_world_id}"
                                )
                                worlds_added += 1
                                world_threads_found += 1
                                results.append(f"✅ Added missing world link for thread: {thread.name}")
                            except Exception as e:
                                config.logger.error(f"Error adding world post: {e}")
                                # Count as thread without world since we couldn't add it
                                threads_without_worlds.append((thread.id, thread.name))
                    else:
                        # No world ID found - this is a thread without a VRChat world
                        threads_without_worlds.append((thread.id, thread.name))
            except Exception as e:
                config.logger.error(f"Error processing thread {thread.id}: {e}")
        
        # Add missing threads to scan data
        scan_data['missing_threads'] = threads_without_worlds
        
        # STEP 6: Generate comprehensive reports
        results.append(f"\n**SCAN RESULTS:**")
        results.append(f"✅ Valid VRChat world threads: {world_threads_found}")
        if worlds_added > 0:
            results.append(f"✅ Added world links for {worlds_added} threads")
        results.append(f"🏷️ Threads with missing tags: {scan_data['tags_to_fix']}")
        
        # Report on threads without VRChat worlds
        if scan_data['missing_threads']:
            results.append(f"\n⚠️ **Found {len(scan_data['missing_threads'])} threads needing review:**")
            results.append("These threads don't have detectable VRChat world links. They may need manual inspection or cleanup.")
            # Only show up to 10 to avoid making the message too long
            for i, (thread_id, thread_name) in enumerate(scan_data['missing_threads'][:10]):
                results.append(f"- {thread_name} (ID: {thread_id})")
            if len(scan_data['missing_threads']) > 10:
                results.append(f"...and {len(scan_data['missing_threads']) - 10} more threads")
                
        # Report on duplicate worlds
        scan_data['duplicate_worlds'] = duplicate_worlds

        if duplicate_worlds:
            results.append(f"\n⚠️ **Found {len(duplicate_worlds)} duplicate VRChat worlds:**")
            results.append("These threads contain worlds that already exist in other threads:")
            for world_id, thread_id1, thread_id2 in duplicate_worlds[:10]:
                results.append(f"- World: {world_id}")
                results.append(f"  Original thread: <#{thread_id1}>")
                results.append(f"  Duplicate thread: <#{thread_id2}>")
            if len(duplicate_worlds) > 10:
                results.append(f"...and {len(duplicate_worlds) - 10} more duplicates")
        
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
                title="VRChat World Showcase Scan",
                description="✅ Scan complete. No issues found.",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Scan completed on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}")
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    """
    Set up the cog.
    
    Args:
        bot: The bot instance
    """
    await bot.add_cog(MaintenanceCommands(bot))