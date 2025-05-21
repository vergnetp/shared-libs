import time
from typing import Any, Optional
from abc import ABC, abstractmethod

from ...errors import try_catch
from ...utils import async_method


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
    @async_method
    @try_catch
    async def health_check(self) -> bool:
        """
        Checks if the pool is healthy by testing a connection.
        
        To avoid excessive health checks, this caches the result for a short time.
        
        Returns:
            True if the pool is healthy, False otherwise
        """
        # Get cache values from instance attributes or provide defaults
        last_health_check = getattr(self, '_last_health_check', 0)
        health_check_interval = getattr(self, '_health_check_interval', 5.0)
        healthy = getattr(self, '_healthy', True)
        
        now = time.time()
        if now - last_health_check < health_check_interval and healthy:
            return healthy
            
        setattr(self, '_last_health_check', now)
        try:
            conn = await self.acquire()
            try:
                # This is the database-specific part - subclasses should override
                await self._test_connection(conn)
                setattr(self, '_healthy', True)
                return True
            finally:
                await self.release(conn)
        except Exception:
            setattr(self, '_healthy', False)
            return False
    
    @try_catch
    @abstractmethod
    async def _test_connection(self, connection: Any) -> None:
        """Run a database-specific test query on the connection"""
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires a connection from the pool with optional timeout.
        
        Args:
            timeout (Optional[float]): Maximum time in seconds to wait for a connection.
                                      If None, defaults to 10 seconds.
        
        Returns:
            Any: A database connection specific to the underlying driver.
            
        Raises:
            TimeoutError: If the acquisition times out.
            Exception: For other acquisition errors.
        """
        pass
        
    @async_method
    @try_catch
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
        
    @async_method
    @try_catch
    @abstractmethod
    async def close(self, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:          
            timeout (Optional[float]): Maximum time in seconds to wait for graceful shutdown                                                           

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
   