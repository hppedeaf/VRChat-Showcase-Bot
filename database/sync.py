"""
Database migration module for moving data from SQLite to PostgreSQL.
Replaces the complex sync system with a simpler one-way migration when needed.
"""
import logging
import sqlite3
import os
import config as config

# Initialize logger
logger = logging.getLogger(__name__)

def migrate_sqlite_to_postgres():
    """
    Migrate data from SQLite to PostgreSQL.
    This is a one-way migration intended to be used when:
    1. PostgreSQL was previously unavailable but is now available
    2. A new deployment is being set up with existing SQLite data
    
    Returns:
        dict: Results of the migration with counts of migrated records per table
    """
    # Check if SQLite database exists
    sqlite_db_path = config.DATABASE_FILE
    if not os.path.exists(sqlite_db_path):
        logger.warning(f"SQLite database {sqlite_db_path} not found, skipping migration")
        return {"status": "error", "message": "SQLite database not found"}
    
    # Check if PostgreSQL is available
    if not config.PG_AVAILABLE:
        logger.warning("PostgreSQL is not available, skipping migration")
        return {"status": "error", "message": "PostgreSQL not available"}
    
    logger.info(f"Starting migration from SQLite database {sqlite_db_path} to PostgreSQL")
    
    # Connect to both databases
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    
    # Tables to migrate - add all your tables here
    tables_to_migrate = [
        "server_channels",
        "world_posts",
        "user_world_links",
        "thread_world_links",
        "server_tags",
        "vrchat_worlds",
        "tag_usage",
        "bot_activity_log",
        "activity_stats",
        "guild_tracking",
        "bot_stats"
    ]
    
    results = {}
    try:
        # Get PostgreSQL connection
        from database.pg_handler import get_postgres_connection
        pg_conn = get_postgres_connection()
        
        # For each table, migrate the data
        for table in tables_to_migrate:
            logger.info(f"Migrating table: {table}")
            
            # Skip SQLite system tables
            if table.startswith('sqlite_'):
                continue
                
            # Get table schema to determine columns
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in sqlite_cursor.fetchall()]
            
            if not columns:
                logger.warning(f"No columns found for table {table}, skipping")
                results[table] = 0
                continue
                
            # Get data from SQLite
            sqlite_cursor.execute(f"SELECT * FROM {table}")
            rows = sqlite_cursor.fetchall()
            
            if not rows:
                logger.info(f"No data in table {table}, skipping")
                results[table] = 0
                continue
                
            # Insert data into PostgreSQL
            migrated_count = 0
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
                        migrated_count += 1
                    except Exception as e:
                        logger.error(f"Error inserting row in table {table}: {e}")
                        # Continue with next row
                        continue
            
            results[table] = migrated_count
            logger.info(f"Migrated {migrated_count} rows from table {table}")
        
        # Commit all changes
        pg_conn.commit()
        pg_conn.close()
        logger.info("Migration completed successfully")
        
        return {
            "status": "success",
            "tables": results,
            "total": sum(results.values())
        }
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {
            "status": "error", 
            "message": str(e)
        }
    finally:
        sqlite_conn.close()

# Simple function to check if migration is needed
def check_migration_needed():
    """
    Check if migration from SQLite to PostgreSQL is needed.
    
    Returns:
        bool: True if migration is needed, False otherwise
    """
    # If PostgreSQL is not available, no migration is needed
    if not config.PG_AVAILABLE:
        return False
    
    # If SQLite database doesn't exist, no migration is needed
    if not os.path.exists(config.DATABASE_FILE):
        return False
    
    try:
        # Check if SQLite has data that PostgreSQL doesn't
        sqlite_conn = sqlite3.connect(config.DATABASE_FILE)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        
        # Check if world_posts table exists and has data
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='world_posts'")
        if not sqlite_cursor.fetchone():
            sqlite_conn.close()
            return False
        
        # Check if there are records in SQLite
        sqlite_cursor.execute("SELECT COUNT(*) FROM world_posts")
        sqlite_count = sqlite_cursor.fetchone()[0]
        sqlite_conn.close()
        
        # If no records in SQLite, no migration needed
        if sqlite_count == 0:
            return False
        
        # Check PostgreSQL record count
        from database.pg_handler import get_postgres_connection
        pg_conn = get_postgres_connection()
        pg_cursor = pg_conn.cursor()
        
        # Check if world_posts table exists in PostgreSQL
        pg_cursor.execute("SELECT to_regclass('world_posts')")
        if not pg_cursor.fetchone()[0]:
            pg_conn.close()
            return True  # Migration needed if table doesn't exist in PostgreSQL
        
        # Compare record counts
        pg_cursor.execute("SELECT COUNT(*) FROM world_posts")
        pg_count = pg_cursor.fetchone()[0]
        pg_conn.close()
        
        # Migration needed if SQLite has more records
        return sqlite_count > pg_count
        
    except Exception as e:
        logger.error(f"Error checking migration need: {e}")
        return False  # On error, assume no migration needed