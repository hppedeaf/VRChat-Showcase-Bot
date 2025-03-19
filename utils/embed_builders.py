"""
Functions to build Discord embeds for various purposes.
"""
import re
import discord
from typing import Dict, Any, List, Optional
from datetime import datetime
import config as config
from utils.formatters import truncate_text, bytes_to_mb

def build_world_embed(
    world_info: Dict[str, Any], 
    world_id: str, 
    world_size: str, 
    platform_info: str,
    user_name: str
) -> discord.Embed:
    """
    Build a Discord embed for a VRChat world.
    
    Args:
        world_info: World information from VRChat API
        world_id: VRChat world ID
        world_size: World size string (e.g., "10.5 MB")
        platform_info: Platform support string
        user_name: Name of the Discord user posting the world
        
    Returns:
        Discord embed for the world
    """
    # Debug log to check what's being passed to the function
    config.logger.info(f"Building embed with size: {world_size}")
    
    world_name = world_info['name']
    author_name = world_info['authorName']
    description = world_info.get('description', 'No description available')
    capacity = world_info.get('capacity', 'Unknown')
    created_at = world_info.get('created_at', 'Unknown')
    updated_at = world_info.get('updated_at', 'Unknown')
    visits = world_info.get('visits', 'Unknown')
    favorites = world_info.get('favorites', 'Unknown')
    image_url = world_info.get('imageUrl', 'No image available')
    world_link = f"https://vrchat.com/home/world/{world_id}"
    
    # Format dates
    if created_at != 'Unknown':
        from utils.formatters import format_vrchat_date
        created_at = format_vrchat_date(created_at)
    
    if updated_at != 'Unknown':
        from utils.formatters import format_vrchat_date
        updated_at = format_vrchat_date(updated_at)
    
    # Create embed
    embed = discord.Embed(
        title=world_name,
        color=discord.Color.dark_red(),
        url=world_link
    )
    
    embed.set_footer(text=f"Posted by {user_name}")
    embed.description = truncate_text(description, 4096)
    
    # Format visits and favorites if they are between 100,000 and 1,000,000
    if visits != 'Unknown':
        visits = "{:,}".format(visits)
        
    if favorites != 'Unknown':
        favorites = "{:,}".format(favorites)
    
    # Handle Unknown world size with a better fallback message
    display_size = world_size
    if world_size == "Unknown":
        display_size = "Not Available"

    # Add fields with proper fallbacks
    embed.add_field(name="World Size", value=display_size, inline=True)
    embed.add_field(name="Platform", value=platform_info, inline=True)
    embed.add_field(name="Capacity", value=capacity, inline=True)
    embed.add_field(name="Published", value=created_at, inline=True)
    embed.add_field(name="Updated", value=updated_at, inline=True)
    embed.add_field(name="Author", value=author_name, inline=True)
    embed.add_field(name="Visits", value=visits, inline=True)
    embed.add_field(name="Favorites", value=favorites, inline=True)
    
    if image_url and image_url != 'No image available':
        embed.set_image(url=image_url)
    
    return embed

