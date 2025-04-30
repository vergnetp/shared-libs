import sys
import json
import hashlib
import asyncio
import contextlib
from typing import Callable, Awaitable, Optional, Tuple, List, Any, Dict, final, Union
from abc import ABC, abstractmethod
from ..errors import TrackError
from .. import log as logger
from .. import utils

import sqlite3
import aiosqlite
import psycopg2
import asyncpg
import pymysql
import aiomysql

class AsyncConnection(ABC):
    """
    Abstract base class defining the interface for asynchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends asynchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """

    @abstractmethod
    def get_raw_connection(self) -> Any:
        """
        Returns the underlying raw database connection object.
        
        This method allows access to the actual database driver connection
        when needed for advanced operations not covered by the standard API.
        
        Returns:
            Any: The underlying database connection object.
        """
        pass

    @abstractmethod
    async def execute_async(self, sql: str, params: Optional[tuple] = None) -> Any:
        """
        Asynchronously executes a SQL query with optional parameters.
        
        Args:
            sql (str): The SQL query to execute.
            params (Optional[tuple], optional): Query parameters to bind. Defaults to None.
        
        Returns:
            Any: Query result, format depends on the database backend.
        """
        pass

    @abstractmethod
    async def executemany_async(self, sql: str, param_list: List[tuple]) -> Any:
        """
        Asynchronously executes a SQL query multiple times with different parameters.
        
        This is typically more efficient than executing the same query multiple times
        for batch operations like bulk inserts.
        
        Args:
            sql (str): The SQL query to execute.
            param_list (List[tuple]): List of parameter tuples, one for each execution.
        
        Returns:
            Any: Query result, format depends on the database backend.
        """
        pass

    @abstractmethod
    async def begin_transaction_async(self) -> None:
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        pass

    @abstractmethod
    async def commit_transaction_async(self) -> None:
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        pass

    @abstractmethod
    async def rollback_transaction_async(self) -> None:
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        """
        pass

    @abstractmethod
    async def close_async(self) -> None:
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        pass


class SyncConnection(ABC):
    """
    Abstract base class defining the interface for synchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends synchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """

    @abstractmethod
    def execute(self, sql: str, params: Optional[tuple] = None) -> Any:
        """
        Executes a SQL query with optional parameters.
        
        Args:
            sql (str): The SQL query to execute.
            params (Optional[tuple], optional): Query parameters to bind. Defaults to None.
        
        Returns:
            Any: Query result, format depends on the database backend.
        """
        pass

    @abstractmethod
    def executemany(self, sql: str, param_list: List[tuple]) -> Any:
        """
        Executes a SQL query multiple times with different parameters.
        
        This is typically more efficient than executing the same query multiple times
        for batch operations like bulk inserts.
        
        Args:
            sql (str): The SQL query to execute.
            param_list (List[tuple]): List of parameter tuples, one for each execution.
        
        Returns:
            Any: Query result, format depends on the database backend.
        """
        pass

    @abstractmethod
    def begin_transaction(self) -> None:
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        pass

    @abstractmethod
    def commit_transaction(self) -> None:
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        pass

    @abstractmethod
    def rollback_transaction(self) -> None:
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        pass

class DatabaseConfig:
    """
    Holds database connection configuration parameters.
    
    This class encapsulates all settings required to establish a database connection,
    including connection parameters, environment information, and connection identification.
    It provides methods to access these settings and generate a unique hash-based 
    identifier for the connection.
    
    Args:
        database (str): Database name.
        host (str, optional): Server hostname. Defaults to "localhost".
        port (int, optional): Server port. Defaults to 5432.
        user (str, optional): Username for authentication. Defaults to None.
        password (str, optional): Password for authentication. Defaults to None.
        alias (str, optional): Friendly name for the connection. Defaults to database name.
        env (str, optional): Environment label (e.g. prod, dev, test). Defaults to "prod".
    """
    def __init__(self, database: str, host: str="localhost", port: int=5432, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod',  *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__host = host
        self.__port = port
        self.__database = database
        self.__user = user
        self.__password = password
        self.__env = env
        self.__alias = alias or database or f'database'

    def config(self) -> Dict:
        """
        Returns the database configuration as a dictionary.
        
        This dictionary contains all the parameters needed to establish a database
        connection and can be passed directly to database drivers.
        
        Returns:
            Dict: Dictionary containing host, port, database, user, and password.
        """
        return {
            'host': self.__host,
            'port': self.__port,
            'database': self.__database,
            'user': self.__user,
            'password': self.__password
        }
    
    def database(self) -> str:
        """
        Returns the database name.
        
        Returns:
            str: The configured database name.
        """
        return self.__database
    
    def alias(self) -> str:
        """
        Returns the database connection alias.
        
        The alias is a friendly name for the connection, which defaults to the
        database name if not explicitly provided.
        
        Returns:
            str: The database connection alias.
        """
        return self.__alias
    
    def host(self) -> str:
        """
        Returns the database host.
        
        Returns:
            str: The configured database host.
        """
        return self.__host
    
    def port(self) -> int:
        """
        Returns the database port.
        
        Returns:
            int: The configured database port.
        """
        return self.__port
    
    def env(self) -> str:
        """
        Returns the database environment.
        
        The environment is a label (e.g., 'prod', 'dev', 'test') that identifies
        the context in which the database is being used.
        
        Returns:
            str: The database environment label.
        """
        return self.__env

    def hash(self) -> str:
        """
        Returns a stable, hash-based key for the database configuration.
        
        This hash is used to uniquely identify connection pools and can be
        used as a key in dictionaries. It is based on all configuration
        parameters except the password.
        
        Returns:
            str: MD5 hash of the JSON-serialized configuration.
        """
        cfg = self.config().copy()
        cfg.pop('password', None)  # optional, if you want pools keyed w/o password
        key_json = json.dumps(cfg, sort_keys=True)
        return hashlib.md5(key_json.encode()).hexdigest()
    
class AsyncPoolManager(ABC):
    """
    Abstract base class to manage the lifecycle of asynchronous connection pools.
    
    This class implements a shared connection pool management system based on
    database configuration. Pools are created lazily, shared across instances
    with the same configuration, and can be properly closed during application
    shutdown.
    
    Subclasses must also inherit from `DatabaseConfig` or provide compatible
    `hash()` and `alias()` methods, and must implement the abstract method
    `_create_pool()` to create a backend-specific connection pool.
    
    Key Features:
        - Pools are shared across instances with the same database configuration
        - Pools are lazily initialized on first use
        - Pools are uniquely identified by the hash of their configuration
        - Thread-safe pool initialization with locks
        - Connection health checking
        - Graceful pool shutdown
    
    Thread Safety:
        - Pool initialization is protected by asyncio.Lock to ensure thread safety
        - Shared pools are accessed via atomic dictionary operations
        - Each distinct database configuration gets its own lock object
        - Multiple threads can safely create instances with the same configuration
        - Pool access is not generally thread-safe and should be used from a single thread
    
    Class Attributes:
        _shared_pools (Dict[str, Any]): Dictionary mapping config hashes to pool instances
        _shared_locks (Dict[str, asyncio.Lock]): Locks for thread-safe pool initialization
    """
    _shared_pools: Dict[str, Any] = {}
    _shared_locks: Dict[str, asyncio.Lock] = {}

    @property
    def _pool(self) -> Optional[Any]:
        """
        Gets the connection pool for this instance's configuration.
        
        The pool is retrieved from the shared pools dictionary using the
        hash of this instance's configuration as the key.
        
        Returns:
            Optional[Any]: The connection pool, or None if not initialized.
        """
        return self._shared_pools.get(self.hash())

    @_pool.setter
    def _pool(self, value: Any) -> None:
        """
        Sets or clears the connection pool for this instance's configuration.
        
        If value is None, the pool is removed from the shared pools dictionary.
        Otherwise, the pool is stored in the shared pools dictionary using the
        hash of this instance's configuration as the key.
        
        Args:
            value (Any): The connection pool to set, or None to clear.
        """
        k = self.hash()
        if value is None:
            self._shared_pools.pop(k, None)
        else:
            self._shared_pools[k] = value

    @property
    def _pool_lock(self) -> asyncio.Lock:
        """
        Gets the lock for this instance's configuration.
        
        The lock is used to ensure thread-safe initialization of the connection pool.
        If no lock exists for this configuration, a new one is created.
        
        Returns:
            asyncio.Lock: The lock for this instance's configuration.
        """
        k = self.hash()
        if k not in self._shared_locks:
            self._shared_locks[k] = asyncio.Lock()
        return self._shared_locks[k]
  
    async def _initialize_pool_if_needed(self) -> None:
        """
        Initializes the connection pool if it doesn't exist or isn't usable.
        
        This method first checks if a pool already exists and is usable by
        attempting to acquire a connection and run a test query. If the pool
        doesn't exist or isn't usable, a new pool is created.
        
        Thread Safety:
            - Pool creation is protected by a per-configuration lock
            - Multiple concurrent calls will only create one pool instance
            - The lock ensures only one thread can initialize a pool at a time
            - After initialization, the pool itself must handle concurrent access
            
        Concurrency:
            - Safe for multiple concurrent calls from the same event loop
            - Database connections are tested with a simple SELECT 1 query
            - Failed pools are properly closed before recreating them
        """
        # Check if existing pool is usable
        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    await self._test_connection(conn)
                return
            except Exception as e:
                logger.debug(f"Existing pool unusable for {self.alias()} - {self.hash()}: {e}")
                try:
                    await self._pool.close()
                except Exception:
                    pass
                self._pool = None

        # Create pool under lock
        async with self._pool_lock:
            if self._pool is None:
                try:
                    self._pool = await self._create_pool(self)
                    logger.info(f"{self.alias()} - {self.hash()} async pool initialized")
                except Exception as e:
                    logger.error(f"{self.alias()} - {self.hash()} async pool creation failed: {e}")
                    self._pool = None
                    raise

    async def _test_connection(self, conn: Any) -> None:
        """
        Tests if a connection is usable by executing a simple query.
        
        Args:
            conn (Any): The connection to test.
            
        Raises:
            Exception: If the test query fails, indicating the connection is not usable.
        """
        try:
            await conn.execute("SELECT 1")
        except Exception:
            raise


    @classmethod
    async def close_pool(cls, config_hash: Optional[str] = None) -> None:
        """
        Closes one or all shared connection pools.
        
        This method should be called during application shutdown to properly
        release database resources.
        
        Args:
            config_hash (Optional[str], optional): Hash of the configuration
                for the pool to close. If None, all pools will be closed.
                Defaults to None.
        """
        keys = [config_hash] if config_hash else list(cls._shared_pools.keys())
        for key in keys:
            pool = cls._shared_pools.get(key)
            if pool:
                try:
                    await pool.close()
                    logger.info(f"Pool for {key} closed")
                except Exception as e:
                    logger.error(f"Error closing pool for {key}: {e}")
                finally:
                    cls._shared_pools.pop(key, None)
                    cls._shared_locks.pop(key, None)

    @abstractmethod
    async def _create_pool(self, config: Dict) -> Any:
        """
        Creates a new connection pool.
        
        This abstract method must be implemented by subclasses to create a
        connection pool specific to the database backend being used.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            Any: A new connection pool object compatible with:
                - acquire() method to get a connection
                - close() method to shutdown the pool
                - Connections support execute("SELECT 1") for health checks
        """
        raise NotImplementedError()

class DatabaseConnectionManager(AsyncPoolManager, DatabaseConfig):
    """
    Manages synchronized and asynchronous database connection lifecycles.
    
    This class provides a unified interface for obtaining both sync and async
    database connections, with proper resource management through context managers.
    It handles connection pooling for async connections and caching for sync
    connections.
    
    Features:
        - Synchronous connection caching with automatic cleanup
        - Asynchronous connection pooling with proper resource management
        - Context managers for safe connection usage
        - Environment detection (async vs sync)
        - Graceful connection release
    
    Thread Safety:
        - Sync connections are NOT thread-safe and should only be used from one thread
        - The cached sync connection (_sync_conn) is per-instance and not shared
        - Async connections use thread-safe connection pools (see AsyncPoolManager)
        - Each instance maintains its own sync connection state
        - DO NOT share a DatabaseConnectionManager instance across threads
    
    Concurrency:
        - Sync methods will block and should not be used from async code
        - Async methods should only be called from async context
        - Auto-detects async environment during initialization
        - Context managers ensure proper connection cleanup even with exceptions
        - Connection release is handled safely in both sync and async contexts
    
    Subclasses must implement:
        - _create_sync_connection(config): Create a backend-specific sync connection
        - _create_pool(config): Create a backend-specific async connection pool
        - _wrap_sync_connection(raw_conn): Wrap raw connection in SyncConnection interface
        - _wrap_async_connection(raw_conn): Wrap raw connection in AsyncConnection interface
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._sync_conn = None       

        if self.is_environment_async():
            try:
                asyncio.get_running_loop().create_task(self._initialize_pool_if_needed())
            except RuntimeError:
                self._sync_conn = self.get_sync_connection()
        else:
            self._sync_conn = self.get_sync_connection()

    def is_environment_async(self) -> bool:
        """
        Determines if code is running in an async environment.
        
        This method checks if an event loop is running in the current thread,
        which indicates that async/await code can be used.
        
        Returns:
            bool: True if running in an async environment, False otherwise.
        """
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    # region -- SYNC METHODS ---------
    
    def get_sync_connection(self) -> SyncConnection:
        """
        Returns a synchronized database connection.
        
        This method returns an existing connection if one is already cached,
        or creates a new one if needed. The connection is wrapped in the
        SyncConnection interface for standardized access.
        
        Thread Safety:
            - NOT thread-safe: the cached connection is per-instance
            - Should only be called from a single thread
            - Multiple instances should be used for multi-threaded applications
        
        Returns:
            SyncConnection: A database connection for synchronous operations.
            
        Note:
            The connection should be closed with release_sync_connection()
            or by using the sync_connection() context manager.
        """
        if self._sync_conn is None:
            raw_conn = self._create_sync_connection(self.config())
            self._sync_conn = self._wrap_sync_connection(raw_conn)
        return self._sync_conn     

    def release_sync_connection(self) -> None:
        """
        Closes and releases the cached synchronous connection.
        
        This method should be called when the connection is no longer needed
        to properly release database resources. After calling this method,
        the next call to get_sync_connection() will create a new connection.
        """
        if self._sync_conn:
            try:
                self._sync_conn.close()
                logger.debug(f"{self.alias()} sync connection closed")
            except Exception as e:
                logger.warning(f"{self.alias()} failed to close sync connection: {e}")
            self._sync_conn = None

    @contextlib.contextmanager
    async def sync_connection(self):
        """
        Context manager for safe synchronous connection usage.
        
        This context manager ensures that the connection is properly released
        when the block exits, even if an exception occurs.
        
        Yields:
            SyncConnection: A database connection for synchronous operations.
            
        Example:
            with db.sync_connection() as conn:
                conn.execute("SELECT * FROM users")
        """
        conn = self.get_sync_connection()
        try:
            yield conn
        finally:
            self.release_sync_connection()

    def __del__(self):
        """
        Destructor that ensures connections are released when the object is garbage collected.
        
        This is a fallback cleanup mechanism and should not be relied upon as the
        primary means of releasing connections.
        """
        try:
            if sys.is_finalizing():
                return
            self.release_sync_connection()
        except Exception:
            pass
    
    # endregion


    # region -- ASYNC METHODS ----------
   
    async def get_async_connection(self) -> AsyncConnection:
        """
        Acquires an asynchronous connection from the pool.
        
        This method ensures the connection pool is initialized, then acquires
        a connection from it and wraps it in the AsyncConnection interface
        for standardized access.
        
        Thread Safety:
            - Safe to call from multiple coroutines in the same event loop
            - The underlying pool handles concurrent connection requests
            - Uses _initialize_pool_if_needed() which has thread safety guarantees
        
        Concurrency:
            - Uses connection pooling for efficient resource sharing
            - Will block only when the pool has reached max_size
            - Each connection is exclusive to the caller until released
        
        Returns:
            AsyncConnection: A database connection for asynchronous operations.
            
        Note:
            The connection should be released with release_async_connection()
            or by using the async_connection() context manager.
        """
        await self._initialize_pool_if_needed()
        raw_conn = await self._pool.acquire() 
        return self._wrap_async_connection(raw_conn)

    async def release_async_connection(self, async_conn: AsyncConnection):
        """
        Releases an asynchronous connection back to the pool.
        
        This method should be called when the connection is no longer needed
        to make it available for reuse by other operations.
        
        Args:
            async_conn (AsyncConnection): The connection to release.
        """
        if async_conn and self._pool:
            try:
                await self._pool.release(async_conn.get_raw_connection())
            except Exception as e:
                logger.warning(f"{self.alias()} failed to release async connection: {e}")

    @contextlib.asynccontextmanager
    async def async_connection(self):
        """
        Async context manager for safe asynchronous connection usage.
        
        This context manager ensures that the connection is properly released
        when the block exits, even if an exception occurs.
        
        Yields:
            AsyncConnection: A database connection for asynchronous operations.
            
        Example:
            async with db.async_connection() as conn:
                await conn.execute_async("SELECT * FROM users")
        """
        conn = await self.get_async_connection()
        try:
            yield conn
        finally:
            await self.release_async_connection(conn)
    
    # endregion

    @abstractmethod
    def _wrap_sync_connection(self, raw_conn: Any) -> SyncConnection:
        """
        Wraps a raw database connection in the SyncConnection interface.
        
        This abstract method must be implemented by subclasses to create a
        database-specific wrapper that implements the SyncConnection interface.
        
        Args:
            raw_conn (Any): The raw database connection to wrap.
            
        Returns:
            SyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        raise NotImplementedError()

    @abstractmethod
    def _wrap_async_connection(self, raw_conn: Any) -> AsyncConnection:
        """
        Wraps a raw database connection in the AsyncConnection interface.
        
        This abstract method must be implemented by subclasses to create a
        database-specific wrapper that implements the AsyncConnection interface.
        
        Args:
            raw_conn (Any): The raw database connection to wrap.
            
        Returns:
            AsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        raise NotImplementedError()

    @abstractmethod
    def _create_sync_connection(self, config: Dict) -> Any:
        """
        Creates a new synchronous database connection.
        
        This abstract method must be implemented by subclasses to create a
        connection specific to the database backend being used.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            Any: A new raw database connection object.
            
        Example implementation:
            return pymysql.connect(**config)
        """
        raise NotImplementedError() 


