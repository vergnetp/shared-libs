import time
import uuid
from typing import Dict, Any, Optional, Tuple, List
from abc import ABC, abstractmethod
import functools
import asyncio
from ...errors import try_catch
from ... import log as logger
from ...utils import async_method, overridable
from ...resilience import with_timeout, retry_with_backoff, circuit_breaker, track_slow_method
from ..sql import SqlGenerator
from .cache import StatementCache


def auto_transaction(func):
    """
    Decorator that automatically wraps a function in a transaction.
    Works for both sync and async functions.
    
    If the decorated function is called when a transaction is already in progress,
    it will use the existing transaction. Otherwise, it will create a new transaction,
    commit it if the function succeeds, or roll it back if an exception occurs.

    Need to be applied to methods of a class that offers in_transaction, begin_transaction (and commit/rollback)
    
    Usage:
        @auto_transaction
        def some_function(self, ...):
            # Function body, runs within a transaction
            
        @auto_transaction
        async def some_async_function(self, ...):
            # Async function body, runs within a transaction
    """
    @functools.wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        if self.in_transaction():
            return func(self, *args, **kwargs)
        else:
            self.begin_transaction()
            try:
                result = func(self, *args, **kwargs)
                self.commit_transaction()
                return result
            except:
                self.rollback_transaction()
                raise

    @functools.wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        if await self.in_transaction():
            return await func(self, *args, **kwargs)
        else:
            await self.begin_transaction()
            try:
                result = await func(self, *args, **kwargs)
                await self.commit_transaction()
                return result
            except:
                await self.rollback_transaction()
                raise

    # Choose the appropriate wrapper based on whether the function is async or not
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
    
class ConnectionInterface(ABC):
    """Interface that defines the required methods and properties for connections."""
    @try_catch(log_success=True)
    @abstractmethod
    def execute(self, sql: str, params: Optional[tuple] = None, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """Execute SQL with parameters"""
        raise NotImplementedError("This method must be implemented by the host class")
    
    @try_catch(log_success=True)
    @abstractmethod
    def executemany(self, sql: str, param_list: List[tuple], timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """Execute SQL multiple times with different parameters"""
        raise NotImplementedError("This method must be implemented by the host class")
    
    @property
    @abstractmethod
    def sql_generator(self) -> SqlGenerator:
        """Returns the SQL parameter converter to use"""
        raise NotImplementedError("This property must be implemented by the host class")
    
class BaseConnection(ConnectionInterface):
    """
    Base class for database connections.
    """
    def __init__(self):
         self._statement_cache = StatementCache() 

    @try_catch    
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

    def _finalize_sql(self, sql: str, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]] = None) -> str:
        combined_parts = []

        if tags:
            comment_sql = self.sql_generator.get_comment_sql(tags)
            if comment_sql:
                combined_parts.append(comment_sql)

        if timeout:
            timeout_sql = self.sql_generator.get_timeout_sql(timeout)
            if timeout_sql:
                combined_parts.append(timeout_sql)

        combined_parts.append(sql)

        return "\n".join(combined_parts)

    @try_catch
    async def _get_statement_async(self, sql: str, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]] = None) -> Any:
        """
        Gets a prepared statement from cache or creates a new one

        Note that statement is unique for the combination of sql, timeout and tags 
        
        Args:
            sql: SQL query with ? placeholders
            timeout: optional timeout in seconds
            tags: optional dictionary of tags to add in the sql comment
                       
        Returns:
            A database-specific prepared statement object
        """
        final_sql = self._finalize_sql(sql, timeout, tags)
        sql_hash = StatementCache.hash(final_sql)      
    
        stmt_tuple = self._statement_cache.get(sql_hash)
        if stmt_tuple:
            return stmt_tuple[0]  # First element is the statement
            
        converted_sql, _ = self.sql_generator.convert_query_to_native(final_sql)
        stmt = await self._prepare_statement_async(converted_sql)
        self._statement_cache.put(sql_hash, stmt, final_sql)

        return stmt

    @try_catch  
    def _get_statement_sync(self, sql: str, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]] = None) -> Any:
        """
        Gets a prepared statement from cache or creates a new one (synchronous version)
        
        Args:
            sql: SQL query with ? placeholders
            timeout: optional timeout in seconds
            tags: optional dictionary of tags to add in the sql comment
            
        Returns:
            A database-specific prepared statement object
        """
        final_sql = self._finalize_sql(sql, timeout, tags)
        sql_hash = StatementCache.hash(final_sql)       
    
        stmt_tuple = self._statement_cache.get(sql_hash)
        if stmt_tuple:
            return stmt_tuple[0]  # First element is the statement
            
        converted_sql, _ = self.sql_generator.convert_query_to_native(final_sql)
        stmt = self._prepare_statement_sync(converted_sql)
        self._statement_cache.put(sql_hash, stmt, final_sql)
        return stmt
    
