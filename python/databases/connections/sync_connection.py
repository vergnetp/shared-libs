from typing import Dict, Any, Optional, Tuple, List
from abc import abstractmethod

from ...errors import try_catch
from ...utils import overridable
from ...resilience import with_timeout,  circuit_breaker, track_slow_method

from ..generators import SqlGenerator
from .connection import Connection
from ..utils.decorators import auto_transaction

class SyncConnection(Connection):
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
        timeout = timeout or self._conn._config.query_execution_timeout()
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
 
