import threading
import itertools
import asyncio
from typing import Dict, Any, Optional
import psycopg2
import asyncpg

from ...resilience import retry_with_backoff
from ...utils import async_method
from ... import log as logger

from ..sql import SqlGenerator
from ..config import DatabaseConfig
from ..connections import ConnectionManager, SyncConnection, AsyncConnection, ConnectionPool, PoolManager
from ..entity import PostgresSqlGenerator # todo: incorrect place

class PostgresSyncConnection(SyncConnection):
    """
    PostgreSQL implementation of the SyncConnection interface.
    
    This class wraps a raw psycopg2 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw psycopg2 connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)   
        logger.debug("postgres init")     
        self._cursor = self._conn.cursor()       
        self._prepared_counter = self.ThreadSafeCounter()
        self._sql_generator = None

    class ThreadSafeCounter:
        def __init__(self, start=0, step=1):
            self.counter = itertools.count(start, step)
            self.lock = threading.Lock()
            
        def next(self):
            with self.lock:
                return next(self.counter)
        
    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the PostgreSQL parameter converter."""
        if not  self._sql_generator:
            self._sql_generator = PostgresSqlGenerator(False)
        return  self._sql_generator
    
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """Prepare a statement using psycopg2"""
        logger.debug("postgres _prepare_statement") 
        stmt_name = f"prep_{self._prepared_counter.next()}" 
        
        # Prepare the statement
        self._cursor.execute(f"PREPARE {stmt_name} AS {native_sql}")
        return stmt_name
    
    @retry_with_backoff(
        max_retries=3, 
        exceptions=(
            psycopg2.OperationalError,
            psycopg2.InterfaceError,
            psycopg2.InternalError
        )
    )
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using psycopg2"""
        try:           
            # Handle the empty parameters case properly
            if not params or len(params) == 0:
                self._cursor.execute(f"EXECUTE {statement}")
            else:
                placeholders = ','.join(['?'] * len(params))
                self._cursor.execute(f"EXECUTE {statement} ({placeholders})", params)
                
            return self._cursor.fetchall()  # Return raw results
        except Exception as e:
            logger.error(f"Error executing statement: {e}")
            raise
  
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        Note:
            In psycopg2, transactions are started implicitly with the first query,
            so this method is a no-op for compatibility.
        """
        # psycopg2 starts transaction implicitly on execute
        pass

    def commit_transaction(self):
        """
        Commits the current transaction.
        
        This permanently applies all changes made since the transaction began.
        """
        self._conn.commit()

    def rollback_transaction(self):
        """
        Rolls back the current transaction.
        
        This discards all changes made since the transaction began.
        """
        self._conn.rollback()

    def close(self):
        """
        Closes the database connection and cursor.
        
        This releases all resources used by the connection. The connection
        should not be used after calling this method.
        """
        self._cursor.close()
        self._conn.close()
    
    def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        cursor = self._conn.cursor()
        cursor.execute("SHOW server_version;")
        server_version = cursor.fetchone()[0]

        import psycopg2
        driver_version = f"psycopg2 {psycopg2.__version__}"

        return {           
            "db_server_version": server_version,
            "db_driver": driver_version
        }