class AsyncConnection(BaseConnection):
    """
    Abstract base class defining the interface for asynchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends asynchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """ 
    def __init__(self, conn: Any):
        super().__init__()
        self._conn = conn
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
    @with_timeout()
    @track_slow_method()
    @circuit_breaker(name="async_execute")    
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
        self._mark_active()
        stmt = await self._get_statement_async(sql, timeout, tags)        
        raw_result = await self._execute_statement_async(stmt, params)
        result = self._normalize_result(raw_result)
        return result

    @async_method   
    @with_timeout()
    @auto_transaction
    @track_slow_method()
    @circuit_breaker(name="async_executemany")
    async def executemany(self, sql: str, param_list: List[tuple], timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """
        Asynchronously executes a SQL query multiple times with different parameters.

        Note:
            Automatically prepares and caches statements for repeated executions.            
            
        Args:
            sql: SQL query with ? placeholders
            param_list: List of parameter tuples, one for each execution
            timeout (float, optional): a timeout, in second, after which a TimeoutError is raised
            tags: optional dictionary of tags to inject to the sql as comment
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        self._mark_active()
        
        if not param_list:
            return []
        
        individual_timeout = None
        if timeout and timeout > 1:
            individual_timeout = timeout * 0.1

        stmt = await self._get_statement_async(sql, individual_timeout, tags)
       
        results = []
        for params in param_list:
            raw_result = await self._execute_statement_async(stmt, params)
            normalized = self._normalize_result(raw_result)
            if normalized:
                results.extend(normalized)
        return results
       

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

class SyncConnection(BaseConnection):
    """
    Abstract base class defining the interface for synchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends synchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """
    def __init__(self, conn: Any):
        super().__init__()
        self._conn = conn
    
    @with_timeout()
    @track_slow_method()
    @circuit_breaker(name="sync_execute")
    def execute(self, sql: str, params: Optional[tuple] = None, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """
        Synchronously executes a SQL query with standard ? placeholders.
        
        Note:
            Automatically prepares and caches statements for repeated executions.

        Args:
            sql: SQL query with ? placeholders
            params: Parameters for the query
            timeout: optional timeout in seconds after which a TimeoutError is raised
            tags: optional dictionary of tags to inject as sql comments
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        stmt = self._get_statement_sync(sql, timeout, tags)
        raw_result = self._execute_statement_sync(stmt, params)
        return self._normalize_result(raw_result)

    @with_timeout()
    @track_slow_method()
    @auto_transaction
    @circuit_breaker(name="sync_executemany")
    @overridable
    def executemany(self, sql: str, param_list: List[tuple], timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """
        Synchronously executes a SQL query multiple times with different parameters.

        Note:
            Automatically prepares and caches statements for repeated executions.
            Subclasses SHOULD override this method if the underlying driver supports native batch/array/bulk execution for better performance.
                   
        Args:
            sql: SQL query with ? placeholders
            param_list: List of parameter tuples, one for each execution
            timeout (float, optional): a timeout, in second, after which a TimeoutError is raised
            tags: optional dictionary of tags to inject to the sql as comment

        Returns:
            List[Tuple]: Result rows as tuples
        """
        if not param_list:
            return []
    
        individual_timeout = None
        if timeout and timeout > 1:
            individual_timeout = timeout * 0.1

        stmt = self._get_statement_sync(sql, individual_timeout, tags)

        # Fallback to executing one-by-one
        results = []
   
        for params in param_list:
            raw_result = self._execute_statement_sync(stmt, params)
            normalized = self._normalize_result(raw_result)
            if normalized:
                results.extend(normalized)

        return results

    def _get_raw_connection(self) -> Any:
        """ Return the underlying database connection (as defined by the driver) """
        return self._conn
    
    # region -- PRIVATE ABSTRACT METHODS ----------

    @try_catch
    @abstractmethod
    async def _prepare_statement_sync(self, native_sql: str) -> Any:
        """
        Prepares a statement using database-specific API
        
        Args:
            native_sql: SQL with database-specific placeholders
            
        Returns:
            A database-specific prepared statement object
        """
        pass

    @try_catch
    @abstractmethod
    async def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """
        Executes a prepared statement with given parameters
        
        Args:
            statement: A database-specific prepared statement
            params: Parameters to bind
            
        Returns:
            Raw execution result
        """
        pass
    
    # endregion --------------------------------
    
    # region -- PUBLIC ABSTRACT METHODS ----------

    @property
    @abstractmethod
    def sql_generator(self) -> SqlGenerator:
        """Returns the parameter converter for this connection."""
        pass

    @abstractmethod
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""
        pass

    @try_catch
    @abstractmethod
    def begin_transaction(self) -> None:
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        pass

    @try_catch
    @abstractmethod
    def commit_transaction(self) -> None:
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        pass

    @try_catch
    @abstractmethod
    def rollback_transaction(self) -> None:
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        pass

    @try_catch
    @abstractmethod
    def close(self) -> None:
        """
        Closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        pass

    @abstractmethod
    def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        pass
 

