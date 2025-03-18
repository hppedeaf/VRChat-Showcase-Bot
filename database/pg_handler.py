"""
Enhanced PostgreSQL database handler for Railway deployment.
Provides better handling of PostgreSQL connections, migrations, and optimized table structures.
"""
import psycopg2
import psycopg2.extras
import logging
import time
import os
from typing import Dict, Any, List, Tuple, Optional, Union
import config as config

def get_postgres_connection():
    """
    Get a connection to the PostgreSQL database on Railway with improved error handling.
    
    Returns:
        Database connection
    """
    # Get DATABASE_URL from Railway environment
    db_url = os.getenv("DATABASE_URL") or config.DATABASE_URL
    
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set")
        
    # Add retry mechanism for connection with exponential backoff
    max_retries = 5
    retry_delay = 3  # initial seconds
    
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(
                db_url,
                connect_timeout=10,  # Set connection timeout
                application_name="VRChat World Showcase Bot"  # Identify app in pg_stat_activity
            )
            conn.autocommit = False  # We'll manage transactions explicitly
            conn.cursor_factory = psycopg2.extras.DictCursor  # Enable dictionary-like access to rows
            
            config.logger.info("Successfully connected to PostgreSQL database")
            return conn
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                config.logger.warning(f"Failed to connect to PostgreSQL (attempt {attempt+1}/{max_retries}): {e}")
                # Exponential backoff
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                config.logger.error(f"Failed to connect to PostgreSQL after {max_retries} attempts: {e}")
                raise

def check_table_exists(conn, table_name: str) -> bool:
    """
    Check if a table exists in the PostgreSQL database.
    
    Args:
        conn: Database connection
        table_name: Name of the table to check
        
    Returns:
        True if the table exists, False otherwise
    """
    with conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (table_name,))
        return cursor.fetchone()[0] is not None

def setup_postgres_tables(conn=None):
    """
    Set up PostgreSQL database tables with optimized indices and constraints.
    
    Args:
        conn: Optional database connection
    """
    connection_created = False
    if conn is None:
        conn = get_postgres_connection()
        connection_created = True
    
    try:
        with conn.cursor() as cursor:
            # Server channels table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS server_channels (
                    server_id BIGINT PRIMARY KEY,
                    forum_channel_id BIGINT NOT NULL,
                    thread_id BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Unified world posts table with improved schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS world_posts (
                    id SERIAL PRIMARY KEY,
                    server_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    thread_id BIGINT,
                    world_id TEXT NOT NULL,
                    world_link TEXT NOT NULL,
                    user_choices TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(server_id, world_id)
                )
            """)
            
            # Legacy tables for backward compatibility
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_world_links (
                    user_id BIGINT PRIMARY KEY,
                    world_link TEXT,
                    user_choices TEXT,
                    world_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS thread_world_links (
                    server_id BIGINT,
                    thread_id BIGINT,
                    world_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (server_id, world_id)
                )
            """)
            
            # Server tags table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS server_tags (
                    server_id BIGINT,
                    tag_id BIGINT,
                    tag_name TEXT,
                    emoji TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                    last_updated TIMESTAMP,
                    platform_type TEXT,
                    world_size_bytes BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tag usage table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tag_usage (
                    server_id BIGINT,
                    thread_id BIGINT,
                    tag_id BIGINT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (server_id, thread_id, tag_id)
                )
            """)
            
            # Bot activity log with improved schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_activity_log (
                    id SERIAL PRIMARY KEY,
                    server_id BIGINT,
                    action_type TEXT,
                    details TEXT,
                    user_id BIGINT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Activity stats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_stats (
                    id SERIAL PRIMARY KEY,
                    server_id BIGINT,
                    date DATE,
                    worlds_added INTEGER DEFAULT 0,
                    users_active INTEGER DEFAULT 0,
                    UNIQUE(server_id, date)
                )
            """)
            
            # Guild tracking table
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
            
            # Bot stats table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_stats (
                    stat_name TEXT PRIMARY KEY,
                    stat_value INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create improved indices for better performance
            
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
            config.logger.info("PostgreSQL tables and indices created successfully")
            
    except Exception as e:
        conn.rollback()
        config.logger.error(f"Error creating PostgreSQL tables: {e}")
        raise
    finally:
        if connection_created:
            conn.close()

