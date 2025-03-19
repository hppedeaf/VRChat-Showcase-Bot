"""
Enhanced database connection and setup module.
Handles creating, upgrading, and cleaning database schemas with improved reliability.
"""
import sqlite3
import os
import time
from typing import Dict, Any, List, Tuple, Optional, Union
import config as config

def get_connection():
    """
    Get a connection to the database (PostgreSQL on Railway, SQLite locally) with improved reliability.
    
    Returns:
        Database connection
    """
    if config.PG_AVAILABLE:
        # Try PostgreSQL first, fall back to SQLite if unavailable
        try:
            # Use our enhanced PostgreSQL handler for Railway
            from database.pg_handler import get_postgres_connection
            return get_postgres_connection()
        except Exception as e:
            # If PostgreSQL is unavailable, log and disable it for the rest of the session
            config.logger.warning(f"PostgreSQL connection failed, disabling for this session: {e}")
            config.PG_AVAILABLE = False
    
    # SQLite fallback for local development with better settings
    tries = 0
    max_tries = 3
    while tries < max_tries:
        try:
            conn = sqlite3.connect(config.DATABASE_FILE, timeout=20)
            conn.row_factory = sqlite3.Row  # Enable dictionary-like access to rows
            
            # Enable foreign key constraints
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for better concurrency
            cursor.execute("PRAGMA busy_timeout = 5000")  # 5 second timeout for busy connections
            
            return conn
        except sqlite3.OperationalError as e:
            tries += 1
            if tries >= max_tries:
                config.logger.error(f"Failed to connect to SQLite database after {max_tries} attempts: {e}")
                raise
            time.sleep(1)  # Wait a second before retrying

def check_database_connection():
    """
    Check if the database connection works and tables are accessible.
    
    Returns:
        Tuple of (success, message)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if essential tables exist
        is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
        
        if is_postgres:
            # PostgreSQL table check
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'server_channels'
                )
            """)
        else:
            # SQLite table check
            cursor.execute("""
                SELECT count(*) FROM sqlite_master 
                WHERE type='table' AND name='server_channels'
            """)
            
        tables_exist = cursor.fetchone()[0]
        
        if not tables_exist:
            conn.close()
            return False, "Database tables do not exist. Setup required."
        
        # Test a quick query
        if is_postgres:
            cursor.execute("SELECT 1")
        else:
            cursor.execute("SELECT 1")
            
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] == 1:
            return True, "Database connection successful and tables exist."
        else:
            return False, "Database query failed."
            
    except Exception as e:
        return False, f"Database connection error: {e}"

if __name__ == '__main__':
    # Check database connection
    from database.db import check_database_connection
    db_success, db_message = check_database_connection()
    
    if not db_success:
        print(f"WARNING: Database issue: {db_message}")
        print("Attempting to set up database...")
        from database.db import setup_database
        setup_success = setup_database()
        if setup_success:
            print("Database setup successful!")
        else:
            print("Database setup failed. Check configuration.")
            
def setup_database(force_rebuild=False) -> bool:
    """
    Set up the database tables safely, handling existing schemas.
    Creates new tables if they don't exist and migrates legacy data.
    
    Args:
        force_rebuild: If True, drop and recreate all tables (CAUTION)
        
    Returns:
        True if setup was successful, False otherwise
    """
    config.logger.info(f"Setting up database: {config.DATABASE_FILE}")
    
    is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
    
    try:
        if is_postgres:
            # Use our enhanced PostgreSQL setup with timeout handling
            try:
                from database.pg_handler import setup_postgres_tables, add_missing_columns, clean_database
                
                # First setup tables
                setup_postgres_tables()
                
                # Then add any missing columns from schema updates
                try:
                    add_missing_columns()
                except Exception as column_error:
                    config.logger.warning(f"Error adding missing columns (continuing anyway): {column_error}")
                
                # Clean database if needed
                if force_rebuild:
                    try:
                        clean_database()
                    except Exception as clean_error:
                        config.logger.warning(f"Database cleaning error (continuing anyway): {clean_error}")
                
                # Migrate data from SQLite if needed
                try:
                    _check_and_migrate_from_sqlite()
                except Exception as migrate_error:
                    config.logger.warning(f"Migration error (continuing anyway): {migrate_error}")
            except Exception as pg_error:
                config.logger.error(f"PostgreSQL setup failed, falling back to SQLite: {pg_error}")
                # Fall through to SQLite setup
                setup_sqlite_tables()
        else:
            # SQLite setup
            if force_rebuild:
                _rebuild_sqlite_database()
            else:
                setup_sqlite_tables()
            
        config.logger.info(f"Database setup completed successfully")
        return True
        
    except Exception as e:
        config.logger.error(f"Database setup failed: {e}")
        return False

