"""
Database models and operations module with enhanced PostgreSQL support.
Contains functions for interacting with database tables.
"""
import sqlite3
from typing import Dict, List, Tuple, Optional, Any, Union
import config as config
from database.db import get_connection, log_activity
import os

# Check if we're using PostgreSQL
IS_POSTGRES = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")

class ServerChannels:
    """Server channel configuration operations."""
    
    @staticmethod
    def get_forum_channel(server_id: int) -> Optional[Tuple[int, int]]:
        """
        Get the forum channel ID and thread ID for a server.
        
        Args:
            server_id: Discord server ID
            
        Returns:
            Tuple of (forum_channel_id, thread_id) or None if not found
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if we're using PostgreSQL
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT forum_channel_id, thread_id FROM server_channels WHERE server_id=%s", 
                    (server_id,)
                )
            else:
                cursor.execute(
                    "SELECT forum_channel_id, thread_id FROM server_channels WHERE server_id=?", 
                    (server_id,)
                )
                
            result = cursor.fetchone()
            
            if result:
                return (result['forum_channel_id'], result['thread_id'])
            return None
    
    @staticmethod
    def set_forum_channel(server_id: int, forum_channel_id: int, thread_id: int) -> None:
        """
        Set or update the forum channel and thread for a server.
        
        Args:
            server_id: Discord server ID
            forum_channel_id: Discord forum channel ID
            thread_id: Discord thread ID for the control thread
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                # PostgreSQL upsert syntax
                cursor.execute(
                    """
                    INSERT INTO server_channels (server_id, forum_channel_id, thread_id) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (server_id) 
                    DO UPDATE SET forum_channel_id = %s, thread_id = %s
                    """,
                    (server_id, forum_channel_id, thread_id, forum_channel_id, thread_id)
                )
            else:
                # SQLite syntax
                cursor.execute(
                    "INSERT OR REPLACE INTO server_channels (server_id, forum_channel_id, thread_id) VALUES (?, ?, ?)",
                    (server_id, forum_channel_id, thread_id)
                )
            
            conn.commit()
        
        log_activity(server_id, "set_forum", f"Channel: {forum_channel_id}, Thread: {thread_id}")

    @staticmethod
    def clear_forum_channel(server_id: int) -> None:
        """
        Clear the forum channel configuration for a server.
        
        Args:
            server_id: Discord server ID
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute("DELETE FROM server_channels WHERE server_id=%s", (server_id,))
            else:
                cursor.execute("DELETE FROM server_channels WHERE server_id=?", (server_id,))
                
            conn.commit()
        
        log_activity(server_id, "clear_forum", f"Removed forum configuration")


class UserWorldLinks:
    """User world links operations."""
    
    @staticmethod
    def get_world_link(user_id: int) -> Optional[str]:
        """
        Get the VRChat world link for a user.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            World link string or None if not found
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute("SELECT world_link FROM user_world_links WHERE user_id=%s", (user_id,))
            else:
                cursor.execute("SELECT world_link FROM user_world_links WHERE user_id=?", (user_id,))
                
            result = cursor.fetchone()
            
            if result:
                return result['world_link']
            return None
    
    @staticmethod
    def set_world_link(user_id: int, world_link: str, world_id: Optional[str] = None) -> None:
        """
        Set or update the VRChat world link for a user.
        
        Args:
            user_id: Discord user ID
            world_link: VRChat world link
            world_id: Extracted world ID (optional)
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    """
                    INSERT INTO user_world_links (user_id, world_link, world_id) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET world_link = %s, world_id = %s
                    """,
                    (user_id, world_link, world_id, world_link, world_id)
                )
            else:
                cursor.execute(
                    "INSERT OR REPLACE INTO user_world_links (user_id, world_link, world_id) VALUES (?, ?, ?)",
                    (user_id, world_link, world_id)
                )
                
            conn.commit()
    
    @staticmethod
    def get_user_choices(user_id: int) -> Optional[List[str]]:
        """
        Get a user's tag choices.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            List of tag names or None if not found
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute("SELECT user_choices FROM user_world_links WHERE user_id=%s", (user_id,))
            else:
                cursor.execute("SELECT user_choices FROM user_world_links WHERE user_id=?", (user_id,))
                
            result = cursor.fetchone()
            
            if result and result['user_choices']:
                return result['user_choices'].split(',')
            return None
    
    @staticmethod
    def set_user_choices(user_id: int, choices: List[str]) -> None:
        """
        Set or update a user's tag choices.
        
        Args:
            user_id: Discord user ID
            choices: List of tag names
        """
        choices_str = ','.join(choices)
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    "UPDATE user_world_links SET user_choices = %s WHERE user_id = %s",
                    (choices_str, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE user_world_links SET user_choices = ? WHERE user_id = ?",
                    (choices_str, user_id)
                )
                
            conn.commit()
    
    @staticmethod
    def find_by_world_id(world_id: str) -> List[Dict[str, Any]]:
        """
        Find users who have posted a specific world.
        
        Args:
            world_id: VRChat world ID
            
        Returns:
            List of user records
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT * FROM user_world_links WHERE world_id = %s OR world_link LIKE %s",
                    (world_id, f"%{world_id}%")
                )
            else:
                cursor.execute(
                    "SELECT * FROM user_world_links WHERE world_id = ? OR world_link LIKE ?",
                    (world_id, f"%{world_id}%")
                )
                
            return [dict(row) for row in cursor.fetchall()]


class ThreadWorldLinks:
    """Thread world links operations."""
    
    @staticmethod
    def get_thread_for_world(server_id: int, world_id: str) -> Optional[int]:
        """
        Get the thread ID for a VRChat world in a server.
        
        Args:
            server_id: Discord server ID
            world_id: VRChat world ID
            
        Returns:
            Thread ID or None if not found
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if we're using PostgreSQL
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT thread_id FROM thread_world_links WHERE server_id=%s AND world_id=%s",
                    (server_id, world_id)
                )
            else:
                cursor.execute(
                    "SELECT thread_id FROM thread_world_links WHERE server_id=? AND world_id=?",
                    (server_id, world_id)
                )
                
            result = cursor.fetchone()
            
            if result:
                return result['thread_id']
            return None

    @staticmethod
    def get_world_for_thread(server_id: int, thread_id: int) -> Optional[str]:
        """
        Get the VRChat world ID for a thread in a server.
        
        Args:
            server_id: Discord server ID
            thread_id: Discord thread ID
            
        Returns:
            World ID or None if not found
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if we're using PostgreSQL
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT world_id FROM thread_world_links WHERE server_id=%s AND thread_id=%s",
                    (server_id, thread_id)
                )
            else:
                cursor.execute(
                    "SELECT world_id FROM thread_world_links WHERE server_id=? AND thread_id=?",
                    (server_id, thread_id)
                )
                
            result = cursor.fetchone()
            
            if result:
                return result['world_id']
            return None
    
    @staticmethod
    def add_thread_world(server_id: int, thread_id: int, world_id: str) -> None:
        """
        Add a new thread-world link.
        
        Args:
            server_id: Discord server ID
            thread_id: Discord thread ID
            world_id: VRChat world ID
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if we're using PostgreSQL
            if IS_POSTGRES:
                # PostgreSQL syntax
                cursor.execute(
                    """
                    INSERT INTO thread_world_links (server_id, thread_id, world_id) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (server_id, world_id) DO UPDATE SET 
                    thread_id = %s
                    """,
                    (server_id, thread_id, world_id, thread_id)
                )
            else:
                # SQLite syntax
                cursor.execute(
                    "INSERT OR REPLACE INTO thread_world_links (server_id, thread_id, world_id) VALUES (?, ?, ?)",
                    (server_id, thread_id, world_id)
                )
                
            conn.commit()
        
        log_activity(server_id, "add_world", f"Thread: {thread_id}, World: {world_id}")
    
    @staticmethod
    def remove_thread(server_id: int, thread_id: int) -> Optional[str]:
        """
        Remove a thread-world link by thread ID.
        
        Args:
            server_id: Discord server ID
            thread_id: Discord thread ID
            
        Returns:
            The world ID that was removed, or None if not found
        """
        # First get the world ID
        world_id = ThreadWorldLinks.get_world_for_thread(server_id, thread_id)
        
        if world_id:
            with get_connection() as conn:
                cursor = conn.cursor()
                
                if IS_POSTGRES:
                    cursor.execute(
                        "DELETE FROM thread_world_links WHERE server_id=%s AND thread_id=%s",
                        (server_id, thread_id)
                    )
                else:
                    cursor.execute(
                        "DELETE FROM thread_world_links WHERE server_id=? AND thread_id=?",
                        (server_id, thread_id)
                    )
                
                conn.commit()
            
            log_activity(server_id, "remove_thread", f"Thread: {thread_id}, World: {world_id}")
            return world_id
        
        return None
    
    @staticmethod
    def remove_world(server_id: int, world_id: str) -> Optional[int]:
        """
        Remove a thread-world link by world ID.
        
        Args:
            server_id: Discord server ID
            world_id: VRChat world ID
            
        Returns:
            The thread ID that was removed, or None if not found
        """
        # First get the thread ID
        thread_id = ThreadWorldLinks.get_thread_for_world(server_id, world_id)
        
        if thread_id:
            with get_connection() as conn:
                cursor = conn.cursor()
                
                if IS_POSTGRES:
                    cursor.execute(
                        "DELETE FROM thread_world_links WHERE server_id=%s AND world_id=%s",
                        (server_id, world_id)
                    )
                else:
                    cursor.execute(
                        "DELETE FROM thread_world_links WHERE server_id=? AND world_id=?",
                        (server_id, world_id)
                    )
                    
                conn.commit()
            
            log_activity(server_id, "remove_world", f"Thread: {thread_id}, World: {world_id}")
            return thread_id
        
        return None
    
    @staticmethod
    def get_all_threads(server_id: int) -> List[Tuple[int, str]]:
        """
        Get all thread-world links for a server.
        
        Args:
            server_id: Discord server ID
            
        Returns:
            List of (thread_id, world_id) tuples
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT thread_id, world_id FROM thread_world_links WHERE server_id=%s",
                    (server_id,)
                )
            else:
                cursor.execute(
                    "SELECT thread_id, world_id FROM thread_world_links WHERE server_id=?",
                    (server_id,)
                )
                
            return [(row['thread_id'], row['world_id']) for row in cursor.fetchall()]


class ServerTags:
    """Server tag operations."""
    
    @staticmethod
    def get_tag_ids(server_id: int, tag_names: List[str]) -> List[int]:
        """
        Get tag IDs for a list of tag names.
        
        Args:
            server_id: Discord server ID
            tag_names: List of tag names
            
        Returns:
            List of tag IDs
        """
        tag_ids = []
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            for tag_name in tag_names:
                if IS_POSTGRES:
                    cursor.execute(
                        "SELECT tag_id FROM server_tags WHERE server_id=%s AND tag_name=%s",
                        (server_id, tag_name)
                    )
                else:
                    cursor.execute(
                        "SELECT tag_id FROM server_tags WHERE server_id=? AND tag_name=?",
                        (server_id, tag_name)
                    )
                    
                result = cursor.fetchone()
                
                if result:
                    tag_ids.append(result['tag_id'])
        
        return tag_ids
    
    @staticmethod
    def get_tag_names(server_id: int, tag_ids: List[int]) -> List[str]:
        """
        Get tag names for a list of tag IDs.
        
        Args:
            server_id: Discord server ID
            tag_ids: List of tag IDs
            
        Returns:
            List of tag names
        """
        tag_names = []
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            for tag_id in tag_ids:
                if IS_POSTGRES:
                    cursor.execute(
                        "SELECT tag_name FROM server_tags WHERE server_id=%s AND tag_id=%s",
                        (server_id, tag_id)
                    )
                else:
                    cursor.execute(
                        "SELECT tag_name FROM server_tags WHERE server_id=? AND tag_id=?",
                        (server_id, tag_id)
                    )
                    
                result = cursor.fetchone()
                
                if result:
                    tag_names.append(result['tag_name'])
        
        return tag_names
    
    @staticmethod
    def add_tag(server_id: int, tag_id: int, tag_name: str, emoji: Optional[str] = None) -> None:
        """
        Add or update a tag.
        
        Args:
            server_id: Discord server ID
            tag_id: Discord tag ID
            tag_name: Tag name
            emoji: Tag emoji (optional)
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    """
                    INSERT INTO server_tags (server_id, tag_id, tag_name, emoji)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (server_id, tag_id)
                    DO UPDATE SET tag_name = %s, emoji = %s
                    """,
                    (server_id, tag_id, tag_name, emoji, tag_name, emoji)
                )
            else:
                cursor.execute(
                    "INSERT OR REPLACE INTO server_tags (server_id, tag_id, tag_name, emoji) VALUES (?, ?, ?, ?)",
                    (server_id, tag_id, tag_name, emoji)
                )
                
            conn.commit()
    
    @staticmethod
    def remove_tag(server_id: int, tag_id: int) -> None:
        """
        Remove a tag.
        
        Args:
            server_id: Discord server ID
            tag_id: Discord tag ID
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    "DELETE FROM server_tags WHERE server_id=%s AND tag_id=%s",
                    (server_id, tag_id)
                )
            else:
                cursor.execute(
                    "DELETE FROM server_tags WHERE server_id=? AND tag_id=?",
                    (server_id, tag_id)
                )
                
            conn.commit()
    
    @staticmethod
    def get_all_tags(server_id: int) -> List[Dict[str, Any]]:
        """
        Get all tags for a server.
        
        Args:
            server_id: Discord server ID
            
        Returns:
            List of tag dictionaries with keys: tag_id, tag_name, emoji
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT tag_id, tag_name, emoji FROM server_tags WHERE server_id=%s",
                    (server_id,)
                )
            else:
                cursor.execute(
                    "SELECT tag_id, tag_name, emoji FROM server_tags WHERE server_id=?",
                    (server_id,)
                )
                
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def sync_tags(server_id: int, forum_tags: List[Dict[str, Any]]) -> Tuple[int, int, int]:
        """
        Synchronize server tags with forum channel tags.
        
        Args:
            server_id: Discord server ID
            forum_tags: List of forum tag dictionaries with keys: id, name, emoji
            
        Returns:
            Tuple of (added, updated, removed) tag counts
        """
        added = 0
        updated = 0
        removed = 0
        
        # Get existing tags
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute("SELECT tag_id, tag_name FROM server_tags WHERE server_id=%s", (server_id,))
            else:
                cursor.execute("SELECT tag_id, tag_name FROM server_tags WHERE server_id=?", (server_id,))
                
            db_tags = {row['tag_id']: row['tag_name'] for row in cursor.fetchall()}
        
        # Add or update tags
        forum_tag_ids = set()
        for tag in forum_tags:
            tag_id = tag['id']
            tag_name = tag['name']
            emoji = tag.get('emoji')
            
            forum_tag_ids.add(tag_id)
            
            if tag_id not in db_tags:
                # Add new tag
                ServerTags.add_tag(server_id, tag_id, tag_name, emoji)
                added += 1
            elif db_tags[tag_id] != tag_name:
                # Update tag name
                ServerTags.add_tag(server_id, tag_id, tag_name, emoji)
                updated += 1
        
        # Remove tags that no longer exist
        for db_tag_id in db_tags:
            if db_tag_id not in forum_tag_ids:
                ServerTags.remove_tag(server_id, db_tag_id)
                removed += 1
        
        return (added, updated, removed)