def add_missing_columns():
    """
    Add any missing columns to existing tables that were added in schema updates.
    This allows for non-breaking schema changes.
    """
    # Check if PostgreSQL is being used
    is_postgres = hasattr(config, 'DATABASE_URL') and config.DATABASE_URL and config.DATABASE_URL.startswith("postgres")
    
    # If not using PostgreSQL, skip this method
    if not is_postgres:
        config.logger.info("Skipping add_missing_columns - not using PostgreSQL")
        return
    
    conn = None
    try:
        # Get database URL from environment or config
        db_url = os.getenv("DATABASE_URL") or getattr(config, 'DATABASE_URL', None)
        
        # Validate database URL
        if not db_url:
            config.logger.warning("No DATABASE_URL found. Skipping add_missing_columns.")
            return
        
        # Establish connection
        conn = psycopg2.connect(
            db_url,
            connect_timeout=10,
            application_name="VRChat World Showcase Bot"
        )
        conn.autocommit = False
        
        with conn.cursor() as cursor:
            # Check and add missing columns for vrchat_worlds
            column_checks = [
                ("capacity", "INTEGER"),
                ("visit_count", "INTEGER"),
                ("favorites_count", "INTEGER"),
                ("last_updated", "TIMESTAMP"),
                ("platform_type", "TEXT"),
                ("world_size_bytes", "BIGINT")
            ]
            
            for column_name, column_type in column_checks:
                try:
                    # Check if column exists
                    cursor.execute(f"SELECT {column_name} FROM vrchat_worlds LIMIT 1")
                except psycopg2.errors.UndefinedColumn:
                    # Add missing column
                    try:
                        cursor.execute(f"ALTER TABLE vrchat_worlds ADD COLUMN {column_name} {column_type}")
                        config.logger.info(f"Added missing column: {column_name} to vrchat_worlds")
                    except Exception as add_column_error:
                        config.logger.error(f"Error adding column {column_name}: {add_column_error}")
                    
                    # Reset any existing error state
                    conn.rollback()
            
            # Check and add missing columns for bot_activity_log
            try:
                cursor.execute("SELECT user_id FROM bot_activity_log LIMIT 1")
            except psycopg2.errors.UndefinedColumn:
                try:
                    cursor.execute("ALTER TABLE bot_activity_log ADD COLUMN user_id BIGINT")
                    config.logger.info("Added missing column: user_id to bot_activity_log")
                except Exception as user_id_error:
                    config.logger.error(f"Error adding user_id column: {user_id_error}")
                
                # Reset any existing error state
                conn.rollback()
            
            # Commit changes
            conn.commit()
            config.logger.info("Successfully completed add_missing_columns")
    
    except Exception as e:
        config.logger.error(f"Error in add_missing_columns: {e}")
        # Attempt to rollback if connection exists
        if conn:
            try:
                conn.rollback()
            except Exception as rollback_error:
                config.logger.error(f"Error during rollback: {rollback_error}")
    
    finally:
        # Ensure connection is closed
        if conn:
            try:
                conn.close()
            except Exception as close_error:
                config.logger.error(f"Error closing connection: {close_error}")

