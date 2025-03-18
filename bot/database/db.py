"""
Database connection and setup module.
Handles creating and upgrading database schema.
"""
import sqlite3
from typing import Dict, Any, List, Tuple, Optional, Union
import bot.config as config
import os

def get_connection():
    """
    Get a connection to the database (PostgreSQL on Railway, SQLite locally).
    
    Returns:
        Database connection
    """
    if hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres"):
        # Use our enhanced PostgreSQL handler for Railway
        from bot.database.pg_handler import get_postgres_connection
        return get_postgres_connection()
    else:
        # SQLite fallback for local development
        conn = sqlite3.connect(config.DATABASE_FILE)
        conn.row_factory = sqlite3.Row  # Enable dictionary-like access to rows
        
        # Enable foreign key constraints
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        
        return conn

def setup_database() -> None:
    """
    Set up the database tables safely, handling existing schemas.
    Creates new tables if they don't exist and migrates legacy data.
    """
    config.logger.info(f"Setting up database: {config.DATABASE_FILE}")
    
    is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
    
    if is_postgres:
        # Use our enhanced PostgreSQL setup
        from bot.database.pg_handler import setup_postgres_tables
        setup_postgres_tables()
    else:
        setup_sqlite_tables()
        
    config.logger.info(f"Database setup completed successfully")

def setup_sqlite_tables():
    """Set up SQLite tables."""
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

def _create_tables(conn: sqlite3.Connection) -> None:
    """
    Create all database tables.
    
    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()
    
    # Server channels table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_channels (
            server_id INTEGER PRIMARY KEY,
            forum_channel_id INTEGER NOT NULL,
            thread_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Unified world posts table
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
    
    # Legacy tables for backward compatibility
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_world_links (
            user_id INTEGER PRIMARY KEY,
            world_link TEXT,
            user_choices TEXT,
            world_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
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
    
    # Server tags table
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
    
    # VRChat worlds table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vrchat_worlds (
            world_id TEXT PRIMARY KEY,
            world_name TEXT,
            author_name TEXT,
            image_url TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Tag usage table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tag_usage (
            server_id INTEGER,
            thread_id INTEGER,
            tag_id INTEGER,
            added_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (server_id, thread_id, tag_id)
        )
    """)
    
    # Bot activity log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            action_type TEXT,
            details TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Activity stats
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
            
            is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
            
            if is_postgres:
                cursor.execute(
                    "INSERT INTO bot_activity_log (server_id, action_type, details) VALUES (%s, %s, %s)",
                    (server_id, action_type, details)
                )
            else:
                cursor.execute(
                    "INSERT INTO bot_activity_log (server_id, action_type, details) VALUES (?, ?, ?)",
                    (server_id, action_type, details)
                )
                
            conn.commit()
    except Exception as e:
        config.logger.error(f"Error logging activity: {e}")

def get_placeholder_style():
    """
    Returns the appropriate placeholder style for the current database.
    
    Returns:
        tuple: (is_postgres, placeholder)
    """
    is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
    placeholder = "%s" if is_postgres else "?"
    return is_postgres, placeholder

def execute_query(conn, query, params=None):
    """
    Execute a query with the appropriate placeholders for the current database.
    
    Args:
        conn: Database connection
        query: SQL query with ? placeholders
        params: Query parameters
        
    Returns:
        cursor: Database cursor after executing query
    """
    cursor = conn.cursor()
    is_postgres, placeholder = get_placeholder_style()
    
    if params is None:
        params = []
    
    # Replace ? with %s for PostgreSQL
    if is_postgres:
        query = query.replace("?", "%s")
    
    cursor.execute(query, params)
    return cursor

