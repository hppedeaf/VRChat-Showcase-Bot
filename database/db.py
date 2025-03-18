"""
Database connection and setup module.
Handles creating and upgrading database schema.
"""
import sqlite3
from typing import Dict, Any, List, Tuple, Optional
import config

def get_connection() -> sqlite3.Connection:
    """
    Get a connection to the SQLite database with proper settings.
    
    Returns:
        sqlite3.Connection: Database connection
    """
    conn = sqlite3.connect(config.DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Enable dictionary-like access to rows
    
    # Enable foreign key constraints
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    
    return conn

def setup_database() -> None:
    """
    Set up the SQLite database tables safely, handling existing schemas.
    Creates new tables if they don't exist and migrates legacy data.
    """
    config.logger.info(f"Setting up database: {config.DATABASE_FILE}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check existing tables to determine if we need migration
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [table[0] for table in cursor.fetchall()]
        
        # Flag to track if we're working with a legacy database
        is_legacy_db = False
        
        # Check if we have old schema tables
        if 'user_world_links' in existing_tables:
            # Check the structure of user_world_links
            cursor.execute("PRAGMA table_info(user_world_links)")
            columns = [col[1] for col in cursor.fetchall()]
            is_legacy_db = 'id' not in columns and 'world_id' not in columns
        
        # If we have a legacy database, back it up and prepare for migration
        if is_legacy_db:
            config.logger.info("Legacy database detected. Creating backup before migration...")
            
            # Backup existing tables with prefix backup_
            for table in existing_tables:
                backup_table = f"backup_{table}"
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {backup_table} AS SELECT * FROM {table}")
                config.logger.info(f"Backed up {table} to {backup_table}")
            
            # Drop existing tables to recreate with new schema
            for table in existing_tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
                config.logger.info(f"Dropped original table {table} for recreation")
        
        # Create tables with current schema
        _create_tables(conn)
        
        # Create indexes after tables exist
        _create_indexes(conn)
        
        # Migrate data if upgrading from legacy schema
        if is_legacy_db:
            _migrate_legacy_data(conn)
        
        config.logger.info(f"Database setup completed successfully: {config.DATABASE_FILE}")
    
    setup_guild_tracking_table()

"""
Enhanced database structure with improved world tracking.
Replace the relevant parts in database/db.py and database/models.py.
"""

# In database/db.py, modify the _create_tables function:

def _create_tables(conn: sqlite3.Connection) -> None:
    """
    Create all database tables.
    
    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()
    
    # Server channels table (unchanged)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_channels (
            server_id INTEGER PRIMARY KEY,
            forum_channel_id INTEGER NOT NULL,
            thread_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Unified world posts table (replaces thread_world_links and enhances user_world_links)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS world_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            thread_id INTEGER,
            world_id TEXT NOT NULL,
            world_link TEXT NOT NULL,
            user_choices TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(server_id, world_id)
        )
    """)
    
    # Create legacy tables for backward compatibility
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_world_links (
            user_id INTEGER,
            world_link TEXT,
            user_choices TEXT,
            world_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS thread_world_links (
            server_id INTEGER,
            thread_id INTEGER,
            world_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (server_id, world_id)
        )
    """)
    
    # Server tags table (unchanged)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_tags (
            server_id INTEGER,
            tag_id INTEGER,
            tag_name TEXT,
            emoji TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (server_id, tag_id)
        )
    """)
    
    # Remaining tables (unchanged)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vrchat_worlds (
            world_id TEXT PRIMARY KEY,
            world_name TEXT,
            author_name TEXT,
            image_url TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tag_usage (
            server_id INTEGER,
            thread_id INTEGER,
            tag_id INTEGER,
            added_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (server_id, thread_id, tag_id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            action_type TEXT,
            details TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            date TEXT,
            worlds_added INTEGER DEFAULT 0,
            users_active INTEGER DEFAULT 0,
            UNIQUE(server_id, date)
        )
    """)
    
    conn.commit()

# In database/db.py, add a migration function:

def migrate_to_unified_world_posts():
    """Migrate data from legacy tables to the new unified world_posts table."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if the unified table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='world_posts'")
        if not cursor.fetchone():
            config.logger.info("world_posts table doesn't exist yet. Creating...")
            _create_tables(conn)
        
        # Migrate data from thread_world_links and user_world_links
        config.logger.info("Migrating data to unified world_posts table...")
        
        # Get all thread_world_links
        cursor.execute("SELECT server_id, thread_id, world_id FROM thread_world_links")
        thread_links = cursor.fetchall()
        
        # For each thread link, try to find matching user data
        for server_id, thread_id, world_id in thread_links:
            # Try to find user who posted this world
            cursor.execute(
                "SELECT user_id, world_link, user_choices FROM user_world_links WHERE world_id=? OR world_link LIKE ?", 
                (world_id, f"%{world_id}%")
            )
            user_data = cursor.fetchone()
            
            if user_data:
                user_id, world_link, user_choices = user_data
            else:
                # If no user data found, use placeholder values
                user_id = 0  # System/unknown user
                world_link = f"https://vrchat.com/home/world/{world_id}"
                user_choices = ""
            
            # Insert into unified table
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO world_posts 
                    (server_id, user_id, thread_id, world_id, world_link, user_choices)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (server_id, user_id, thread_id, world_id, world_link, user_choices))
            except:
                config.logger.warning(f"Failed to migrate world post: {world_id} in thread {thread_id}")
        
        conn.commit()
        config.logger.info("Migration to unified world_posts table complete.")