def _check_and_migrate_from_sqlite():
    """Check if we need to migrate from SQLite and do so if needed."""
    # We only need to migrate if:
    # 1. We're using PostgreSQL
    # 2. SQLite database exists
    # 3. PostgreSQL tables are empty
    
    if not hasattr(config, 'DATABASE_URL') or not config.DATABASE_URL or not config.DATABASE_URL.startswith("postgres"):
        return
    
    # Check if SQLite database exists
    if not os.path.exists(config.DATABASE_FILE):
        return
        
    # Check if PostgreSQL tables are empty
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM server_channels")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        # Tables exist but are empty, migrate data
        config.logger.info("PostgreSQL tables are empty. Migrating data from SQLite...")
        from database.pg_handler import migrate_data_from_sqlite
        migrate_data_from_sqlite()

def _rebuild_sqlite_database():
    """Drop and recreate all SQLite tables (CAUTION)."""
    conn = sqlite3.connect(config.DATABASE_FILE)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    # Drop each table
    for table in tables:
        if table != 'sqlite_sequence':  # Skip SQLite internal tables
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
    
    conn.commit()
    conn.close()
    
    # Now recreate all tables
    setup_sqlite_tables()
    config.logger.info("SQLite database rebuilt from scratch")

def setup_sqlite_tables():
    """Set up SQLite tables with improved schema and indices."""
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
            
        # Add any missing columns that were introduced in later versions
        _add_missing_columns(conn)

def _create_tables(conn: sqlite3.Connection) -> None:
    """
    Create all database tables with improved schema.
    
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
    
    # Unified world posts table with improved schema
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
    
    # VRChat worlds table with improved fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vrchat_worlds (
            world_id TEXT PRIMARY KEY,
            world_name TEXT,
            author_name TEXT,
            image_url TEXT,
            capacity INTEGER,
            visit_count INTEGER,
            favorites_count INTEGER,
            last_updated TEXT,
            platform_type TEXT,
            world_size_bytes INTEGER,
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
    
    # Bot activity log with improved schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            action_type TEXT,
            details TEXT,
            user_id INTEGER,
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
    
    # Guild tracking table
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
    
    # Bot stats table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_stats (
            stat_name TEXT PRIMARY KEY,
            stat_value INTEGER,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    conn.commit()

def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """
    Add missing columns to tables to support schema evolution.
    
    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()
    
    # Function to check if a column exists in a table
    def column_exists(table, column):
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [info[1] for info in cursor.fetchall()]
        return column in columns

    # Add capacity to vrchat_worlds if missing
    if not column_exists('vrchat_worlds', 'capacity'):
        cursor.execute("ALTER TABLE vrchat_worlds ADD COLUMN capacity INTEGER")
        
    # Add visit_count to vrchat_worlds if missing
    if not column_exists('vrchat_worlds', 'visit_count'):
        cursor.execute("ALTER TABLE vrchat_worlds ADD COLUMN visit_count INTEGER")
        
    # Add favorites_count to vrchat_worlds if missing
    if not column_exists('vrchat_worlds', 'favorites_count'):
        cursor.execute("ALTER TABLE vrchat_worlds ADD COLUMN favorites_count INTEGER")
        
    # Add last_updated to vrchat_worlds if missing
    if not column_exists('vrchat_worlds', 'last_updated'):
        cursor.execute("ALTER TABLE vrchat_worlds ADD COLUMN last_updated TEXT")
        
    # Add platform_type to vrchat_worlds if missing
    if not column_exists('vrchat_worlds', 'platform_type'):
        cursor.execute("ALTER TABLE vrchat_worlds ADD COLUMN platform_type TEXT")
        
    # Add world_size_bytes to vrchat_worlds if missing
    if not column_exists('vrchat_worlds', 'world_size_bytes'):
        cursor.execute("ALTER TABLE vrchat_worlds ADD COLUMN world_size_bytes INTEGER")
        
    # Add user_id to bot_activity_log if missing
    if not column_exists('bot_activity_log', 'user_id'):
        cursor.execute("ALTER TABLE bot_activity_log ADD COLUMN user_id INTEGER")
        
    conn.commit()

