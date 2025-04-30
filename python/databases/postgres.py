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
           
            logger.info(f"Successfully connected to PostgreSQL database {database}")
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL database {database}: {e}")
            raise TrackError(e)

        # Async connection setup (initialize on demand)
        self._async_conn = None 

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
    def begin_transaction_real(self) -> None:
        try:
            if self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                self._conn.rollback()
            self._cursor.execute("SET search_path TO public")
            self._cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            self._cursor.execute("BEGIN")
            logger.debug(f"Postgres Transaction started for {self.alias()}")
        except Exception as e:
            logger.error(f"Error beginning Postgres transaction for {self.alias()}: {e}")
            raise TrackError(e)
        
    def commit_transaction_real(self) -> None:
        try:
            self._conn.commit()           
            logger.debug(f"Postgres transaction committed for {self.alias()}")
        except Exception as e:
            logger.error(f"Error committing Postgres transaction for {self.alias()}: {e}")
            raise TrackError(e)

    def rollback_transaction_real(self) -> None:
        try:
            self._conn.rollback()           
            logger.debug(f"Postgres transaction rolled back for {self.alias()}")
        except Exception as e:
            logger.error(f"Error rolling back Postgres transaction for {self.alias()}: {e}")
            raise TrackError(e)

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
            self._conn.reset()  # Try resetting instead of failing outright
            self._cursor = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
        try:
            logger.debug(f"Postgres SQL: {sql}, Parameters: {parameters}")
            self._cursor.execute("SET search_path TO public")
            self._cursor.execute(sql, parameters)
            return self._cursor.fetchall() if self._cursor.description else []
        except Exception as e:
            logger.error(f"Postgres SQL execution error: {e}, SQL: {sql}, Parameters: {parameters}")
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
            logger.debug(f"Postgres SQL: {sql}, Parameters: many")
            self._cursor.execute("SET search_path TO public")
            self._cursor.executemany(sql, parameters_list)
        except Exception as e:
            logger.error(f"SQL executemany error: {e}, SQL: {sql}")
            raise TrackError(e)

    def _close(self) -> None:
        """Close the synchronous database connection."""
        try:
            # Close any active transaction           
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

    async def begin_transaction_real_async(self) -> None:
        # Skip if event loop is not valid
        if not await self._is_event_loop_valid():
            raise TrackError(Exception("Cannot begin transaction: Event loop is not valid"))
            
        # Ensure we have a valid connection
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
        
        try:
            await self._async_conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            await self._async_conn.execute("BEGIN")
            await self._async_conn.execute("SET search_path TO public")
        except Exception as e:
            logger.error(f"Failed to begin transaction for {self.alias()}: {e}")
            raise TrackError(e)

    async def commit_transaction_real_async(self) -> None:
        # Skip if event loop is not valid
        if not await self._is_event_loop_valid():
            raise TrackError(Exception("Cannot begin transaction: Event loop is not valid"))
            
        # Ensure we have a valid connection
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
        
        try:  
            await self._async_conn.execute("COMMIT")
        except Exception as e:
            logger.error(f"Failed to begin transaction for {self.alias()}: {e}")
            raise TrackError(e)

    async def rollback_transaction_real_async(self) -> None:
        # Skip if event loop is not valid
        if not await self._is_event_loop_valid():
            raise TrackError(Exception("Cannot begin transaction: Event loop is not valid"))
            
        # Ensure we have a valid connection
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
        
        try:
            await self._async_conn.execute("ROLLBACK")
        except Exception as e:
            logger.error(f"Failed to begin transaction for {self.alias()}: {e}")
            raise TrackError(e)

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
            conn = self._async_conn
            
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
            conn = self._async_conn
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