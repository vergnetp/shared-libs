from typing import Tuple, Any, List, Optional
import asyncio
import psycopg2
import asyncpg
from ..errors import TrackError
from ..log import logging as logger
from .base import Database

class PostgresDatabase(Database):
    _pool: Optional[asyncpg.Pool] = None 
    _pool_lock = asyncio.Lock()
    
    def __init__(self, database: str, host: str=None, port: int=None, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod'):
        super().__init__(database, host, port, user, password, alias, env)   

        # Sync connection setup
        cfg = self.config().copy()
        cfg["dbname"] = cfg.pop("database")
        self._conn = psycopg2.connect(**cfg)
        self._conn.autocommit = True
        self._conn.set_session(isolation_level='REPEATABLE READ')
        
        self._cursor = self._conn.cursor()
        self._cursor.execute("CREATE SCHEMA IF NOT EXISTS public")
        self._cursor.execute("SET search_path TO public")
        self._conn.autocommit = False

        # Async connection setup
        self._async_conn = None
        self._async_tx = None
        self._tx_active = False
        self._tx_id = 0

    def is_connected(self) -> bool:
        try:
            self._cursor.execute("SELECT 1")
            return True
        except:
            return False

    def type(self) -> str:
        return "postgres"

    def placeholder(self, is_async: bool=True) -> str:
        return '$1' if is_async else "%s"

    # --- Sync methods ---
    def begin_transaction(self) -> None:
        if self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            self._conn.rollback()
        
        self._conn.autocommit = False
        self._cursor.execute("SELECT 1")
        self._cursor.execute("SET search_path TO public")
        
    def commit_transaction(self) -> None:
        self._conn.commit()

    def rollback_transaction(self) -> None:
        if self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            self._conn.rollback()

    def execute_sql(self, sql: str, parameters: Tuple[Any, ...] = ()) -> list:
        if not self.is_connected():
            raise TrackError(Exception("Lost Postgres connection"))
        try:
            self._cursor.execute("SET search_path TO public")
            self._cursor.execute(sql, parameters)
            return self._cursor.fetchall() if self._cursor.description else []
        except Exception as e:
            logger.error(f"SQL execution error: {e}, SQL: {sql}, Parameters: {parameters}")
            raise TrackError(e)

    def executemany_sql(self, sql: str, parameters_list: List[Tuple[Any, ...]]) -> None:
        if not self.is_connected():
            raise TrackError(Exception("Lost Postgres connection"))
        try:
            self._cursor.execute("SET search_path TO public")
            self._cursor.executemany(sql, parameters_list)
        except Exception as e:
            logger.error(f"SQL executemany error: {e}, SQL: {sql}")
            raise TrackError(e)

    def _close(self) -> None:
        try:
            if self._cursor:
                self._cursor.close()
            if self._conn:
                self._conn.close()
        except Exception as e:
            logger.debug(f"Error closing synchronous connection: {e}")

    def clear_all(self) -> None:
        try:
            self._conn.rollback()
            original_autocommit = self._conn.autocommit
            self._conn.autocommit = True
            
            self._cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'public'")
            if self._cursor.fetchone():
                self._cursor.execute('DROP SCHEMA public CASCADE')
                
            self._cursor.execute('CREATE SCHEMA public')
            self._cursor.execute('SET search_path TO public')
            self._conn.autocommit = original_autocommit
            logger.debug(f"Cleared database {self.alias()}")
        except Exception as e:
            try:
                self._conn.autocommit = original_autocommit
            except:
                pass
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
        """Initialize async connections for the database."""
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
        """Start a new transaction."""
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
            # Clean up any existing transaction
            if self._async_tx:
                await self.rollback_transaction_async()
                
            # Get a new transaction connection
            self._tx_id += 1
            try:
                self._async_tx = await PostgresDatabase._pool.acquire()
                
                await self._async_tx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                await self._async_tx.execute("BEGIN")
                self._tx_active = True
                await self._async_tx.execute("SET search_path TO public")
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
        """Commit the current transaction."""
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot commit transaction: Event loop not valid for {self.alias()}")
            return
            
        if not self._async_tx:
            return
            
        try:
            await self._async_tx.execute("COMMIT")
            self._tx_active = False
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
        """Rollback the current transaction."""
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot rollback transaction: Event loop not valid for {self.alias()}")
            return
            
        if not self._async_tx:
            return
            
        try:
            await self._async_tx.execute("ROLLBACK")
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
            self._tx_active = False

    async def execute_sql_async(self, sql: str, parameters: Tuple[Any, ...] = ()) -> list:
        """Execute a SQL query and return results."""
        if not await self._is_event_loop_valid():
            raise TrackError(Exception(f"Cannot execute SQL: Event loop not valid for {self.alias()}"))
            
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
            
        try:
            parameters = list(parameters) if parameters else []
            conn = self._async_tx if self._async_tx else self._async_conn
            
            await conn.execute('SET search_path TO public')
            return await conn.fetch(sql, *parameters)
        except Exception as e:
            logger.error(f"SQL execution error for {self.alias()}: {e}, SQL: {sql}")
            raise TrackError(e)

    async def executemany_sql_async(self, sql: str, parameters_list: List[Tuple[Any, ...]]) -> None:
        """Execute a SQL query multiple times with different parameters."""
        if not await self._is_event_loop_valid():
            raise TrackError(Exception(f"Cannot execute SQL: Event loop not valid for {self.alias()}"))
            
        if not await self._init_async():
            raise TrackError(Exception(f"Failed to initialize async connection for {self.alias()}"))
            
        try:
            conn = self._async_tx if self._async_tx else self._async_conn
            await conn.execute('SET search_path TO public')
            
            for params in parameters_list:
                params = list(params) if params else []
                await conn.execute(sql, *params)
        except Exception as e:
            logger.error(f"SQL executemany async error for {self.alias()}: {e}, SQL: {sql}")
            raise TrackError(e)

    async def _close_async(self) -> None:
        """Release connections to the pool, but don't close the pool itself."""
        if not await self._is_event_loop_valid():
            logger.debug(f"Cannot close connections: Event loop not valid for {self.alias()}")
            return
            
        try:
            # Handle transaction connections
            if self._async_tx:
                try:
                    if self._tx_active:
                        await self._async_tx.execute("ROLLBACK")
                    if PostgresDatabase._pool:
                        await PostgresDatabase._pool.release(self._async_tx)
                except Exception as e:
                    logger.debug(f"Error releasing transaction connection for {self.alias()}: {e}")
                finally:
                    self._async_tx = None
                    self._tx_active = False
                
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
        """Reset the database to a clean state."""
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
                try:
                    exists = await self._async_conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'public')"
                    )
                    
                    if exists:
                        await self._async_conn.execute('DROP SCHEMA public CASCADE')
                        
                    await self._async_conn.execute('CREATE SCHEMA public')
                    await self._async_conn.execute('SET search_path TO public')
                    logger.debug(f"Cleared database {self.alias()}")
                except Exception as e:
                    logger.debug(f"Error resetting schema for {self.alias()}: {e}")
                    
            self._tx_active = False  
        except Exception as e:
            logger.error(f"Failed to clear database {self.alias()}: {e}")
            
    @classmethod
    async def close_pool(cls):
        """Close the shared connection pool."""
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