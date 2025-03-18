"""
UI modals for the VRChat World Showcase Bot.
"""
import discord
from typing import Optional, Dict, Any, List, Union
from collections import namedtuple
import config
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
                # Get tags from the forum channel
                for tag in forum_channel.available_tags:
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
        """Handle the submission of tags and create the world post."""
        # Extract world ID
        world_id = extract_world_id(world_link)
        
        # Update user data with selected tags
        self.selected_tags = selected_tags
        
        # Save tags to database for this user
        UserWorldLinks.set_user_choices(interaction.user.id, selected_tags)
        
        # Log the submission
        config.logger.info(f"User {interaction.user.id} selected tags: {selected_tags} for world {world_id}")
        
        # Proceed with world post creation
        await self.create_world_post(interaction, world_id, interaction.user, world_link)

    async def create_world_post(
        self, 
        interaction: discord.Interaction, 
        world_id: str, 
        author: discord.User, 
        world_link: str
    ):
        """
        Create a new thread for a VRChat world post.
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
        
        def debug_file_id_extraction(world_details):
            """Debug function to log details about file ID extraction"""
            config.logger.info("===== FILE ID EXTRACTION DEBUG =====")
            
            if not world_details:
                config.logger.warning("World details is None")
                return
            
            # Log all top-level keys
            config.logger.info(f"World info keys: {list(world_details.keys())}")
            
            # Check for direct assetUrl
            if "assetUrl" in world_details:
                config.logger.info(f"Direct assetUrl: {world_details['assetUrl']}")
            
            # Check for unityPackages
            if "unityPackages" in world_details:
                packages = world_details["unityPackages"]
                config.logger.info(f"Found {len(packages)} unity packages")
                
                for i, package in enumerate(packages):
                    config.logger.info(f"Package {i+1} keys: {list(package.keys())}")
                    
                    if "assetUrl" in package:
                        config.logger.info(f"Package {i+1} assetUrl: {package['assetUrl']}")
                    
                    if "platform" in package:
                        config.logger.info(f"Package {i+1} platform: {package['platform']}")
                        
            # Check for version information
            if "version" in world_details:
                version = world_details["version"]
                if isinstance(version, dict):
                    config.logger.info(f"Version keys: {list(version.keys())}")
            
            # Check for any keys that might contain "file" in their name
            file_related_keys = [k for k in world_details.keys() if "file" in k.lower()]
            if file_related_keys:
                config.logger.info(f"File-related keys: {file_related_keys}")
                for key in file_related_keys:
                    config.logger.info(f"{key}: {world_details[key]}")
            
            # Check for any keys that might contain "asset" in their name
            asset_related_keys = [k for k in world_details.keys() if "asset" in k.lower()]
            if asset_related_keys:
                config.logger.info(f"Asset-related keys: {asset_related_keys}")
                for key in asset_related_keys:
                    config.logger.info(f"{key}: {world_details[key]}")
            
            # Check for imageUrl - sometimes contains similar patterns
            if "imageUrl" in world_details:
                config.logger.info(f"Image URL: {world_details['imageUrl']}")
            
            # Manual pattern search for file IDs
            import re
            for key, value in world_details.items():
                if isinstance(value, str):
                    match = re.search(r'file_[a-f0-9-]+', value)
                    if match:
                        config.logger.info(f"Found potential file ID pattern in {key}: {match.group(0)}")
            
            config.logger.info("===== END FILE ID DEBUG =====")
    
        # Add this to your modals.py file where you're experiencing the issue

        def debug_vrchat_world(world_details, file_id=None):
            """Debug function to log details about VRChat world information and file size"""
            config.logger.info("===== VRCHAT WORLD DEBUG =====")
            
            # PART 1: Debug file ID extraction
            if not world_details:
                config.logger.warning("World details is None")
                return
            
            # Log all top-level keys
            config.logger.info(f"World info keys: {list(world_details.keys())}")
            
            # Check for direct assetUrl
            if "assetUrl" in world_details:
                config.logger.info(f"Direct assetUrl: {world_details['assetUrl']}")
            
            # Check for unityPackages
            if "unityPackages" in world_details:
                packages = world_details["unityPackages"]
                config.logger.info(f"Found {len(packages)} unity packages")
                
                for i, package in enumerate(packages):
                    config.logger.info(f"Package {i+1} keys: {list(package.keys())}")
                    
                    if "assetUrl" in package:
                        config.logger.info(f"Package {i+1} assetUrl: {package['assetUrl']}")
                    
                    if "platform" in package:
                        config.logger.info(f"Package {i+1} platform: {package['platform']}")
            
            # Check for any keys that might contain "file" in their name
            file_related_keys = [k for k in world_details.keys() if "file" in k.lower()]
            if file_related_keys:
                config.logger.info(f"File-related keys: {file_related_keys}")
                for key in file_related_keys:
                    config.logger.info(f"{key}: {world_details[key]}")
            
            # Manual pattern search for file IDs
            import re
            for key, value in world_details.items():
                if isinstance(value, str):
                    match = re.search(r'file_[a-f0-9-]+', value)
                    if match:
                        config.logger.info(f"Found potential file ID pattern in {key}: {match.group(0)}")
            
            # PART 2: Debug world size if file_id is provided
            if file_id:
                config.logger.info(f"File ID for world: {file_id}")
                
                # Try to directly get file info
                try:
                    from utils.api import VRChatAPI
                    api = VRChatAPI(config.AUTH)
                    file_info = api.get_file_info(file_id)
                    
                    if file_info:
                        config.logger.info(f"File info retrieved successfully")
                        config.logger.info(f"File info keys: {list(file_info.keys())}")
                        
                        if "versions" in file_info:
                            versions = file_info["versions"]
                            config.logger.info(f"Found {len(versions)} versions")
                            
                            # Check last version
                            if versions and len(versions) > 0:
                                last_version = versions[-1]
                                config.logger.info(f"Last version keys: {list(last_version.keys())}")
                                
                                if "file" in last_version:
                                    file_data = last_version["file"]
                                    config.logger.info(f"File data keys: {list(file_data.keys())}")
                                    
                                    if "sizeInBytes" in file_data:
                                        size = file_data["sizeInBytes"]
                                        config.logger.info(f"Size in bytes: {size}")
                                        
                                        # Test bytes_to_mb function
                                        from utils.formatters import bytes_to_mb
                                        formatted = bytes_to_mb(size)
                                        config.logger.info(f"Formatted size: {formatted}")
                    else:
                        config.logger.warning("Failed to retrieve file info")
                except Exception as e:
                    config.logger.error(f"Error getting file info: {e}")
            
            config.logger.info("===== END VRCHAT WORLD DEBUG =====")

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
            
            # Get file ID and world size
            file_rest_id = vrchat_api.get_file_rest_id(world_details)
            config.logger.info(f"File ID for world {world_id}: {file_rest_id}")
            
            # Debug the world details and file ID extraction
            debug_vrchat_world(world_details, file_rest_id)
            
            # Get world size in bytes
            world_size_bytes = vrchat_api.get_world_size(file_rest_id)
            config.logger.info(f"World size raw value: {world_size_bytes}")
            
            # Convert to human-readable format
            world_size_mb = bytes_to_mb(world_size_bytes)
            config.logger.info(f"Formatted world size: {world_size_mb}")
            
            platform_info = vrchat_api.get_platform_info(world_details)
            
            # Get world size in bytes
            world_size_bytes = vrchat_api.get_world_size(file_rest_id)
            config.logger.info(f"World size raw value: {world_size_bytes}")
            
            # Convert to human-readable format
            world_size_mb = bytes_to_mb(world_size_bytes)
            config.logger.info(f"Formatted world size: {world_size_mb}")
            
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
            # Use self.selected_tags directly instead of retrieving from database
            if self.selected_tags:
                # Get tag IDs from the database
                tag_ids = ServerTags.get_tag_ids(server_id, self.selected_tags)
                
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
                        config.logger.info(f"Added tags {self.selected_tags} to thread {thread.id}")
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

            # Save thread information to the database
            thread_id = thread.id
            
            # Use the WorldPosts class to save all relevant information
            WorldPosts.add_world_post(
                server_id=server_id,
                user_id=user_id,
                thread_id=thread_id,
                world_id=world_id,
                world_link=world_link,
                user_choices=self.selected_tags  # Use self.selected_tags directly
            )

            await interaction.followup.send(
                f"Thank you! Your world has been posted successfully! View it here: <#{thread_id}>", 
                ephemeral=True
            )
            
        except Exception as e:
            config.logger.error(f"Error creating world post: {e}")
            await interaction.followup.send(f"An error occurred while creating the post: {e}", ephemeral=True)