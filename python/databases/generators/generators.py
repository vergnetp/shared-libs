
import re
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Any, Optional, final
from ...utils import overridable

class SqlGenerator(ABC):
    """
    Abstract base class defining the interface for database-specific SQL generation.
    
    SQL Generation Syntax Conventions:
    ---------------------------------
    The database layer follows SQL Server-style syntax conventions that are automatically 
    translated to each database's native syntax:
    
    1. Identifiers (table and column names) should be wrapped in square brackets:
    - Correct: SELECT [column_name] FROM [table_name]
    - Incorrect: SELECT column_name FROM table_name
    
    2. Parameter placeholders should use question marks:
    - Correct: WHERE [id] = ?
    - Incorrect: WHERE [id] = $1 or WHERE [id] = %s
    
    Examples:
        - Basic query: "SELECT [id], [name] FROM [customers] WHERE [status] = ?"
        - Insert: "INSERT INTO [orders] ([id], [product]) VALUES (?, ?)"
        - Update: "UPDATE [users] SET [last_login] = ? WHERE [id] = ?"
    
    These conventions ensure SQL statements work safely across all supported 
    databases and properly handle reserved SQL keywords.
    """
    
    @final
    def get_comment_sql(self, tags: Optional[Dict[str, Any]]) -> Optional[str]:
        """
        Return SQL comment with tags if supported by database.

        Args:
            tags (Optional[Dict[str, Any]]): Tags to include as comment.

        Returns:
            Optional[str]: SQL comment or None.
        """
        if tags:
            parts = [f"{k}={v}" for k, v in tags.items()]
            return f"/* {' '.join(parts)} */"
        return None
    
    def escape_identifier(self, identifier: str) -> str:
        """
        Escape a SQL identifier (table or column name).
        
        This must be implemented by each database-specific generator.
        """
        raise NotImplementedError("Subclasses must implement escape_identifier")
    
    def convert_query_to_native(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """
        Converts a standard SQL query with ? placeholders to a database-specific format and
        escapes SQL identifiers.
        
        Args:
            sql: SQL query with ? placeholders
            params: Positional parameters for the query
            
        Returns:
            Tuple containing the converted SQL and the converted parameters
        """
        # First, temporarily replace escaped brackets
        sql = sql.replace('[[', '___OPEN_BRACKET___').replace(']]', '___CLOSE_BRACKET___')
        
        # Process identifiers - replace [identifier] with properly escaped version
        pattern = r'\[(\w+)\]'
        
        def replace_id(match):
            return self.escape_identifier(match.group(1))
        
        escaped_sql = re.sub(pattern, replace_id, sql)
        
        # Restore escaped brackets
        escaped_sql = escaped_sql.replace('___OPEN_BRACKET___', '[').replace('___CLOSE_BRACKET___', ']')
        
        # Now handle parameter placeholders
        return self._convert_parameters(escaped_sql, params)
    
    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """
        Convert parameter placeholders.
        This should be implemented by each subclass based on their parameter style.
        """
        return sql, params
 