def migrate_data_from_sqlite():
    """
    Migrate data from SQLite to PostgreSQL.
    
    This function should be called if you want to move data from a local SQLite
    database to the PostgreSQL database on Railway.
    """
    import sqlite3
    from database.db import get_connection
    
    # Check if SQLite database exists
    sqlite_db_path = config.DATABASE_FILE
    if not os.path.exists(sqlite_db_path):
        config.logger.warning(f"SQLite database {sqlite_db_path} not found, skipping migration")
        return
    
    config.logger.info(f"Starting migration from SQLite database {sqlite_db_path} to PostgreSQL")
    
    # Connect to both databases
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    
    pg_conn = get_postgres_connection()
    
    try:
        # First, get a list of all tables to migrate
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in sqlite_cursor.fetchall()]
        
        # For each table, migrate the data
        for table in tables:
            config.logger.info(f"Migrating table: {table}")
            
            # Skip SQLite system tables
            if table.startswith('sqlite_'):
                continue
                
            # Get table schema to determine columns
            sqlite_cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in sqlite_cursor.fetchall()]
            
            if not columns:
                config.logger.warning(f"No columns found for table {table}, skipping")
                continue
                
            # Get data from SQLite
            sqlite_cursor.execute(f"SELECT * FROM {table}")
            rows = sqlite_cursor.fetchall()
            
            if not rows:
                config.logger.info(f"No data in table {table}, skipping")
                continue
                
            # Insert data into PostgreSQL
            with pg_conn.cursor() as pg_cursor:
                for row in rows:
                    # Convert row to dict
                    row_dict = {columns[i]: row[i] for i in range(len(columns))}
                    
                    # Prepare columns and values for INSERT
                    cols = ", ".join(row_dict.keys())
                    placeholders = ", ".join(["%s"] * len(row_dict))
                    values = list(row_dict.values())
                    
                    try:
                        # Insert with ON CONFLICT DO NOTHING to avoid duplicates
                        pg_cursor.execute(
                            f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                            values
                        )
                    except Exception as e:
                        config.logger.error(f"Error inserting row in table {table}: {e}")
                        # Continue with next row
                        continue
                        
            config.logger.info(f"Migrated {len(rows)} rows from table {table}")
            
        # Commit all changes
        pg_conn.commit()
        config.logger.info("Migration completed successfully")
        
    except Exception as e:
        pg_conn.rollback()
        config.logger.error(f"Migration failed: {e}")
    finally:
        sqlite_conn.close()
        pg_conn.close()

def clean_database():
    """
    Clean the database by removing orphaned data and fixing inconsistencies.
    """
    conn = None
    try:
        conn = get_postgres_connection()
        with conn.cursor() as cursor:
            # 1. Find and remove thread_world_links with no matching thread in Discord
            cursor.execute("""
                DELETE FROM thread_world_links
                WHERE server_id NOT IN (SELECT server_id FROM server_channels)
            """)
            deleted_count = cursor.rowcount
            config.logger.info(f"Cleaned {deleted_count} orphaned thread_world_links")
            
            # 2. Remove duplicate world entries (keeping the most recent)
            cursor.execute("""
                DELETE FROM world_posts wp1
                WHERE EXISTS (
                    SELECT 1 FROM world_posts wp2
                    WHERE wp1.server_id = wp2.server_id
                    AND wp1.world_id = wp2.world_id
                    AND wp1.id < wp2.id
                )
            """)
            deleted_count = cursor.rowcount
            config.logger.info(f"Cleaned {deleted_count} duplicate world posts")
            
            # 3. Clean up old activity logs (older than 90 days)
            cursor.execute("""
                DELETE FROM bot_activity_log
                WHERE timestamp < NOW() - INTERVAL '90 days'
            """)
            deleted_count = cursor.rowcount
            config.logger.info(f"Cleaned {deleted_count} old activity logs")
            
            # 4. Run VACUUM to reclaim space and optimize performance
            conn.set_isolation_level(0)  # AUTOCOMMIT for VACUUM
            cursor.execute("VACUUM ANALYZE")
            conn.set_isolation_level(1)  # Reset isolation level
            
            config.logger.info("Database cleaning completed successfully")
            conn.commit()
            
    except Exception as e:
        if conn:
            conn.rollback()
        config.logger.error(f"Database cleaning failed: {e}")
    finally:
        if conn:
            conn.close()

