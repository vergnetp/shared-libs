from abc import ABC, abstractmethod
from typing import Dict, Tuple, List, Any, Optional


class SqlEntityGenerator(ABC):
    """
    Abstract base class defining the interface for database-specific SQL generation.
    
    This class defines the contract that all database-specific SQL generators must implement.
    Each database backend (PostgreSQL, SQLite, MySQL, etc.) will have its own implementation
    that handles the specific SQL dialect and features of that database.
    """
    
    @abstractmethod
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """
        Generate database-specific upsert SQL for an entity.
        
        Args:
            entity_name: Name of the entity (table)
            fields: List of field names to include in the upsert operation
            
        Returns:
            SQL string with placeholders for the upsert operation
        """
        pass
        
    @abstractmethod
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """
        Generate database-specific CREATE TABLE SQL.
        
        Args:
            entity_name: Name of the entity (table) to create
            columns: List of (column_name, column_type) tuples
            
        Returns:
            SQL string for creating the table
        """
        pass
    
    @abstractmethod
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """
        Generate database-specific SQL for creating a metadata table.
        
        Args:
            entity_name: Name of the entity whose metadata table to create
            
        Returns:
            SQL string for creating the metadata table
        """
        pass
        
    @abstractmethod
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """
        Generate database-specific history table SQL.
        
        Args:
            entity_name: Name of the entity whose history to track
            columns: List of (column_name, column_type) tuples from the main table
            
        Returns:
            SQL string for creating the history table
        """
        pass
    
    @abstractmethod
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """
        Get SQL to list all tables in the database.
        
        Returns:
            Tuple of (SQL string, parameters) for listing tables
        """
        pass
    
    @abstractmethod
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """
        Get SQL to list all columns in a table (same order as in the table)
        
        Args:
            table_name: Name of the table to list columns for
            
        Returns:
            Tuple of (SQL string, parameters) for listing columns
        """
        pass
    
    @abstractmethod
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """
        Generate database-specific upsert SQL for a metadata table.
        
        Args:
            entity_name: Name of the entity whose metadata to upsert
            
        Returns:
            SQL string with placeholders for the metadata upsert
        """
        pass
    
    @abstractmethod
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """
        Generate SQL to add a column to an existing table.
        
        Args:
            table_name: Name of the table to alter
            column_name: Name of the column to add
            
        Returns:
            SQL string for adding the column
        """
        pass
    
    @abstractmethod
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """
        Generate SQL to check if a table exists.
        
        Args:
            table_name: Name of the table to check
            
        Returns:
            Tuple of (SQL string, parameters) for checking table existence
        """
        pass
    
    @abstractmethod
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """
        Generate SQL to check if a column exists in a table.
        
        Args:
            table_name: Name of the table to check
            column_name: Name of the column to check
            
        Returns:
            Tuple of (SQL string, parameters) for checking column existence
        """
        pass
    
    @abstractmethod
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """
        Generate SQL to retrieve an entity by ID.
        
        Args:
            entity_name: Name of the entity to retrieve
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            SQL string with placeholders for the query
        """
        pass
    
    @abstractmethod
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """
        Generate SQL to retrieve the history of an entity.
        
        Args:
            entity_name: Name of the entity
            id: ID of the entity
            
        Returns:
            Tuple of (SQL string, parameters) for retrieving entity history
        """
        pass
    
    @abstractmethod
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """
        Generate SQL to retrieve a specific version of an entity.
        
        Args:
            entity_name: Name of the entity
            id: ID of the entity
            version: Version number to retrieve
            
        Returns:
            Tuple of (SQL string, parameters) for retrieving the entity version
        """
        pass
    
    @abstractmethod
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """
        Generate SQL for soft-deleting an entity.
        
        Args:
            entity_name: Name of the entity to soft-delete
            
        Returns:
            SQL string with placeholders for the soft delete
        """
        pass
    
    @abstractmethod
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """
        Generate SQL for restoring a soft-deleted entity.
        
        Args:
            entity_name: Name of the entity to restore
            
        Returns:
            SQL string with placeholders for the restore operation
        """
        pass
    
    @abstractmethod
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """
        Generate SQL for counting entities, optionally with a WHERE clause.
        
        Args:
            entity_name: Name of the entity to count
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            SQL string with placeholders for the count query
        """
        pass
    
    @abstractmethod
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """
        Generate SQL for a flexible query with various clauses.
        
        Args:
            entity_name: Name of the entity to query
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
            limit: Optional LIMIT value
            offset: Optional OFFSET value
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            SQL string with placeholders for the query
        """
        pass
    
    @abstractmethod
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """
        Generate SQL for updating specific fields of an entity.
        
        Args:
            entity_name: Name of the entity to update
            fields: List of field names to update
            
        Returns:
            SQL string with placeholders for the update
        """
        pass
    
    @abstractmethod
    def get_pragma_or_settings_sql(self) -> List[str]:
        """
        Get a list of database-specific PRAGMA or settings statements.
        
        These are typically executed when initializing a connection to
        configure optimal settings for the database.
        
        Returns:
            List of SQL statements to execute for optimal configuration
        """
        pass
    
    @abstractmethod
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """
        Generate SQL to get the next value from a sequence.
        
        Not all databases support sequences. For those that don't,
        this method should return None.
        
        Args:
            sequence_name: Name of the sequence
            
        Returns:
            SQL string for getting the next sequence value, or None
        """
        pass
    
    def get_timeout_sql(self, timeout: Optional[float]) -> Optional[str]:
        """
        Return a SQL statement to enforce query timeout (if applicable).

        Args:
            timeout (Optional[float]): Timeout in seconds.

        Returns:
            Optional[str]: SQL statement to enforce timeout, or None if not supported.
        """
        return None


