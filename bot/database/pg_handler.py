"""
PostgreSQL database handler for Railway deployment.
Provides better handling of PostgreSQL connections and migrations.
"""
import psycopg2
import psycopg2.extras
import logging
import time
import os
from typing import Dict, Any, List, Tuple, Optional
import bot.config as config

def get_postgres_connection():
    """
    Get a connection to the PostgreSQL database on Railway.
    
    Returns:
        Database connection
    """
    # Get DATABASE_URL from Railway environment
    db_url = os.getenv("DATABASE_URL") or config.DATABASE_URL
    
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set")
        
    # Add retry mechanism for connection
    max_retries = 5
    retry_delay = 3  # seconds
    
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = False  # We'll manage transactions explicitly
            conn.cursor_factory = psycopg2.extras.DictCursor  # Enable dictionary-like access to rows
            
            config.logger.info("Successfully connected to PostgreSQL database")
            return conn
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                config.logger.warning(f"Failed to connect to PostgreSQL (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                config.logger.error(f"Failed to connect to PostgreSQL after {max_retries} attempts: {e}")
                raise

def setup_postgres_tables(conn=None):
    """
    Set up PostgreSQL database tables.
    
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
            
            # Unified world posts table
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
            
            # VRChat worlds table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vrchat_worlds (
                    world_id TEXT PRIMARY KEY,
                    world_name TEXT,
                    author_name TEXT,
                    image_url TEXT,
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
            
            # Bot activity log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_activity_log (
                    id SERIAL PRIMARY KEY,
                    server_id BIGINT,
                    action_type TEXT,
                    details TEXT,
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
            
            # Create indexes for better performance
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
            config.logger.info("PostgreSQL tables created successfully")
            
    except Exception as e:
        conn.rollback()
        config.logger.error(f"Error creating PostgreSQL tables: {e}")
        raise
    finally:
        if connection_created:
            conn.close()

def migrate_data_from_sqlite():
    """
    Migrate data from SQLite to PostgreSQL.
    
    This function should be called if you want to move data from a local SQLite
    database to the PostgreSQL database on Railway.
    """
    # This function would implement the data migration logic if needed
    # For now, it's a placeholder - implement when needed
    pass

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