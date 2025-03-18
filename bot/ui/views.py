"""
UI views for the VRChat World Showcase Bot.
"""
import discord
from typing import Dict, Any, List, Callable, Awaitable, Optional, Union
from collections import namedtuple
import config
import logging

class TagSelectionView(discord.ui.View):
    """View for selecting tags for a world post."""
    
    def __init__(
        self, 
        tag_mapping: Dict[str, str], 
        callback: Callable[[discord.Interaction, str, List[str]], Awaitable[None]], 
        world_link: str
    ):
        """
        Initialize the tag selection view.
        
        Args:
            tag_mapping: Dictionary mapping emoji to tag name
            callback: Callback function to call when tags are submitted
            world_link: VRChat world link
        """
        super().__init__(timeout=config.TAG_VIEW_TIMEOUT)
        self.tag_mapping = tag_mapping
        self.selected_tags: List[str] = []
        self.callback = callback
        self.world_link = world_link
        self.message: Optional[discord.Message] = None
        
        # Organize buttons in rows (max 5 buttons per row, max 5 rows = 25 tags maximum)
        items_per_row = 5
        max_rows = 4  # Allow for 4 rows of tags (20 tags) + 1 row for Submit/Cancel
        items = list(tag_mapping.items())
        
        # Limit to max number of tags we can display
        max_tags = items_per_row * max_rows
        if len(items) > max_tags:
            items = items[:max_tags]
            config.logger.warning(f"Too many tags ({len(tag_mapping)}), limiting to {max_tags}")
        
        # Add tag buttons organized in rows
        for i in range(0, len(items), items_per_row):
            row_items = items[i:i+items_per_row]
            for emoji_identifier, tag in row_items:
                # Add the button with appropriate emoji
                self._add_tag_button(emoji_identifier, tag, i // items_per_row)
        
        # Add Submit and Cancel buttons in the last row
        last_row = max_rows  # Always put control buttons in the last row
        
        submit_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Submit",
            emoji="✅",
            custom_id="submit_button",
            row=last_row
        )
        submit_button.callback = self.submit_callback
        self.add_item(submit_button)
        
        cancel_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Cancel",
            emoji="❌",
            custom_id="cancel_button",
            row=last_row
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    def _add_tag_button(self, emoji_identifier: str, tag: str, row: int):
        """
        Add a tag button to the view.
        
        Args:
            emoji_identifier: Emoji identifier (Unicode or Discord custom emoji)
            tag: Tag name
            row: Row number
        """
        # Handle different types of emoji
        emoji = self._parse_emoji(emoji_identifier)
        
        # Create the button
        button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=tag,
            emoji=emoji,
            custom_id=f"tag_{tag}",
            row=row
        )
        button.callback = self.tag_button_callback
        self.add_item(button)
    
    def _parse_emoji(self, emoji_identifier: str) -> Union[str, discord.PartialEmoji, None]:
        """
        Parse an emoji identifier into a usable emoji object.
        
        Args:
            emoji_identifier: Emoji identifier (Unicode or Discord custom emoji)
            
        Returns:
            Parsed emoji object
        """
        # Check if this is a custom emoji (starts with <: or <a:)
        if emoji_identifier.startswith('<:') or emoji_identifier.startswith('<a:'):
            # Extract emoji ID from the format <:name:id> or <a:name:id>
            emoji_parts = emoji_identifier.strip('<>').split(':')
            if len(emoji_parts) == 3:  # Should be [animated or empty, name, id]
                emoji_name = emoji_parts[1]
                emoji_id = int(emoji_parts[2])
                # Create a discord.Emoji or discord.PartialEmoji object
                if emoji_identifier.startswith('<a:'):
                    return discord.PartialEmoji(name=emoji_name, id=emoji_id, animated=True)
                else:
                    return discord.PartialEmoji(name=emoji_name, id=emoji_id)
        
        # Use as Unicode emoji or fallback
        return emoji_identifier
    
    async def tag_button_callback(self, interaction: discord.Interaction):
        """
        Handle tag button clicks.
        
        Args:
            interaction: Discord interaction
        """
        # Extract tag name from custom_id
        tag = interaction.data["custom_id"].replace("tag_", "")
        
        # Toggle tag selection
        if tag in self.selected_tags:
            self.selected_tags.remove(tag)
            # Update button to show deselected state
            for child in self.children:
                if hasattr(child, "custom_id") and child.custom_id == f"tag_{tag}":
                    child.style = discord.ButtonStyle.secondary
        else:
            # Check if we can add more tags
            if len(self.selected_tags) < 5:
                self.selected_tags.append(tag)
                # Update button to show selected state
                for child in self.children:
                    if hasattr(child, "custom_id") and child.custom_id == f"tag_{tag}":
                        child.style = discord.ButtonStyle.primary
            else:
                await interaction.response.send_message(
                    "You can only select up to 5 tags. Deselect one first.", 
                    ephemeral=True
                )
                return
        
        # Update the message with current selections
        embed = interaction.message.embeds[0]
        embed.description = (
            f"Selected tags ({len(self.selected_tags)}/5): {', '.join(self.selected_tags)}\n\n"
            "Click on tags to select/deselect. Click Submit when done."
        )
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def submit_callback(self, interaction: discord.Interaction):
        """
        Handle submit button click.
        
        Args:
            interaction: Discord interaction
        """
        if not self.selected_tags:
            await interaction.response.send_message(
                "Please select at least one tag before submitting.", 
                ephemeral=True
            )
            return
        
        # Call the provided callback with the selected tags
        await interaction.response.defer()
        await self.callback(interaction, self.world_link, self.selected_tags)
        
        # Disable all buttons to prevent further interactions
        for child in self.children:
            child.disabled = True
        
        await interaction.message.edit(view=self)
        await interaction.message.delete(delay=1)  # Delete message after a short delay
    
    async def cancel_callback(self, interaction: discord.Interaction):
        """
        Handle cancel button click.
        
        Args:
            interaction: Discord interaction
        """
        await interaction.response.send_message("Tag selection canceled.", ephemeral=True)
        await interaction.message.delete()
        self.stop()

    async def on_timeout(self):
        """Handle view timeout."""
        # If the view times out, disable all buttons
        for child in self.children:
            child.disabled = True
        
        # Try to update the message if it still exists
        if self.message:
            try:
                await self.message.edit(view=self)
                await self.message.delete(delay=5)  # Delete after 5 seconds
            except discord.NotFound:
                pass  # Message was already deleted
            except Exception as e:
                config.logger.error(f"Error handling view timeout: {e}")
                