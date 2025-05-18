import asyncio
from typing import Dict, Any, Optional
import sqlite3
import aiosqlite

from ...resilience import retry_with_backoff
from ...utils import async_method

from ..sql import SqlGenerator
from ..config import DatabaseConfig
from ..connections import ConnectionManager, SyncConnection, AsyncConnection, ConnectionPool, PoolManager
from ..entity import SqliteSqlGenerator # todo: incorrect place


class SqliteSyncConnection(SyncConnection):
    """
    SQLite implementation of the SyncConnection interface.
    
    This class wraps a raw sqlite3 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw sqlite3 connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)
        self._cursor = self._conn.cursor()
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the SQL parameter converter."""
        if not self._sql_generator:
            self._sql_generator = SqliteSqlGenerator()
        return self._sql_generator

    @retry_with_backoff()
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """
        SQLite with sqlite3 doesn't have a separate prepare API,
        so we just return the SQL for later execution
        """
        return native_sql  # Just return the SQL string
    
    @retry_with_backoff()
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a statement using sqlite3"""
        # statement is the SQL string
        self._cursor.execute(statement, params or ())
        return self._cursor.fetchall()  # Return raw results
        
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return self._conn.in_transaction

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        self._conn.execute("BEGIN")

    def commit_transaction(self):
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        self._conn.commit()

    def rollback_transaction(self):
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
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
        cursor.execute("SELECT sqlite_version();")
        server_version = cursor.fetchone()[0]

        import sqlite3
        driver_version = f"sqlite3 {sqlite3.sqlite_version}"

        return {          
            "db_server_version": server_version,
            "db_driver": driver_version
        }
           
class SqliteAsyncConnection(AsyncConnection):
    """
    SQLite implementation of the AsyncConnection interface.
    
    This class wraps a raw aiosqlite connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw aiosqlite connection object.
    """
    def __init__(self, conn):
        super().__init__(conn) 
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the SQL parameter converter."""
        if not self._sql_generator:
            self._sql_generator = SqliteSqlGenerator()
        return self._sql_generator
  
    @retry_with_backoff()
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """
        SQLite with aiosqlite doesn't have a separate prepare API, so returning the sql        
        """       
        return native_sql
    
    @retry_with_backoff()
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using aiosqlite"""
        async with self._conn.execute(statement, params or ()) as cursor:
            return await cursor.fetchall()

    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        # aiosqlite allows checking transaction status via in_transaction property
        return self._conn.in_transaction

    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        await self._conn.execute("BEGIN")

    @async_method
    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        await self._conn.commit()

    @async_method
    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        """
        await self._conn.rollback()

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
        async with self._conn.execute("SELECT sqlite_version();") as cursor:
            row = await cursor.fetchone()
            server_version = row[0]

        import aiosqlite
        driver_version = f"aiosqlite {aiosqlite.__version__}"

        return {
            "db_server_version": server_version,
            "db_driver": driver_version
        }
            
class SqliteConnectionPool(ConnectionPool):
    """
    SQLite implementation of ConnectionPool.
    
    Since SQLite doesn't natively support connection pooling, this implementation
    provides a pool-like interface around a single SQLite connection that can
    only be used by one client at a time.
    
    Attributes:
        _conn: The single SQLite connection
        _in_use: Whether the connection is currently checked out
        _timeout: Default timeout for connection acquisition
        _lock: Lock to ensure thread safety
    """
    
    def __init__(self, conn, timeout: float = 10.0):
        """
        Initialize a SQLite connection pool wrapper.
        
        Args:
            conn: The single aiosqlite connection
            timeout: Default timeout for connection acquisition in seconds
        """
        self._conn = conn
        self._in_use = False
        self._timeout = timeout
        self._lock = asyncio.Lock()
    
    @async_method
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires the SQLite connection if it's not in use.
        
        SQLite doesn't support concurrent access to the same connection,
        so this implementation only allows one client to use the connection
        at a time.
        
        Args:
            timeout: Maximum time to wait for the connection to be available
            
        Returns:
            The SQLite connection
            
        Raises:
            TimeoutError: If the connection is busy for too long
        """
        timeout = timeout if timeout is not None else self._timeout
        try:
            # Wait for the lock with timeout
            acquired = await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
            if not acquired:
                raise TimeoutError(f"Timed out waiting for SQLite connection after {timeout}s")
                
            self._in_use = True
            return self._conn
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for SQLite connection after {timeout}s")
    
    @async_method
    async def release(self, connection: Any) -> None:
        """
        Releases the SQLite connection back to the pool.
        
        Args:
            connection: The SQLite connection to release (must be the same one)
        """
        if connection is not self._conn:
            raise ValueError("Released connection is not the same as the managed connection")
            
        self._in_use = False
        self._lock.release()
    
    @async_method
    async def close(self, timeout: Optional[float] = None) -> None:
        """
        Closes the SQLite connection.
        
        Args:       
            timeout: Maximum time to wait for the connection to be released 
        """
        # Wait for the connection to be released first
        if self._in_use and timeout:
            try:
                # Try to acquire the lock (which means the connection is released)
                # and then release it immediately
                acquired = await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
                if acquired:
                    self._lock.release()
            except asyncio.TimeoutError:
                # Timeout waiting for release, close anyway
                pass
            # Close the connection
            await self._conn.close()
    
    async def _test_connection(self, connection):
        await connection.execute("SELECT 1")
    
    @property
    def min_size(self) -> int:
        """Always returns 1 for SQLite (single connection)."""
        return 1
    
    @property
    def max_size(self) -> int:
        """Always returns 1 for SQLite (single connection)."""
        return 1
    
    @property
    def size(self) -> int:
        """Always returns 1 for SQLite (single connection)."""
        return 1
    
    @property
    def in_use(self) -> int:
        """Returns 1 if the connection is in use, 0 otherwise."""
        return 1 if self._in_use else 0
    
    @property
    def idle(self) -> int:
        """Returns 0 if the connection is in use, 1 otherwise."""
        return 0 if self._in_use else 1

class SqlitePoolManager(PoolManager):
    async def _create_pool(self, config: DatabaseConfig, connection_acquisition_timeout: float) -> ConnectionPool:
        db_path = config.config()["database"]
        conn = await aiosqlite.connect(db_path)
        return SqliteConnectionPool(
            conn,
            timeout=self.connection_acquisition_timeout
        )
    
class SqliteDatabase(ConnectionManager):
    """
    SQLite implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for SQLite using sqlite3 for synchronous operations
    and aiosqlite for asynchronous operations.
    
    Usage:
        db = SqliteDatabase(
            database="path/to/my_database.db"
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
            self._pool_manager = SqlitePoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw sqlite3 connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new sqlite3 connection.
            
        Note:
            For SQLite, only the 'database' parameter is used, which should
            be the path to the database file.
        """       
        return sqlite3.connect(config["database"])        
    
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw aiosqlite connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw aiosqlite connection.
            
        Returns:
            SqliteAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return SqliteAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw sqlite3 connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw sqlite3 connection.
            
        Returns:
            SqliteSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return SqliteSyncConnection(raw_conn)
    # endregion
