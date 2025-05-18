
import sys
import time
import asyncio
import threading
import contextlib
from typing import Dict, Any, Iterator
from abc import abstractmethod
from ...errors import try_catch
from ... import log as logger
from ...utils import async_method
from ..config import DatabaseConfig
from .base import SyncConnection, AsyncConnection
from .pools import PoolManager


class ConnectionManager():
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
        - DO NOT share a ConnectionManager instance across threads
    
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
    
    Args:
        config (DatabaseConfig)     
        ...
    """
    def __init__(self, config: DatabaseConfig=None, database: str=None, host: str="localhost", port: int=5432, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod', 
                 connection_acquisition_timeout: float=10.0, *args, **kwargs):
        super().__init__(*args,**kwargs)
        
        # todo: move in config
        self._connection_acquisition_timeout = connection_acquisition_timeout
        
        # todo add validation or remove named args
        if config:
            self.config = config
        else:
            self.config = DatabaseConfig(
            database=database, 
            host=host, 
            port=port, 
            user=user, 
            password=password, 
            alias=alias, 
            env=env)           
              
        # Use thread-local storage for sync connections
        self._local = threading.local()
        self._local._sync_conn = None     

        if not self.is_environment_async():
            self._local._sync_conn = self.get_sync_connection()

    @property
    def connection_acquisition_timeout(self) -> float:
        '''Returns the connection acqusition timeout defined in the ConnectionManager'''
        return self._connection_acquisition_timeout
    
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
    
    @try_catch
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
        thread_id = threading.get_ident()
        logger.info(f"Thread {thread_id}: Requesting sync connection for {self.config.alias()}")
    

        if not hasattr(self._local, '_sync_conn') or self._local._sync_conn is None:
            try:
                start_time = time.time()
                raw_conn = self._create_sync_connection(self.config.config())
                logger.info(f"Thread {thread_id}: Sync connection created and cached for {self.config.alias()} in {(time.time() - start_time):.2f}s")
                self._local._sync_conn = self._wrap_sync_connection(raw_conn)
            except Exception as e:
                logger.error(f"Thread {thread_id}: Could not create a sync connection for {self.config.alias()}: {e}")                     
        else:
            logger.info(f"Thread {thread_id}: Reusing existing sync connection for {self.config.alias()}")
        
        return self._local._sync_conn     

    @try_catch
    def release_sync_connection(self) -> None:
        """
        Closes and releases the cached synchronous connection.
        
        This method should be called when the connection is no longer needed
        to properly release database resources. After calling this method,
        the next call to get_sync_connection() will create a new connection.
        """
        if hasattr(self._local, '_sync_conn') and self._local._sync_conn:
            try:
                self._local._sync_conn.close()
                logger.debug(f"{self.config.alias()} sync connection closed")
            except Exception as e:
                logger.warning(f"{self.config.alias()} failed to close sync connection: {e}")
            self._local._sync_conn = None

    @contextlib.contextmanager
    def sync_connection(self) -> Iterator[SyncConnection]:
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

    @try_catch
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
   
    @async_method
    @try_catch
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
        await self.pool_manager._initialize_pool_if_needed()
        async_conn = await self.pool_manager._get_connection_from_pool(self._wrap_async_connection)
        return async_conn

    @async_method
    @try_catch
    async def release_async_connection(self, async_conn: AsyncConnection):
        """
        Releases an asynchronous connection back to the pool.
        
        This method should be called when the connection is no longer needed
        to make it available for reuse by other operations.
        Connections are always properly tracked even if release fails, preventing connection leaks.
        
        Args:
            async_conn (AsyncConnection): The connection to release.
        """
        if not async_conn or not self.pool_manager._pool:
            return
            
        try:
            await self.pool_manager._release_connection_to_pool(async_conn)
        except Exception as e:
            logger.error(f"{self.config.alias()} failed to release async connection: {e}")
            
            # Try to close the connection directly to prevent resource leaks
            try:
                await async_conn.close()
            except Exception as close_error:
                logger.error(f"Failed to close leaked connection: {close_error}")
            
            # Try to maintain pool health by creating a replacement connection
            try:
                asyncio.create_task(self.pool_manager._initialize_pool_if_needed())
            except Exception:
                pass

    #@async_method
    @contextlib.asynccontextmanager
    async def async_connection(self) -> Iterator[AsyncConnection]:
        """
        Async context manager for safe asynchronous connection usage.
        
        This context manager ensures that the connection is properly released
        when the block exits, even if an exception occurs.
        
        Yields:
            AsyncConnection: A database connection for asynchronous operations.
            
        Example:
            async with db.async_connection() as conn:
                await conn.execute("SELECT * FROM users")
        """
        conn = await self.get_async_connection()
        try:
            yield conn
        finally:
            await self.release_async_connection(conn)
    
    # endregion

    @property
    @abstractmethod
    def pool_manager(self) -> PoolManager:
        raise Exception("Derived class must implement this")


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
    @try_catch
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
