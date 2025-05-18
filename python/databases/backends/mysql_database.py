import asyncio
from typing import Dict, Any, Optional
import pymysql
import aiomysql

from ...resilience import retry_with_backoff
from ...utils import async_method

from ..sql import SqlGenerator
from ..config import DatabaseConfig
from ..connections import ConnectionManager, SyncConnection, AsyncConnection, ConnectionPool, PoolManager
from ..entity import MySqlSqlGenerator # todo: incorrect place

class MysqlSyncConnection(SyncConnection):
    """
    MySQL implementation of the SyncConnection interface.
    
    This class wraps a raw pymysql connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw pymysql connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)       
        self._cursor = self._conn.cursor()
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the MySql parameter converter."""
        if not self._sql_generator:
            self._sql_generator = MySqlSqlGenerator()
        return self._sql_generator
    
    @retry_with_backoff()
    def _prepare_statement_sync(self, converted_sql: str) -> Any:
        """
        MySQL with pymysql doesn't have true prepared statements API
        so we just return the SQL for later execution
        """
        return converted_sql  # Just return the converted SQL

    @retry_with_backoff()
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a statement using pymysql"""
        # statement is just the SQL string
        self._cursor.execute(statement, params or ())
        return self._cursor.fetchall()  # Return raw results

     
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return not self._conn.get_autocommit()

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        self._conn.begin()

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
        cursor.execute("SELECT VERSION();")
        server_version = cursor.fetchone()[0]

        module = type(self._conn).__module__.split(".")[0]
        driver_version = f"{module} {__import__(module).__version__}"

        return {
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    
class MysqlAsyncConnection(AsyncConnection):
    """
    MySQL implementation of the AsyncConnection interface.
    
    This class wraps a raw aiomysql connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw aiomysql connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)        
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the MySql parameter converter."""
        if not self._sql_generator:
            self._sql_generator = MySqlSqlGenerator()
        return self._sql_generator

    @retry_with_backoff()
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """
        MySQL with aiomysql doesn't have true prepared statements API
        so we just return the SQL for later execution
        """
        return native_sql
    
    @retry_with_backoff()
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a statement using aiomysql"""
        # statement is just the SQL string
        async with self._conn.cursor() as cursor:
            await cursor.execute(statement, params or ())
            return await cursor.fetchall()   
 
    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return not self._conn.get_autocommit()
    
    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed,
        regardless of whether you've explicitly started a transaction.
        """
        await self._conn.begin()

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
    
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed, and any previous insert/update would not be rolled back.
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
        async with self._conn.cursor() as cursor:
            await cursor.execute("SELECT VERSION();")
            row = await cursor.fetchone()
            server_version = row[0]

        import aiomysql
        driver_version = f"aiomysql {aiomysql.__version__}"

        return {           
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    
class MySqlConnectionPool(ConnectionPool):
    """
    MySQL implementation of ConnectionPool using aiomysql.
    
    This class wraps aiomysql's connection pool to provide a standardized interface
    and additional functionality for connection management.
    
    Attributes:
        _pool: The underlying aiomysql pool
        _timeout: Default timeout for connection acquisition
    """
    
    def __init__(self, pool, timeout: float = 10.0):
        """
        Initialize a MySQL connection pool wrapper.
        
        Args:
            pool: The underlying aiomysql pool
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
            The raw aiomysql connection
            
        Raises:
            TimeoutError: If connection acquisition times out
        """
        timeout = timeout if timeout is not None else self._timeout
        try:
            # aiomysql doesn't directly support timeout in acquire
            return await asyncio.wait_for(self._pool.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for MySQL connection after {timeout}s")
    
    @async_method
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The aiomysql connection to release
        """
        self._pool.release(connection)
    
    @async_method
    async def close(self, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args
            
            timeout: Maximum time to wait for graceful shutdown
        """        
        if self._pool:
            await self._pool.close()            
            self._pool = None
    
    async def _test_connection(self, connection):
        await connection.execute("SELECT 1")
    
    @property
    def min_size(self) -> int:
        """Gets the minimum number of connections the pool maintains."""
        return self._pool.minsize
    
    @property
    def max_size(self) -> int:
        """Gets the maximum number of connections the pool can create."""
        return self._pool.maxsize
    
    @property
    def size(self) -> int:
        """Gets the current number of connections in the pool."""
        return self._pool.size
    
    @property
    def in_use(self) -> int:
        """Gets the number of connections currently in use."""
        # aiomysql pool tracks free connections, so in-use is size - len(free)
        return self._pool.size - len(self._pool._free)
    
    @property
    def idle(self) -> int:
        """Gets the number of idle connections in the pool."""
        return len(self._pool._free)   

class MySqlPoolManager(PoolManager):
    async def _create_pool(self, config: DatabaseConfig, connection_acquisition_timeout: float) -> ConnectionPool:
        min_size, max_size = self._calculate_pool_size()
        cfg = config.config().copy()
        cfg["db"] = cfg.pop("database")  # aiomysql expects "db"
        raw_pool = await aiomysql.create_pool(
            minsize=min_size, 
            maxsize=max_size, 
            **cfg
        )
        return MySqlConnectionPool(
            raw_pool, 
            timeout=self.connection_acquisition_timeout
        )
    
class MySqlDatabase(ConnectionManager):
    """
    MySQL implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for MySQL using pymysql for synchronous operations
    and aiomysql for asynchronous operations.
    
    Usage:
        db = MySqlDatabase(
            database="my_database",
            host="localhost",
            user="root",
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
            self._pool_manager = MySqlPoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw pymysql connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new pymysql connection.
        """        
        return pymysql.connect(**config)        
    
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw aiomysql connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw aiomysql connection.
            
        Returns:
            MysqlAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return MysqlAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw pymysql connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw pymysql connection.
            
        Returns:
            MysqlSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return MysqlSyncConnection(raw_conn)
    # endregion
