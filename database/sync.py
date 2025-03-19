"""
Database synchronization module for keeping SQLite and PostgreSQL in sync.
"""
import time
import threading
import schedule
import logging
from typing import Dict, List, Tuple, Any, Optional
import sqlite3
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
import config as config

# Initialize logger
logger = logging.getLogger(__name__)

class DatabaseSynchronizer:
    """
    Class for bidirectional synchronization between SQLite and PostgreSQL databases.
    """
    
    def __init__(self, sync_interval: int = 300):
        """
        Initialize the synchronizer.
        
        Args:
            sync_interval: Time in seconds between automatic syncs (default: 5 minutes)
        """
        self.sync_interval = sync_interval
        self.last_sync_time = 0
        self.running = False
        self.sync_thread = None
        self.initialization_attempts = 0
        self.max_initialization_attempts = 5
        
        # Tables to synchronize - add all your tables here
        self.tables_to_sync = [
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
        
        # Delay initialization to allow database setup to complete
        self._delayed_init()
    
    def _delayed_init(self):
        """Initialize the synchronization system with a delay to allow database setup."""
        def init_task():
            time.sleep(5)  # Wait 5 seconds before initializing
            try:
                # Make sure the database file exists
                if not self._is_pg_available() and not os.path.exists(config.DATABASE_FILE):
                    logger.info(f"SQLite database file does not exist yet. Creating directory...")
                    os.makedirs(os.path.dirname(config.DATABASE_FILE), exist_ok=True)
                    
                    # Create an empty database file
                    conn = sqlite3.connect(config.DATABASE_FILE)
                    conn.close()
                    logger.info(f"Created empty SQLite database file: {config.DATABASE_FILE}")
                
                # Initialize tracking tables
                self._init_sync_tracking()
                logger.info("Delayed initialization of sync tracking completed successfully")
            except Exception as e:
                self.initialization_attempts += 1
                if self.initialization_attempts < self.max_initialization_attempts:
                    logger.warning(f"Initialization attempt {self.initialization_attempts} failed: {e}. Retrying in 5 seconds...")
                    threading.Timer(5, init_task).start()
                else:
                    logger.error(f"Failed to initialize after {self.max_initialization_attempts} attempts: {e}")
        
        # Start the delayed initialization in a separate thread
        threading.Thread(target=init_task, daemon=True).start()
    
    def _init_sync_tracking(self):
        """Initialize the synchronization tracking tables in both databases."""
        # SQLite tracking table
        try:
            # First check if SQLite database exists
            if not os.path.exists(config.DATABASE_FILE):
                logger.warning(f"SQLite database file does not exist: {config.DATABASE_FILE}")
                database_dir = os.path.dirname(config.DATABASE_FILE)
                if not os.path.exists(database_dir):
                    os.makedirs(database_dir, exist_ok=True)
                    logger.info(f"Created database directory: {database_dir}")
                
                # Create empty database
                conn = sqlite3.connect(config.DATABASE_FILE)
                conn.close()
                logger.info(f"Created empty SQLite database file: {config.DATABASE_FILE}")
            
            sqlite_conn = self._get_sqlite_connection()
            if not sqlite_conn:
                logger.error("Failed to connect to SQLite database")
                return
                
            sqlite_cursor = sqlite_conn.cursor()
            
            sqlite_cursor.execute("""
                CREATE TABLE IF NOT EXISTS db_sync_tracking (
                    table_name TEXT PRIMARY KEY,
                    last_sqlite_sync TEXT,
                    last_pg_sync TEXT
                )
            """)
            
            # Insert initial records for all tables if they don't exist
            for table in self.tables_to_sync:
                sqlite_cursor.execute("""
                    INSERT OR IGNORE INTO db_sync_tracking (table_name, last_sqlite_sync, last_pg_sync)
                    VALUES (?, datetime('now'), datetime('now'))
                """, (table,))
            
            sqlite_conn.commit()
            sqlite_conn.close()
            
            # PostgreSQL tracking table
            if self._is_pg_available():
                pg_conn = self._get_pg_connection()
                if not pg_conn:
                    logger.error("Failed to connect to PostgreSQL database")
                    return
                    
                pg_cursor = pg_conn.cursor()
                
                pg_cursor.execute("""
                    CREATE TABLE IF NOT EXISTS db_sync_tracking (
                        table_name TEXT PRIMARY KEY,
                        last_sqlite_sync TIMESTAMP,
                        last_pg_sync TIMESTAMP
                    )
                """)
                
                # Insert initial records for all tables if they don't exist
                for table in self.tables_to_sync:
                    pg_cursor.execute("""
                        INSERT INTO db_sync_tracking (table_name, last_sqlite_sync, last_pg_sync)
                        VALUES (%s, NOW(), NOW())
                        ON CONFLICT (table_name) DO NOTHING
                    """, (table,))
                
                pg_conn.commit()
                pg_conn.close()
            
            logger.info("Initialized sync tracking tables")
        except Exception as e:
            logger.error(f"Error initializing sync tracking: {e}")
            raise
    
    def _is_pg_available(self) -> bool:
        """Check if PostgreSQL is available and configured using individual environment variables."""
        # Check if the essential PostgreSQL connection parameters are set
        pg_host = os.environ.get('PGHOST') or os.environ.get('POSTGRES_HOST')
        pg_user = os.environ.get('PGUSER') or os.environ.get('POSTGRES_USER')
        pg_password = os.environ.get('PGPASSWORD') or os.environ.get('POSTGRES_PASSWORD')
        
        # Check if we're running locally
        is_local = not os.environ.get('RAILWAY_ENVIRONMENT')
        
        # If running locally but with Railway environment variables, still disable PG
        if is_local and "railway" in (pg_host or ""):
            return False
        
        # If essential connection parameters are available, PostgreSQL is considered available
        return bool(pg_host and pg_user and pg_password)

    def _get_sqlite_connection(self):
        """
        Get a connection to the SQLite database with better error handling.
        
        Returns:
            SQLite connection or None if connection fails
        """
        try:
            # Make sure the database directory exists
            db_dir = os.path.dirname(config.DATABASE_FILE)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created database directory: {db_dir}")
            
            # Try to connect with timeout
            conn = sqlite3.connect(config.DATABASE_FILE, timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.error(f"Error connecting to SQLite database: {e}")
            return None
    
    def _get_pg_connection(self):
        """
        Get a connection to the PostgreSQL database using individual environment variables.
        
        Returns:
            PostgreSQL connection or None if connection fails
        """
        if not self._is_pg_available():
            return None
            
        try:
            # Get connection parameters from environment variables with fallbacks
            pg_host = os.environ.get('PGHOST') or os.environ.get('POSTGRES_HOST')
            pg_port = os.environ.get('PGPORT') or os.environ.get('POSTGRES_PORT', '5432')
            pg_user = os.environ.get('PGUSER') or os.environ.get('POSTGRES_USER')
            pg_password = os.environ.get('PGPASSWORD') or os.environ.get('POSTGRES_PASSWORD')
            pg_database = os.environ.get('PGDATABASE') or os.environ.get('POSTGRES_DB', 'postgres')
            
            # Build connection string
            conn_params = {
                'host': pg_host,
                'port': pg_port,
                'user': pg_user,
                'password': pg_password,
                'dbname': pg_database,
                'connect_timeout': 10,
                'application_name': "VRChat World Showcase Bot"
            }
            
            # Optional SSL parameters
            if os.environ.get('PGSSLMODE'):
                conn_params['sslmode'] = os.environ.get('PGSSLMODE')
            
            import psycopg2
            import psycopg2.extras
            
            conn = psycopg2.connect(**conn_params)
            conn.cursor_factory = psycopg2.extras.DictCursor
            return conn
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL database: {e}")
            return None
    
    def _get_table_columns(self, table_name: str) -> List[str]:
        """
        Get the column names for a table from SQLite.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column names
        """
        conn = self._get_sqlite_connection()
        if not conn:
            return []
            
        try:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row['name'] for row in cursor.fetchall()]
            conn.close()
            return columns
        except Exception as e:
            logger.error(f"Error getting columns for {table_name}: {e}")
            if conn:
                conn.close()
            return []
    
    def _get_primary_key_columns(self, table_name: str) -> List[str]:
        """
        Get the primary key columns for a table from SQLite.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of primary key column names
        """
        conn = self._get_sqlite_connection()
        if not conn:
            return []
            
        try:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            pk_columns = [row['name'] for row in cursor.fetchall() if row['pk'] > 0]
            conn.close()
            
            # If no primary key is defined, return the first column as a fallback
            if not pk_columns:
                columns = self._get_table_columns(table_name)
                if columns:
                    return [columns[0]]
            
            return pk_columns
        except Exception as e:
            logger.error(f"Error getting primary key for {table_name}: {e}")
            if conn:
                conn.close()
            return []
    
    def _get_last_sync_time(self, table_name: str) -> Tuple[datetime, datetime]:
        """
        Get the last synchronization times for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Tuple of (last_sqlite_sync, last_pg_sync) timestamps
        """
        sqlite_conn = self._get_sqlite_connection()
        if not sqlite_conn:
            now = datetime.now()
            return (now, now)
            
        try:
            sqlite_cursor = sqlite_conn.cursor()
            
            sqlite_cursor.execute("""
                SELECT last_sqlite_sync, last_pg_sync FROM db_sync_tracking
                WHERE table_name = ?
            """, (table_name,))
            
            result = sqlite_cursor.fetchone()
            sqlite_conn.close()
            
            if result:
                last_sqlite_sync = datetime.fromisoformat(result['last_sqlite_sync'].replace('Z', '+00:00'))
                last_pg_sync = datetime.fromisoformat(result['last_pg_sync'].replace('Z', '+00:00'))
                return (last_sqlite_sync, last_pg_sync)
        except Exception as e:
            logger.error(f"Error getting last sync time for {table_name}: {e}")
            if sqlite_conn:
                sqlite_conn.close()
        
        # Return default values if no record exists or an error occurred
        now = datetime.now()
        return (now, now)
    
    def _update_sync_time(self, table_name: str, source: str):
        """
        Update the synchronization time for a table.
        
        Args:
            table_name: Name of the table
            source: Source database ('sqlite' or 'pg')
        """
        # Update in SQLite
        sqlite_conn = self._get_sqlite_connection()
        if not sqlite_conn:
            return
            
        try:
            sqlite_cursor = sqlite_conn.cursor()
            
            if source == 'sqlite':
                sqlite_cursor.execute("""
                    UPDATE db_sync_tracking
                    SET last_sqlite_sync = datetime('now')
                    WHERE table_name = ?
                """, (table_name,))
            else:
                sqlite_cursor.execute("""
                    UPDATE db_sync_tracking
                    SET last_pg_sync = datetime('now')
                    WHERE table_name = ?
                """, (table_name,))
            
            sqlite_conn.commit()
            sqlite_conn.close()
            
            # Update in PostgreSQL if available
            if self._is_pg_available():
                pg_conn = self._get_pg_connection()
                if not pg_conn:
                    return
                    
                pg_cursor = pg_conn.cursor()
                
                if source == 'sqlite':
                    pg_cursor.execute("""
                        UPDATE db_sync_tracking
                        SET last_sqlite_sync = NOW()
                        WHERE table_name = %s
                    """, (table_name,))
                else:
                    pg_cursor.execute("""
                        UPDATE db_sync_tracking
                        SET last_pg_sync = NOW()
                        WHERE table_name = %s
                    """, (table_name,))
                
                pg_conn.commit()
                pg_conn.close()
        except Exception as e:
            logger.error(f"Error updating sync time for {table_name}: {e}")
            if sqlite_conn:
                sqlite_conn.close()
    
    def sync_sqlite_to_pg(self, table_name: str) -> int:
        """
        Synchronize changes from SQLite to PostgreSQL.
        
        Args:
            table_name: Name of the table to synchronize
            
        Returns:
            Number of rows synchronized
        """
        if not self._is_pg_available():
            logger.warning("PostgreSQL is not available, skipping sync")
            return 0
        
        try:
            # Check if tables exist before syncing
            sqlite_conn = self._get_sqlite_connection()
            if not sqlite_conn:
                return 0
                
            sqlite_cursor = sqlite_conn.cursor()
            
            # Check if table exists in SQLite
            sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if not sqlite_cursor.fetchone():
                logger.warning(f"Table {table_name} does not exist in SQLite database")
                sqlite_conn.close()
                return 0
            
            sqlite_conn.close()
            
            # Get the last synchronization time
            last_sqlite_sync, _ = self._get_last_sync_time(table_name)
            
            # Connect to both databases
            sqlite_conn = self._get_sqlite_connection()
            if not sqlite_conn:
                return 0
                
            pg_conn = self._get_pg_connection()
            if not pg_conn:
                if sqlite_conn:
                    sqlite_conn.close()
                return 0
            
            sqlite_cursor = sqlite_conn.cursor()
            pg_cursor = pg_conn.cursor()
            
            # Check if table exists in PostgreSQL
            pg_cursor.execute("SELECT to_regclass(%s)", (table_name,))
            if not pg_cursor.fetchone()[0]:
                logger.warning(f"Table {table_name} does not exist in PostgreSQL database")
                sqlite_conn.close()
                pg_conn.close()
                return 0
            
            # Get columns for this table
            columns = self._get_table_columns(table_name)
            if not columns:
                sqlite_conn.close()
                pg_conn.close()
                return 0
            
            # Get primary key columns
            pk_columns = self._get_primary_key_columns(table_name)
            if not pk_columns:
                logger.error(f"No primary key found for table {table_name}, skipping sync")
                sqlite_conn.close()
                pg_conn.close()
                return 0
            
            # Build WHERE condition for primary keys
            pk_conditions = " AND ".join([f"{pk} = %s" for pk in pk_columns])
            
            # Get all rows from SQLite that have been updated since last sync
            # For tables without updated_at column, get all rows
            if 'updated_at' in columns:
                sqlite_cursor.execute(f"""
                    SELECT * FROM {table_name}
                    WHERE datetime(updated_at) > datetime(?)
                """, (last_sqlite_sync.isoformat(),))
            else:
                sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            
            rows = sqlite_cursor.fetchall()
            
            # Build column list string
            cols_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            
            # Build SET clause for UPDATE statement
            set_clause = ", ".join([f"{col} = %s" for col in columns if col not in pk_columns])
            
            synced_count = 0
            
            # Process each row
            for row in rows:
                # Convert row to dict
                row_dict = {col: row[col] for col in columns}
                
                # Extract primary key values
                pk_values = [row_dict[pk] for pk in pk_columns]
                
                # Check if this row exists in PostgreSQL
                pg_cursor.execute(f"""
                    SELECT 1 FROM {table_name}
                    WHERE {pk_conditions}
                """, pk_values)
                
                exists = pg_cursor.fetchone() is not None
                
                if exists:
                    # Update existing row
                    update_values = [row_dict[col] for col in columns if col not in pk_columns]
                    update_values.extend(pk_values)  # Add PK values for WHERE clause
                    
                    pg_cursor.execute(f"""
                        UPDATE {table_name}
                        SET {set_clause}
                        WHERE {pk_conditions}
                    """, update_values)
                else:
                    # Insert new row
                    values = [row_dict[col] for col in columns]
                    
                    pg_cursor.execute(f"""
                        INSERT INTO {table_name} ({cols_str})
                        VALUES ({placeholders})
                    """, values)
                
                synced_count += 1
            
            # Commit changes
            pg_conn.commit()
            
            # Update sync time
            self._update_sync_time(table_name, 'sqlite')
            
            # Close connections
            sqlite_conn.close()
            pg_conn.close()
            
            logger.info(f"Synced {synced_count} rows from SQLite to PostgreSQL for table {table_name}")
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing {table_name} from SQLite to PostgreSQL: {e}")
            return 0
    
    def sync_pg_to_sqlite(self, table_name: str) -> int:
        """
        Synchronize changes from PostgreSQL to SQLite.
        
        Args:
            table_name: Name of the table to synchronize
            
        Returns:
            Number of rows synchronized
        """
        if not self._is_pg_available():
            logger.warning("PostgreSQL is not available, skipping sync")
            return 0
        
        try:
            # Check if tables exist before syncing
            sqlite_conn = self._get_sqlite_connection()
            if not sqlite_conn:
                return 0
                
            sqlite_cursor = sqlite_conn.cursor()
            
            # Check if table exists in SQLite
            sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if not sqlite_cursor.fetchone():
                logger.warning(f"Table {table_name} does not exist in SQLite database")
                sqlite_conn.close()
                return 0
            
            sqlite_conn.close()
            
            # Get the last synchronization time
            _, last_pg_sync = self._get_last_sync_time(table_name)
            
            # Connect to both databases
            sqlite_conn = self._get_sqlite_connection()
            if not sqlite_conn:
                return 0
                
            pg_conn = self._get_pg_connection()
            if not pg_conn:
                if sqlite_conn:
                    sqlite_conn.close()
                return 0
            
            sqlite_cursor = sqlite_conn.cursor()
            pg_cursor = pg_conn.cursor()
            
            # Check if table exists in PostgreSQL
            pg_cursor.execute("SELECT to_regclass(%s)", (table_name,))
            if not pg_cursor.fetchone()[0]:
                logger.warning(f"Table {table_name} does not exist in PostgreSQL database")
                sqlite_conn.close()
                pg_conn.close()
                return 0
            
            # Get columns for this table
            columns = self._get_table_columns(table_name)
            if not columns:
                sqlite_conn.close()
                pg_conn.close()
                return 0
            
            # Get primary key columns
            pk_columns = self._get_primary_key_columns(table_name)
            if not pk_columns:
                logger.error(f"No primary key found for table {table_name}, skipping sync")
                sqlite_conn.close()
                pg_conn.close()
                return 0
            
            # Build WHERE condition for primary keys
            sqlite_pk_conditions = " AND ".join([f"{pk} = ?" for pk in pk_columns])
            
            # Get all rows from PostgreSQL that have been updated since last sync
            # For tables without updated_at column, get all rows
            if 'updated_at' in columns:
                pg_cursor.execute(f"""
                    SELECT * FROM {table_name}
                    WHERE updated_at > %s
                """, (last_pg_sync.isoformat(),))
            else:
                pg_cursor.execute(f"SELECT * FROM {table_name}")
            
            rows = pg_cursor.fetchall()
            
            # Build column list string
            cols_str = ", ".join(columns)
            placeholders = ", ".join(["?"] * len(columns))
            
            # Build SET clause for UPDATE statement
            set_clause = ", ".join([f"{col} = ?" for col in columns if col not in pk_columns])
            
            synced_count = 0
            
            # Process each row
            for row in rows:
                # Convert row to dict
                row_dict = {col: row[col] for col in columns}
                
                # Extract primary key values
                pk_values = [row_dict[pk] for pk in pk_columns]
                
                # Check if this row exists in SQLite
                sqlite_cursor.execute(f"""
                    SELECT 1 FROM {table_name}
                    WHERE {sqlite_pk_conditions}
                """, pk_values)
                
                exists = sqlite_cursor.fetchone() is not None
                
                if exists:
                    # Update existing row
                    update_values = [row_dict[col] for col in columns if col not in pk_columns]
                    update_values.extend(pk_values)  # Add PK values for WHERE clause
                    
                    sqlite_cursor.execute(f"""
                        UPDATE {table_name}
                        SET {set_clause}
                        WHERE {sqlite_pk_conditions}
                    """, update_values)
                else:
                    # Insert new row
                    values = [row_dict[col] for col in columns]
                    
                    sqlite_cursor.execute(f"""
                        INSERT INTO {table_name} ({cols_str})
                        VALUES ({placeholders})
                    """, values)
                
                synced_count += 1
            
            # Commit changes
            sqlite_conn.commit()
            
            # Update sync time
            self._update_sync_time(table_name, 'pg')
            
            # Close connections
            sqlite_conn.close()
            pg_conn.close()
            
            logger.info(f"Synced {synced_count} rows from PostgreSQL to SQLite for table {table_name}")
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing {table_name} from PostgreSQL to SQLite: {e}")
            return 0
    
    def sync_all_tables(self) -> Dict[str, Dict[str, int]]:
        """
        Synchronize all tables in both directions.
        
        Returns:
            Dictionary with sync results for each table
        """
        results = {}
        
        for table_name in self.tables_to_sync:
            sqlite_to_pg = self.sync_sqlite_to_pg(table_name)
            pg_to_sqlite = self.sync_pg_to_sqlite(table_name)
            
            results[table_name] = {
                'sqlite_to_pg': sqlite_to_pg,
                'pg_to_sqlite': pg_to_sqlite
            }
        
        self.last_sync_time = time.time()
        return results
    
    def _sync_job(self):
        """Job function for scheduled sync."""
        try:
            logger.info("Starting scheduled database sync")
            results = self.sync_all_tables()
            
            # Log summary of results
            total_sqlite_to_pg = sum([r['sqlite_to_pg'] for r in results.values()])
            total_pg_to_sqlite = sum([r['pg_to_sqlite'] for r in results.values()])
            
            logger.info(f"Scheduled sync complete: SQLite → PG: {total_sqlite_to_pg} rows, PG → SQLite: {total_pg_to_sqlite} rows")
        except Exception as e:
            logger.error(f"Error in scheduled sync job: {e}")
    
    def start_sync_scheduler(self):
        """Start the synchronization scheduler in a separate thread."""
        if self.running:
            logger.warning("Sync scheduler is already running")
            return
        
        def scheduler_thread():
            """Thread function for the scheduler."""
            logger.info(f"Starting sync scheduler (interval: {self.sync_interval} seconds)")
            
            # Schedule the sync job to run at the specified interval
            schedule.every(self.sync_interval).seconds.do(self._sync_job)
            
            # Run the job once at startup
            # Wait 20 seconds before the first sync to allow database initialization
            logger.info("Waiting 20 seconds before first sync to allow database initialization...")
            time.sleep(20)
            self._sync_job()
            
            # Keep running until self.running is False
            while self.running:
                schedule.run_pending()
                time.sleep(1)
            
            logger.info("Sync scheduler stopped")
        
        self.running = True
        self.sync_thread = threading.Thread(target=scheduler_thread, daemon=True)
        self.sync_thread.start()
    
    def stop_sync_scheduler(self):
        """Stop the synchronization scheduler."""
        if not self.running:
            logger.warning("Sync scheduler is not running")
            return
        
        self.running = False
        
        if self.sync_thread:
            self.sync_thread.join(timeout=10)
            if self.sync_thread.is_alive():
                logger.warning("Sync thread did not terminate gracefully")
            
            self.sync_thread = None
        
        logger.info("Sync scheduler stopped")

# Singleton instance
synchronizer = None

def get_synchronizer() -> DatabaseSynchronizer:
    """Get the singleton DatabaseSynchronizer instance."""
    global synchronizer
    if synchronizer is None:
        synchronizer = DatabaseSynchronizer()
    return synchronizer

def start_sync_scheduler():
    """Start the database synchronization scheduler."""
    get_synchronizer().start_sync_scheduler()

def stop_sync_scheduler():
    """Stop the database synchronization scheduler."""
    if synchronizer:
        synchronizer.stop_sync_scheduler()

def sync_now():
    """Perform an immediate sync of all tables."""
    return get_synchronizer().sync_all_tables()