class PostgresAsyncConnection(AsyncConnection):
    """
    PostgreSQL implementation of the AsyncConnection interface.
    
    This class wraps a raw asyncpg connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw asyncpg connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)        
        self._tx = None 
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the PostgreSQL parameter converter."""
        if not  self._sql_generator:
            self._sql_generator = PostgresSqlGenerator(True)
        return  self._sql_generator

    @retry_with_backoff(
        exceptions=(
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            asyncpg.exceptions.ConnectionFailureError
        )
    )
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """Prepare a statement using asyncpg"""
        try:
            return await self._conn.prepare(native_sql)
        except Exception as e:
            logger.error(f'Error while Postgres async driver tried to prepare this: {native_sql}: {e}')
            raise

    
    @retry_with_backoff(
        exceptions=(
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            asyncpg.exceptions.TooManyConnectionsError,
            asyncpg.exceptions.ConnectionFailureError
        )
    )
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using asyncpg"""
        return await statement.fetch(*(params or []))
    
    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""       
        return self._conn.is_in_transaction()

    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        if self._tx is None:
            self._tx = self._conn.transaction()
            await self._tx.start()

    @async_method
    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.commit()
            self._tx = None

    @async_method
    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.rollback()
            self._tx = None

    @async_method
    async def close(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

    @async_method
    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        version_tuple = self._conn.get_server_version()
        server_version = ".".join(str(v) for v in version_tuple[:2])

        import asyncpg
        driver_version = f"asyncpg {asyncpg.__version__}"

        return {      
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    
class PostgresConnectionPool(ConnectionPool):
    """
    PostgreSQL implementation of ConnectionPool using asyncpg.
    
    This class wraps asyncpg's connection pool to provide a standardized interface
    and additional functionality for connection management.
    
    Attributes:
        _pool: The underlying asyncpg pool
        _timeout: Default timeout for connection acquisition
    """
    
    def __init__(self, pool, timeout: float = 10.0):
        """
        Initialize a PostgreSQL connection pool wrapper.
        
        Args:
            pool: The underlying asyncpg pool
            timeout: Default timeout for connection acquisition in seconds
        """
        self._pool = pool
        self._timeout = timeout        
       
    @async_method
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires a connection from the pool with timeout.
        
        Args:
            timeout: Maximum time to wait for connection, defaults to pool default
            
        Returns:
            The raw asyncpg connection
            
        Raises:
            TimeoutError: If connection acquisition times out
        """
        timeout = timeout if timeout is not None else self._timeout
        try:
            return await asyncio.wait_for(self._pool.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for PostgreSQL connection after {timeout}s")
    
    @async_method
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The asyncpg connection to release
        """
        await self._pool.release(connection)
    
    @async_method
    async def close(self, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:
           
            timeout: Maximum time to wait for graceful shutdown 
        """
        await self._pool.close()
    

    async def _test_connection(self, connection):
        await connection.execute("SELECT 1")

    
    @property
    def min_size(self) -> int:
        """Gets the minimum number of connections the pool maintains."""
        return self._pool._minsize
    
    @property
    def max_size(self) -> int:
        """Gets the maximum number of connections the pool can create."""
        return self._pool._maxsize
    
    @property
    def size(self) -> int:
        """Gets the current number of connections in the pool."""
        return len(self._pool._holders)
    
    @property
    def in_use(self) -> int:
        """Gets the number of connections currently in use."""
        return len([h for h in self._pool._holders if h._in_use])
    
    @property
    def idle(self) -> int:
        """Gets the number of idle connections in the pool."""
        return len([h for h in self._pool._holders if not h._in_use])

class PostgresPoolManager(PoolManager):
    async def _create_pool(self, config: DatabaseConfig, connection_acquisition_timeout: float) -> ConnectionPool:
        min_size, max_size = self._calculate_pool_size()
        raw_pool = await asyncpg.create_pool(
            min_size=min_size, 
            max_size=max_size, 
            command_timeout=connection_acquisition_timeout,  
            host=config.host(),
             port=config.port(),
              database=config.database(),
               user=config.user(),
                password=config.password()
           
        )
        return PostgresConnectionPool(
            raw_pool, 
            timeout=self.connection_acquisition_timeout
        )
    
class PostgresDatabase(ConnectionManager):
    """
    PostgreSQL implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for PostgreSQL using psycopg2 for synchronous operations
    and asyncpg for asynchronous operations.
    
    Usage:
        db = PostgresDatabase(
            database="my_database",
            host="localhost",
            user="postgres",
            password="secret"
        )
        
        # Synchronous
        with db.sync_connection() as conn:
            conn.execute("SELECT * FROM users")
            
        # Asynchronous
        async with db.async_connection() as conn:
            await conn.execute("SELECT * FROM users")
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs) 
        self._pool_manager = None
        
    # region -- Implementation of Abstract methods ---------
    @property
    def pool_manager(self):
        if not self._pool_manager:
            self._pool_manager = PostgresPoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw psycopg2 connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new psycopg2 connection.
        """
        return psycopg2.connect(**config)
          
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw asyncpg connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw asyncpg connection.
            
        Returns:
            PostgresAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return PostgresAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw psycopg2 connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw psycopg2 connection.
            
        Returns:
            PostgresSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return PostgresSyncConnection(raw_conn)
    # endregion