class VRChatWorlds:
    """VRChat worlds operations."""
    
    @staticmethod
    def add_world(world_id: str, world_name: str, author_name: str, image_url: Optional[str] = None) -> None:
        """
        Add or update a VRChat world.
        
        Args:
            world_id: VRChat world ID
            world_name: World name
            author_name: Author name
            image_url: Image URL (optional)
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    """
                    INSERT INTO vrchat_worlds (world_id, world_name, author_name, image_url)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (world_id)
                    DO UPDATE SET world_name = %s, author_name = %s, image_url = %s
                    """,
                    (world_id, world_name, author_name, image_url, world_name, author_name, image_url)
                )
            else:
                cursor.execute(
                    "INSERT OR REPLACE INTO vrchat_worlds (world_id, world_name, author_name, image_url) VALUES (?, ?, ?, ?)",
                    (world_id, world_name, author_name, image_url)
                )
                
            conn.commit()
    
    @staticmethod
    def get_world(world_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a VRChat world.
        
        Args:
            world_id: VRChat world ID
            
        Returns:
            World dictionary or None if not found
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute("SELECT * FROM vrchat_worlds WHERE world_id=%s", (world_id,))
            else:
                cursor.execute("SELECT * FROM vrchat_worlds WHERE world_id=?", (world_id,))
                
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            return None
        
# In database/models.py, add a new WorldPosts class:

class WorldPosts:
    """Unified world posts operations."""
    
    @staticmethod
    def get_thread_for_world(server_id: int, world_id: str) -> Optional[int]:
        """
        Get the thread ID for a VRChat world in a server.
        
        Args:
            server_id: Discord server ID
            world_id: VRChat world ID
            
        Returns:
            Thread ID or None if not found
        """
        # First check the thread_world_links table
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if we're using PostgreSQL
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT thread_id FROM thread_world_links WHERE server_id=%s AND world_id=%s",
                    (server_id, world_id)
                )
            else:
                cursor.execute(
                    "SELECT thread_id FROM thread_world_links WHERE server_id=? AND world_id=?",
                    (server_id, world_id)
                )
                
            result = cursor.fetchone()
            
            if result:
                return result['thread_id']
            return None

    @staticmethod
    def get_world_for_thread(server_id: int, thread_id: int) -> Optional[str]:
        """
        Get the VRChat world ID for a thread in a server.
        
        Args:
            server_id: Discord server ID
            thread_id: Discord thread ID
            
        Returns:
            World ID or None if not found
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if we're using PostgreSQL
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT world_id FROM thread_world_links WHERE server_id=%s AND thread_id=%s",
                    (server_id, thread_id)
                )
            else:
                cursor.execute(
                    "SELECT world_id FROM thread_world_links WHERE server_id=? AND thread_id=?",
                    (server_id, thread_id)
                )
                
            result = cursor.fetchone()
            
            if result:
                return result['world_id']
            return None
    
    @staticmethod
    def add_world_post(
        server_id: int, 
        user_id: int, 
        thread_id: int, 
        world_id: str,
        world_link: str,
        user_choices: Optional[List[str]] = None
    ) -> None:
        """
        Add a new world post.
        
        Args:
            server_id: Discord server ID
            user_id: Discord user ID
            thread_id: Discord thread ID
            world_id: VRChat world ID
            world_link: VRChat world link
            user_choices: List of tag choices (optional)
        """
        choices_str = ",".join(user_choices) if user_choices else ""
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # First save to thread_world_links table
            if IS_POSTGRES:
                cursor.execute(
                    """
                    INSERT INTO thread_world_links (server_id, thread_id, world_id) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (server_id, world_id) 
                    DO UPDATE SET thread_id = %s
                    """,
                    (server_id, thread_id, world_id, thread_id)
                )
                
                # Then save user choices to user_world_links
                cursor.execute(
                    """
                    INSERT INTO user_world_links (user_id, world_link, world_id, user_choices) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET world_link = %s, world_id = %s, user_choices = %s
                    """,
                    (user_id, world_link, world_id, choices_str, world_link, world_id, choices_str)
                )
            else:
                # SQLite syntax
                cursor.execute(
                    "INSERT OR REPLACE INTO thread_world_links (server_id, thread_id, world_id) VALUES (?, ?, ?)",
                    (server_id, thread_id, world_id)
                )
                
                # Then save user choices to user_world_links
                cursor.execute(
                    "INSERT OR REPLACE INTO user_world_links (user_id, world_link, world_id, user_choices) VALUES (?, ?, ?, ?)",
                    (user_id, world_link, world_id, choices_str)
                )
            
            conn.commit()
        
        log_activity(server_id, "add_world", f"User: {user_id}, Thread: {thread_id}, World: {world_id}")
    
    @staticmethod
    def remove_post_by_thread(server_id: int, thread_id: int) -> Optional[str]:
        """
        Remove a world post by thread ID.
        
        Args:
            server_id: Discord server ID
            thread_id: Discord thread ID
            
        Returns:
            The world ID that was removed, or None if not found
        """
        # First get the world ID
        world_id = WorldPosts.get_world_for_thread(server_id, thread_id)
        
        if world_id:
            with get_connection() as conn:
                cursor = conn.cursor()
                
                if IS_POSTGRES:
                    cursor.execute(
                        "DELETE FROM thread_world_links WHERE server_id=%s AND thread_id=%s",
                        (server_id, thread_id)
                    )
                else:
                    cursor.execute(
                        "DELETE FROM thread_world_links WHERE server_id=? AND thread_id=?",
                        (server_id, thread_id)
                    )
                    
                conn.commit()
            
            log_activity(server_id, "remove_thread", f"Thread: {thread_id}, World: {world_id}")
            return world_id
        
        return None
    
    @staticmethod
    def remove_post_by_world(server_id: int, world_id: str) -> Optional[int]:
        """
        Remove a world post by world ID.
        
        Args:
            server_id: Discord server ID
            world_id: VRChat world ID
            
        Returns:
            The thread ID that was removed, or None if not found
        """
        # First get the thread ID
        thread_id = WorldPosts.get_thread_for_world(server_id, world_id)
        
        if thread_id:
            with get_connection() as conn:
                cursor = conn.cursor()
                
                if IS_POSTGRES:
                    cursor.execute(
                        "DELETE FROM thread_world_links WHERE server_id=%s AND world_id=%s",
                        (server_id, world_id)
                    )
                else:
                    cursor.execute(
                        "DELETE FROM thread_world_links WHERE server_id=? AND world_id=?",
                        (server_id, world_id)
                    )
                    
                conn.commit()
            
            log_activity(server_id, "remove_world", f"Thread: {thread_id}, World: {world_id}")
            return thread_id
        
        return None
    
    @staticmethod
    def repair_missing_threads(server_id: int) -> int:
        """
        Repair threads in the database that are missing world IDs.
        
        Args:
            server_id: Discord server ID
            
        Returns:
            Number of threads repaired
        """
        fixed_count = 0
        
        # Look for threads without world IDs
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Find discord threads that have no world IDs
            if IS_POSTGRES:
                cursor.execute("""
                    SELECT t.thread_id 
                    FROM thread_world_links t 
                    WHERE t.server_id = %s AND (t.world_id IS NULL OR t.world_id = '')
                """, (server_id,))
            else:
                cursor.execute("""
                    SELECT t.thread_id 
                    FROM thread_world_links t 
                    WHERE t.server_id = ? AND (t.world_id IS NULL OR t.world_id = '')
                """, (server_id,))
                
            threads_to_fix = cursor.fetchall()
            
            for row in threads_to_fix:
                thread_id = row['thread_id']
                
                # Try to find a matching user submission
                if IS_POSTGRES:
                    cursor.execute("""
                        SELECT user_id, world_link, world_id 
                        FROM user_world_links 
                        WHERE world_id IS NOT NULL
                    """)
                else:
                    cursor.execute("""
                        SELECT user_id, world_link, world_id 
                        FROM user_world_links 
                        WHERE world_id IS NOT NULL
                    """)
                    
                user_worlds = cursor.fetchall()
                
                # Check if any world matches this thread
                for user_row in user_worlds:
                    world_id = user_row['world_id']
                    
                    # Check if this world ID is not already assigned to another thread
                    if IS_POSTGRES:
                        cursor.execute("""
                            SELECT thread_id 
                            FROM thread_world_links 
                            WHERE server_id = %s AND world_id = %s
                        """, (server_id, world_id))
                    else:
                        cursor.execute("""
                            SELECT thread_id 
                            FROM thread_world_links 
                            WHERE server_id = ? AND world_id = ?
                        """, (server_id, world_id))
                        
                    existing_thread = cursor.fetchone()
                    
                    if not existing_thread:
                        # Found a world that's not assigned to any thread, assign it to this thread
                        if IS_POSTGRES:
                            cursor.execute("""
                                UPDATE thread_world_links 
                                SET world_id = %s 
                                WHERE server_id = %s AND thread_id = %s
                            """, (world_id, server_id, thread_id))
                        else:
                            cursor.execute("""
                                UPDATE thread_world_links 
                                SET world_id = ? 
                                WHERE server_id = ? AND thread_id = ?
                            """, (world_id, server_id, thread_id))
                            
                        fixed_count += 1
                        break
            
            conn.commit()
        
        return fixed_count
    
    @staticmethod
    def get_all_posts(server_id: int) -> List[Dict[str, Any]]:
        """
        Get all world posts for a server.
        
        Args:
            server_id: Discord server ID
            
        Returns:
            List of world post dictionaries
        """
        result = []
        
        # First get data from thread_world_links
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT thread_id, world_id FROM thread_world_links WHERE server_id = %s",
                    (server_id,)
                )
            else:
                cursor.execute(
                    "SELECT thread_id, world_id FROM thread_world_links WHERE server_id = ?",
                    (server_id,)
                )
                
            thread_worlds = cursor.fetchall()
            
            for row in thread_worlds:
                thread_id = row['thread_id']
                world_id = row['world_id']
                
                # Try to find user data for this world
                if IS_POSTGRES:
                    cursor.execute(
                        "SELECT user_id, world_link, user_choices FROM user_world_links WHERE world_id = %s OR world_link LIKE %s",
                        (world_id, f"%{world_id}%")
                    )
                else:
                    cursor.execute(
                        "SELECT user_id, world_link, user_choices FROM user_world_links WHERE world_id = ? OR world_link LIKE ?",
                        (world_id, f"%{world_id}%")
                    )
                    
                user_data = cursor.fetchone()
                
                post = {
                    'server_id': server_id,
                    'thread_id': thread_id,
                    'world_id': world_id,
                    'user_id': user_data['user_id'] if user_data else 0,
                    'world_link': user_data['world_link'] if user_data else f"https://vrchat.com/home/world/{world_id}",
                    'user_choices': user_data['user_choices'] if user_data else ""
                }
                
                result.append(post)
        
        return result

    # Also add a convenience method to get all threads
    @staticmethod
    def get_all_threads(server_id: int) -> List[Tuple[int, str]]:
        """
        Get all thread-world links for a server.
        
        Args:
            server_id: Discord server ID
            
        Returns:
            List of (thread_id, world_id) tuples
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    "SELECT thread_id, world_id FROM thread_world_links WHERE server_id=%s",
                    (server_id,)
                )
            else:
                cursor.execute(
                    "SELECT thread_id, world_id FROM thread_world_links WHERE server_id=?",
                    (server_id,)
                )
                
            return [(row['thread_id'], row['world_id']) for row in cursor.fetchall()]
        
class GuildTracking:
    """Guild tracking operations."""
    
    @staticmethod
    def add_guild(guild_id: int, guild_name: str, member_count: int) -> None:
        """
        Add a new guild to tracking.
        
        Args:
            guild_id: Discord guild ID
            guild_name: Guild name
            member_count: Current member count
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    """
                    INSERT INTO guild_tracking (guild_id, guild_name, member_count)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id) DO NOTHING
                    """,
                    (guild_id, guild_name, member_count)
                )
                
                # Update stats
                cursor.execute(
                    """
                    INSERT INTO bot_stats (stat_name, stat_value, updated_at)
                    VALUES ('total_guilds', (SELECT COUNT(*) FROM guild_tracking), NOW())
                    ON CONFLICT (stat_name) DO UPDATE
                    SET stat_value = (SELECT COUNT(*) FROM guild_tracking), updated_at = NOW()
                    """
                )
            else:
                cursor.execute(
                    "INSERT OR IGNORE INTO guild_tracking (guild_id, guild_name, member_count) VALUES (?, ?, ?)",
                    (guild_id, guild_name, member_count)
                )
                
                # Update stats
                cursor.execute(
                    "INSERT OR REPLACE INTO bot_stats (stat_name, stat_value, updated_at) " +
                    "VALUES ('total_guilds', (SELECT COUNT(*) FROM guild_tracking), datetime('now'))"
                )
                
            conn.commit()
    
    @staticmethod
    def remove_guild(guild_id: int) -> None:
        """
        Remove a guild from tracking.
        
        Args:
            guild_id: Discord guild ID
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute("DELETE FROM guild_tracking WHERE guild_id = %s", (guild_id,))
                
                # Update stats
                cursor.execute(
                    """
                    INSERT INTO bot_stats (stat_name, stat_value, updated_at)
                    VALUES ('total_guilds', (SELECT COUNT(*) FROM guild_tracking), NOW())
                    ON CONFLICT (stat_name) DO UPDATE
                    SET stat_value = (SELECT COUNT(*) FROM guild_tracking), updated_at = NOW()
                    """
                )
            else:
                cursor.execute("DELETE FROM guild_tracking WHERE guild_id = ?", (guild_id,))
                
                # Update stats
                cursor.execute(
                    "INSERT OR REPLACE INTO bot_stats (stat_name, stat_value, updated_at) " +
                    "VALUES ('total_guilds', (SELECT COUNT(*) FROM guild_tracking), datetime('now'))"
                )
                
            conn.commit()
    
    @staticmethod
    def update_guild_status(guild_id: int, has_forum: bool) -> None:
        """
        Update a guild's forum status.
        
        Args:
            guild_id: Discord guild ID
            has_forum: Whether the guild has an active forum
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    """
                    UPDATE guild_tracking 
                    SET has_forum = %s, last_active = NOW() 
                    WHERE guild_id = %s
                    """,
                    (has_forum, guild_id)
                )
                
                # Update stats
                cursor.execute(
                    """
                    INSERT INTO bot_stats (stat_name, stat_value, updated_at)
                    VALUES ('guilds_with_forums', (SELECT COUNT(*) FROM guild_tracking WHERE has_forum = true), NOW())
                    ON CONFLICT (stat_name) DO UPDATE
                    SET stat_value = (SELECT COUNT(*) FROM guild_tracking WHERE has_forum = true), updated_at = NOW()
                    """
                )
            else:
                cursor.execute(
                    "UPDATE guild_tracking SET has_forum = ?, last_active = datetime('now') WHERE guild_id = ?",
                    (1 if has_forum else 0, guild_id)
                )
                
                # Update stats
                cursor.execute(
                    "INSERT OR REPLACE INTO bot_stats (stat_name, stat_value, updated_at) " +
                    "VALUES ('guilds_with_forums', (SELECT COUNT(*) FROM guild_tracking WHERE has_forum = 1), datetime('now'))"
                )
                
            conn.commit()
    
    @staticmethod
    def update_member_count(guild_id: int, member_count: int) -> None:
        """
        Update a guild's member count.
        
        Args:
            guild_id: Discord guild ID
            member_count: Current member count
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute(
                    """
                    UPDATE guild_tracking 
                    SET member_count = %s, last_active = NOW() 
                    WHERE guild_id = %s
                    """,
                    (member_count, guild_id)
                )
            else:
                cursor.execute(
                    "UPDATE guild_tracking SET member_count = ?, last_active = datetime('now') WHERE guild_id = ?",
                    (member_count, guild_id)
                )
                
            conn.commit()
    
    @staticmethod
    def get_guild_count() -> int:
        """
        Get the total number of guilds.
        
        Returns:
            Total number of guilds
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM guild_tracking")
            result = cursor.fetchone()
            return result[0] if result else 0
    
    @staticmethod
    def get_forums_count() -> int:
        """
        Get the total number of guilds with forums.
        
        Returns:
            Number of guilds with active forums
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if IS_POSTGRES:
                cursor.execute("SELECT COUNT(*) FROM guild_tracking WHERE has_forum = true")
            else:
                cursor.execute("SELECT COUNT(*) FROM guild_tracking WHERE has_forum = 1")
                
            result = cursor.fetchone()
            return result[0] if result else 0
    
    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """
        Get all bot stats.
        
        Returns:
            Dictionary of stats
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT stat_name, stat_value, updated_at FROM bot_stats")
            return {row['stat_name']: {'value': row['stat_value'], 'updated_at': row['updated_at']} 
                   for row in cursor.fetchall()}