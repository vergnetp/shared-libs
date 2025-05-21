import asyncio
from typing import Any, Optional
import aiomysql

from ....utils import async_method

from ...config import DatabaseConfig
from ...pools import  ConnectionPool, PoolManager

class MySqlConnectionPool(ConnectionPool):
    """
    MySQL implementation of ConnectionPool using aiomysql.
    
    This class wraps aiomysql's connection pool to provide a standardized interface
    and additional functionality for connection management.
    
    Attributes:
        _pool: The underlying aiomysql pool
        _timeout: Default timeout for connection acquisition
    """
    
    def __init__(self, pool):
        """
        Initialize a MySQL connection pool wrapper.
        
        Args:
            pool: The underlying aiomysql pool
            timeout: Default timeout for connection acquisition in seconds
        """
        self._pool = pool      
     
    @async_method
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires a connection from the pool with timeout.
        
        Args:
            timeout: Maximum time to wait for connection, defaults to 10 seconds
            
        Returns:
            The raw aiomysql connection
            
        Raises:
            TimeoutError: If connection acquisition times out
        """
        timeout = timeout if timeout is not None else 10
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
    async def _create_pool(self, config: DatabaseConfig) -> ConnectionPool:
        min_size, max_size = self._calculate_pool_size()
        raw_pool = await asyncio.wait_for(
            aiomysql.create_pool(
                minsize=min_size, 
                maxsize=max_size, 
                host=config.host(),
                port=config.port(),
                user=config.user(),
                password=config.password(),
                db=config.database(),
                charset='utf8mb4',  # Recommended for proper UTF-8 support
                autocommit=False,
                connect_timeout=config.connection_creation_timeout
            ),
            timeout=config.pool_creation_timeout
        )
        return MySqlConnectionPool(
            raw_pool           
        )
 