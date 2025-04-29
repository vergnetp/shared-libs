import asyncio
import uuid
from typing import Tuple, Any, List, Optional, Dict
import psycopg2
import psycopg2.extras
import asyncpg
from ..errors import TrackError
from ..log import logging as logger
from .base import Database

class PostgresDatabase(Database):
    """PostgreSQL database implementation supporting both sync and async operations."""
    
    # Class-level shared connection pool
    _pool: Optional[asyncpg.Pool] = None 
    _pool_lock = asyncio.Lock()
    
    def __init__(self, database: str, host: str="localhost", port: int=5432, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod', **kwargs):
        """
        Initialize a PostgreSQL database connection.
        
        Args:
            database: Database name
            host: Database server hostname
            port: Database server port
            user: Username for authentication
            password: Password for authentication
            alias: Friendly name for this database connection
            env: Environment name (prod, dev, test)
            **kwargs: Additional connection parameters
        """
        super().__init__(database, host, port, user, password, alias, env)   

        # Sync connection setup
        cfg = self.config().copy()
        cfg["dbname"] = cfg.pop("database")  # psycopg2 uses dbname instead of database
        
        # Add additional kwargs
        cfg.update(kwargs)
        
        try:
            # Initialize synchronous connection
            self._conn = psycopg2.connect(**cfg)
            self._conn.autocommit = True  # Start with autocommit mode
            
            # Use DictCursor for easier column access
            self._cursor = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Set schema and isolation level
            self._cursor.execute("CREATE SCHEMA IF NOT EXISTS public")
            self._cursor.execute("SET search_path TO public")
            self._conn.set_session(isolation_level='REPEATABLE READ')
            
            # Turn off autocommit for transaction control
            self._conn.autocommit = False
            
            # Transaction state tracking
            self._sync_tx_active = False
            
            logger.info(f"Successfully connected to PostgreSQL database {database}")
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL database {database}: {e}")
            raise TrackError(e)

        # Async connection setup (initialize on demand)
        self._async_conn = None
        self._async_tx = None
        self._async_tx_active = False
        self._tx_id = 0

    def is_connected(self) -> bool:
        """
        Check if the database connection is active.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            self._cursor.execute("SELECT 1")
            return True
        except Exception:
            return False

    def type(self) -> str:
        """
        Get the database type.
        
        Returns:
            'postgres'
        """
        return "postgres"

    def placeholder(self, is_async: bool=True) -> str:
        """
        Get the parameter placeholder for PostgreSQL.
        
        Args:
            is_async: Whether this is for async operations
            
        Returns:
            '$1' for async queries, '%s' for sync queries
        """
        return '$1' if is_async else "%s"

    # --- Sync methods ---
    def begin_transaction(self) -> None:
        """Begin a new transaction."""
        if self._sync_tx_active:
            logger.debug(f"Transaction already active for {self.alias()}")
            return
            
        # If there's an existing transaction in wrong state, roll it back
        if self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            self._conn.rollback()
        
        # Set isolation level and start transaction
        self._cursor.execute("SET search_path TO public")
        self._cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        self._sync_tx_active = True
        logger.debug(f"Transaction started for {self.alias()}")
        
    def commit_transaction(self) -> None:
        """Commit the current transaction."""
        if not self._sync_tx_active:
            return
            
        try:
            self._conn.commit()
            self._sync_tx_active = False
            logger.debug(f"Transaction committed for {self.alias()}")
        except Exception as e:
            logger.error(f"Error committing transaction for {self.alias()}: {e}")
            raise TrackError(e)

    def rollback_transaction(self) -> None:
        """Roll back the current transaction."""
        if not self._sync_tx_active:
            return
            
        try:
            self._conn.rollback()
            self._sync_tx_active = False
            logger.debug(f"Transaction rolled back for {self.alias()}")
        except Exception as e:
            logger.error(f"Error rolling back transaction for {self.alias()}: {e}")

    def execute_sql(self, sql: str, parameters: Tuple[Any, ...] = ()) -> list:
        """
        Execute a SQL query with parameters.
        
        Args:
            sql: SQL query
            parameters: Query parameters
            
        Returns:
            List of rows
            
        Raises:
            TrackError: On database errors
        """
        if not self.is_connected():
            raise TrackError(Exception("Lost PostgreSQL connection"))
            
        try:
            self._cursor.execute("SET search_path TO public")
            self._cursor.execute(sql, parameters)
            return self._cursor.fetchall() if self._cursor.description else []
        except Exception as e:
            logger.error(f"SQL execution error: {e}, SQL: {sql}, Parameters: {parameters}")
            raise TrackError(e)

    def executemany_sql(self, sql: str, parameters_list: List[Tuple[Any, ...]]) -> None:
        """
        Execute a SQL query multiple times with different parameters.
        
        Args:
            sql: SQL query
            parameters_list: List of parameter tuples
            
        Raises:
            TrackError: On database errors
        """
        if not self.is_connected():
            raise TrackError(Exception("Lost PostgreSQL connection"))
            
        try:
            self._cursor.execute("SET search_path TO public")
            self._cursor.executemany(sql, parameters_list)
        except Exception as e:
            logger.error(f"SQL executemany error: {e}, SQL: {sql}")
            raise TrackError(e)

    def _close(self) -> None:
        """Close the synchronous database connection."""
        try:
            # Close any active transaction
            if self._sync_tx_active:
                try:
                    self.rollback_transaction()
                except Exception:
                    pass
                    
            if self._cursor:
                self._cursor.close()
                self._cursor = None
                
            if self._conn:
                self._conn.close()
                self._conn = None
                
            self._sync_tx_active = False
            logger.debug(f"{self.alias()} database closed")
        except Exception as e:
            logger.debug(f"Error closing synchronous connection: {e}")

    def clear_all(self) -> None:
        """
        Clear all data in the database.

        Raises:
            TrackError: On database errors
        """
        try:
            # Roll back any existing transaction
            if self._sync_tx_active:
                try:
                    self.rollback_transaction()
                except Exception:
                    pass

            try:
                # If transaction still somehow active, force rollback
                if self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                    self._conn.rollback()

                original_autocommit = self._conn.autocommit
                self._conn.autocommit = True
           
                # Now safe to change search_path or drop schema
                self._cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'public'")
                if self._cursor.fetchone():
                    self._cursor.execute('DROP SCHEMA public CASCADE')

                self._cursor.execute('CREATE SCHEMA public')
                self._cursor.execute('SET search_path TO public')
            except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
                logger.debug(f"Ignored expected connection error during clear_all(): {e}")
                return

            # Restore original autocommit setting
            self._conn.autocommit = original_autocommit
            logger.debug(f"Cleared database {self.alias()}")
        except Exception as e:
            # Restore autocommit if possible
            try:
                self._conn.autocommit = original_autocommit
            except:
                pass

            logger.error(f"Failed to clear database {self.alias()}: {e}")
            raise TrackError(e)


    # --- Async methods ---
    async def _is_event_loop_valid(self):
        """
        Check if the current event loop is valid for async operations.
        
        Returns:
            True if valid, False otherwise
        """
        try:
            loop = asyncio.get_running_loop()
            return not loop.is_closed()
        except RuntimeError:
            return False

    @classmethod
    async def initialize_pool_if_needed(cls, config):
        """
        Initialize the connection pool if it doesn't exist.
        
        Args:
            config: Connection configuration
            
        Raises:
            Exception: On pool initialization errors
        """
        # First, check if existing pool is usable
        if cls._pool:
            try:
                # Test if pool is still operational
                async with cls._pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                return  # Pool is working, nothing to do
            except Exception as e:
                logger.debug(f"Existing pool is not usable: {e}")
                # Continue to recreate pool
                try:
                    await cls._pool.close()
                except Exception:
                    pass
                cls._pool = None
        
        # Create a new pool
        try:
            async with cls._pool_lock:
                if cls._pool is None:
                    cls._pool = await asyncpg.create_pool(
                        min_size=1,
                        max_size=10,
                        command_timeout=60.0,
                        **config
                    )
                    logger.info("PostgreSQL connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection pool: {e}")
            cls._pool = None
            raise

    async def _init_async(self):
        """
        Initialize async connections for the database.
        
        Returns:
            True if successful, False otherwise
        """
        # Verify event loop is usable
        if not await self._is_event_loop_valid():
            logger.debug(f"Event loop is not valid for {self.alias()}")
            return False
                
        try:
            # Initialize/verify pool
            if PostgresDatabase._pool is None:
                await self.initialize_pool_if_needed(self.config())
            
            # Test pool if it exists
            if PostgresDatabase._pool is None:
                logger.error(f"Failed to create pool for {self.alias()}")
                return False
                
            # Get a connection if we don't have one
            if self._async_conn is None:
                try:
                    self._async_conn = await PostgresDatabase._pool.acquire()
                    await self._async_conn.execute('CREATE SCHEMA IF NOT EXISTS public')
                    await self._async_conn.execute('SET search_path TO public')
                except Exception as e:
                    logger.error(f"Error acquiring connection for {self.alias()}: {e}")
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Error initializing async connection for {self.alias()}: {e}")
            return False

    async def begin_transaction_async(self) -> None:
        """Begin a new transaction asynchronously."""
        # Skip if event loop is not valid
        if not await self._is_event_loop_valid():
            raise TrackError(Exception("Cannot begin transaction: Event loop is not valid"))
            
        # Ensure we have a valid connection
        if not await self._init_async():
            # Try one more time with a fresh pool
            if PostgresDatabase._pool:
                try:
                    await PostgresDatabase._pool.close()
                except Exception:
                    pass
                PostgresDatabase._pool = None
                
            if not await self._init_async():
                raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
        
        try:
            # Skip if transaction already active
            if self._async_tx_active:
                logger.debug(f"Async transaction already active for {self.alias()}")
                return
                
            # Clean up any existing transaction
            if self._async_tx:
                await self.rollback_transaction_async()
                
            # Get a new transaction connection
            self._tx_id += 1
            try:
                self._async_tx = await PostgresDatabase._pool.acquire()
                
                await self._async_tx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                await self._async_tx.execute("BEGIN")
                self._async_tx_active = True
                await self._async_tx.execute("SET search_path TO public")
                
                logger.debug(f"Async transaction started for {self.alias()}")
            except Exception as e:
                # Handle failed transaction setup
                if self._async_tx:
                    try:
                        await PostgresDatabase._pool.release(self._async_tx)
                    except Exception as release_error:
                        logger.debug(f"Failed to release transaction connection: {release_error}")
                    self._async_tx = None
                raise e
        except Exception as e:
            logger.error(f"Failed to begin transaction for {self.alias()}: {e}")
            raise TrackError(e)

    async def commit_transaction_async(self) -> None:
        """Commit the current transaction asynchronously."""
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot commit transaction: Event loop not valid for {self.alias()}")
            return
            
        if not self._async_tx or not self._async_tx_active:
            return
            
        try:
            await self._async_tx.execute("COMMIT")
            self._async_tx_active = False
            logger.debug(f"Async transaction committed for {self.alias()}")
        except Exception as e:
            logger.error(f"Error during commit for {self.alias()}: {e}")
            raise TrackError(e)
        finally:
            # Always release transaction connection
            if self._async_tx and PostgresDatabase._pool:
                try:
                    await PostgresDatabase._pool.release(self._async_tx)
                except Exception as e:
                    logger.debug(f"Error releasing transaction connection for {self.alias()}: {e}")
            self._async_tx = None

    async def rollback_transaction_async(self) -> None:
        """Roll back the current transaction asynchronously."""
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot rollback transaction: Event loop not valid for {self.alias()}")
            return
            
        if not self._async_tx:
            return
            
        try:
            if self._async_tx_active:
                await self._async_tx.execute("ROLLBACK")
                self._async_tx_active = False
                logger.debug(f"Async transaction rolled back for {self.alias()}")
        except Exception as e:
            logger.debug(f"Error during rollback for {self.alias()}: {e}")
        finally:
            # Always clean up resources
            if self._async_tx and PostgresDatabase._pool:
                try:
                    await PostgresDatabase._pool.release(self._async_tx)
                except Exception as e:
                    logger.debug(f"Error releasing transaction connection for {self.alias()}: {e}")
            self._async_tx = None

    async def _ensure_tables_exist_async(self, entity_name: str) -> None:
        """
        Override to create tables for PostgreSQL asynchronously.
        
        Args:
            entity_name: Name of the entity
            
        Raises:
            TrackError: On database errors
        """
        entity_name = self._sanitize_identifier(entity_name)
        
        # Set connection for operation
        conn = self._async_tx if self._async_tx_active else self._async_conn
        
        # Check if we're in a transaction
        if self._async_tx_active:
            # Exit transaction to perform DDL operations
            logger.debug(f"Exiting async transaction to create tables")
            await self._async_tx.execute("COMMIT")
            self._async_tx_active = False
            
            # Create tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS _meta_version (
                    entity_name VARCHAR(255) PRIMARY KEY,
                    version INTEGER
                )
            """)
            
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                    name VARCHAR(255),
                    type VARCHAR(255),
                    PRIMARY KEY (name)
                )
            """)
            
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_name} (
                    id VARCHAR(255),
                    PRIMARY KEY (id)
                )
            """)
            
            # Restart transaction
            await self._async_tx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            await self._async_tx.execute("BEGIN")
            self._async_tx_active = True
            await self._async_tx.execute("SET search_path TO public")
            logger.debug(f"Async transaction restarted after table creation")
        else:
            # Create tables outside of transaction
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS _meta_version (
                    entity_name VARCHAR(255) PRIMARY KEY,
                    version INTEGER
                )
            """)
            
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                    name VARCHAR(255),
                    type VARCHAR(255),
                    PRIMARY KEY (name)
                )
            """)
            
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_name} (
                    id VARCHAR(255),
                    PRIMARY KEY (id)
                )
            """)

    async def execute_sql_async(self, sql: str, parameters: Tuple[Any, ...] = ()) -> list:
        """
        Execute a SQL query and return results asynchronously.
        
        Args:
            sql: SQL query
            parameters: Query parameters
            
        Returns:
            List of rows
            
        Raises:
            TrackError: On database errors
        """
        if not await self._is_event_loop_valid():
            raise TrackError(Exception(f"Cannot execute SQL: Event loop not valid for {self.alias()}"))
            
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
            
        try:
            # Convert parameters to list for asyncpg
            parameters = list(parameters) if parameters else []
            
            # Use transaction connection if in transaction
            conn = self._async_tx if self._async_tx_active else self._async_conn
            
            # Ensure proper schema
            await conn.execute('SET search_path TO public')
            
            # Add UUID comment for query cache busting in PostgreSQL
            if not sql.endswith("-- " + str(uuid.uuid4())):
                sql += f" -- {uuid.uuid4()}"
                
            return await conn.fetch(sql, *parameters)
        except Exception as e:
            logger.error(f"SQL execution error for {self.alias()}: {e}, SQL: {sql}")
            raise TrackError(e)

    async def executemany_sql_async(self, sql: str, parameters_list: List[Tuple[Any, ...]]) -> None:
        """
        Execute a SQL query multiple times with different parameters asynchronously.
        
        Args:
            sql: SQL query
            parameters_list: List of parameter tuples
            
        Raises:
            TrackError: On database errors
        """
        if not await self._is_event_loop_valid():
            raise TrackError(Exception(f"Cannot execute SQL: Event loop not valid for {self.alias()}"))
            
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
            
        try:
            # Use transaction connection if in transaction
            conn = self._async_tx if self._async_tx_active else self._async_conn
            await conn.execute('SET search_path TO public')
            
            # Add UUID comment for query cache busting in PostgreSQL
            if not sql.endswith("-- " + str(uuid.uuid4())):
                sql += f" -- {uuid.uuid4()}"
            
            # Execute each set of parameters
            for params in parameters_list:
                params = list(params) if params else []
                await conn.execute(sql, *params)
        except Exception as e:
            logger.error(f"SQL executemany async error for {self.alias()}: {e}, SQL: {sql}")
            raise TrackError(e)

    async def _close_async(self) -> None:
        """
        Release connections to the pool, but don't close the pool itself.
        """
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot close connections: Event loop not valid for {self.alias()}")
            return
            
        try:
            # Handle transaction connections
            if self._async_tx:
                try:
                    if self._async_tx_active:
                        await self._async_tx.execute("ROLLBACK")
                        self._async_tx_active = False
                    if PostgresDatabase._pool:
                        await PostgresDatabase._pool.release(self._async_tx)
                except Exception as e:
                    logger.debug(f"Error releasing transaction connection for {self.alias()}: {e}")
                finally:
                    self._async_tx = None
                
            # Handle regular connections
            if self._async_conn and PostgresDatabase._pool:
                try:
                    await PostgresDatabase._pool.release(self._async_conn)
                    logger.debug(f"{self.alias()} async database connection released")
                except Exception as e:
                    logger.debug(f"Error releasing connection for {self.alias()}: {e}")
                self._async_conn = None
            
            logger.debug(f"{self.alias()} async database closed")
        except Exception as e:
            logger.debug(f"Error during async connection cleanup for {self.alias()}: {e}")

    async def clear_all_async(self) -> None:
        """
        Reset the database to a clean state asynchronously.
        
        Raises:
            TrackError: On database errors
        """
        # Skip if event loop is not valid
        if not await self._is_event_loop_valid():
            logger.debug(f"{self.alias()} not cleared: event loop not valid")
            return
                
        try:
            # Clean up any existing transactions
            if self._async_tx:
                try:
                    await self.rollback_transaction_async()
                except Exception as e:
                    logger.debug(f"Error rolling back transaction during cleanup: {e}")
            
            # Only proceed if we can get a connection
            if await self._init_async():
                # Check if public schema exists
                exists = await self._async_conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'public')"
                )
                
                # Drop and recreate schema
                if exists:
                    await self._async_conn.execute("""
                        DO $$
                        DECLARE
                            r RECORD;
                        BEGIN
                            FOR r IN (SELECT pid FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid())
                            LOOP
                                EXECUTE 'SELECT pg_terminate_backend(' || r.pid || ')';
                            END LOOP;
                        END;
                        $$;
                    """)
                    await self._async_conn.execute('DROP SCHEMA public CASCADE')
                    
                await self._async_conn.execute('CREATE SCHEMA public')
                await self._async_conn.execute('SET search_path TO public')
                logger.debug(f"Cleared database {self.alias()}")
        except Exception as e:
            logger.error(f"Failed to clear database {self.alias()}: {e}")
            raise TrackError(e)
            
    @classmethod
    async def close_pool(cls):
        """
        Close the shared connection pool.
        
        This should be called at application shutdown.
        """
        try:
            if cls._pool:
                try:
                    await cls._pool.close()
                    logger.info("PostgreSQL connection pool closed")
                except Exception as e:
                    logger.error(f"Error closing PostgreSQL connection pool: {e}")
                finally:
                    cls._pool = None
        except Exception as e:
            logger.error(f"Error in close_pool: {e}")