def execute_insert_query(conn, query, params=None):
    """
    Execute an insert query with the appropriate syntax for the current database.
    
    Args:
        conn: Database connection
        query: SQL query with ? placeholders and "INSERT OR REPLACE"/"INSERT OR IGNORE"
        params: Query parameters
        
    Returns:
        cursor: Database cursor after executing query
    """
    cursor = conn.cursor()
    is_postgres, placeholder = get_placeholder_style()
    
    if params is None:
        params = []
    
    if is_postgres:
        # Handle PostgreSQL specific syntax
        if "INSERT OR REPLACE" in query:
            # For PostgreSQL, transform the query to use ON CONFLICT syntax
            # First determine the table and columns
            parts = query.split()
            table_idx = parts.index("INTO") + 1
            table_name = parts[table_idx].strip()
            
            # Extract column names from the query
            columns_start = query.find("(", query.find(table_name)) + 1
            columns_end = query.find(")", columns_start)
            columns_str = query[columns_start:columns_end].strip()
            columns = [col.strip() for col in columns_str.split(",")]
            
            # Assume the first column is the primary key
            primary_key = columns[0]
            
            # Reconstruct the query using ON CONFLICT
            values_str = ", ".join(["%s" for _ in range(len(columns))])
            update_parts = []
            
            for col in columns[1:]:  # Skip the primary key
                update_parts.append(f"{col} = EXCLUDED.{col}")
                
            update_clause = ", ".join(update_parts)
            
            query = f"""
                INSERT INTO {table_name} ({columns_str})
                VALUES ({values_str})
                ON CONFLICT ({primary_key}) DO UPDATE SET {update_clause}
            """
        elif "INSERT OR IGNORE" in query:
            # Transform to use ON CONFLICT DO NOTHING
            query = query.replace("INSERT OR IGNORE", "INSERT")
            
            # Find the table name
            parts = query.split()
            table_idx = parts.index("INTO") + 1
            table_name = parts[table_idx].strip()
            
            # Extract column names to determine primary key
            columns_start = query.find("(", query.find(table_name)) + 1
            columns_end = query.find(")", columns_start)
            columns_str = query[columns_start:columns_end].strip()
            columns = [col.strip() for col in columns_str.split(",")]
            
            # Assume the first column is the primary key
            primary_key = columns[0]
            
            # Add ON CONFLICT clause
            if ")" in query and "VALUES" in query:
                query = query.replace("VALUES", f") ON CONFLICT ({primary_key}) DO NOTHING VALUES")
            else:
                query += f" ON CONFLICT ({primary_key}) DO NOTHING"
            
        # Replace ? with %s for PostgreSQL
        query = query.replace("?", "%s")
    
    cursor.execute(query, params)
    return cursor

def setup_guild_tracking_table():
    """Set up the table to track guilds (servers)."""
    is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if is_postgres:
            # Create guild tracking table for PostgreSQL
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guild_tracking (
                    guild_id BIGINT PRIMARY KEY,
                    guild_name TEXT,
                    member_count INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    has_forum BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Create a stats table for summary information
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_stats (
                    stat_name TEXT PRIMARY KEY,
                    stat_value INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            # Create guild tracking table for SQLite
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

def migrate_to_unified_world_posts():
    """Migrate data from legacy tables to the new unified world_posts table."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if the unified table exists
        is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
        
        if is_postgres:
            cursor.execute("SELECT to_regclass('world_posts')")
            table_exists = cursor.fetchone()[0] is not None
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='world_posts'")
            table_exists = cursor.fetchone() is not None
            
        if not table_exists:
            config.logger.info("world_posts table doesn't exist yet. Creating...")
            if is_postgres:
                from bot.database.pg_handler import setup_postgres_tables
                setup_postgres_tables()
            else:
                with get_connection() as conn2:
                    _create_tables(conn2)
        
        # Migrate data from thread_world_links and user_world_links
        config.logger.info("Migrating data to unified world_posts table...")
        
        # Get all thread_world_links
        cursor.execute("SELECT server_id, thread_id, world_id FROM thread_world_links")
        thread_links = cursor.fetchall()
        
        # For each thread link, try to find matching user data
        for row in thread_links:
            server_id = row[0]
            thread_id = row[1]
            world_id = row[2]
            
            # Try to find user who posted this world
            if is_postgres:
                cursor.execute(
                    "SELECT user_id, world_link, user_choices FROM user_world_links WHERE world_id=%s OR world_link LIKE %s", 
                    (world_id, f"%{world_id}%")
                )
            else:
                cursor.execute(
                    "SELECT user_id, world_link, user_choices FROM user_world_links WHERE world_id=? OR world_link LIKE ?", 
                    (world_id, f"%{world_id}%")
                )
                
            user_data = cursor.fetchone()
            
            if user_data:
                user_id = user_data[0]
                world_link = user_data[1]
                user_choices = user_data[2]
            else:
                # If no user data found, use placeholder values
                user_id = 0  # System/unknown user
                world_link = f"https://vrchat.com/home/world/{world_id}"
                user_choices = ""
            
            # Insert into unified table
            try:
                if is_postgres:
                    cursor.execute("""
                        INSERT INTO world_posts 
                        (server_id, user_id, thread_id, world_id, world_link, user_choices)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (server_id, world_id) DO NOTHING
                    """, (server_id, user_id, thread_id, world_id, world_link, user_choices))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO world_posts 
                        (server_id, user_id, thread_id, world_id, world_link, user_choices)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (server_id, user_id, thread_id, world_id, world_link, user_choices))
            except Exception as e:
                config.logger.warning(f"Failed to migrate world post: {world_id} in thread {thread_id} - {e}")
        
        conn.commit()
        config.logger.info("Migration to unified world_posts table complete.")