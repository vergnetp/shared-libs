import sys
import os
import json
import time
import hashlib
import asyncio
import contextlib
import traceback
from typing import Set, Awaitable, Callable, Optional, Tuple, List, Any, Dict, final, Union
from typing import AsyncIterator, Iterator
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


from abc import ABC, abstractmethod
from typing import Tuple, List, Any, Optional

class SqlParameterConverter(ABC):
    """
    Abstract base class for SQL parameter placeholder conversion.
    
    Different databases use different parameter placeholder syntax. This class
    provides a way to convert between a standard format (? placeholders)
    and database-specific formats for positional parameters.
    """
    
    @abstractmethod
    def convert_query(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """
        Converts a standard SQL query with ? placeholders to a database-specific format.
        
        Args:
            sql: SQL query with ? placeholders
            params: Positional parameters for the query
            
        Returns:
            Tuple containing the converted SQL and the converted parameters
        """
        pass

class PostgresAsyncConverter(SqlParameterConverter):
    """Converter for PostgreSQL numeric placeholders ($1, $2, etc.)"""    
    def convert_query(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        if not params:
            return sql, []
        new_sql = sql
        for i in range(1, len(params) + 1):
            new_sql = new_sql.replace('?', f"${i}", 1)
        
        return new_sql, params

class PostgresSyncConverter(SqlParameterConverter):
    """Converter for PostgreSQL percent placeholders (%s)"""    
    def convert_query(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        if not params:
            return sql, [] 
        new_sql = sql.replace('?', '%s')
        return new_sql, params

class MySqlConverter(SqlParameterConverter):
    """Converter for MySQL placeholders (%s)"""    
    def convert_query(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        if not params:
            return sql, []
        new_sql = sql.replace('?', '%s')
        return new_sql, params

class SqliteConverter(SqlParameterConverter):
    """Converter for SQLite placeholders (?)"""    
    def convert_query(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        return sql, params

class BaseConnection:
    """
    Base class for database connections.
    """
    
    @property
    @abstractmethod
    def parameter_converter(self) -> SqlParameterConverter:
        """Returns the parameter converter for this connection."""
        pass

    def _normalize_result(self, raw_result: Any) -> List[Tuple]:
        """
        Default implementation to normalize results to a list of tuples.
        
        This handles common result types:
        - None/empty results → empty list
        - Cursor objects → fetch all results as tuples
        - List of tuples → returned as is
        - List of dict-like objects → converted to tuples
        - Single scalar result → wrapped in a list with a single tuple
        
        Subclasses can override for database-specific behavior.
        """
        # Handle None/empty results
        if raw_result is None:
            return []
        
        # Handle cursor objects (common in sync drivers)
        if hasattr(raw_result, 'fetchall') and callable(getattr(raw_result, 'fetchall')):
            return raw_result.fetchall()
        
        # Already a list of tuples
        if (isinstance(raw_result, list) and 
            (not raw_result or isinstance(raw_result[0], tuple))):
            return raw_result
        
        # Handle Oracle/SQL Server specific cursor result types
        if hasattr(raw_result, 'rowcount') and hasattr(raw_result, 'description'):
            try:
                return list(raw_result)  # Many cursor objects are iterable
            except (TypeError, ValueError):
                if hasattr(raw_result, 'fetchall'):
                    return raw_result.fetchall()
        
        # List of dict-like objects (e.g., asyncpg Records)
        if (isinstance(raw_result, list) and raw_result and
            hasattr(raw_result[0], 'keys') and 
            callable(getattr(raw_result[0], 'keys'))):
            # Convert each record to a tuple
            return [tuple(record.values()) for record in raw_result]
        
        # Single scalar result
        if not isinstance(raw_result, (list, tuple)):
            return [(raw_result,)]
        
        # Default case - try to convert to a list of tuples
        try:
            return [tuple(row) if not isinstance(row, tuple) else row 
                  for row in raw_result]
        except (TypeError, ValueError):
            # If conversion fails, wrap in a list with single tuple
            return [(raw_result,)]
            
class AsyncConnection(BaseConnection, ABC):
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
    async def _execute_async(self, sql: str, params: Optional[tuple] = None) -> Any:
        """
        Asynchronously executes a SQL query with optional parameters.

        This protected method is called by execute_async and should be implemented
        by subclasses to handle the driver-specific execution.
        
        Args:
            sql (str): The SQL query to execute.
            params (Optional[tuple], optional): Query parameters to bind. Defaults to None.
        
        Returns:
            Any: Query result, format depends on the database backend.
        """
        pass

    async def execute_async(self, sql: str, params: Optional[tuple] = None) -> List[Tuple]:
        """
        Asynchronously executes a SQL query with standard ? placeholders.
        
        Args:
            sql: SQL query with ? placeholders
            params: Parameters for the query
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        converted_sql, converted_params = self.parameter_converter.convert_query(sql, params)
        raw_result = await self._execute_async(converted_sql, converted_params)
        return self._normalize_result(raw_result)

    @abstractmethod
    async def _executemany_async(self, sql: str, param_list: List[tuple]) -> Any:
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

    async def executemany_async(self, sql: str, param_list: List[tuple]) -> List[Tuple]:
        """
        Asynchronously executes a SQL query multiple times with different parameters.
        
        Args:
            sql: SQL query with ? placeholders
            param_list: List of parameter tuples, one for each execution
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        converted_sql, _ = self.parameter_converter.convert_query(sql)
        # Note: we're only converting the SQL, not the parameters list
        raw_result = await self._executemany_async(converted_sql, param_list)
        return self._normalize_result(raw_result)

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
    def _execute(self, sql: str, params: Optional[tuple] = None) -> Any:
        """
        Executes a SQL query with optional parameters.

        This protected method is called by execute and should be implemented
        by subclasses to handle the driver-specific execution.

        Args:
            sql (str): The SQL query to execute.
            params (Optional[tuple], optional): Query parameters to bind. Defaults to None.
        
        Returns:
            Any: Query result, format depends on the database backend.
        """
        pass

    def execute(self, sql: str, params: Optional[tuple] = None) -> list[Tuple]:
        """
        Executes a SQL query with standard ? placeholders.
        
        Args:
            sql: SQL query with ? placeholders
            params: Parameters for the query
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        converted_sql, converted_params = self.parameter_converter.convert_query(sql, params)
        raw_result = self._execute(converted_sql, converted_params)
        return self._normalize_result(raw_result)
    
    @abstractmethod
    def _executemany(self, sql: str, param_list: List[tuple]) -> Any:
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

    def executemany(self, sql: str, param_list: List[tuple]) -> List[Tuple]:
        """
        Executes a SQL query multiple times with different parameters.
        
        Args:
            sql: SQL query with ? placeholders
            param_list: List of parameter tuples, one for each execution
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        converted_sql, _ = self.parameter_converter.convert_query(sql)
        raw_result = self._executemany(converted_sql, param_list)
        return self._normalize_result(raw_result)

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

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, List

class ConnectionPool(ABC):
    """
    Abstract connection pool interface that standardizes behavior across database drivers.
    
    This interface provides a consistent API for connection pool operations, regardless
    of the underlying database driver. It abstracts away driver-specific details and
    ensures that all pools implement the core functionality needed by the connection
    management system.
    
    Implementation Requirements:
        - Must handle timeout properly in acquire()
        - Must properly track connection state
        - Must handle force close behavior appropriately
        - Must implement health checking for pool vitality
    """
    
    @abstractmethod
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires a connection from the pool with optional timeout.
        
        Args:
            timeout (Optional[float]): Maximum time in seconds to wait for a connection.
                                      If None, use the pool's default timeout.
        
        Returns:
            Any: A database connection specific to the underlying driver.
            
        Raises:
            TimeoutError: If the acquisition times out.
            Exception: For other acquisition errors.
        """
        pass
        
    @abstractmethod
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The connection to release, specific to the underlying driver.
            
        Raises:
            Exception: If the connection cannot be released.
        """
        pass
        
    @abstractmethod
    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:
            force (bool): If True, forcibly close connections, potentially 
                          interrupting operations in progress.
            timeout (Optional[float]): Maximum time in seconds to wait for graceful shutdown
                                      when force=False. If None, wait indefinitely.
                          
        Notes:
            - When force=False, wait for all connections to be released naturally
            - When force=True, terminate any executing operations (may cause data loss)
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Checks if the pool is healthy by testing a connection.
        
        Returns:
            bool: True if the pool is healthy, False otherwise.
        """
        pass
    
    @property
    @abstractmethod
    def min_size(self) -> int:
        """
        Gets the minimum number of connections the pool maintains.
        
        Returns:
            int: The minimum pool size.
        """
        pass
    
    @property
    @abstractmethod
    def max_size(self) -> int:
        """
        Gets the maximum number of connections the pool can create.
        
        Returns:
            int: The maximum pool size.
        """
        pass
    
    @property
    @abstractmethod
    def size(self) -> int:
        """
        Gets the current number of connections in the pool.
        
        Returns:
            int: The total number of connections (both in-use and idle).
        """
        pass
    
    @property
    @abstractmethod
    def in_use(self) -> int:
        """
        Gets the number of connections currently in use.
        
        Returns:
            int: The number of connections currently checked out from the pool.
        """
        pass
    
    @property
    @abstractmethod
    def idle(self) -> int:
        """
        Gets the number of idle connections in the pool.
        
        Returns:
            int: The number of connections currently available for checkout.
        """
        pass

    @abstractmethod
    async def execute_on_pool(self, sql: str, params: Optional[Tuple] = None) -> Any:
        """
        Convenience method to execute a query without explicitly acquiring/releasing a connection.
        
        This method acquires a connection, executes the query, and releases the connection
        in a single operation, making it more efficient for simple queries.
        
        Args:
            sql (str): The SQL query to execute.
            params (Optional[Tuple]): Query parameters.
            
        Returns:
            Any: The query result.
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
    
    This class implements a shared connection pool management system based on database configuration. Pools are created lazily, shared across instances with the same configuration, and can be properly closed during application shutdown.
    
    Subclasses must also inherit from `DatabaseConfig` or provide compatible `hash()` and `alias()` methods, and must implement the abstract method `_create_pool()` to create a backend-specific connection pool.
    
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
        _active_connections (Dict[str, Set[AsyncConnection]]): Keep track of active connections
    """
    _shared_pools: Dict[str, Any] = {}
    _shared_locks: Dict[str, asyncio.Lock] = {}
    _active_connections: Dict[str, Set[AsyncConnection]] = {}
    _shutting_down: Dict[str, bool] = {}  # to track shutdown state per pool
    _metrics: Dict[str, Dict[str, int]] = {}
    
    def _track_metrics(self, is_new: bool=True, error: Exception=None, is_timeout: bool=False):       
        k = self.hash()
        if k not in self._metrics:
            self._metrics[k] = {
                'total_acquired': 1 if is_new and not error and not is_timeout else 0,
                'total_released': 0,
                'current_active': 1 if is_new and not error and not is_timeout else 0,
                'peak_active': 1 if is_new and not error and not is_timeout else 0,
                'errors': 0 if not error else 1,
                'timeouts': 0 if not is_timeout else 1,
                'last_timeout_timestamp': time.time() if is_timeout else None,
                'avg_acquisition_time': 0.0,  # We'll calculate this as a running average
            }
        else:
            # Update existing metrics
            metrics = self._metrics[k]
            if is_timeout:
                metrics['timeouts'] += 1
                metrics['last_timeout_timestamp'] = time.time()
            elif error:
                metrics['errors'] += 1
            else:
                if is_new:
                    metrics['total_acquired'] += 1
                    metrics['current_active'] += 1
                else:
                    metrics['total_released'] += 1
                    metrics['current_active'] = max(0, metrics['current_active'] - 1)  # Avoid negative
                
                # Update peak value
                metrics['peak_active'] = max(metrics['peak_active'], metrics['current_active'])
        
        try:
            logger.info(f"Pool status:\n{json.dumps(self.get_pool_status())}")
        except Exception as e:
            logger.warning(f"Error logging metrics: {e}")

    def get_pool_status(self) -> Dict[str, Any]:
        """
        Gets comprehensive status information about the connection pool.
        
        Returns:
            Dict[str, Any]: Dictionary containing detailed pool status.
        """
        if not self._pool:
            return {
                "initialized": False,
                "alias": self.alias(),
                "hash": self.hash()
            }
            
        metrics = self._metrics.get(self.hash(), {})
        
        return {
            "initialized": True,
            "alias": self.alias(),
            "hash": self.hash(),     
            "min_size": self._pool.min_size,
            "max_size": self._pool.max_size,
            "current_size": self._pool.size,
            "in_use": self._pool.in_use,
            "idle": self._pool.idle,
            "active_connections": len(self._connections),
            "shutting_down": self._shutting_down.get(self.hash(), False),
            "metrics": {
                "total_acquired": metrics.get("total_acquired", 0),
                "total_released": metrics.get("total_released", 0),
                "current_active": metrics.get("current_active", 0),
                "peak_active": metrics.get("peak_active", 0),
                "errors": metrics.get("errors", 0),
                "timeouts": metrics.get("timeouts", 0),
                "last_timeout": metrics.get("last_timeout_timestamp"),
                "avg_acquisition_time": metrics.get("avg_acquisition_time", 0),
            }
        }
    
    @classmethod
    async def health_check_all_pools(cls) -> Dict[str, bool]:
        """
        Checks the health of all connection pools.
        
        Returns:
            Dict[str, bool]: Dictionary mapping pool keys to health status.
        """
        results = {}
        for key, pool in cls._shared_pools.items():
            try:
                is_healthy = await pool.health_check()
                results[key] = is_healthy
            except Exception:
                results[key] = False
        return results    

    @classmethod
    def get_pool_metrics(cls, config_hash=None):
        if config_hash:
            return cls._metrics.get(config_hash, {})
        return cls._metrics
    
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

    @property
    def _connections(self) -> Set[AsyncConnection]:
        """Gets the set of active connections for this instance's configuration."""
        k = self.hash()
        if k not in self._active_connections:
            self._active_connections[k] = set()
        return self._active_connections[k]      
   
    async def _get_connection_from_pool(self, wrap_raw_connection: Callable) -> AsyncConnection:
        """
        Acquires a connection from the pool with timeout handling and leak tracking.
        """
        if self._shutting_down.get(self.hash(), False):
            raise RuntimeError(f"Cannot acquire new connections: pool for {self.alias()} is shutting down")
        
        if not self._pool:
            await self._initialize_pool_if_needed()
        if not self._pool:
            raise Exception(f"Cannot get a connection from the pool as the pool could not be initialized for {self.alias()} - {self.hash()}")
        
        # Define a timeout for connection acquisition (in seconds)
        acquisition_timeout = getattr(self, 'connection_acquisition_timeout', 10.0)
        
        try:
            start_time = time.time()
            try:
                # Acquire connection
                raw_conn = await self._pool.acquire(timeout=acquisition_timeout)
                acquisition_time = time.time() - start_time
                logger.debug(f"Connection acquired from {self.alias()} pool in {acquisition_time:.2f}s")
                self._track_metrics(True)
            except TimeoutError as e:
                acquisition_time = time.time() - start_time
                logger.warning(f"Timeout acquiring connection from {self.alias()} pool after {acquisition_time:.2f}s")
                self._track_metrics(is_new=False, error=None, is_timeout=True)
                raise  # Re-raise the TimeoutError
                
        except Exception as e:
            if isinstance(e, TimeoutError):
                # Re-raise the timeout
                raise
                
            # Other errors
            pool_info = {
                'active_connections': len(self._connections),
                'pool_exists': self._pool is not None,
            }
            logger.error(f"Connection acquisition failed for {self.alias()} pool: {e}, pool info: {pool_info}")
            self._track_metrics(True, e)           
            raise
        
        async_conn = wrap_raw_connection(raw_conn)
        
        # Add tracking information for leak detection
        async_conn._acquired_time = time.time()
        async_conn._acquired_stack = traceback.format_stack()
        
        self._connections.add(async_conn)
        return async_conn

    async def _release_connection_to_pool(self, async_conn: AsyncConnection) -> None:
        try:
            # Calculate how long this connection was out
            if hasattr(async_conn, '_acquired_time'):
                duration = time.time() - async_conn._acquired_time
                
                # Log if this connection was out for a long time
                if duration > 60:  # 1 minute
                    logger.warning(
                        f"Connection from {self.alias()} pool was out for {duration:.2f}s. "
                        f"This may indicate inefficient usage. Stack trace at acquisition:\n"
                        f"{getattr(async_conn, '_acquired_stack', 'Stack not available')}"
                    )
                
                # Clean up tracking attributes
                delattr(async_conn, '_acquired_time')
                delattr(async_conn, '_acquired_stack')
            
            start_time = time.time()
            # Use the ConnectionPool interface
            await self._pool.release(async_conn.get_raw_connection())
            logger.debug(f"Connection released back to {self.alias()} pool in {(time.time() - start_time):.2f}s")
            self._track_metrics(False)
        except Exception as e:
            pool_info = {
                'active_connections': len(self._connections),
                'pool_exists': self._pool is not None,
            }
            logger.error(f"Connection release failed for {self.alias()} pool: {e}, pool info: {pool_info}")
            self._track_metrics(False, e)
            raise
        self._connections.discard(async_conn)

    async def check_for_leaked_connections(self, threshold_seconds=300):
        """
        Check for connections that have been active for longer than the threshold.
        Returns a list of (connection, duration, stack) tuples for leaked connections.
        """
        now = time.time()
        leaked_connections = []
        
        for conn in self._connections:
            if hasattr(conn, '_acquired_time'):
                duration = now - conn._acquired_time
                if duration > threshold_seconds:
                    leaked_connections.append((
                        conn,
                        duration,
                        getattr(conn, '_acquired_stack', 'Stack not available')
                    ))
        
        # Log any leaks
        for conn, duration, stack in leaked_connections:
            logger.warning(
                f"Connection leak detected in {self.alias()} pool! "
                f"Connection has been active for {duration:.2f}s. "
                f"Stack trace at acquisition:\n{stack}"
            )
        
        return leaked_connections

    async def _initialize_pool_if_needed(self) -> None:
        """
        Initializes the connection pool if it doesn't exist or isn't usable.
        
        This method first checks if a pool already exists and is usable by attempting to acquire a connection and run a test query. If the pool doesn't exist or isn't usable, a new pool is created.
        
        Thread Safety:
            - Pool creation is protected by a per-configuration lock
            - Multiple concurrent calls will only create one pool instance
            - The lock ensures only one thread can initialize a pool at a time
            - After initialization, the pool itself must handle concurrent access
            
        Concurrency:
            - Safe for multiple concurrent calls from the same event loop
            - Database connections are tested with a simple SELECT 1 query
            - Failed pools are properly closed before recreating them
            - Connections acquired for testing are properly released back to the pool
        """
        # Check if existing pool is usable
        if self._pool:
            is_healthy = False
            try:
                is_healthy = await self._pool.health_check()
            except Exception as e:
                pass
            if not is_healthy:
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
                    start_time = time.time()
                    self._pool = await self._create_pool(self)
                    logger.info(f"{self.alias()} - {self.hash()} async pool initialized in {(time.time() - start_time):.2f}s")
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
    async def _cleanup_connection(cls, async_conn: AsyncConnection):
        try:            
            try:
                await async_conn.commit_transaction_async()
            except Exception as e:
                logger.warning(f"Error committing transaction during cleanup: {e}")

            try:      
                raw_conn = async_conn.get_raw_connection()
                for key, conn_set in cls._active_connections.items():
                    if async_conn in conn_set:
                        pool = cls._shared_pools.get(key)
                        if pool:
                            await pool.release(raw_conn)
                        conn_set.discard(async_conn)
                        break
            except Exception as e:
                logger.warning(f"Error releasing connection during cleanup: {e}")
        except Exception as e:
            logger.error(f"Error during connection cleanup: {e}")

    @classmethod
    async def _release_pending_connections(cls, key, timeout):
        # Handle active connections first
        active_conns = cls._active_connections.get(key, set())
        if active_conns:
            logger.info(f"Cleaning up {len(active_conns)} active connections for pool {key}")
            
            # Process each tracked connection with a timeout
            cleanup_tasks = []
            for conn in list(active_conns):
                task = asyncio.create_task(cls._cleanup_connection(conn))
                cleanup_tasks.append(task)
            
            # Wait for all connections to be cleaned up with timeout
            if cleanup_tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*cleanup_tasks), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for connections to be released for pool {key}")

    @classmethod
    async def close_pool(cls, config_hash: Optional[str] = None, timeout: Optional[float]=60) -> None:
        """
        Closes one or all shared connection pools with proper cleanup.

        This method should be called during application shutdown to properly
        release database resources. It first prevents new connections from being acquired,
        then attempts to gracefully commit and release all active connections before
        closing the pool.

        Args:
            config_hash (Optional[str], optional): Hash of the configuration
                for the pool to close. If None, all pools will be closed.
                Defaults to None.
            timeout (Optional[float]): The number of seconds to wait before
                canceling the proper commit+release of pending connections. 
                If timeout is reached, will forcibly close connections (losing active transactions) (at least for Postgres, MySql and Sqlite)
        """
        keys = [config_hash] if config_hash else list(cls._shared_pools.keys())
        
        # First mark all specified pools as shutting down
        for key in keys:
            cls._shutting_down[key] = True
            logger.info(f"Pool {key} marked as shutting down, no new connections allowed")
        
        # Then process each pool
        for key in keys:
            try:
                await AsyncPoolManager._release_pending_connections(key, timeout)
                pool = cls._shared_pools.get(key)
                if pool:
                    try:
                        # Use the ConnectionPool interface force parameter
                        await pool.close(force=True)
                        logger.info(f"Pool for {key} closed")
                    except Exception as e:
                        logger.error(f"Error closing pool for {key}: {e}")
            finally:
                # Clean up all references to this pool
                cls._shared_pools.pop(key, None)
                cls._shared_locks.pop(key, None)
                cls._active_connections.pop(key, None)
                cls._shutting_down.pop(key, None)

    @abstractmethod
    async def _create_pool(self, config: Dict) -> ConnectionPool:
        """
        Creates a new connection pool.
        
        This abstract method must be implemented by subclasses to create a
        ConnectionPool implementation specific to the database backend being used.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            ConnectionPool: A connection pool that implements the ConnectionPool interface.
        """
        raise NotImplementedError()

class DatabaseConnectionManager(AsyncPoolManager, DatabaseConfig):
    """
    Manages synchronized and asynchronous database connection lifecycles.
    
    This class provides a unified interface for obtaining both sync and async database connections, with proper resource management through context managers. It handles connection pooling for async connections and caching for sync connections.
    
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
                asyncio.get_running_loop().create_task(self._leak_detection_task())
            except RuntimeError:
                self._sync_conn = self.get_sync_connection()
        else:
            self._sync_conn = self.get_sync_connection()

    async def _leak_detection_task(self):
        """Background task that periodically checks for connection leaks"""
        while True:
            try:
                await self.check_for_leaked_connections()
            except Exception as e:
                logger.error(f"Error in leak detection: {e}")
            
            # Check every 5 minutes
            await asyncio.sleep(300)

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
        
        This method returns an existing connection if one is already cached, or creates a new one if needed. The connection is wrapped in the SyncConnection interface for standardized access.
        
        Thread Safety:
            - NOT thread-safe: the cached connection is per-instance
            - Should only be called from a single thread
            - Multiple instances should be used for multi-threaded applications
        
        Returns:
            SyncConnection: A database connection for synchronous operations.
            
        Note:
            The connection should be closed with release_sync_connection() or by using the sync_connection() context manager.
        """
        if self._sync_conn is None:
            try:
                start_time = time.time()
                raw_conn = self._create_sync_connection(self.config())
                logger.info(f"Sync connection created and cached for {self.alias()} in {(time.time() - start_time):.2f}s")
            except Exception as e:
                logger.error(f"Could not create a sync connection for {self.alias()}")
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
        
        This method ensures the connection pool is initialized, then acquires a connection from it and wraps it in the AsyncConnection interface for standardized access.
        
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
            The connection should be released with release_async_connection() or by using the async_connection() context manager.
        """
        await self._initialize_pool_if_needed()
        async_conn = await self._get_connection_from_pool(self._wrap_async_connection)
        return async_conn

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
                await self._release_connection_to_pool(async_conn)
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
        raise Exception("Derived class must implement this")

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
        raise Exception("Derived class must implement this")

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
        raise Exception("Derived class must implement this")  


class BaseDatabase(DatabaseConnectionManager):
    '''
    Base class for all database implementations.
    
    This class inherits from DatabaseConnectionManager to provide connection management functionality. Specific database implementations (PostgreSQL, MySQL, SQLite) should inherit from this class and implement the required abstract methods.
    
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
                 password: str=None, alias: str=None, env: str='prod', 
                 connection_acquisition_timeout: float=10.0, *args, **kwargs):
        # Store the timeout value
        self.connection_acquisition_timeout = connection_acquisition_timeout
        
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

    def _calculate_pool_size(self) -> Tuple[int, int]:
        """Calculate optimal pool size based on environment"""        
        if self.env() == 'prod':
            cpus = os.cpu_count() or 1
            min_size = max(2, cpus // 4)
            max_size = cpus * 2
        else:
            min_size = 1
            max_size = 5
        return min_size, max_size

    @contextlib.asynccontextmanager
    async def async_transaction(self) -> AsyncIterator[AsyncConnection]:
        """
        Async context manager for database transactions.
        
        This ensures that operations performed within the context are either
        all committed or all rolled back in case of an exception. Handles
        proper connection lifecycle and transaction boundaries.
        
        Database-specific transaction behaviors (such as MySQL auto-committing
        on DDL statements) are handled by the underlying connection implementations.
        
        Yields:
            AsyncConnection: A database connection with an active transaction.
            
        Example:
            async with db.async_transaction() as conn:
                await conn.execute_async("INSERT INTO users (name) VALUES (?)", ("Alice",))
                await conn.execute_async("UPDATE user_counts SET count = count + 1")
        """
        async with self.async_connection() as conn:
            logger.debug(f"Beginning transaction on {self.alias()} ({self.hash()[:8]})")
            await conn.begin_transaction_async()
            try:
                yield conn
                logger.debug(f"Committing transaction on {self.alias()} ({self.hash()[:8]})")
                await conn.commit_transaction_async()
            except Exception as e:
                logger.debug(f"Rolling back transaction on {self.alias()} ({self.hash()[:8]}) due to: {type(e).__name__}: {e}")
                await conn.rollback_transaction_async()
                raise
    
    @contextlib.contextmanager
    def sync_transaction(self) -> Iterator[SyncConnection]:
        """
        Synchronous context manager for database transactions.
        
        This ensures that operations performed within the context are either
        all committed or all rolled back in case of an exception. Handles
        proper connection lifecycle and transaction boundaries.
        
        Database-specific transaction behaviors (such as MySQL auto-committing
        on DDL statements) are handled by the underlying connection implementations.
        
        Yields:
            SyncConnection: A database connection with an active transaction.
            
        Example:
            with db.sync_transaction() as conn:
                conn.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
                conn.execute("UPDATE user_counts SET count = count + 1")
        """
        with self.sync_connection() as conn:
            logger.debug(f"Beginning sync transaction on {self.alias()} ({self.hash()[:8]})")
            conn.begin_transaction()
            try:
                yield conn
                logger.debug(f"Committing sync transaction on {self.alias()} ({self.hash()[:8]})")
                conn.commit_transaction()
            except Exception as e:
                logger.debug(f"Rolling back sync transaction on {self.alias()} ({self.hash()[:8]}) due to: {type(e).__name__}: {e}")
                conn.rollback_transaction()
                raise

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
        self._param_converter = PostgresSyncConverter()

    @property
    def parameter_converter(self) -> SqlParameterConverter:
        """Returns the PostgreSQL parameter converter."""
        return self._param_converter
    
    def _execute(self, sql, params=None) -> Any:
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

    def _executemany(self, sql, param_list) -> Any:
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
        self._param_converter = PostgresAsyncConverter()

    @property
    def parameter_converter(self) -> SqlParameterConverter:
        """Returns the PostgreSQL parameter converter."""
        return self._param_converter
    
    def get_raw_connection(self):
        """
        Returns the underlying raw asyncpg connection.
        
        Returns:
            The raw asyncpg connection object.
        """
        return self._conn

    async def _execute_async(self, sql, params=None) -> Any:
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
    
    async def _executemany_async(self, sql: str, param_list: List[tuple]) -> Any:
        """
        Executes a SQL query multiple times with different parameters.
        Since asyncpg doesn't have a direct executemany equivalent, this method
        executes the query in a loop for each parameter set.
        """
        results = []
        for params in param_list:
            # Note: asyncpg expects parameters as separate arguments
            result = await self._conn.execute(sql, *params)
            if result:
                results.append(result)
        return results

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


class PostgresConnectionPool(ConnectionPool):
    """
    PostgreSQL implementation of ConnectionPool using asyncpg.
    
    This class wraps asyncpg's connection pool to provide a standardized interface
    and additional functionality for connection management.
    
    Attributes:
        _pool: The underlying asyncpg pool
        _timeout: Default timeout for connection acquisition
        _last_health_check: Timestamp of the last health check
        _health_check_interval: Minimum time between health checks in seconds
        _healthy: Current known health state
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
        self._last_health_check = 0
        self._health_check_interval = 5.0  # Check at most every 5 seconds
        self._healthy = True
    
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
    
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The asyncpg connection to release
        """
        await self._pool.release(connection)
    
    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:
            force: If True, forcibly terminate connections
            timeout: Maximum time to wait for graceful shutdown when force=False
        """
        # asyncpg.Pool.close() has a cancel_tasks parameter that maps to our force parameter
        await self._pool.close(cancel_tasks=force)
    
    async def health_check(self) -> bool:
        """
        Checks if the pool is healthy by testing a connection.
        
        To avoid excessive health checks, this caches the result for a short time.
        
        Returns:
            True if the pool is healthy, False otherwise
        """
        now = time.time()
        if now - self._last_health_check < self._health_check_interval and self._healthy:
            return self._healthy
            
        self._last_health_check = now
        try:
            conn = await self.acquire()
            try:
                await conn.execute("SELECT 1")
                self._healthy = True
                return True
            finally:
                await self.release(conn)
        except Exception:
            self._healthy = False
            return False
    
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
    
    async def execute_on_pool(self, sql: str, params: Optional[Tuple] = None) -> Any:
        """
        Executes a query on a temporary connection from the pool.
        
        Args:
            sql: The SQL query to execute
            params: Query parameters
            
        Returns:
            The query result
        """
        conn = await self.acquire()
        try:
            return await conn.execute(sql, *(params or []))
        finally:
            await self.release(conn)

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
       
    async def _create_pool(self, config: Dict) -> ConnectionPool:
        """
        Creates a PostgreSQL connection pool wrapped in our interface.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            ConnectionPool: A PostgreSQL-specific pool implementation.
        """
        min_size, max_size = self._calculate_pool_size()
        raw_pool = await asyncpg.create_pool(
            min_size=min_size, 
            max_size=max_size, 
            command_timeout=60.0, 
            **config
        )
        return PostgresConnectionPool(
            raw_pool, 
            timeout=self.connection_acquisition_timeout
        )
    
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
        self._param_converter = MySqlConverter()

    @property
    def parameter_converter(self) -> SqlParameterConverter:
        """Returns the PostgreSQL parameter converter."""
        return self._param_converter

    def _execute(self, sql, params=None) -> Any:
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

    def _executemany(self, sql, param_list) -> Any:
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
        self._param_converter = MySqlConverter()

    @property
    def parameter_converter(self) -> SqlParameterConverter:
        """Returns the PostgreSQL parameter converter."""
        return self._param_converter

    def get_raw_connection(self):
        """
        Returns the underlying raw aiomysql connection.
        
        Returns:
            The raw aiomysql connection object.
        """
        return self._conn

    async def _execute_async(self, sql, params=None) -> Any:
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

    async def _executemany_async(self, sql, param_list) -> Any:
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
        
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed,
        regardless of whether you've explicitly started a transaction.
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
    
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed, and any previous insert/update would not be rolled back.
        """
        await self._conn.rollback()

    async def close_async(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        self._conn.close()

class MySqlConnectionPool(ConnectionPool):
    """
    MySQL implementation of ConnectionPool using aiomysql.
    
    This class wraps aiomysql's connection pool to provide a standardized interface
    and additional functionality for connection management.
    
    Attributes:
        _pool: The underlying aiomysql pool
        _timeout: Default timeout for connection acquisition
        _last_health_check: Timestamp of the last health check
        _health_check_interval: Minimum time between health checks in seconds
        _healthy: Current known health state
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
        self._last_health_check = 0
        self._health_check_interval = 5.0  # Check at most every 5 seconds
        self._healthy = True
    
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
    
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The aiomysql connection to release
        """
        self._pool.release(connection)
    
    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:
            force: If True, forcibly terminate connections
            timeout: Maximum time to wait for graceful shutdown when force=False
        """
        if force:
            # aiomysql doesn't have a direct force close option
            # This is a workaround to mark the pool as closing and wake up waiters
            self._pool._closing = True
            if hasattr(self._pool, '_cond') and hasattr(self._pool._cond, 'notify_all'):
                self._pool._cond._loop.call_soon(self._pool._cond.notify_all)
        await self._pool.close()
    
    async def health_check(self) -> bool:
        """
        Checks if the pool is healthy by testing a connection.
        
        To avoid excessive health checks, this caches the result for a short time.
        
        Returns:
            True if the pool is healthy, False otherwise
        """
        now = time.time()
        if now - self._last_health_check < self._health_check_interval and self._healthy:
            return self._healthy
            
        self._last_health_check = now
        try:
            conn = await self.acquire()
            try:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    # Must fetch result to complete the query
                    await cur.fetchone()
                self._healthy = True
                return True
            finally:
                await self.release(conn)
        except Exception:
            self._healthy = False
            return False
    
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
    
    async def execute_on_pool(self, sql: str, params: Optional[Tuple] = None) -> Any:
        """
        Executes a query on a temporary connection from the pool.
        
        Args:
            sql: The SQL query to execute
            params: Query parameters
            
        Returns:
            The query result
        """
        conn = await self.acquire()
        try:
            async with conn.cursor() as cur:
                await cur.execute(sql, params or ())
                return await cur.fetchall()
        finally:
            await self.release(conn)

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

    async def _create_pool(self, config: Dict) -> ConnectionPool:
        """
        Creates a MySQL connection pool wrapped in our interface.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            ConnectionPool: A MySQL-specific pool implementation.
        """
        min_size, max_size = self._calculate_pool_size()
        cfg = config.copy()
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
        self._param_converter = SqliteConverter()

    @property
    def parameter_converter(self) -> SqlParameterConverter:
        """Returns the PostgreSQL parameter converter."""
        return self._param_converter

    def _execute(self, sql, params=None) -> Any:
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

    def _executemany(self, sql, param_list) -> Any:
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
        self._param_converter = SqliteConverter()

    @property
    def parameter_converter(self) -> SqlParameterConverter:
        """Returns the PostgreSQL parameter converter."""
        return self._param_converter

    def get_raw_connection(self):
        """
        Returns the underlying raw aiosqlite connection.
        
        Returns:
            The raw aiosqlite connection object.
        """
        return self._conn

    async def _execute_async(self, sql, params=None) -> Any:
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

    async def _executemany_async(self, sql, param_list) -> None:
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
        self._last_health_check = 0
        self._health_check_interval = 5.0
        self._healthy = True
    
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
    
    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
        """
        Closes the SQLite connection.
        
        Args:
            force: If True, close immediately regardless of active use
            timeout: Maximum time to wait for the connection to be released when force=False
        """
        if force:
            # Force close immediately
            await self._conn.close()
        else:
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
    
    async def health_check(self) -> bool:
        """
        Checks if the SQLite connection is healthy.
        
        Returns:
            True if the connection is healthy, False otherwise
        """
        now = time.time()
        if now - self._last_health_check < self._health_check_interval and self._healthy:
            return self._healthy
            
        self._last_health_check = now
        
        # If the connection is in use, assume it's healthy
        if self._in_use:
            return True
            
        # Otherwise, test it
        try:
            async with self._lock:
                await self._conn.execute("SELECT 1")
                self._healthy = True
                return True
        except Exception:
            self._healthy = False
            return False
    
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
    
    async def execute_on_pool(self, sql: str, params: Optional[Tuple] = None) -> Any:
        """
        Executes a query on the SQLite connection.
        
        Args:
            sql: The SQL query to execute
            params: Query parameters
            
        Returns:
            The query result
        """
        conn = await self.acquire()
        try:
            async with conn.execute(sql, params or ()) as cursor:
                return await cursor.fetchall()
        finally:
            await self.release(conn)

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

    async def _create_pool(self, config: Dict) -> ConnectionPool:
        """
        Creates a SQLite connection wrapped in our pool interface.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            ConnectionPool: A SQLite-specific pool implementation.
        """
        db_path = config["database"]
        conn = await aiosqlite.connect(db_path)
        return SqliteConnectionPool(
            conn,
            timeout=self.connection_acquisition_timeout
        )
    
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


class DatabaseFactory:
    @staticmethod
    def create_database(db_type: str, db_config: DatabaseConfig) -> BaseDatabase:
        """Factory method to create the appropriate database instance"""
        if db_type.lower() == 'postgres':
            return PostgresDatabase(**db_config.config())
        elif db_type.lower() == 'mysql':
            return MySqlDatabase(**db_config.config())
        elif db_type.lower() == 'sqlite':
            return SqliteDatabase(**db_config.config())
        else:
            raise ValueError(f"Unsupported database type: {db_type}")