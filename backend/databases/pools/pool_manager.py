import os
import sys
import time
import json
import asyncio
import traceback
from typing import Dict, Any, Optional, Tuple, Callable, Set, ClassVar, Final, List
from abc import ABC, abstractmethod

from ...errors import try_catch
from ... import log as logger
from ...utils import async_method

from ..config import DatabaseConfig
from ..connections import AsyncConnection
from .connection_pool import ConnectionPool
  
class PoolManager(ABC):
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
        _shutting_down: [Dict[str, bool]: Keep track of pools shutdown status
        _metrics: Dict[str, Dict[str, int]]: keep track of some metrics for each pool (e.g. how many connection acquisitions timed out)
    """
    _shared_pools: ClassVar[Final[Dict[str, Any]]] = {}
    _shared_locks: ClassVar[Final[Dict[str, asyncio.Lock]]] = {}
    _active_connections: ClassVar[Final[Dict[str, Set[AsyncConnection]]]] = {}
    _shutting_down: ClassVar[Final[Dict[str, bool]]] = {}
    _metrics: ClassVar[Final[Dict[str, Dict[str, int]]]] = {}
    _metrics_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    
    def __init__(self, config: DatabaseConfig):
        self._alias = config.alias()
        self._hash = config.hash()
        self.config = config 
        
        # Try to initialize pool and start leak detection task if in async environment
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._initialize_pool_if_needed())
            if "pytest" not in sys.modules:
                loop.create_task(self._leak_detection_task())
        except RuntimeError:
            # Not in an async environment, which is fine
            pass
     
    async def _leak_detection_task(self):
        """Background task that periodically checks for and recovers from connection leaks"""
        IDLE_TIMEOUT = 1800  # 30 minutes idle time before considering a connection dead
        LEAK_THRESHOLD_SECONDS = 300  # if a connection has been used for longer than 5 mins, it should be considered leaked
        SLEEP_TIME = 300  # 300 seconds are 5 mins

        # Store a reference to the task so we can cancel it later
        task_key = self.hash()
        self.__class__._leak_tasks = getattr(self.__class__, '_leak_tasks', {})
        self.__class__._leak_tasks[task_key] = asyncio.current_task()

        logger.info("Task started: will check and reclaim leaked or idle connections from the pool", 
                    pool_name=self.alias(), 
                    check_interval_mins=int(SLEEP_TIME/60))
                    
        try:
            while True:
                try:
                    # Wait to avoid excessive CPU usage
                    try:
                        await asyncio.sleep(SLEEP_TIME)  
                    except asyncio.CancelledError:
                        logger.info("Leak detection task cancelled", pool_name=self.alias())
                        return
                    
                    # Check if the pool is shutting down or removed
                    if self.hash() not in self._shared_pools or self._shutting_down.get(self.hash(), False):
                        logger.info("Pool is shutting down or removed, stopping leak detection task", 
                                pool_name=self.alias())
                        return
                    
                    # Check for leaked connections
                    leaked_conns = await self.check_for_leaked_connections(threshold_seconds=LEAK_THRESHOLD_SECONDS)  
                    
                    # Attempt recovery for leaked connections
                    for conn, duration, stack in leaked_conns:
                        try:
                            # Mark as leaked to avoid duplicate recovery attempts
                            conn._mark_leaked()
                            
                            # Try to gracefully return to the pool
                            logger.warning(f"Attempting to recover leaked connection that has leaked for {duration:.2f}s)", 
                                        pool_name=self.alias(), 
                                        duration_seconds=duration,
                                        connection_id=conn._id)
                                        
                            await self._release_connection_to_pool(conn)
                            
                            logger.info("Successfully recovered leaked connection", 
                                    pool_name=self.alias(), connection_id=conn._id)
                                    
                        except Exception as e:
                            logger.error("Failed to recover leaked connection", pool_name=self.alias(), connection_id=conn._id, error=e.to_string() if hasattr(e, 'to_string') else str(e))
                                        
                            self._connections.discard(conn)  # Explicitly discard leaked connection
                            # Try to close directly as a last resort
                            try:
                                await conn.close()
                            except Exception:
                                pass
                    
                    # Additionally check for idle connections               
                    idle_conns = []
                    
                    for conn in self._connections:
                        if conn._is_idle(IDLE_TIMEOUT) and not conn._is_leaked:
                            idle_conns.append(conn)
                    
                    # Log idle connections
                    if idle_conns:
                        logger.warning(f"There some idle connections", 
                                    pool_name=self.alias(), 
                                    idle_connections_count=len(idle_conns), 
                                    idle_threshold_mins=int(IDLE_TIMEOUT/60))

                    # Also recover idle connections
                    for conn in idle_conns:
                        try:
                            logger.warning("Recovering idle connection", 
                                        pool_name=self.alias(), connection_id=conn._id)
                                        
                            await self._release_connection_to_pool(conn)
                            
                        except Exception as e:
                            logger.error("Failed to recover idle connection", 
                                        pool_name=self.alias(), connection_id=conn._id,
                                        error=e.to_string() if hasattr(e, 'to_string') else str(e))
                                        
                except asyncio.CancelledError:
                    # Handle task cancellation
                    logger.info("Leak detection task cancelled", pool_name=self.alias())
                    return
                except Exception as e:
                    logger.error(f"Error in connection leak detection task for {self.alias()} pool: {e}", 
                                pool_name=self.alias(),
                                error=e.to_string() if hasattr(e, 'to_string') else str(e))
        finally:
            # Always remove the task reference
            leak_tasks = getattr(self.__class__, '_leak_tasks', {})
            if task_key in leak_tasks:
                del leak_tasks[task_key]
            logger.info(f"Leak detection task for {self.alias()} exiting", pool_name=self.alias())

    def alias(self):
        return self._alias

    def hash(self):
        return self._hash

    @try_catch
    def _calculate_pool_size(self) -> Tuple[int, int]:
        """
        Calculate optimal pool size based on workload characteristics.
        
        This uses a combination of:
        - CPU count (for CPU-bound workloads)
        - System memory (to avoid exhausting resources)
        - Expected concurrency
        
        Returns:
            Tuple[int, int]: (min_size, max_size) of the connection pool
        """
        # Get system information
        cpus = os.cpu_count() or 1
        
        # Try to get available memory in GB
        try:
            import psutil
            available_memory_gb = psutil.virtual_memory().available / (1024 * 1024 * 1024)
        except (ImportError, AttributeError):
            # Default assumption if psutil is not available
            available_memory_gb = 4.0
        
        estimated_mem = 0.03
        
        # Calculate max connections based on memory
        max_by_memory = int(available_memory_gb / estimated_mem * 0.5)  # Use no more than 50% of available memory

        min_size = max(3, cpus // 2)
        # Max should be enough to handle spikes but not exhaust resources
        max_size = min(max(cpus * 4, 20), max_by_memory)       
        
        # Log the calculation for transparency
        logger.debug(f"Calculated connection pool size: min={min_size}, max={max_size} " +
                    f"(cpus={cpus}, mem={available_memory_gb:.1f}GB)")
        
        return min_size, max_size

    async def _track_metrics(self, is_new: bool=True, error: Exception=None, is_timeout: bool=False):
        k = self.hash()
        async with self._metrics_lock:
            if k not in self._metrics:
                self._metrics[k] = {
                    'total_acquired': 1 if is_new and not error and not is_timeout else 0,
                    'total_released': 0,
                    'current_active': 1 if is_new and not error and not is_timeout else 0,
                    'peak_active': 1 if is_new and not error and not is_timeout else 0,
                    'errors': 0 if not error else 1,
                    'timeouts': 0 if not is_timeout else 1,
                    'last_timeout_timestamp': time.time() if is_timeout else None,
                    'avg_acquisition_time': 0.0,
                }
            else:
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
                        metrics['current_active'] = max(0, metrics['current_active'] - 1)

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
    
    @async_method
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
    def get_pool_metrics(cls, config_hash=None) -> Dict:
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
   
    @try_catch
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
                
        try:
            start_time = time.time()
            try:
                # Acquire connection
                raw_conn = await self._pool.acquire(timeout=self.config.connection_acquisition_timeout)
                acquisition_time = time.time() - start_time
                logger.debug(f"Connection acquired from {self.alias()} pool in {acquisition_time:.2f}s")
                await self._track_metrics(True)
            except TimeoutError as e:
                acquisition_time = time.time() - start_time
                logger.warning(f"Timeout acquiring connection from {self.alias()} pool after {acquisition_time:.2f}s")
                await self._track_metrics(is_new=False, error=None, is_timeout=True)
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
            await self._track_metrics(True, e)           
            raise
        
        async_conn = wrap_raw_connection(raw_conn, self.config)
        
        # Add tracking information for leak detection
        async_conn._acquired_time = time.time()
        async_conn._acquired_stack = traceback.format_stack()
        
        self._connections.add(async_conn)
        return async_conn

    @try_catch
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
            await self._pool.release(async_conn._get_raw_connection())
            logger.debug(f"Connection released back to {self.alias()} pool in {(time.time() - start_time):.2f}s")
            await self._track_metrics(False)
        except Exception as e:
            pool_info = {
                'active_connections': len(self._connections),
                'pool_exists': self._pool is not None,
            }
            logger.error(f"Connection release failed for {self.alias()} pool: {e}, pool info: {pool_info}")
            await self._track_metrics(False, e)
            raise
        finally:
            self._connections.discard(async_conn)

    @async_method
    @try_catch
    async def check_for_leaked_connections(self, threshold_seconds=300) -> List[Tuple[AsyncConnection, float, str]]:
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

    @try_catch
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
                logger.debug(f"Health check failed for {self.alias()} pool: {e}")
            
            if not is_healthy:
                logger.debug(f"Existing pool unusable for {self.alias()} - {self.hash()}")
                try:
                    await self._pool.close()
                except Exception as e:
                    logger.warning(f"Error closing unusable pool: {e}")
                self._pool = None

        async with self._pool_lock:
            if self._pool is None:
                try:
                    start_time = time.time()
                    
                    # Create the task for pool creation
                    creation_task = asyncio.create_task(self._create_pool(self.config))
                    
                    # Add a done callback to handle exceptions and prevent warnings
                    def _on_done(task):
                        try:
                            # Just access the exception to mark it as handled
                            task.exception()
                        except (asyncio.CancelledError, asyncio.InvalidStateError):
                            pass
                    
                    creation_task.add_done_callback(_on_done)
                    
                    # Wait for the task with timeout but don't cancel the task itself
                    timeout = self.config.pool_creation_timeout
                    try:
                        self._pool = await asyncio.wait_for(asyncio.shield(creation_task), timeout=timeout)
                        logger.info(f"{self.alias()} pool initialized in {(time.time() - start_time):.2f}s")
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout initializing {self.alias()} pool after {timeout}s")
                        # Don't cancel the task, let it complete in the background
                        # Just raise the timeout to the caller
                        raise TimeoutError(f"Pool initialization timed out after {timeout}s")
                        
                except Exception as e:
                    logger.error(f"Pool creation failed for {self.alias()}: {e}")
                    self._pool = None
                    raise


    @try_catch
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
    @try_catch
    async def _cleanup_connection(cls, async_conn: AsyncConnection):
        try:            
            try:
                await async_conn.commit_transaction()
            except Exception as e:
                logger.warning(f"Error committing transaction during cleanup: {e}")

            try:      
                raw_conn = async_conn._get_raw_connection()
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
    @try_catch
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

    @abstractmethod
    @try_catch
    async def _create_pool(self, config: DatabaseConfig) -> ConnectionPool:
        """
        Creates a new connection pool.
        
        This abstract method must be implemented by subclasses to create a
        ConnectionPool implementation specific to the database backend being used.
        
        Args:
            config (DatabaseConfig): Database configuration.
            
        Returns:
            ConnectionPool: A connection pool that implements the ConnectionPool interface.
        """
        raise NotImplementedError()

    @classmethod
    @try_catch
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
            
            # Cancel any leak detection tasks
            leak_tasks = getattr(cls, '_leak_tasks', {})
            if key in leak_tasks:
                task = leak_tasks[key]
                if not task.done() and not task.cancelled():
                    task.cancel()
                    try:
                        # Give the task a brief moment to clean up
                        await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
        
        # Then process each pool
        for key in keys:
            try:
                await cls._release_pending_connections(key, timeout)
                pool = cls._shared_pools.get(key)
                if pool:
                    try:
                        # Use the ConnectionPool interface force parameter
                        await pool.close()
                        logger.info(f"Pool for {key} closed")
                    except Exception as e:
                        logger.error(f"Error closing pool for {key}: {e}")
            finally:
                # Clean up all references to this pool
                cls._shared_pools.pop(key, None)
                cls._shared_locks.pop(key, None)
                cls._active_connections.pop(key, None)
                cls._shutting_down.pop(key, None)
                
                # Clean up the leak task reference
                leak_tasks = getattr(cls, '_leak_tasks', {})
                if key in leak_tasks:
                    leak_tasks.pop(key, None)