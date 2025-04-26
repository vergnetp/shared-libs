import asyncio
import pymysql
import aiomysql
from typing import Tuple, Any, List, Optional
from ..errors import TrackError
from ..log import logging as logger
from .base import Database

class MySqlDatabase(Database):
    _pool: Optional[aiomysql.Pool] = None
    _pool_lock = asyncio.Lock()
    
    def __init__(self, database: str, host: str=None, port: int=None, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod', **kwargs):
        super().__init__(database, host, port, user, password, alias, env)

        # Additional connection options
        self._conn_config = self.config().copy()
        self._conn_config.update(kwargs)
        
        # Initialize with defaults
        self._conn = None
        self._cursor = None
        
        try:
            # Sync connection
            self._conn = pymysql.connect(**self._conn_config)
            self._cursor = self._conn.cursor()
            self._sync_tx_active = False
            
            # Verify that we can select the database
            self._cursor.execute(f"USE {database}")
            logger.info(f"Successfully connected to MySQL database {database}")
        except Exception as e:
            logger.error(f"Error connecting to MySQL database {database}: {e}")
            raise

        # Async connection (init in async flow)
        self._pool = None
        self._async_conn = None
        self._tx_active = False

    def is_connected(self) -> bool:
        try:
            self._conn.ping(reconnect=True)
            return True
        except Exception as e:
            logger.debug(f"Connection check failed for {self.alias()}: {e}")
            return False

    def type(self) -> str:
        return "mysql"

    def placeholder(self, is_async: bool=True) -> str:
        return "%s"

    # --- Sync methods ---
    def begin_transaction(self) -> None:
        try:
            # Make sure we have the right database selected
            db_name = self.config().get("database")
            self._cursor.execute(f"USE {db_name}")
            
            # Set isolation level to ensure consistency
            self._cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            
            # Start transaction
            self._conn.autocommit = False
            self._cursor.execute("START TRANSACTION")
            self._sync_tx_active = True
            logger.debug(f"Transaction started for {self.alias()}")
        except Exception as e:
            logger.error(f"Error beginning transaction for {self.alias()}: {e}")
            raise TrackError(e)

    def commit_transaction(self) -> None:
        try:
            # Make sure we're in the right database
            db_name = self.config().get("database")
            self._cursor.execute(f"USE {db_name}")
            
            # Execute explicit commit
            self._cursor.execute("COMMIT")
            self._sync_tx_active = False
            logger.debug(f"Transaction committed for {self.alias()}")
        except Exception as e:
            logger.error(f"Error committing transaction for {self.alias()}: {e}")
            raise TrackError(e)

    def rollback_transaction(self) -> None:
        try:
            # Make sure we're in the right database
            db_name = self.config().get("database")
            self._cursor.execute(f"USE {db_name}")
            
            # Execute explicit rollback
            self._cursor.execute("ROLLBACK")
            self._sync_tx_active = False
            logger.debug(f"Transaction rolled back for {self.alias()}")
        except Exception as e:
            logger.error(f"Error rolling back transaction for {self.alias()}: {e}")

    def execute_sql(self, sql: str, parameters=()) -> list:
        if not self.is_connected():
            raise TrackError(Exception(f"Lost MySQL connection for {self.alias()}"))
        
        try:

            logger.debug(f"Inside execute_sql, transaction active: {self._sync_tx_active} sql: {sql[:40]}")

            # Always select the database before executing queries
            db_name = self.config().get("database")
            self._cursor.execute(f"USE {db_name}")
            
            # Execute the actual query
            self._cursor.execute(sql, parameters)
            if self._cursor.description:
                return self._cursor.fetchall()
            return []
        except Exception as e:
            logger.error(f"SQL execution error for {self.alias()}: {e}, SQL: {sql}")
            raise TrackError(e)

    def executemany_sql(self, sql: str, parameters_list: list) -> None:
        if not self.is_connected():
            raise TrackError(Exception(f"Lost MySQL connection for {self.alias()}"))
        
        try:
            logger.debug(f"Inside executemany_sql, transaction active: {self._sync_tx_active}")
            # Always select the database before executing queries
            db_name = self.config().get("database")
            self._cursor.execute(f"USE {db_name}")
            
            self._cursor.executemany(sql, parameters_list)
        except Exception as e:
            logger.error(f"SQL executemany error for {self.alias()}: {e}, SQL: {sql}")
            raise TrackError(e)

    def _close(self) -> None:
        try:
            if self._cursor:
                self._cursor.close()
            if self._conn:
                self._conn.close()
            self._sync_tx_active = False
        except Exception as e:
            logger.debug(f"Error closing synchronous connection for {self.alias()}: {e}")
    
    def _o_ensure_tables_exist(self, entity_name: str) -> None:
        """Override to create InnoDB tables for MySQL."""
        entity_name = self._sanitize_identifier(entity_name)
        
        # Check if we're in a transaction
        in_transaction = not getattr(self._conn, 'autocommit', True)
        if in_transaction:
            # Exit transaction to perform DDL operations
            logger.debug(f"Exiting transaction to create tables")
            self._cursor.execute("COMMIT")
            self._conn.autocommit = True
            
            # Create tables with InnoDB engine
            self._cursor.execute("""
                CREATE TABLE IF NOT EXISTS _meta_version (
                    entity_name VARCHAR(255) PRIMARY KEY,
                    version INTEGER
                ) ENGINE=InnoDB
            """)
            
            self._cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                    name VARCHAR(255),
                    type VARCHAR(255),
                    PRIMARY KEY (name)
                ) ENGINE=InnoDB
            """)
            
            self._cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_name} (
                    id VARCHAR(255),
                    PRIMARY KEY (id)
                ) ENGINE=InnoDB
            """)
            
            # Restart transaction
            self._conn.autocommit = False
            self._cursor.execute("START TRANSACTION")
            logger.debug(f"Transaction restarted after table creation")
        else:
            # Create tables with InnoDB engine outside of transaction
            self._cursor.execute("""
                CREATE TABLE IF NOT EXISTS _meta_version (
                    entity_name VARCHAR(255) PRIMARY KEY,
                    version INTEGER
                ) ENGINE=InnoDB
            """)
            
            self._cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                    name VARCHAR(255),
                    type VARCHAR(255),
                    PRIMARY KEY (name)
                ) ENGINE=InnoDB
            """)
            
            self._cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_name} (
                    id VARCHAR(255),
                    PRIMARY KEY (id)
                ) ENGINE=InnoDB
            """)

    def clear_all(self) -> None:
        try:            
            # Make sure we're in the right database
            db_name = self.config().get("database")
            self._cursor.execute(f"USE {db_name}")
            
            # Get all tables and drop them
            self._cursor.execute("SHOW TABLES")
            tables = [row[0] for row in self._cursor.fetchall()]
            
            for table in tables:
                self._cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
                
            # Create required meta tables
            self._cursor.execute('''
                CREATE TABLE IF NOT EXISTS _meta_version (
                    entity_name VARCHAR(255) PRIMARY KEY,
                    version INTEGER
                ) ENGINE=InnoDB
            ''')
            
            logger.debug(f"Cleared database {self.alias()}")
        except Exception as e:
            logger.error(f"Failed to clear database {self.alias()}: {e}")
            raise TrackError(e)

    # --- Async methods ---
    async def _is_event_loop_valid(self):
        """Check if the current event loop is valid for async operations."""
        try:
            loop = asyncio.get_running_loop()
            return not loop.is_closed()
        except RuntimeError:
            return False

    @classmethod
    async def initialize_pool_if_needed(cls, config):
        """Initialize the connection pool if it doesn't exist."""
        # First, check if existing pool is usable
        if cls._pool:
            try:
                # Test if pool is still operational
                async with cls._pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SELECT 1")
                return  # Pool is working, nothing to do
            except Exception as e:
                logger.debug(f"Existing MySQL pool is not usable: {e}")
                # Continue to recreate pool
                try:
                    cls._pool.close()
                    await cls._pool.wait_closed()
                except Exception:
                    pass
                cls._pool = None
        
        # Create a new pool
        try:
            async with cls._pool_lock:
                if cls._pool is None:
                    # MySQL requires 'db' instead of 'database'
                    cfg = config.copy()
                    cfg["db"] = cfg.pop("database")
                    
                    cls._pool = await aiomysql.create_pool(
                        minsize=1,
                        maxsize=10,
                        **cfg
                    )
                    logger.info("MySQL connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MySQL connection pool: {e}")
            cls._pool = None
            raise

    async def _init_async(self):
        """Initialize async connections for the database."""
        # Verify event loop is usable
        if not await self._is_event_loop_valid():
            logger.debug(f"Event loop is not valid for {self.alias()}")
            return False
                
        try:
            # Initialize/verify pool
            if MySqlDatabase._pool is None:
                await self.initialize_pool_if_needed(self.config())
            
            # Test pool if it exists
            if MySqlDatabase._pool is None:
                logger.error(f"Failed to create pool for {self.alias()}")
                return False
                
            # Get a connection if we don't have one
            if self._async_conn is None:
                try:
                    self._async_conn = await MySqlDatabase._pool.acquire()
                    
                    # Explicitly select the database for this connection
                    db_name = self.config().get("database")
                    async with self._async_conn.cursor() as cursor:
                        await cursor.execute(f"USE {db_name}")
                        
                except Exception as e:
                    logger.error(f"Error acquiring connection for {self.alias()}: {e}")
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Error initializing async connection for {self.alias()}: {e}")
            return False

    async def begin_transaction_async(self) -> None:
        """Start a new transaction."""
        # Skip if event loop is not valid
        if not await self._is_event_loop_valid():
            raise TrackError(Exception(f"Cannot begin transaction: Event loop not valid for {self.alias()}"))
            
        # Ensure we have a valid connection
        if not await self._init_async():
            if not await self._init_async():
                raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
        
        try:
            # Make sure the right database is selected
            async with self._async_conn.cursor() as cursor:
                # Set isolation level to ensure consistency
                await cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                
                # Set autocommit to False
                await self._async_conn.autocommit(False)
                
                # Start the transaction explicitly
                await cursor.execute("START TRANSACTION")
                self._tx_active = True
                
                logger.debug(f"Async transaction started for {self.alias()}")
        except Exception as e:
            logger.error(f"Failed to begin transaction for {self.alias()}: {e}")
            raise TrackError(e)

    async def commit_transaction_async(self) -> None:
        """Commit the current transaction."""
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot commit transaction: Event loop not valid for {self.alias()}")
            return
            
        if not self._async_conn or not self._tx_active:
            return
            
        try:
            async with self._async_conn.cursor() as cursor:
                # Make sure we're in the right database
                db_name = self.config().get("database")
                await cursor.execute(f"USE {db_name}")
                
                # Explicitly commit transaction
                await cursor.execute("COMMIT")
            
            await self._async_conn.autocommit(True)
            self._tx_active = False
            logger.debug(f"Async transaction committed for {self.alias()}")
        except Exception as e:
            logger.error(f"Error during commit for {self.alias()}: {e}")
            raise TrackError(e)

    async def rollback_transaction_async(self) -> None:
        """Rollback the current transaction."""
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot rollback transaction: Event loop not valid for {self.alias()}")
            return
            
        if not self._async_conn:
            logger.debug(f"No connection to roll back for {self.alias()}")
            return
            
        try:
            # Force a rollback regardless of transaction state tracking
            async with self._async_conn.cursor() as cursor:
                # Ensure we're in the right database
                db_name = self.config().get("database")
                await cursor.execute(f"USE {db_name}")
                
                # Always try a rollback
                await cursor.execute("ROLLBACK")
                
            # Reset state
            await self._async_conn.autocommit(True)
            self._tx_active = False
            logger.debug(f"Async transaction rolled back for {self.alias()}")
        except Exception as e:
            logger.error(f"Error during async rollback for {self.alias()}: {e}")

    async def _ensure_tables_exist_async(self, entity_name: str) -> None:
        """Override to create InnoDB tables for MySQL."""
        entity_name = self._sanitize_identifier(entity_name)
        
        # Check if we're in a transaction
        if self._tx_active:
            # Exit transaction to perform DDL operations
            logger.debug(f"Exiting async transaction to create tables")
            async with self._async_conn.cursor() as cursor:
                await cursor.execute("COMMIT")
            await self._async_conn.autocommit(True)
            self._tx_active = False
            
            # Create tables with InnoDB engine
            async with self._async_conn.cursor() as cursor:
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _meta_version (
                        entity_name VARCHAR(255) PRIMARY KEY,
                        version INTEGER
                    ) ENGINE=InnoDB
                """)
                
                await cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                        name VARCHAR(255),
                        type VARCHAR(255),
                        PRIMARY KEY (name)
                    ) ENGINE=InnoDB
                """)
                
                await cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {entity_name} (
                        id VARCHAR(255),
                        PRIMARY KEY (id)
                    ) ENGINE=InnoDB
                """)
            
            # Restart transaction
            await self._async_conn.autocommit(False)
            async with self._async_conn.cursor() as cursor:
                await cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                await cursor.execute("START TRANSACTION")
            self._tx_active = True
            logger.debug(f"Async transaction restarted after table creation")
        else:
            # Create tables with InnoDB engine outside of transaction
            async with self._async_conn.cursor() as cursor:
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _meta_version (
                        entity_name VARCHAR(255) PRIMARY KEY,
                        version INTEGER
                    ) ENGINE=InnoDB
                """)
                
                await cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                        name VARCHAR(255),
                        type VARCHAR(255),
                        PRIMARY KEY (name)
                    ) ENGINE=InnoDB
                """)
                
                await cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {entity_name} (
                        id VARCHAR(255),
                        PRIMARY KEY (id)
                    ) ENGINE=InnoDB
                """)

    async def execute_sql_async(self, sql: str, parameters=()) -> list:
        """Execute a SQL query and return results."""
        if not await self._is_event_loop_valid():
            raise TrackError(Exception(f"Cannot execute SQL: Event loop not valid for {self.alias()}"))
            
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
            
        try:
            async with self._async_conn.cursor() as cursor:
                # Make sure the right database is selected
                db_name = self.config().get("database")
                await cursor.execute(f"USE {db_name}")
                
                # Execute the query
                await cursor.execute(sql, parameters)
                if cursor.description:
                    return await cursor.fetchall()
                return []
        except Exception as e:
            logger.error(f"SQL execution error for {self.alias()}: {e}, SQL: {sql}")
            raise TrackError(e)

    async def executemany_sql_async(self, sql: str, parameters_list: list) -> None:
        """Execute a SQL query multiple times with different parameters."""
        if not await self._is_event_loop_valid():
            raise TrackError(Exception(f"Cannot execute SQL: Event loop not valid for {self.alias()}"))
            
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
            
        try:
            async with self._async_conn.cursor() as cursor:
                # Make sure the right database is selected
                db_name = self.config().get("database")
                await cursor.execute(f"USE {db_name}")
                
                # Execute the batch query
                await cursor.executemany(sql, parameters_list)
        except Exception as e:
            logger.error(f"SQL executemany error for {self.alias()}: {e}, SQL: {sql}")
            raise TrackError(e)

    async def _close_async(self) -> None:
        """Release connections to the pool, but don't close the pool itself."""
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot close connections: Event loop not valid for {self.alias()}")
            return
            
        try:
            # Handle transaction cleanup if needed
            if self._async_conn and self._tx_active:
                try:
                    async with self._async_conn.cursor() as cursor:
                        await cursor.execute("ROLLBACK")
                    await self._async_conn.autocommit(True)
                    self._tx_active = False
                except Exception as e:
                    logger.debug(f"Error rolling back transaction during close for {self.alias()}: {e}")
                
            # Handle regular connections
            if self._async_conn and MySqlDatabase._pool:
                try:
                    await MySqlDatabase._pool.release(self._async_conn)
                    logger.debug(f"{self.alias()} async database connection released")
                except Exception as e:
                    logger.debug(f"Error releasing connection for {self.alias()}: {e}")
                self._async_conn = None
            
            logger.debug(f"{self.alias()} async database closed")
        except Exception as e:
            logger.debug(f"Error during async connection cleanup for {self.alias()}: {e}")

    async def clear_all_async(self) -> None:
        """Reset the database to a clean state."""
        # Skip if event loop is not valid
        if not await self._is_event_loop_valid():
            logger.debug(f"{self.alias()} not cleared: event loop not valid")
            return
                
        try:
            # Make sure we have a connection
            if not await self._init_async():
                logger.debug(f"Cannot clear database {self.alias()}: connection initialization failed")
                return
                
            # Clean up any existing transactions
            if self._tx_active:
                try:
                    async with self._async_conn.cursor() as cursor:
                        await cursor.execute("ROLLBACK")
                    await self._async_conn.autocommit(True)
                    self._tx_active = False
                except Exception as e:
                    logger.debug(f"Error rolling back transaction during cleanup for {self.alias()}: {e}")
            
            # Get all tables and drop them
            async with self._async_conn.cursor() as cursor:
                # Make sure we're in the right database
                db_name = self.config().get("database")
                await cursor.execute(f"USE {db_name}")
                
                # Get list of tables
                await cursor.execute("SHOW TABLES")
                tables = [row[0] for row in await cursor.fetchall()]
                
                # Drop each table
                for table in tables:
                    await cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
                
                # Create required meta tables
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS _meta_version (
                        entity_name VARCHAR(255) PRIMARY KEY,
                        version INTEGER
                    ) ENGINE=InnoDB
                ''')
                
            logger.debug(f"Cleared database {self.alias()}")
        except Exception as e:
            logger.error(f"Failed to clear database {self.alias()}: {e}")
            raise TrackError(e)
            
    @classmethod
    async def close_pool(cls):
        """Close the shared connection pool."""
        try:
            if cls._pool:
                try:
                    cls._pool.close()
                    await cls._pool.wait_closed()
                    logger.info("MySQL connection pool closed")
                except Exception as e:
                    logger.error(f"Error closing MySQL connection pool: {e}")
                finally:
                    cls._pool = None
        except Exception as e:
            logger.error(f"Error in close_pool: {e}")