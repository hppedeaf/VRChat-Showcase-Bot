"""
UI modals for the VRChat World Showcase Bot.
"""
import discord
from typing import Optional, Dict, Any, List, Union
from collections import namedtuple
import config as config
import logging
from database.models import UserWorldLinks, ThreadWorldLinks, ServerChannels, ServerTags, WorldPosts
from utils.api import extract_world_id, VRChatAPI
from utils.formatters import bytes_to_mb, format_vrchat_date
from utils.embed_builders import build_world_embed, build_tag_selection_embed
from ui.views import TagSelectionView

class WorldLinkModal(discord.ui.Modal, title='Post World Link Here'):
    """Modal for entering a VRChat world link."""
    
    def __init__(self):
        """Initialize the world link modal."""
        super().__init__(timeout=None)
        self.guild_id: Optional[int] = None
        self.message_id: Optional[int] = None
        self.selected_tags: List[str] = []  # Initialize selected_tags list

    # Define the text input field
    answer = discord.ui.TextInput(
        label='Link here', 
        style=discord.TextStyle.short, 
        placeholder="https://vrchat.com/home/world/wrld_..."
    )

    async def on_submit(self, interaction: discord.Interaction):
        """
        Handle modal submission.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(ephemeral=True)  # Defer the response
        
        # Store guild_id from the interaction for later use
        self.guild_id = interaction.guild_id
        
        link = self.answer.value
        world_id = extract_world_id(link)
        
        if not world_id:
            # If the link does not contain a valid world ID
            await interaction.followup.send(
                'Invalid VRChat world link. Please provide a valid link.', 
                ephemeral=True
            )
            return
    
        # Check if the world_id already exists in the database
        existing_thread = ThreadWorldLinks.get_thread_for_world(interaction.guild_id, world_id)
        
        if existing_thread:
            # If the world already exists, notify the user and reference the thread
            await interaction.followup.send(
                f"This world has already been posted in the thread: <#{existing_thread}>.",
                ephemeral=True
            )
            return  # Stop further execution since the world already exists
    
        # Initialize VRChat API with auth token from config
        vrchat_api = VRChatAPI()
        
        # Fetch world details from the VRChat API
        world_details = vrchat_api.get_world_info(world_id)
        if not world_details:
            # If fetching details fails
            await interaction.followup.send(
                "Failed to fetch world details. VRChat API might be restricted or invalid credentials were used.",
                ephemeral=True
            )
            return
    
        # Save the new world link to the database
        user_id = interaction.user.id
        try:
            UserWorldLinks.set_world_link(user_id, link, world_id)
        except Exception as e:
            config.logger.error(f"Database error in on_submit: {e}")
            await interaction.followup.send(f"Database error: {e}", ephemeral=True)
            return
    
        # Proceed to allow the user to choose tags
        await self.choose_tags(interaction, world_details, link)

    async def choose_tags(self, interaction: discord.Interaction, world_details: Dict[str, Any], world_link: str):
        """
        Allow the user to choose tags for the world.
        
        Args:
            interaction: Discord interaction
            world_details: World details from VRChat API
            world_link: VRChat world link
        """
        world_name = world_details['name']
        image_url = world_details.get('imageUrl', 'No image available')
        server_id = interaction.guild.id

        # Create embed for tag selection
        embed = build_tag_selection_embed(world_name, image_url)
                
        # Get tags from the database and forum channel
        choice_map = {}
        
        # First, get the forum channel
        forum_config = ServerChannels.get_forum_channel(server_id)
        
        if not forum_config:
            # Fallback to default tags if no forum channel is set
            choice_map = config.DEFAULT_TAGS
        else:
            forum_channel_id = forum_config[0]
            forum_channel = interaction.guild.get_channel(forum_channel_id)
            
            if forum_channel and forum_channel.available_tags:
                # Check if user has moderator permissions
                is_moderator = (interaction.user.guild_permissions.manage_messages or 
                            interaction.user.guild_permissions.moderate_members or
                            interaction.user.guild_permissions.administrator)
                
                config.logger.info(f"User {interaction.user.id} has moderator permissions: {is_moderator}")
                
                # Get tags from the forum channel
                for tag in forum_channel.available_tags:
                    # Check if this tag has the moderator-only setting
                    is_moderated = False
                    try:
                        # Access the moderated attribute directly
                        is_moderated = getattr(tag, "moderated", False)
                    except AttributeError:
                        # If attribute doesn't exist, check if it's in the dictionary
                        if hasattr(tag, "__dict__"):
                            is_moderated = tag.__dict__.get("moderated", False)
                    
                    config.logger.debug(f"Tag {tag.name} (ID: {tag.id}) is moderated: {is_moderated}")
                    
                    # Skip moderated tags for non-moderators
                    if is_moderated and not is_moderator:
                        config.logger.info(f"Skipping moderated tag '{tag.name}' (ID: {tag.id}) for non-moderator user {interaction.user.id}")
                        continue
                        
                    # Get the emoji for this tag
                    emoji = str(tag.emoji) if tag.emoji else "🏷️"
                    choice_map[emoji] = tag.name
            else:
                # Fallback to getting tags from the database
                server_tags = ServerTags.get_all_tags(server_id)
                
                # Use default emoji if we can't get the actual emoji
                for tag in server_tags:
                    emoji = tag.get('emoji', "🏷️")
                    choice_map[emoji] = tag['tag_name']
        
        # If we still have no tags, use the default ones
        if not choice_map:
            config.logger.warning(f"No tags found for server {server_id}, using defaults")
            choice_map = config.DEFAULT_TAGS
        
        # Create the tag selection view
        view = TagSelectionView(choice_map, self.handle_tag_submission, world_link)
        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.message = message

    async def handle_tag_submission(self, interaction: discord.Interaction, world_link: str, selected_tags: List[str]):
        """
        Handle the submission of tags and create the world post with improved validation.
        
        Args:
            interaction: Discord interaction
            world_link: VRChat world link
            selected_tags: List of selected tag names
        """
        # Extract world ID
        world_id = extract_world_id(world_link)
        
        if not world_id:
            await interaction.followup.send(
                "Failed to extract a valid world ID from the provided link. Please try again with a correct VRChat world link.",
                ephemeral=True
            )
            return
            
        # Update user data with selected tags
        self.selected_tags = selected_tags
        
        # Log the submission with more details
        config.logger.info(f"User {interaction.user.id} selected tags: {selected_tags} for world {world_id}")
        
        # Validate tags against forum channel permissions
        server_id = interaction.guild_id
        forum_config = ServerChannels.get_forum_channel(server_id)
        
        if forum_config:
            forum_channel_id = forum_config[0]
            forum_channel = interaction.guild.get_channel(forum_channel_id)
            
            if forum_channel and forum_channel.available_tags:
                # Check if any selected tags are moderated
                moderated_tags = []
                for tag_name in selected_tags:
                    for available_tag in forum_channel.available_tags:
                        if available_tag.name == tag_name:
                            is_moderated = getattr(available_tag, "moderated", False)
                            if is_moderated:
                                moderated_tags.append(tag_name)
                            break
                
                # If moderated tags were selected, check if user has permission
                if moderated_tags:
                    has_permission = (
                        interaction.user.guild_permissions.manage_messages or
                        interaction.user.guild_permissions.moderate_members or
                        interaction.user.guild_permissions.administrator
                    )
                    
                    if not has_permission:
                        config.logger.warning(
                            f"User {interaction.user.id} selected moderated tags {moderated_tags} without permission"
                        )
                        # We'll continue but log the warning - tags will be filtered during application
        
        # Save tags to database for this user
        UserWorldLinks.set_user_choices(interaction.user.id, selected_tags)
        
        # Proceed with world post creation
        await self.create_world_post(interaction, world_id, interaction.user, world_link)

# In ui/modals.py, update the create_world_post method to better handle tag application

async def create_world_post(
    self, 
    interaction: discord.Interaction, 
    world_id: str, 
    author: discord.User, 
    world_link: str
):
    """
    Create a new thread for a VRChat world post with improved tag handling.
    """
    server_id = self.guild_id
    user_id = author.id
    
    # Get the forum channel for this server
    forum_config = ServerChannels.get_forum_channel(server_id)
    if not forum_config:
        await interaction.followup.send(
            "Forum channel is not set for this server. Use `/world-create` to create a new forum channel.",
            ephemeral=True
        )
        return

    forum_channel_id = forum_config[0]
    forum_channel = interaction.client.get_channel(forum_channel_id)

    if not forum_channel:
        await interaction.followup.send(
            "Forum channel is not set correctly. Please use `/world-create` to create a new forum channel.",
            ephemeral=True
        )
        return

    # Check if this world already exists in this server
    from database.models import WorldPosts
    existing_thread_id = WorldPosts.get_thread_for_world(server_id, world_id)
    if existing_thread_id:
        await interaction.followup.send(
            f"A thread for this VRChat world already exists: <#{existing_thread_id}>. " +
            f"If **Unknown**, please send to the server admin with the ID number: {existing_thread_id}",
            ephemeral=True
        )
        return

    # Initialize VRChat API with auth token from config
    vrchat_api = VRChatAPI(config.AUTH)
    
    # [Debug logging and world details fetching code omitted for brevity]

    world_details = vrchat_api.get_world_info(world_id)
    if not world_details:
        await interaction.followup.send(
            "Failed to retrieve world information. Please check your VRChat link and try again.",
            ephemeral=True
        )
        return

    try:
        # Extract world details
        world_name = world_details['name']
        author_name = world_details['authorName']
        
        # [World details processing code omitted for brevity]
        file_rest_id = vrchat_api.get_file_rest_id(world_details)
        world_size_bytes = vrchat_api.get_world_size(file_rest_id)
        world_size_mb = bytes_to_mb(world_size_bytes)
        platform_info = vrchat_api.get_platform_info(world_details)
        
        # Create visit button for the world
        visit_button = discord.ui.Button(
            style=discord.ButtonStyle.link,
            label="Visit World",
            url=f"https://vrchat.com/home/world/{world_id}"
        )
        
        # Create view with the visit button
        view = discord.ui.View()
        view.add_item(visit_button)
        
        # Build the world embed
        embed = build_world_embed(
            world_details, 
            world_id, 
            world_size_mb, 
            platform_info,
            interaction.user.name
        )

        # Create a thread in the forum channel
        created = await forum_channel.create_thread(
            name=world_name,
            embed=embed,
            view=view
        )

        thread = created.thread
        
        # Apply tags to the thread based on user's choices
        if self.selected_tags:
            config.logger.info(f"Attempting to apply tags: {self.selected_tags} to thread {thread.id}")
            
            # Verify which tags the user can apply
            valid_tags = []
            for tag_name in self.selected_tags:
                # Find the tag in the forum's available tags
                tag_id = None
                is_moderated = False
                
                for available_tag in forum_channel.available_tags:
                    if available_tag.name == tag_name:
                        tag_id = available_tag.id
                        try:
                            is_moderated = getattr(available_tag, "moderated", False)
                        except:
                            is_moderated = False
                        break
                
                if tag_id is None:
                    config.logger.warning(f"Tag '{tag_name}' not found in forum channel tags")
                    continue
                
                # Check if user can apply this tag
                can_apply = True
                if is_moderated:
                    has_permission = (
                        interaction.user.guild_permissions.manage_messages or
                        interaction.user.guild_permissions.moderate_members or
                        interaction.user.guild_permissions.administrator
                    )
                    if not has_permission:
                        config.logger.warning(f"User {interaction.user.id} cannot apply moderated tag '{tag_name}'")
                        can_apply = False
                
                if can_apply:
                    valid_tags.append((tag_id, tag_name))
            
            # Get tag IDs from the database
            tag_ids = [tag_id for tag_id, _ in valid_tags]
            
            if tag_ids:
                # Create a namedtuple to represent tags with IDs
                Tag = namedtuple('Tag', ['id'])
                
                # Create tag objects
                tag_objects = [Tag(id=tag_id) for tag_id in tag_ids]
                
                if tag_objects:
                    if len(tag_objects) > 5:
                        tag_objects = tag_objects[:5]  # Limit to 5 tags

                    try:
                        # Add tags to the thread
                        await thread.add_tags(*tag_objects, reason="Added by bot based on user's choices")
                        config.logger.info(f"Added tags {[name for _, name in valid_tags]} to thread {thread.id}")
                    except Exception as e:
                        config.logger.error(f"Error adding tags: {e}")
                        # Try alternative method for adding tags
                        try:
                            config.logger.info(f"Trying alternative method for adding tags to thread {thread.id}")
                            # Try to edit the thread to apply tags
                            await thread.edit(applied_tags=tag_objects)
                            config.logger.info(f"Successfully added tags using edit method")
                        except Exception as edit_error:
                            config.logger.error(f"Error adding tags with edit method: {edit_error}")
            else:
                config.logger.warning(f"No valid tags to apply to thread {thread.id}")

        # Save thread information to the database
        thread_id = thread.id
        
        # Use the WorldPosts class to save all relevant information
        WorldPosts.add_world_post(
            server_id=server_id,
            user_id=user_id,
            thread_id=thread_id,
            world_id=world_id,
            world_link=world_link,
            user_choices=self.selected_tags  # Save all selected tags, even if some couldn't be applied
        )

        await interaction.followup.send(
            f"Thank you! Your world has been posted successfully! View it here: <#{thread_id}>", 
            ephemeral=True
        )
        
    except Exception as e:
        config.logger.error(f"Error creating world post: {e}")
        await interaction.followup.send(f"An error occurred while creating the post: {e}", ephemeral=True)