def _create_indexes(conn: sqlite3.Connection) -> None:
    """
    Create database indexes for improved query performance.
    
    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()
    
    try:
        # Indices for world_posts
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_world_posts_server_id ON world_posts(server_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_world_posts_user_id ON world_posts(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_world_posts_thread_id ON world_posts(thread_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_world_posts_world_id ON world_posts(world_id)")
        
        # Indices for user_world_links
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_world_links_world_id ON user_world_links(world_id)")
        
        # Indices for thread_world_links
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_world_links_thread_id ON thread_world_links(thread_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_world_links_server_id ON thread_world_links(server_id)")
        
        # Indices for server_tags
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_server_tags_tag_name ON server_tags(server_id, tag_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_server_tags_server_id ON server_tags(server_id)")
        
        # Indices for tag_usage
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_usage_server_id ON tag_usage(server_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_usage_tag_id ON tag_usage(tag_id)")
        
        # Indices for activity_stats
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_stats_date ON activity_stats(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_stats_server_id ON activity_stats(server_id)")
        
        # Indices for bot_activity_log
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bot_activity_timestamp ON bot_activity_log(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bot_activity_server_id ON bot_activity_log(server_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bot_activity_action_type ON bot_activity_log(action_type)")
        
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

def clean_database():
    """
    Clean the database by removing orphaned records and fixing inconsistencies.
    This function works with both SQLite and PostgreSQL.
    """
    is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
    
    if is_postgres:
        # Use PostgreSQL-specific cleaning
        from database.pg_handler import clean_database
        clean_database()
        return
    
    # SQLite cleaning
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Start transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. Find and remove thread_world_links with no matching thread in Discord
        cursor.execute("""
            DELETE FROM thread_world_links
            WHERE server_id NOT IN (SELECT server_id FROM server_channels)
        """)
        deleted_count = cursor.rowcount
        config.logger.info(f"Cleaned {deleted_count} orphaned thread_world_links")
        
        # 2. Remove duplicate world entries (keeping the most recent)
        cursor.execute("""
            DELETE FROM world_posts 
            WHERE rowid NOT IN (
                SELECT MIN(rowid) 
                FROM world_posts 
                GROUP BY server_id, world_id
            )
        """)
        deleted_count = cursor.rowcount
        config.logger.info(f"Cleaned {deleted_count} duplicate world posts")
        
        # 3. Clean up old activity logs (older than 90 days)
        cursor.execute("""
            DELETE FROM bot_activity_log
            WHERE datetime(timestamp) < datetime('now', '-90 days')
        """)
        deleted_count = cursor.rowcount
        config.logger.info(f"Cleaned {deleted_count} old activity logs")
        
        # 4. Remove orphaned tag_usage entries
        cursor.execute("""
            DELETE FROM tag_usage
            WHERE (server_id, thread_id) NOT IN (
                SELECT server_id, thread_id FROM thread_world_links
            )
        """)
        deleted_count = cursor.rowcount
        config.logger.info(f"Cleaned {deleted_count} orphaned tag_usage entries")
        
        # 5. Rebuild indices for better performance
        cursor.execute("PRAGMA optimize")
        
        # Commit the transaction
        cursor.execute("COMMIT")
        
        # Vacuum the database to reclaim space
        cursor.execute("VACUUM")
        
        config.logger.info("Database cleaning completed successfully")
        
    except Exception as e:
        if conn:
            cursor.execute("ROLLBACK")
        config.logger.error(f"Database cleaning failed: {e}")
    finally:
        if conn:
            conn.close()

def verify_database_integrity():
    """
    Verify the integrity of the database and fix any issues.
    
    Returns:
        Tuple of (is_valid, message)
    """
    is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
    
    if is_postgres:
        # For PostgreSQL, we need to use the analyze command
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Check for corruption by analyzing tables
            cursor.execute("ANALYZE")
            conn.close()
            
            return True, "PostgreSQL database integrity verified."
        except Exception as e:
            return False, f"PostgreSQL database integrity check failed: {e}"
    else:
        # For SQLite, we can use pragma integrity_check
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            
            if result == "ok":
                # Also check foreign key constraints
                cursor.execute("PRAGMA foreign_key_check")
                fk_violations = cursor.fetchall()
                
                if not fk_violations:
                    conn.close()
                    return True, "SQLite database integrity verified."
                else:
                    conn.close()
                    return False, f"SQLite database has {len(fk_violations)} foreign key violations."
            else:
                conn.close()
                return False, f"SQLite database integrity check failed: {result}"
                
        except Exception as e:
            return False, f"SQLite database integrity check failed: {e}"

def log_activity(server_id: int, action_type: str, details: str, user_id: Optional[int] = None) -> None:
    """
    Log an activity to the database with enhanced tracking.
    
    Args:
        server_id: The Discord server ID
        action_type: Type of action (e.g., "create_world", "remove_world")
        details: Details about the action
        user_id: Optional Discord user ID who performed the action
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
            
            if is_postgres:
                cursor.execute(
                    "INSERT INTO bot_activity_log (server_id, action_type, details, user_id) VALUES (%s, %s, %s, %s)",
                    (server_id, action_type, details, user_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO bot_activity_log (server_id, action_type, details, user_id) VALUES (?, ?, ?, ?)",
                    (server_id, action_type, details, user_id)
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
                from database.pg_handler import setup_postgres_tables
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
            
            # Skip if already in world_posts
            if is_postgres:
                cursor.execute(
                    "SELECT 1 FROM world_posts WHERE server_id=%s AND world_id=%s", 
                    (server_id, world_id)
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM world_posts WHERE server_id=? AND world_id=?", 
                    (server_id, world_id)
                )
                
            if cursor.fetchone():
                continue  # Skip if already exists
            
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