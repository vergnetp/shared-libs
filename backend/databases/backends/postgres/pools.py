import asyncio
from typing import Any, Optional
import asyncpg

from ....utils import async_method

from ...config import DatabaseConfig
from ...pools import  ConnectionPool, PoolManager

   
class PostgresConnectionPool(ConnectionPool):
    """
    PostgreSQL implementation of ConnectionPool using asyncpg.
    
    This class wraps asyncpg's connection pool to provide a standardized interface
    and additional functionality for connection management.
    
    Attributes:
        _pool: The underlying asyncpg pool
        _timeout: Default timeout for connection acquisition
    """
    
    def __init__(self, pool):
        """
        Initialize a PostgreSQL connection pool wrapper.
        
        Args:
            pool: The underlying asyncpg pool            
        """
        self._pool = pool             
       
    @async_method
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires a connection from the pool with timeout.
        
        Args:
            timeout: Maximum time to wait for connection, defaults to 10 seconds
            
        Returns:
            The raw asyncpg connection
            
        Raises:
            TimeoutError: If connection acquisition times out
        """
        timeout = timeout if timeout is not None else 10
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
    async def _create_pool(self, config: DatabaseConfig) -> ConnectionPool:
        min_size, max_size = self._calculate_pool_size()        
        raw_pool = await asyncio.wait_for(asyncpg.create_pool(
            min_size=min_size, 
            max_size=max_size,            
            host=config.host(),
            port=config.port(),
            database=config.database(),
            user=config.user(),
            password=config.password(),
            timeout=config.connection_creation_timeout        
        ), timeout=config.pool_creation_timeout)
        return PostgresConnectionPool(
            raw_pool           
        )
    