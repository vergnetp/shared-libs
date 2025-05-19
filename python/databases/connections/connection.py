from typing import Dict, Any, Optional, Tuple, List
from abc import ABC, abstractmethod

from ...errors import try_catch

from ..generators import SqlGenerator
from ..utils.caching import StatementCache

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
    
class Connection(ConnectionInterface):
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
    