class BaseDatabase(DatabaseConnectionManager):
    '''
    Base class for all database implementations.
    
    This class inherits from DatabaseConnectionManager to provide connection
    management functionality. Specific database implementations (PostgreSQL,
    MySQL, SQLite) should inherit from this class and implement the required
    abstract methods.
    
    Public API:
        - get_sync_connection() / release_sync_connection(): Manage sync connections
        - get_async_connection() / release_async_connection(): Manage async connections
        - sync_connection() context manager: For safe sync connection usage
        - async_connection() context manager: For safe async connection usage
        - close_pool() class method: For shutting down connection pools
    
    Thread Safety:
        - Inherits thread safety properties from DatabaseConnectionManager
        - Each BaseDatabase instance maintains its own sync connection state
        - Instances should not be shared across threads
        - For multi-threaded applications, create one instance per thread
        - For async applications, a single instance can be shared within one event loop
    
    Concurrency Model:
        - Sync operations: Single-threaded, blocking I/O model
        - Async operations: Event-loop based, non-blocking I/O model
        - Do not mix sync and async operations in the same call chain
        - Sync connections are cached per instance
        - Async connections are pooled and shared across instances with identical config
    
    Implementation Requirements:
        Derived classes must implement:
        - _create_sync_connection(config): Create raw synchronous connection
        - _create_pool(config): Create asynchronous connection pool
        - _wrap_async_connection(raw_conn): Wrap raw connection in AsyncConnection
        - _wrap_sync_connection(raw_conn): Wrap raw connection in SyncConnection
    
    Args:
        database (str): Database name.
        host (str, optional): Server hostname. Defaults to "localhost".
        port (int, optional): Server port. Defaults to 5432.
        user (str, optional): Username for authentication. Defaults to None.
        password (str, optional): Password for authentication. Defaults to None.
        alias (str, optional): Friendly name for the connection. Defaults to database name.
        env (str, optional): Environment label (e.g. prod, dev, test). Defaults to "prod".
    '''
    def __init__(self, database: str, host: str="localhost", port: int=5432, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod', *args, **kwargs):
        # Forward all named parameters
        super().__init__(
            database=database, 
            host=host, 
            port=port, 
            user=user, 
            password=password, 
            alias=alias, 
            env=env, 
            *args, 
            **kwargs
        )


class PostgresSyncConnection(SyncConnection):
    """
    PostgreSQL implementation of the SyncConnection interface.
    
    This class wraps a raw psycopg2 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw psycopg2 connection object.
    """
    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()

    def execute(self, sql, params=None) -> Any:
        """
        Executes a SQL query with PostgreSQL parameter binding.
        
        PostgreSQL uses %s as parameter placeholders regardless of the data type.
        
        Args:
            sql (str): SQL query with %s placeholders.
            params (tuple, optional): Parameters to bind. Defaults to None.
            
        Returns:
            Any: The cursor object, which can be used to fetch results.
        """
        return self._cursor.execute(sql, params or ())

    def executemany(self, sql, param_list) -> Any:
        """
        Executes a SQL query multiple times with different parameters.
        
        Args:
            sql (str): SQL query with %s placeholders.
            param_list (List[tuple]): List of parameter tuples, one for each execution.
            
        Returns:
            Any: The cursor object, which can be used to fetch results.
        """
        return self._cursor.executemany(sql, param_list)

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

class PostgresAsyncConnection(AsyncConnection):
    """
    PostgreSQL implementation of the AsyncConnection interface.
    
    This class wraps a raw asyncpg connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        raw_conn: Raw asyncpg connection object.
    """
    def __init__(self, raw_conn):
        self._conn = raw_conn
        self._tx = None

    def get_raw_connection(self):
        """
        Returns the underlying raw asyncpg connection.
        
        Returns:
            The raw asyncpg connection object.
        """
        return self._conn

    async def execute_async(self, sql, params=None) -> Any:
        """
        Asynchronously executes a SQL query with PostgreSQL parameter binding.
        
        asyncpg uses positional parameters with the format $1, $2, etc., but this
        method accepts standard tuples and handles the conversion.
        
        Args:
            sql (str): SQL query with %s or $1, $2, etc. placeholders.
            params (tuple, optional): Parameters to bind. Defaults to None.
            
        Returns:
            Any: The query result from asyncpg.
        """
        return await self._conn.execute(sql, *(params or []))

    async def executemany_async(self, sql, param_list) -> Any:
        """
        Asynchronously executes a SQL query multiple times with different parameters.
        
        Since asyncpg doesn't have a direct executemany equivalent, this method
        executes the query in a loop for each parameter set.
        
        Args:
            sql (str): SQL query with $1, $2, etc. placeholders.
            param_list (List[tuple]): List of parameter tuples, one for each execution.
            
        Returns:
            Any: Result of the last execution.
        """
        for params in param_list:
            await self._conn.execute(sql, *params)

    async def begin_transaction_async(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        if self._tx is None:
            self._tx = self._conn.transaction()
            await self._tx.start()

    async def commit_transaction_async(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.commit()
            self._tx = None

    async def rollback_transaction_async(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.rollback()
            self._tx = None

    async def close_async(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

class PostgresDatabase(BaseDatabase):
    """
    PostgreSQL implementation of the BaseDatabase.
    
    This class provides concrete implementations of the abstract methods
    in BaseDatabase for PostgreSQL using psycopg2 for synchronous operations
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
            await conn.execute_async("SELECT * FROM users")
    """

    # region -- Implementation of Abstract methods ---------
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw psycopg2 connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new psycopg2 connection.
        """
        return psycopg2.connect(**config)
       
    async def _create_pool(self, config: Dict) -> Any:
        """
        Creates an asyncpg connection pool.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            An asyncpg connection pool with configured limits and timeouts.
        """
        return await asyncpg.create_pool(min_size=1, max_size=10, command_timeout=60.0, **config) 
    
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

class MysqlSyncConnection(SyncConnection):
    """
    MySQL implementation of the SyncConnection interface.
    
    This class wraps a raw pymysql connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw pymysql connection object.
    """
    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()

    def execute(self, sql, params=None) -> Any:
        """
        Executes a SQL query with MySQL parameter binding.
        
        MySQL uses %s as parameter placeholders regardless of the data type.
        
        Args:
            sql (str): SQL query with %s placeholders.
            params (tuple, optional): Parameters to bind. Defaults to None.
            
        Returns:
            Any: The cursor object, which can be used to fetch results.
        """
        return self._cursor.execute(sql, params or ())

    def executemany(self, sql, param_list) -> Any:
        """
        Executes a SQL query multiple times with different parameters.
        
        Args:
            sql (str): SQL query with %s placeholders.
            param_list (List[tuple]): List of parameter tuples, one for each execution.
            
        Returns:
            Any: The cursor object, which can be used to fetch results.
        """
        return self._cursor.executemany(sql, param_list)

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

class MysqlAsyncConnection(AsyncConnection):
    """
    MySQL implementation of the AsyncConnection interface.
    
    This class wraps a raw aiomysql connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw aiomysql connection object.
    """
    def __init__(self, conn):
        self._conn = conn

    def get_raw_connection(self):
        """
        Returns the underlying raw aiomysql connection.
        
        Returns:
            The raw aiomysql connection object.
        """
        return self._conn

    async def execute_async(self, sql, params=None) -> Any:
        """
        Asynchronously executes a SQL query with MySQL parameter binding.
        
        Args:
            sql (str): SQL query with %s placeholders.
            params (tuple, optional): Parameters to bind. Defaults to None.
            
        Returns:
            Any: The query result from aiomysql.
        """
        async with self._conn.cursor() as cur:
            await cur.execute(sql, params or ())
            return await cur.fetchall()

    async def executemany_async(self, sql, param_list) -> Any:
        """
        Asynchronously executes a SQL query multiple times with different parameters.
        
        Args:
            sql (str): SQL query with %s placeholders.
            param_list (List[tuple]): List of parameter tuples, one for each execution.
            
        Returns:
            Any: Result of the execution.
        """
        async with self._conn.cursor() as cur:
            return await cur.executemany(sql, param_list)

    async def begin_transaction_async(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        await self._conn.begin()

    async def commit_transaction_async(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        await self._conn.commit()

    async def rollback_transaction_async(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        """
        await self._conn.rollback()

    async def close_async(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        self._conn.close()

class MySqlDatabase(BaseDatabase):
    """
    MySQL implementation of the BaseDatabase.
    
    This class provides concrete implementations of the abstract methods
    in BaseDatabase for MySQL using pymysql for synchronous operations
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
            await conn.execute_async("SELECT * FROM users")
    """

    # region -- Implementation of Abstract methods ---------
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw pymysql connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new pymysql connection.
        """        
        return pymysql.connect(**config)        

    async def _create_pool(self, config: Dict) -> Any:
        """
        Creates an aiomysql connection pool.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            An aiomysql connection pool with configured limits.
            
        Note:
            aiomysql expects the database name as 'db' instead of 'database',
            so the configuration is adjusted accordingly.
        """
        cfg = config.copy()
        cfg["db"] = cfg.pop("database")  # aiomysql expects "db"
        return await aiomysql.create_pool(minsize=1, maxsize=10, **cfg)
    
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

class SqliteSyncConnection(SyncConnection):
    """
    SQLite implementation of the SyncConnection interface.
    
    This class wraps a raw sqlite3 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw sqlite3 connection object.
    """
    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()

    def execute(self, sql, params=None) -> Any:
        """
        Executes a SQL query with SQLite parameter binding.
        
        SQLite uses ? as parameter placeholders.
        
        Args:
            sql (str): SQL query with ? placeholders.
            params (tuple, optional): Parameters to bind. Defaults to None.
            
        Returns:
            Any: The cursor object, which can be used to fetch results.
        """
        return self._cursor.execute(sql, params or ())

    def executemany(self, sql, param_list) -> Any:
        """
        Executes a SQL query multiple times with different parameters.
        
        Args:
            sql (str): SQL query with ? placeholders.
            param_list (List[tuple]): List of parameter tuples, one for each execution.
            
        Returns:
            Any: The cursor object, which can be used to fetch results.
        """
        return self._cursor.executemany(sql, param_list)

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

class SqliteAsyncConnection(AsyncConnection):
    """
    SQLite implementation of the AsyncConnection interface.
    
    This class wraps a raw aiosqlite connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw aiosqlite connection object.
    """
    def __init__(self, conn):
        self._conn = conn

    def get_raw_connection(self):
        """
        Returns the underlying raw aiosqlite connection.
        
        Returns:
            The raw aiosqlite connection object.
        """
        return self._conn

    async def execute_async(self, sql, params=None) -> Any:
        """
        Asynchronously executes a SQL query with SQLite parameter binding.
        
        Args:
            sql (str): SQL query with ? placeholders.
            params (tuple, optional): Parameters to bind. Defaults to None.
            
        Returns:
            Any: The query result from aiosqlite.
        """
        async with self._conn.execute(sql, params or ()) as cursor:
            return await cursor.fetchall()

    async def executemany_async(self, sql, param_list) -> Any:
        """
        Asynchronously executes a SQL query multiple times with different parameters.
        
        Since aiosqlite doesn't have a direct executemany equivalent, this method
        executes the query in a loop for each parameter set.
        
        Args:
            sql (str): SQL query with ? placeholders.
            param_list (List[tuple]): List of parameter tuples, one for each execution.
            
        Returns:
            Any: None - This method doesn't return results for SQLite.
        """
        for params in param_list:
            await self._conn.execute(sql, params)

    async def begin_transaction_async(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        await self._conn.execute("BEGIN")

    async def commit_transaction_async(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        await self._conn.commit()

    async def rollback_transaction_async(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        """
        await self._conn.rollback()

    async def close_async(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

class SqliteDatabase(BaseDatabase):
    """
    SQLite implementation of the BaseDatabase.
    
    This class provides concrete implementations of the abstract methods
    in BaseDatabase for SQLite using sqlite3 for synchronous operations
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
            await conn.execute_async("SELECT * FROM users")
    """

    # region -- Implementation of Abstract methods ---------
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

    async def _create_pool(self, config: Dict) -> Any:
        """
        Creates a simple connection pool for SQLite.
        
        Since SQLite doesn't have a native connection pool concept, this method
        creates a single connection wrapped in a simple pool-like interface.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A simple pool wrapper for an aiosqlite connection.
        """
        db_path = config["database"]
        conn = await aiosqlite.connect(db_path)
        return SqliteDatabase._SimplePool(conn)
    
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

    # region -- Helpers ------
    class _SimplePool:
        """
        A simple connection pool implementation for SQLite.
        
        Since SQLite doesn't have a native connection pool concept, this class
        provides a minimal pool-like interface around a single connection.
        
        Args:
            conn: An aiosqlite connection.
        """
        def __init__(self, conn):
            self._conn = conn

        async def acquire(self) -> Any:
            """
            Returns the managed connection.
            
            Since this is a simple pool with just one connection, this method
            always returns the same connection.
            
            Returns:
                The managed aiosqlite connection.
            """
            return self._conn

        async def close(self):
            """
            Closes the managed connection.
            
            This should be called during application shutdown to properly
            release database resources.
            """
            await self._conn.close()
    # endregion

""" 
Example usage:
# Create a PostgreSQL database connection
db = PostgresDatabase(
    database="my_database",
    host="localhost",
    port=5432,
    user="postgres",
    password="secret",
    alias="main_db",
    env="dev"
)

# Synchronous usage
with db.sync_connection() as conn:
    result = conn.execute("SELECT * FROM users WHERE id = %s", (1,))
    # Process result...

# Asynchronous usage
async def async_example():
    async with db.async_connection() as conn:
        result = await conn.execute_async("SELECT * FROM users WHERE id = %s", (1,))
        # Process result...

# Cleanup at application shutdown
async def shutdown():
    await PostgresDatabase.close_pool() 
"""


class EntityRepository:
    def __init__(self, db: BaseDatabase):
        self._db = db
    
    def get_entity(self, entity_id):
        raise NotImplementedError()

class PostgresEntityRepository(EntityRepository):
    def get_entity(self, entity_id):
        with self._db.sync_connection() as conn:
            result = conn.execute("SELECT * FROM entities WHERE id = %s", (entity_id,))
            # Process result...
            return result


class MetadataCacheMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self._load_all_metadata()
        except Exception as e:
            logger.warning(f"Metadata load failed: {e}")

    def _load_all_metadata(self):
        # Assumes a working sync connection
        rows = self.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_meta'"
        )
        for (table,) in rows:
            if not table.endswith("_meta"):
                continue
            entity = table[:-5]
            meta_rows = self.execute_sql(f"SELECT name, type FROM {table}")
            meta = {name: typ for name, typ in meta_rows}
            self._meta_cache[entity] = meta
            self._keys_cache[entity] = list(meta.keys())
            self._types_cache[entity] = list(meta.values())