def _create_indexes(conn: sqlite3.Connection) -> None:
    """
    Create database indexes for improved query performance.
    
    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()
    
    try:
        # Check if world_id column exists in user_world_links
        cursor.execute("PRAGMA table_info(user_world_links)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'world_id' in columns:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_world_links_world_id 
                ON user_world_links(world_id)
            """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_world_links_thread_id 
            ON thread_world_links(thread_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_server_tags_tag_name 
            ON server_tags(server_id, tag_name)
        """)
        
        conn.commit()
    except sqlite3.OperationalError as e:
        config.logger.warning(f"Warning creating indexes: {e}")

def _migrate_legacy_data(conn: sqlite3.Connection) -> None:
    """
    Migrate data from backup tables to new schema.
    
    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()
    
    try:
        config.logger.info("Migrating data from backup tables...")
        
        # Migrate server_channels
        cursor.execute("""
            INSERT INTO server_channels (server_id, forum_channel_id, thread_id)
            SELECT server_id, forum_channel_id, thread_id FROM backup_server_channels
        """)
        
        # Migrate user_world_links
        cursor.execute("SELECT user_id, world_link, user_choices FROM backup_user_world_links")
        old_user_links = cursor.fetchall()
        
        # Import locally to avoid circular imports
        from utils.api import extract_world_id
        
        for row in old_user_links:
            user_id = row[0]
            world_link = row[1]
            user_choices = row[2]
            
            # Extract world_id from link
            world_id = None
            if world_link:
                world_id = extract_world_id(world_link)
            
            cursor.execute("""
                INSERT INTO user_world_links (user_id, world_link, user_choices, world_id)
                VALUES (?, ?, ?, ?)
            """, (user_id, world_link, user_choices, world_id))
        
        # Migrate thread_world_links
        cursor.execute("""
            INSERT INTO thread_world_links (server_id, thread_id, world_id)
            SELECT server_id, thread_id, world_id FROM backup_thread_world_links
        """)
        
        # Migrate server_tags
        cursor.execute("""
            INSERT INTO server_tags (server_id, tag_id, tag_name)
            SELECT server_id, tag_id, tag_name FROM backup_server_tags
        """)
        
        conn.commit()
        config.logger.info("Data migration completed successfully")
        
    except Exception as e:
        config.logger.error(f"Error during data migration: {e}")
        conn.rollback()

def log_activity(server_id: int, action_type: str, details: str) -> None:
    """
    Log an activity to the database.
    
    Args:
        server_id: The Discord server ID
        action_type: Type of action (e.g., "create_world", "remove_world")
        details: Details about the action
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO bot_activity_log (server_id, action_type, details) VALUES (?, ?, ?)",
                (server_id, action_type, details)
            )
            conn.commit()
    except Exception as e:
        config.logger.error(f"Error logging activity: {e}")
        
def setup_guild_tracking_table():
    """Set up the table to track guilds (servers)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Create guild tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guild_tracking (
                guild_id INTEGER PRIMARY KEY,
                guild_name TEXT,
                member_count INTEGER,
                joined_at TEXT DEFAULT (datetime('now')),
                last_active TEXT DEFAULT (datetime('now')),
                has_forum BOOLEAN DEFAULT 0
            )
        """)
        
        # Create a stats table for summary information
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                stat_name TEXT PRIMARY KEY,
                stat_value INTEGER,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        
        conn.commit()