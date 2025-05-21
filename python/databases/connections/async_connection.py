import time
import uuid
import asyncio
from typing import Dict, Any, Optional, Tuple, List
from abc import abstractmethod

from ...errors import try_catch
from ...utils import async_method
from ...resilience import profile, execute_with_timeout, circuit_breaker, track_slow_method

from .connection import Connection
from ..utils.decorators import auto_transaction
from ..config import DatabaseConfig

class AsyncConnection(Connection):
    """
    Abstract base class defining the interface for asynchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends asynchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """ 
    def __init__(self, conn: Any, config: DatabaseConfig):
        super().__init__()
        self._conn = conn
        self.config = config
        self._acquired_time = None
        self._acquired_stack = None
        self._last_active_time = None
        self._leaked = False
        self._id = str(uuid.uuid4())  # Unique ID for tracking

    def _mark_active(self):
        """Mark the connection as active (used recently)"""
        self._last_active_time = time.time()
    
    def _is_idle(self, timeout_seconds: int=1800):
        """Check if the connection has been idle for too long (default to 30mns)"""
        if self._last_active_time is None:
            return False
        return (time.time() - self._last_active_time) > timeout_seconds
    
    def _mark_leaked(self):
        """Mark this connection as leaked"""
        self._leaked = True
    
    @property
    def _is_leaked(self):
        """Check if this connection has been marked as leaked"""
        return self._leaked

    
    @async_method
    @try_catch()
    @auto_transaction
    @circuit_breaker(name="async_execute")
    @track_slow_method
    @profile
    async def execute(self, sql: str, params: Optional[tuple] = None, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """
        Asynchronously executes a SQL query with standard ? placeholders.
        
        Note:
            Automatically prepares and caches statements for repeated executions.

        Args:
            sql: SQL query with ? placeholders
            params: Parameters for the query
            timeout (float, optional): a timeout, in second, after which a TimeoutError is raised
            tags: optional dictionary of tags to inject to the sql as comment
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        timeout = timeout or self.config.query_execution_timeout
        self._mark_active()        
        
        try:
            stmt = await self._get_statement_async(sql, tags)        
            raw_result = await execute_with_timeout(self._execute_statement_async, (stmt, params), timeout=timeout, override_context=True)
            result = self._normalize_result(raw_result)            
 
            return result
            
        except (TimeoutError, RuntimeError) as e:
           raise TimeoutError(f"Execute operation timed out after {timeout}s")  


    @async_method
    @try_catch()
    @auto_transaction
    @circuit_breaker(name="async_executemany")
    @track_slow_method
    @profile
    async def executemany(self, sql: str, param_list: List[tuple], timeout: Optional[float] = None, tags: Optional[Dict[str, Any]] = None) -> List[Tuple]:
        """
        Asynchronously executes a SQL query multiple times with different parameters.
        
        Note:
            This runs on a single connection sequentially. For parallel execution,
            you would need multiple connections from a connection pool.
            
        Args:
            sql: SQL query with ? placeholders
            param_list: List of parameter tuples for the query
            timeout (float, optional): Total timeout in seconds for all executions
            tags: Optional dictionary of tags to inject to the SQL as comment
            
        Returns:
            List[Tuple]: Combined result rows from all executions
        """        
        timeout = timeout or self.config.query_execution_timeout
        self._mark_active()

        stmt = await self._get_statement_async(sql, tags)
        
        try:
            async def execute_all():
                results = []
                for i, params in enumerate(param_list):
                    raw_result = await self._execute_statement_async(stmt, params)
                    normalized = self._normalize_result(raw_result)
                    if normalized:
                        results.extend(normalized)
                return results
            
            # Execute with overall timeout
            results = await asyncio.wait_for(execute_all(), timeout=timeout)            
            return results
            
        except asyncio.TimeoutError:
            raise TimeoutError(f"Executemany operation timed out after {timeout}s")       
       

    def _get_raw_connection(self) -> Any:
        """ Return the underlying database connection (as defined by the driver) """
        return self._conn
    
    # region -- PRIVATE ABSTRACT METHODS ----------

    @async_method
    @try_catch
    @abstractmethod
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """
        Prepares a statement using database-specific API
        
        Args:
            native_sql: SQL with database-specific placeholders
            
        Returns:
            A database-specific prepared statement object
        """
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """
        Executes a prepared statement with given parameters
        
        Args:
            statement: A database-specific prepared statement
            params: Parameters to bind
            
        Returns:
            Raw execution result
        """
        pass

    # endregion
    
    # region -- PUBLIC ABSTRACT METHODS ----------

    @abstractmethod
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def begin_transaction(self) -> None:
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def commit_transaction(self) -> None:
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def rollback_transaction(self) -> None:
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def close(self) -> None:
        """
        Closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        pass

    @async_method
    @abstractmethod
    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        pass
 
    # endregion --------------------------------