class PostgresExecutor:
    """Helper class for executing PostgreSQL queries with proper error handling."""
    
    @staticmethod
    def execute_query(query: str, params=None, fetch_one=False, fetch_all=False, commit=True):
        """
        Execute a query with proper error handling and connection management.
        
        Args:
            query: SQL query string
            params: Query parameters
            fetch_one: Whether to fetch one result
            fetch_all: Whether to fetch all results
            commit: Whether to commit the transaction
            
        Returns:
            Query results if fetch_one or fetch_all is True, or None
        """
        conn = None
        try:
            conn = get_postgres_connection()
            cursor = conn.cursor()
            
            cursor.execute(query, params or ())
            
            result = None
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()
                
            if commit:
                conn.commit()
                
            return result
        except Exception as e:
            if conn:
                conn.rollback()
            config.logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    @staticmethod
    def insert_or_update(table: str, data: Dict[str, Any], unique_columns: List[str]):
        """
        Insert a row or update it if it already exists.
        This is the PostgreSQL equivalent of SQLite's "INSERT OR REPLACE".
        
        Args:
            table: Table name
            data: Column name to value mapping
            unique_columns: Columns that uniquely identify the row
            
        Returns:
            Number of rows affected
        """
        columns = list(data.keys())
        values = list(data.values())
        placeholders = [f"%s" for _ in values]
        
        # Build the ON CONFLICT part
        conflict_columns = ", ".join(unique_columns)
        
        # Build the UPDATE part (exclude the unique columns)
        update_parts = []
        for col in columns:
            if col not in unique_columns:
                update_parts.append(f"{col} = EXCLUDED.{col}")
        
        update_clause = ", ".join(update_parts) if update_parts else "id = EXCLUDED.id"
        
        query = f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT ({conflict_columns})
            DO UPDATE SET {update_clause}
        """
        
        return PostgresExecutor.execute_query(query, values, commit=True)
    
    @staticmethod
    def insert_or_ignore(table: str, data: Dict[str, Any], unique_columns: List[str]):
        """
        Insert a row if it doesn't already exist.
        This is the PostgreSQL equivalent of SQLite's "INSERT OR IGNORE".
        
        Args:
            table: Table name
            data: Column name to value mapping
            unique_columns: Columns that uniquely identify the row
            
        Returns:
            Number of rows affected
        """
        columns = list(data.keys())
        values = list(data.values())
        placeholders = [f"%s" for _ in values]
        
        # Build the ON CONFLICT part
        conflict_columns = ", ".join(unique_columns)
        
        query = f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT ({conflict_columns})
            DO NOTHING
        """
        
        return PostgresExecutor.execute_query(query, values, commit=True)
    
    @staticmethod
    def bulk_insert(table: str, data_list: List[Dict[str, Any]], unique_columns: List[str]=None):
        """
        Insert multiple rows at once for better performance.
        
        Args:
            table: Table name
            data_list: List of dictionaries mapping column names to values
            unique_columns: Columns that uniquely identify rows (for ON CONFLICT)
            
        Returns:
            Number of rows affected
        """
        if not data_list:
            return 0
            
        # All dictionaries must have the same keys
        columns = list(data_list[0].keys())
        
        # Prepare values list
        all_values = []
        for data in data_list:
            values = [data.get(col) for col in columns]
            all_values.append(values)
            
        # Create placeholders
        placeholders = [f"%s" for _ in columns]
        placeholders_str = f"({', '.join(placeholders)})"
        
        # Prepare the base query
        query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES "
        
        # Add the values placeholders
        values_part = ", ".join([placeholders_str] * len(data_list))
        query += values_part
        
        # Add ON CONFLICT clause if unique_columns is provided
        if unique_columns:
            conflict_columns = ", ".join(unique_columns)
            query += f" ON CONFLICT ({conflict_columns}) DO NOTHING"
            
        # Flatten all_values for the execute function
        flat_values = [val for sublist in all_values for val in sublist]
        
        return PostgresExecutor.execute_query(query, flat_values, commit=True)