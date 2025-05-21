import asyncio
from typing import  Any, Optional
import aiosqlite

from ....utils import async_method

from ...config import DatabaseConfig
from ...pools import ConnectionPool, PoolManager

        
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
    
    def __init__(self, conn):
        """
        Initialize a SQLite connection pool wrapper.
        
        Args:
            conn: The single aiosqlite connection
            timeout: Default timeout for connection acquisition in seconds
        """
        self._conn = conn
        self._in_use = False       
        self._lock = asyncio.Lock()
    
    @async_method
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires the SQLite connection if it's not in use.
        
        SQLite doesn't support concurrent access to the same connection,
        so this implementation only allows one client to use the connection
        at a time.
        
        Args:
            timeout: Maximum time to wait for the connection to be available. Default to 10 seconds.
            
        Returns:
            The SQLite connection
            
        Raises:
            TimeoutError: If the connection is busy for too long
        """
        timeout = timeout if timeout is not None else 10
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
        
        # Close the connection - this should be outside the if block
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
    async def _create_pool(self, config: DatabaseConfig) -> ConnectionPool:
        db_path = config.config()["database"]
        conn = await aiosqlite.connect(db_path)
        return SqliteConnectionPool(
            conn           
        )
    
