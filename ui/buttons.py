"""
UI button components for the VRChat World Showcase Bot.
"""
import discord
from typing import Optional, List, Dict, Any, Callable, Awaitable, Tuple
import config as config
import logging
from ui.modals import WorldLinkModal

class WorldButton(discord.ui.View):
    """Button view for creating a new VRChat world post."""
    
    def __init__(self, allowed_user_id: Optional[int] = None):
        """
        Initialize the world button view.
        
        Args:
            allowed_user_id: If set, only this user can use the button
        """
        # Create a persistent view with no timeout
        super().__init__(timeout=config.BUTTON_TIMEOUT)
        self.message_id: Optional[int] = None
        self.allowed_user_id = allowed_user_id  # Store the allowed user ID

    @discord.ui.button(
        label='Share World', 
        emoji="🌎", 
        style=discord.ButtonStyle.green, 
        custom_id="world_button"
    )
    async def world_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Handle world button click.
        
        Args:
            interaction: Discord interaction
            button: Button that was clicked
        """
        # Create and show modal for entering world link
        modal = WorldLinkModal()
        modal.guild_id = interaction.guild.id
        await interaction.response.send_modal(modal)

class ScanActionButtons(discord.ui.View):
    """Buttons for taking action on scan results."""
    
    def __init__(self, scan_data: Dict[str, Any]):
        """
        Initialize scan action buttons.
        
        Args:
            scan_data: Dictionary with scan results
        """
        super().__init__(timeout=600)  # 10 minute timeout
        self.scan_data = scan_data
        
        # Disable buttons if there's nothing to fix
        duplicate_disabled = len(scan_data.get('duplicate_worlds', [])) == 0
        missing_disabled = len(scan_data.get('missing_threads', [])) == 0
        tags_disabled = scan_data.get('tags_to_fix', 0) == 0
        
        # Get counts for display
        duplicate_count = len(scan_data.get('duplicate_worlds', []))
        missing_count = len(scan_data.get('missing_threads', []))
        tags_count = scan_data.get('tags_to_fix', 0)
        
        # Add the buttons with improved labels
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label=f"Remove Duplicates ({duplicate_count})",
                emoji="🔄",
                custom_id="remove_duplicates",
                disabled=duplicate_disabled,
                row=0
            )
        )
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"Remove Empty Threads ({missing_count})",
                emoji="🔍",
                custom_id="remove_empty",
                disabled=missing_disabled,
                row=0
            )
        )
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=f"Fix Tags ({tags_count})",
                emoji="🏷️",
                custom_id="fix_tags",
                disabled=tags_disabled,
                row=1
            )
        )
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Fix All Issues",
                emoji="✅",
                custom_id="fix_all",
                disabled=(duplicate_disabled and missing_disabled and tags_disabled),
                row=1
            )
        )
        
        # Connect button callbacks
        self.children[0].callback = self.remove_duplicates_callback
        self.children[1].callback = self.remove_empty_callback
        self.children[2].callback = self.fix_tags_callback
        self.children[3].callback = self.fix_all_callback
    
    async def remove_duplicates_callback(self, interaction: discord.Interaction):
        """
        Handle removing duplicate world threads.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(thinking=True)
        
        duplicate_worlds = self.scan_data.get('duplicate_worlds', [])
        if not duplicate_worlds:
            await interaction.followup.send("No duplicate worlds to remove.")
            return
        
        server_id = self.scan_data.get('server_id')
        forum_channel_id = self.scan_data.get('forum_channel_id')
        forum_channel = interaction.guild.get_channel(forum_channel_id)
        
        removed_count = 0
        failed_count = 0
        
        for world_id, thread_id1, thread_id2 in duplicate_worlds:
            try:
                # Try to get the duplicate thread (thread_id2)
                thread = forum_channel.get_thread(thread_id2)
                if thread:
                    # First remove from database if it exists
                    from database.models import WorldPosts
                    WorldPosts.remove_post_by_thread(server_id, thread_id2)
                    
                    # Then delete the actual thread
                    await thread.delete()
                    removed_count += 1
            except Exception as e:
                config.logger.error(f"Error removing duplicate thread {thread_id2}: {e}")
                failed_count += 1
        
        # Update the button to show it's been completed
        self.children[0].disabled = True
        self.children[0].label = f"Duplicates Removed ({removed_count})"
        
        # Update the fix all button if everything is fixed
        if all(child.disabled for child in self.children[:3]):
            self.children[3].disabled = True
            self.children[3].label = "All Issues Fixed"
        
        await interaction.message.edit(view=self)
        await interaction.followup.send(f"✅ Successfully removed {removed_count} duplicate world threads.")
    
    async def remove_empty_callback(self, interaction: discord.Interaction):
        """
        Handle removing empty threads.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(thinking=True)
        
        missing_threads = self.scan_data.get('missing_threads', [])
        if not missing_threads:
            await interaction.followup.send("No empty threads to remove.")
            return
        
        server_id = self.scan_data.get('server_id')
        forum_channel_id = self.scan_data.get('forum_channel_id')
        forum_channel = interaction.guild.get_channel(forum_channel_id)
        
        removed_count = 0
        failed_count = 0
        
        for thread_id, thread_name in missing_threads:
            try:
                # Get the thread for this ID
                thread = forum_channel.get_thread(thread_id)
                if thread:
                    # First remove from database if it exists
                    from database.models import WorldPosts
                    WorldPosts.remove_post_by_thread(server_id, thread_id)
                    
                    # Then delete the thread
                    await thread.delete()
                    removed_count += 1
            except Exception as e:
                config.logger.error(f"Error removing thread {thread_id}: {e}")
                failed_count += 1
        
        # Update the button to show it's been completed
        self.children[1].disabled = True
        self.children[1].label = f"Empty Threads Removed ({removed_count})"
        
        # Update the fix all button if everything is fixed
        if all(child.disabled for child in self.children[:3]):
            self.children[3].disabled = True
            self.children[3].label = "All Issues Fixed"
        
        await interaction.message.edit(view=self)
        await interaction.followup.send(f"✅ Successfully removed {removed_count} threads without VRChat worlds.")
    
    async def fix_tags_callback(self, interaction: discord.Interaction):
        """
        Handle fixing missing tags.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(thinking=True)
        
        tags_to_fix = self.scan_data.get('tags_to_fix', 0)
        if tags_to_fix == 0:
            await interaction.followup.send("No tags to fix.")
            return
        
        tag_data = self.scan_data.get('tag_fix_data', [])
        fixed_count = 0
        fixed_thread_names = []
        detailed_log = []
        
        for thread_id, missing_tag_ids in tag_data:
            try:
                # Get the channel for the thread
                forum_channel_id = self.scan_data.get('forum_channel_id')
                forum_channel = interaction.guild.get_channel(forum_channel_id)
                
                if forum_channel:
                    # First, try to get thread directly
                    thread = None
                    
                    # Try different methods to get the thread
                    try:
                        # Method 1: Direct get_thread
                        thread = forum_channel.get_thread(thread_id)
                    except:
                        pass
                    
                    if not thread:
                        # Method 2: Search for thread in active threads
                        for active_thread in forum_channel.threads:
                            if active_thread.id == thread_id:
                                thread = active_thread
                                break
                    
                    if not thread:
                        # Method 3: Try to fetch the thread
                        try:
                            thread = await interaction.guild.fetch_channel(thread_id)
                        except:
                            pass
                    
                    if thread:
                        # Get current thread tags
                        current_tags = []
                        try:
                            current_tags = thread.applied_tags
                        except AttributeError:
                            # Try alternative attribute names
                            current_tags = getattr(thread, "tags", []) or getattr(thread, "applied_tags", [])
                        
                        # Get tag names for logging
                        from database.models import ServerTags
                        missing_tag_names = ServerTags.get_tag_names(
                            self.scan_data.get('server_id'), 
                            missing_tag_ids
                        )
                        
                        detailed_log.append(f"Fixing thread: {thread.name}")
                        detailed_log.append(f"- Missing tags: {', '.join(missing_tag_names)}")
                        
                        # Create tag objects
                        from collections import namedtuple
                        Tag = namedtuple('Tag', ['id'])
                        
                        # Create the FULL set of tags - current tags + missing tags
                        all_tag_ids = set(current_tags) | set(missing_tag_ids)
                        all_tags = [Tag(id=tag_id) for tag_id in all_tag_ids]
                        
                        # Check max tag limit
                        if len(all_tags) > 5:
                            all_tags = all_tags[:5]  # Limit to 5 tags
                            detailed_log.append(f"- Warning: Limited to 5 tags")
                        
                        try:
                            # Try using edit method to set all tags at once
                            await thread.edit(applied_tags=all_tags)
                            fixed_count += 1
                            fixed_thread_names.append(thread.name)
                            detailed_log.append(f"- ✅ Success: Tags updated")
                            
                            # Update user choices in database
                            try:
                                from database.models import ThreadWorldLinks, UserWorldLinks
                                world_id = ThreadWorldLinks.get_world_for_thread(
                                    self.scan_data.get('server_id'),
                                    thread_id
                                )
                                
                                if world_id:
                                    # Find user who posted this world
                                    users = UserWorldLinks.find_by_world_id(world_id)
                                    for user in users:
                                        user_id = user['user_id']
                                        current_choices = user.get('user_choices', '')
                                        
                                        # Update user choices with missing tags
                                        user_tags = current_choices.split(',') if current_choices else []
                                        for tag_name in missing_tag_names:
                                            if tag_name not in user_tags:
                                                user_tags.append(tag_name)
                                        
                                        # Save updated choices
                                        UserWorldLinks.set_user_choices(user_id, user_tags)
                                        
                                        detailed_log.append(f"- ✅ Updated user choices for user {user_id}")
                            except Exception as db_error:
                                detailed_log.append(f"- ⚠️ Failed to update database: {db_error}")
                                
                        except Exception as edit_error:
                            detailed_log.append(f"- ❌ Error with edit method: {edit_error}")
                            
                            try:
                                # Fallback: Try add_tags method
                                tag_ids_to_add = [Tag(id=tag_id) for tag_id in missing_tag_ids]
                                await thread.add_tags(*tag_ids_to_add, reason="Auto-fixed by scan command")
                                fixed_count += 1
                                fixed_thread_names.append(thread.name)
                                detailed_log.append(f"- ✅ Success with add_tags fallback")
                            except Exception as add_error:
                                detailed_log.append(f"- ❌ Failed to fix tags: {add_error}")
                    else:
                        detailed_log.append(f"❌ Could not find thread with ID {thread_id}")
                else:
                    detailed_log.append(f"❌ Could not find forum channel with ID {forum_channel_id}")
            except Exception as e:
                detailed_log.append(f"❌ General error fixing tags for thread {thread_id}: {e}")
                config.logger.error(f"Error fixing tags for thread {thread_id}: {e}")
                    
        # Update the button to show it's been completed
        if fixed_count > 0:
            self.children[2].disabled = True
            self.children[2].label = f"Tags Fixed ({fixed_count})"
            
            # Update the fix all button if everything is fixed
            if all(child.disabled for child in self.children[:3]):
                self.children[3].disabled = True
                self.children[3].label = "All Issues Fixed"
            
            await interaction.message.edit(view=self)
            
            # Create a compact summary
            summary = f"✅ Successfully fixed tags on {fixed_count} threads:\n"
            summary += "\n".join([f"- {name}" for name in fixed_thread_names[:5]])
            if len(fixed_thread_names) > 5:
                summary += f"\n...and {len(fixed_thread_names) - 5} more threads"
            
            # Send the summary with a toggle for detailed log
            embed = discord.Embed(
                title="Tag Fix Results",
                description=summary,
                color=discord.Color.dark_red()
            )
            
            # Add detailed log to a field
            if detailed_log:
                from utils.formatters import truncate_text
                full_log = "\n".join(detailed_log)
                # If the log is too long, trim it
                full_log = truncate_text(full_log, 1000)
                embed.add_field(name="Detailed Log", value=full_log, inline=False)
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Failed to fix any tags. Check the bot logs for details.")
    
    async def fix_all_callback(self, interaction: discord.Interaction):
        """
        Handle fixing all issues.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(thinking=True)
        
        results = []
        
        # Fix duplicate worlds
        if not self.children[0].disabled:
            await self.remove_duplicates_callback(interaction)
            results.append("🔄 Removed duplicate world threads")
        
        # Fix empty threads
        if not self.children[1].disabled:
            await self.remove_empty_callback(interaction)
            results.append("🔍 Removed threads without VRChat worlds")
        
        # Fix tags
        if not self.children[2].disabled:
            await self.fix_tags_callback(interaction)
            results.append("🏷️ Fixed missing tags on threads")
        
        # Update the fix all button
        self.children[3].disabled = True
        self.children[3].label = "All Issues Fixed"
        
        await interaction.message.edit(view=self)
        
        if results:
            await interaction.followup.send("✅ Successfully fixed all issues:\n" + "\n".join(results))
        else:
            await interaction.followup.send("✅ No issues to fix.")
            
    async def review_empty_callback(self, interaction: discord.Interaction):
        """
        Handle reviewing empty threads - show more details and options.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(thinking=True)
        
        missing_threads = self.scan_data.get('missing_threads', [])
        if not missing_threads:
            await interaction.followup.send("No empty threads to review.")
            return
        
        # Create a detailed embed for review
        embed = discord.Embed(
            title="Empty Thread Review",
            description="These threads don't have detectable VRChat world links. You can:",
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name="Options",
            value=(
                "1️⃣ **Keep threads** - These might be valid threads that need manual fixing\n"
                "2️⃣ **Remove threads** - Delete these threads if they're not useful\n"
                "3️⃣ **Scan for links** - Attempt to find VRChat links in thread messages"
            ),
            inline=False
        )
        
        thread_list = ""
        for i, (thread_id, thread_name) in enumerate(missing_threads[:10]):
            thread_list += f"{i+1}. {thread_name} (<#{thread_id}>)\n"
        
        if len(missing_threads) > 10:
            thread_list += f"...and {len(missing_threads) - 10} more threads"
            
        embed.add_field(
            name="Threads Without VRChat Links",
            value=thread_list or "No threads found",
            inline=False
        )
        
        # Create view with options
        view = ThreadReviewView(self.scan_data, missing_threads)
        await interaction.followup.send(embed=embed, view=view)
        
    async def review_duplicates_callback(self, interaction: discord.Interaction):
        """
        Handle reviewing duplicate world threads with options.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(thinking=True)
        
        duplicate_worlds = self.scan_data.get('duplicate_worlds', [])
        if not duplicate_worlds:
            await interaction.followup.send("No duplicate worlds to review.")
            return
        
        # Create a detailed embed for review
        embed = discord.Embed(
            title="Duplicate World Review",
            description="These threads contain worlds that also exist in other threads. You can:",
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name="Options",
            value=(
                "1️⃣ **Keep both** - Don't delete any threads (may cause confusion)\n"
                "2️⃣ **Keep oldest** - Keep the original thread and remove duplicates\n"
                "3️⃣ **Review individually** - Select which threads to keep/remove"
            ),
            inline=False
        )
        
        duplicate_list = ""
        for i, (world_id, thread_id1, thread_id2) in enumerate(duplicate_worlds[:5]):
            duplicate_list += f"{i+1}. World `{world_id}`\n"
            duplicate_list += f"   - Original: <#{thread_id1}>\n"
            duplicate_list += f"   - Duplicate: <#{thread_id2}>\n"
        
        if len(duplicate_worlds) > 5:
            duplicate_list += f"...and {len(duplicate_worlds) - 5} more duplicates\n"
            
        embed.add_field(
            name="Duplicate World Threads",
            value=duplicate_list or "No duplicates found",
            inline=False
        )
        
        # Create view with options
        view = DuplicateReviewView(self.scan_data, duplicate_worlds)
        await interaction.followup.send(embed=embed, view=view)

# Additional UI components for thread reviews
class ThreadReviewView(discord.ui.View):
    """View for reviewing and handling threads without VRChat world links."""
    
    def __init__(self, scan_data: Dict[str, Any], threads: List[Tuple[int, str]]):
        super().__init__(timeout=300)  # 5 minute timeout
        self.scan_data = scan_data
        self.threads = threads
        
    @discord.ui.button(label="Keep Threads", style=discord.ButtonStyle.secondary, emoji="1️⃣", row=0)
    async def keep_threads(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Keep all threads and mark them as reviewed."""
        await interaction.response.defer(thinking=True)
        
        embed = discord.Embed(
            title="Thread Review Result",
            description=f"✅ Keeping all {len(self.threads)} threads without modification.",
            color=discord.Color.dark_red()
        )
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        
        await interaction.followup.send(embed=embed)
        await interaction.message.edit(view=self)
    
    @discord.ui.button(label="Remove Threads", style=discord.ButtonStyle.danger, emoji="2️⃣", row=0)
    async def remove_threads(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove all threads without VRChat world links."""
        await interaction.response.defer(thinking=True)
        
        server_id = self.scan_data.get('server_id')
        forum_channel_id = self.scan_data.get('forum_channel_id')
        forum_channel = interaction.guild.get_channel(forum_channel_id)
        
        removed_count = 0
        failed_count = 0
        
        for thread_id, thread_name in self.threads:
            try:
                # Get the thread
                thread = forum_channel.get_thread(thread_id)
                if thread:
                    await thread.delete()
                    
                    # Remove from database if it exists
                    from database.models import WorldPosts
                    WorldPosts.remove_post_by_thread(server_id, thread_id)
                    
                    removed_count += 1
            except Exception as e:
                config.logger.error(f"Error removing thread {thread_id}: {e}")
                failed_count += 1
        
        embed = discord.Embed(
            title="Thread Review Result",
            description=f"✅ Removed {removed_count} threads without VRChat worlds.",
            color=discord.Color.dark_red()
        )
        
        if failed_count > 0:
            embed.add_field(
                name="Issues",
                value=f"⚠️ Failed to remove {failed_count} threads due to errors.",
                inline=False
            )
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        
        await interaction.followup.send(embed=embed)
        await interaction.message.edit(view=self)
    
    @discord.ui.button(label="Scan for Links", style=discord.ButtonStyle.primary, emoji="3️⃣", row=0)
    async def scan_for_links(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Advanced scan to try finding VRChat links in thread messages."""
        await interaction.response.defer(thinking=True)
        
        server_id = self.scan_data.get('server_id')
        forum_channel_id = self.scan_data.get('forum_channel_id')
        forum_channel = interaction.guild.get_channel(forum_channel_id)
        
        fixed_count = 0
        not_found_count = 0
        
        progress_message = await interaction.followup.send("🔍 Scanning threads for VRChat links...")
        
        # Import needed modules
        from utils.api import extract_world_id
        from database.models import WorldPosts
        import re
        
        for thread_id, thread_name in self.threads:
            try:
                # Get the thread
                thread = forum_channel.get_thread(thread_id)
                if not thread:
                    continue
                
                # Look through more messages (up to 20) to find links
                found_world_id = None
                found_world_link = None
                
                async for message in thread.history(limit=20):
                    # Check message content for VRChat links
                    if message.content:
                        urls = re.findall(
                            r'https://vrchat\.com/home/world/wrld_[a-zA-Z0-9_-]+(?:/info)?', 
                            message.content
                        )
                        if urls:
                            found_world_link = urls[0]
                            found_world_id = extract_world_id(found_world_link)
                            break
                
                    # Check embeds too
                    if message.embeds:
                        for embed in message.embeds:
                            if embed.url and "vrchat.com/home/world" in embed.url:
                                found_world_link = embed.url
                                found_world_id = extract_world_id(found_world_link)
                                break
                
                    if found_world_id:
                        break
                
                if found_world_id:
                    # Found a world ID, add it to the database
                    WorldPosts.add_world_post(
                        server_id=server_id,
                        user_id=message.author.id if message.author else 0,
                        thread_id=thread_id,
                        world_id=found_world_id,
                        world_link=found_world_link
                    )
                    fixed_count += 1
                else:
                    not_found_count += 1
                    
            except Exception as e:
                config.logger.error(f"Error scanning thread {thread_id}: {e}")
                not_found_count += 1
        
        embed = discord.Embed(
            title="Advanced Thread Scan Result",
            description=f"✅ Found valid VRChat world links in {fixed_count} threads!",
            color=discord.Color.dark_red()
        )
        
        if not_found_count > 0:
            embed.add_field(
                name="Remaining Issues",
                value=f"⚠️ Could not find VRChat world links in {not_found_count} threads. These may need manual review.",
                inline=False
            )
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        
        await progress_message.edit(embed=embed)
        await interaction.message.edit(view=self)

# Duplicate world handling view
class DuplicateReviewView(discord.ui.View):
    """View for reviewing and handling duplicate world threads."""
    
    def __init__(self, scan_data: Dict[str, Any], duplicates: List[Tuple[str, int, int]]):
        super().__init__(timeout=300)  # 5 minute timeout
        self.scan_data = scan_data
        self.duplicates = duplicates
        
    @discord.ui.button(label="Keep All", style=discord.ButtonStyle.secondary, emoji="1️⃣", row=0)
    async def keep_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Keep all duplicate threads."""
        await interaction.response.defer(thinking=True)
        
        embed = discord.Embed(
            title="Duplicate Review Result",
            description=f"✅ Keeping all {len(self.duplicates)} duplicate world threads.",
            color=discord.Color.dark_red()
        )
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        
        await interaction.followup.send(embed=embed)
        await interaction.message.edit(view=self)
    
    @discord.ui.button(label="Keep Oldest Only", style=discord.ButtonStyle.danger, emoji="2️⃣", row=0)
    async def keep_oldest(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Keep the oldest threads and remove duplicates."""
        await interaction.response.defer(thinking=True)
        
        server_id = self.scan_data.get('server_id')
        forum_channel_id = self.scan_data.get('forum_channel_id')
        forum_channel = interaction.guild.get_channel(forum_channel_id)
        
        removed_count = 0
        failed_count = 0
        
        for world_id, thread_id1, thread_id2 in self.duplicates:
            try:
                # Get the duplicate thread
                thread = forum_channel.get_thread(thread_id2)
                if thread:
                    await thread.delete()
                    
                    # Remove from database if it exists
                    from database.models import WorldPosts
                    WorldPosts.remove_post_by_thread(server_id, thread_id2)
                    
                    removed_count += 1
            except Exception as e:
                config.logger.error(f"Error removing duplicate thread {thread_id2}: {e}")
                failed_count += 1
        
        embed = discord.Embed(
            title="Duplicate Review Result",
            description=f"✅ Removed {removed_count} duplicate world threads.",
            color=discord.Color.dark_red()
        )
        
        if failed_count > 0:
            embed.add_field(
                name="Issues",
                value=f"⚠️ Failed to remove {failed_count} threads due to errors.",
                inline=False
            )
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        
        await interaction.followup.send(embed=embed)
        await interaction.message.edit(view=self)
    
    @discord.ui.button(label="Review Individually", style=discord.ButtonStyle.primary, emoji="3️⃣", row=0)
    async def review_individually(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show an interface to review each duplicate pair individually."""
        await interaction.response.defer(thinking=True)
        
        embed = discord.Embed(
            title="Individual Review",
            description="This would show an interface for reviewing each duplicate thread individually.",
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name="Feature Coming Soon",
            value="Individual review functionality is under development. For now, please use the other options.",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)