def build_about_embed() -> discord.Embed:
    """
    Build an enhanced Discord embed for the about command.
    
    Returns:
        Discord embed with detailed information about the bot
    """
    embed = discord.Embed(
        title="VRChat World Showcase Bot",
        description="This bot helps you create and manage an organized showcase of VRChat worlds in your Discord server. Find exciting new worlds to explore!",
        color=discord.Color.dark_red()
    )
    
    embed.add_field(
        name="📋 What This Bot Does",
        value=(
            "• Creates a forum channel to showcase VRChat worlds\n"
            "• Allows users to submit worlds with proper tags\n"
            "• Extracts detailed information directly from VRChat API\n"
            "• Shows world size, platform support, and capacity\n"
            "• Prevents duplicate world submissions\n"
            "• Organizes worlds with customizable tags\n"
            "• Sets up gallery view for visual browsing\n"
            "• Automatically adds visit buttons to each world"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔍 For Server Members",
        value=(
            "To submit a VRChat world:\n"
            "1. Go to the world showcase channel\n"
            "2. Find the pinned post with the **World** button\n"
            "3. Click the **World** button\n"
            "4. Paste the VRChat world link (e.g., https://vrchat.com/home/world/wrld_...)\n"
            "5. Select appropriate tags for better discovery\n"
            "6. Click Submit to share the world with everyone!"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ For Admins",
        value=(
            "Available commands:\n"
            "• `/world-create` - Create a new forum channel for showcasing worlds\n"
            "• `/world-set` - Configure an existing forum channel\n"
            "• `/world-remove` - Remove a specific world post\n"
            "• `/scan` - Scan forum for issues and fix them automatically\n"
            "• `/clean-db` - Clean up database entries for deleted channels\n"
            "• `/repair-threads` - Fix threads with missing world links\n"
            "• `/world` - Add a world submission button in any channel"
        ),
        inline=False
    )
    
    embed.add_field(
        name="💡 Tips",
        value=(
            "• World posts include direct visit links to the VRChat worlds\n"
            "• Tags help users find worlds matching specific interests\n"
            "• Admins can use `/scan` to fix missing tags or duplicates\n"
            "• Discord forum searching works for finding specific worlds\n" 
            "• The bot prevents duplicate submissions automatically"
        ),
        inline=False
    )
    
    embed.set_footer(text="Made with ❤️ for the VRChat community")
    
    return embed

def build_help_embed() -> discord.Embed:
    """
    Build an enhanced Discord embed for the help command.
    
    Returns:
        Discord embed with detailed command help information
    """
    embed = discord.Embed(
        title="VRChat World Showcase Bot - Command Guide",
        description="This bot helps you create and manage a showcase of VRChat worlds in your Discord server. Here are all the available commands with detailed explanations:",
        color=discord.Color.dark_red()
    )
    
    embed.add_field(
        name="📝 Member Commands",
        value=(
            "**`/about`**\n"
            "Learn what this bot does and how to use it\n\n"
            "**`/help`**\n"
            "Display this list of commands with explanations\n\n"
            "**`/test`**\n"
            "Check if the bot is online and responding\n\n"
            "**`/world`**\n"
            "Create a VRChat world submission button in the current channel"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Admin Commands",
        value=(
            "**`/world-create`**\n"
            "Create a new forum channel set up for VRChat world posts with proper permissions and tags\n\n"
            "**`/world-set [forum_channel]`**\n"
            "Set up an existing forum channel for VRChat world posts\n\n"
            "**`/world-remove [world_id_or_url] [thread]`**\n"
            "Remove a specific world post by URL, ID, or thread selection\n\n"
            "**`/scan`**\n"
            "Comprehensive scan of the forum to identify and fix issues (missing tags, duplicates, etc.)\n\n"
            "**`/clean-db`**\n"
            "Clean the database by removing references to deleted channels\n\n"
            "**`/repair-threads`**\n"
            "Fix threads that don't have proper world links in the database\n\n"
            "**`/sync`**\n"
            "Sync bot commands with Discord (useful after bot updates)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔍 Submission Process",
        value=(
            "1. Click the **World** button in the showcase channel\n"
            "2. Paste a VRChat world URL\n"
            "3. Select appropriate tags for the world\n"
            "4. Submit to create a new forum post\n\n"
            "The bot will automatically extract details from VRChat including world size, platform compatibility, capacity, and more!"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🚀 Getting Started",
        value=(
            "If you're a server admin setting up the bot for the first time:\n"
            "1. Use `/world-create` to set up a new forum channel, or\n"
            "2. Use `/world-set` to configure an existing forum channel\n"
            "3. The bot will create a control thread with a World button\n"
            "4. Members can use this button to submit VRChat worlds"
        ),
        inline=False
    )
    
    embed.set_footer(text="Use /about for more information about the bot's features")
    
    return embed

# In utils/embed_builders.py, replace or update the build_scan_results_embed function:

def build_scan_results_embed(title: str, results: List[str], part: int = 1, total_parts: int = 1) -> discord.Embed:
    """
    Build a visually enhanced Discord embed for scan results.
    
    Args:
        title: Embed title
        results: List of result strings
        part: Current part number
        total_parts: Total number of parts
        
    Returns:
        Discord embed with scan results
    """
    # Parse results to organize them into categories
    current_category = None
    categories = {
        "TAG SCAN": [],
        "THREAD SCAN": [],
        "WARNING": [],
        "HEADER": []
    }
    
    for line in results:
        if not line.strip():
            continue
            
        if "**VRCHAT WORLD SCAN RESULTS**" in line:
            categories["HEADER"].append(line)
        elif "**TAG SCAN:**" in line:
            current_category = "TAG SCAN"
        elif "**THREAD SCAN:**" in line:
            current_category = "THREAD SCAN"
        elif "⚠️ **Found" in line:
            current_category = "WARNING"
            categories[current_category].append(line)
        elif current_category:
            categories[current_category].append(line)
    
    # Create a beautiful embed with proper formatting and organization
    embed = discord.Embed(
        title=f"🔍 {title} (Part {part}/{total_parts})",
        color=discord.Color.dark_red(),
        timestamp=datetime.now()
    )
    
    # Set a thumbnail image 
    embed.set_thumbnail(url="https://cdn.discordapp.com/avatars/1156538533876613121/8acb3d0ce2c328987ad86355e0d0b528.png")
    
    # Add the header as the top section
    if categories["HEADER"]:
        embed.description = "# 🔍 VRChat World Scan Complete!\n"
        embed.description += "A comprehensive analysis of your showcase forum has been completed."
    
    # Add Tag Scan section with fancy formatting
    if categories["TAG SCAN"]:
        tag_content = "\n".join(categories["TAG SCAN"])
        # Extract numbers for visual representation
        added_match = re.search(r'Added (\d+)', tag_content)
        updated_match = re.search(r'Updated (\d+)', tag_content)
        removed_match = re.search(r'Removed (\d+)', tag_content)
        
        added = int(added_match.group(1)) if added_match else 0
        updated = int(updated_match.group(1)) if updated_match else 0
        removed = int(removed_match.group(1)) if removed_match else 0
        
        tag_field = (
            "### 🏷️ Tag Information\n"
            f"✅ **Added:** {added} new tags\n"
            f"🔄 **Updated:** {updated} existing tags\n"
            f"🗑️ **Removed:** {removed} unused tags\n"
        )
        embed.add_field(name="", value=tag_field, inline=False)
    
    # Add Thread Scan section with fancy formatting
    if categories["THREAD SCAN"]:
        thread_content = "\n".join(categories["THREAD SCAN"])
        worlds_match = re.search(r'Valid VRChat world threads: (\d+)', thread_content)
        tags_match = re.search(r'Threads with missing tags: (\d+)', thread_content)
        
        worlds = int(worlds_match.group(1)) if worlds_match else 0
        missing_tags = int(tags_match.group(1)) if tags_match else 0
        
        thread_field = (
            "### 🌐 Thread Analysis\n"
            f"✅ **Valid World Posts:** {worlds} threads\n"
            f"🏷️ **Missing Tags:** {missing_tags} tags need fixing\n"
        )
        embed.add_field(name="", value=thread_field, inline=False)
    
    # Add Warning section with fancy formatting
    if categories["WARNING"]:
        warning_content = "\n".join(categories["WARNING"])
        
        # Process duplicate warnings
        duplicate_match = re.search(r'Found (\d+) duplicate VRChat worlds', warning_content)
        if duplicate_match:
            duplicate_count = int(duplicate_match.group(1))
            
            duplicates_field = (
                "### ⚠️ Duplicate Worlds Detected\n"
                f"Found **{duplicate_count}** duplicate world posts\n"
                "These are worlds that appear in multiple threads."
            )
            embed.add_field(name="", value=duplicates_field, inline=False)
        
        # Process threads without worlds warnings
        missing_match = re.search(r'Found (\d+) threads needing review', warning_content)
        if missing_match:
            missing_count = int(missing_match.group(1))
            
            missing_field = (
                "### ⚠️ Threads Without Worlds\n"
                f"Found **{missing_count}** threads without valid world links\n"
                "These may need manual review or cleanup."
            )
            embed.add_field(name="", value=missing_field, inline=False)
        
        # If we have thread examples, add them in a collapsible format
        thread_examples = re.findall(r'- (.+) \(ID: (\d+)\)', warning_content)
        if thread_examples:
            examples_field = "### 📋 Example Threads Needing Review\n"
            for name, thread_id in thread_examples[:5]:
                examples_field += f"• **{name}** (<#{thread_id}>)\n"
            
            if len(thread_examples) > 5:
                examples_field += f"...and {len(thread_examples) - 5} more threads"
                
            embed.add_field(name="", value=examples_field, inline=False)
    
    # Add a footer with timestamp
    if part == total_parts:
        embed.set_footer(
            text="Use the buttons below to manage issues • Scan completed",
            icon_url="https://cdn.discordapp.com/emojis/1049421057178079262.webp?size=96&quality=lossless"
        )
    else:
        embed.set_footer(
            text=f"Scan results part {part} of {total_parts}",
            icon_url="https://cdn.discordapp.com/emojis/1049421057178079262.webp?size=96&quality=lossless"
        )
    
    return embed

def build_tag_selection_embed(world_name: str, image_url: str) -> discord.Embed:
    """
    Build a Discord embed for tag selection.
    
    Args:
        world_name: VRChat world name
        image_url: World image URL
        
    Returns:
        Discord embed for tag selection
    """
    embed = discord.Embed(
        title=f"Choose Tags for the World: {world_name}",
        description="Selected tags (0/5): None\n\nClick on tags to select/deselect. Click Submit when done.",
        color=discord.Color.dark_red()
    )
    
    if image_url and image_url != 'No image available':
        embed.set_image(url=image_url)
    
    return embed