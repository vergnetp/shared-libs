from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple, Union, Set

class SqlGenerator(ABC):
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
        Get SQL to list all columns in a table.
        
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


    class PostgresSqlGenerator(SqlGenerator):
    """
    PostgreSQL-specific SQL generator implementation.
    
    This class provides SQL generation tailored to PostgreSQL's dialect and features.
    """
    
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate PostgreSQL-specific upsert SQL for an entity."""
        fields_str = ', '.join(fields)
        placeholders = ', '.join(['?'] * len(fields))
        update_clause = ', '.join([f"{field}=EXCLUDED.{field}" for field in fields if field != 'id'])
        
        return f"INSERT INTO {entity_name} ({fields_str}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {update_clause}"
    
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate PostgreSQL-specific CREATE TABLE SQL."""
        column_defs = []
        for name, type_name in columns:
            if name == 'id':
                column_defs.append(f"id TEXT PRIMARY KEY")
            else:
                column_defs.append(f"{name} TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name} (
                {', '.join(column_defs)}
            )
        """
    
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """Generate PostgreSQL-specific SQL for creating a metadata table."""
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                name TEXT PRIMARY KEY,
                type TEXT
            )
        """
    
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate PostgreSQL-specific history table SQL."""
        column_defs = [f"{name} TEXT" for name, _ in columns]
        column_defs.append("version INTEGER")
        column_defs.append("history_timestamp TEXT")
        column_defs.append("history_user_id TEXT")
        column_defs.append("history_comment TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name}_history (
                {', '.join(column_defs)},
                PRIMARY KEY (id, version)
            )
        """
    
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """Get SQL to list all tables in PostgreSQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name LIKE %s",
            ('%_meta',)
        )
    
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a PostgreSQL table."""
        return (
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = %s",
            (table_name,)
        )
    
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """Generate PostgreSQL-specific upsert SQL for a metadata table."""
        return f"INSERT INTO {entity_name}_meta VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET type=EXCLUDED.type"
    
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """Generate SQL to add a column to an existing PostgreSQL table."""
        return f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} TEXT"
    
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a table exists in PostgreSQL."""
        return (
            "SELECT table_name FROM information_schema.tables WHERE table_name = %s",
            (table_name,)
        )
    
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a column exists in a PostgreSQL table."""
        return (
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (table_name, column_name)
        )
    
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """Generate SQL to retrieve an entity by ID in PostgreSQL."""
        query = f"SELECT * FROM {entity_name} WHERE id = ?"
        
        if not include_deleted:
            query += " AND deleted_at IS NULL"
            
        return query
    
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """Generate SQL to retrieve the history of an entity in PostgreSQL."""
        return (
            f"SELECT * FROM {entity_name}_history WHERE id = %s ORDER BY version DESC",
            (id,)
        )
    
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """Generate SQL to retrieve a specific version of an entity in PostgreSQL."""
        return (
            f"SELECT * FROM {entity_name}_history WHERE id = %s AND version = %s",
            (id, version)
        )
    
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """Generate SQL for soft-deleting an entity in PostgreSQL."""
        return f"UPDATE {entity_name} SET deleted_at = ?, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """Generate SQL for restoring a soft-deleted entity in PostgreSQL."""
        return f"UPDATE {entity_name} SET deleted_at = NULL, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """Generate SQL for counting entities in PostgreSQL."""
        query = f"SELECT COUNT(*) FROM {entity_name}"
        conditions = []
        
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        return query
    
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """Generate SQL for a flexible query in PostgreSQL."""
        query = f"SELECT * FROM {entity_name}"
        conditions = []
        
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        if order_by:
            query += f" ORDER BY {order_by}"
            
        if limit is not None:
            query += f" LIMIT {limit}"
            
        if offset is not None:
            query += f" OFFSET {offset}"
            
        return query
    
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQL for updating specific fields of an entity in PostgreSQL."""
        set_clause = ", ".join([f"{field} = ?" for field in fields])
        return f"UPDATE {entity_name} SET {set_clause}, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_pragma_or_settings_sql(self) -> List[str]:
        """Get optimal PostgreSQL settings."""
        return [
            "SET TIME ZONE 'UTC'",
            "SET application_name = 'EntityManager'"
        ]
    
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """Generate SQL to get the next value from a PostgreSQL sequence."""
        return f"SELECT nextval('{sequence_name}')"
    

class MySqlSqlGenerator(SqlGenerator):
    """
    MySQL-specific SQL generator implementation.
    
    This class provides SQL generation tailored to MySQL's dialect and features.
    """
    
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate MySQL-specific upsert SQL for an entity."""
        fields_str = ', '.join(fields)
        placeholders = ', '.join(['?'] * len(fields))
        update_clause = ', '.join([f"{field}=VALUES({field})" for field in fields if field != 'id'])
        
        return f"INSERT INTO {entity_name} ({fields_str}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate MySQL-specific CREATE TABLE SQL."""
        column_defs = []
        for name, type_name in columns:
            if name == 'id':
                column_defs.append(f"id VARCHAR(36) PRIMARY KEY")
            else:
                column_defs.append(f"{name} TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name} (
                {', '.join(column_defs)}
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """Generate MySQL-specific SQL for creating a metadata table."""
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                name VARCHAR(255) PRIMARY KEY,
                type VARCHAR(50)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate MySQL-specific history table SQL."""
        column_defs = []
        for name, _ in columns:
            if name == 'id':
                column_defs.append(f"id VARCHAR(36)")
            else:
                column_defs.append(f"{name} TEXT")
                
        column_defs.append("version INT")
        column_defs.append("history_timestamp TEXT")
        column_defs.append("history_user_id TEXT")
        column_defs.append("history_comment TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name}_history (
                {', '.join(column_defs)},
                PRIMARY KEY (id, version)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """Get SQL to list all tables in MySQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=DATABASE() AND table_name LIKE %s",
            ('%_meta',)
        )
    
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a MySQL table."""
        return (
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = %s AND table_schema = DATABASE()",
            (table_name,)
        )
    
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """Generate MySQL-specific upsert SQL for a metadata table."""
        return f"INSERT INTO {entity_name}_meta VALUES (?, ?) AS new ON DUPLICATE KEY UPDATE type=new.type"
    
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """Generate SQL to add a column to an existing MySQL table."""
        # MySQL doesn't support IF NOT EXISTS for columns, so the caller must check first
        return f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT"
    
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a table exists in MySQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            (table_name,)
        )
    
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a column exists in a MySQL table."""
        return (
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s AND table_schema = DATABASE()",
            (table_name, column_name)
        )
    
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """Generate SQL to retrieve an entity by ID in MySQL."""
        query = f"SELECT * FROM {entity_name} WHERE id = ?"
        
        if not include_deleted:
            query += " AND deleted_at IS NULL"
            
        return query
    
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """Generate SQL to retrieve the history of an entity in MySQL."""
        return (
            f"SELECT * FROM {entity_name}_history WHERE id = %s ORDER BY version DESC",
            (id,)
        )
    
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """Generate SQL to retrieve a specific version of an entity in MySQL."""
        return (
            f"SELECT * FROM {entity_name}_history WHERE id = %s AND version = %s",
            (id, version)
        )
    
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """Generate SQL for soft-deleting an entity in MySQL."""
        return f"UPDATE {entity_name} SET deleted_at = ?, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """Generate SQL for restoring a soft-deleted entity in MySQL."""
        return f"UPDATE {entity_name} SET deleted_at = NULL, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """Generate SQL for counting entities in MySQL."""
        query = f"SELECT COUNT(*) FROM {entity_name}"
        conditions = []
        
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        return query
    
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """Generate SQL for a flexible query in MySQL."""
        query = f"SELECT * FROM {entity_name}"
        conditions = []
        
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        if order_by:
            query += f" ORDER BY {order_by}"
            
        if limit is not None:
            query += f" LIMIT {limit}"
            
        if offset is not None:
            query += f" LIMIT {offset}, {limit if limit is not None else 18446744073709551615}"
            
        return query
    
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQL for updating specific fields of an entity in MySQL."""
        set_clause = ", ".join([f"{field} = ?" for field in fields])
        return f"UPDATE {entity_name} SET {set_clause}, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_pragma_or_settings_sql(self) -> List[str]:
        """Get optimal MySQL settings."""
        return [
            "SET NAMES utf8mb4",
            "SET time_zone = '+00:00'",
            "SET sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'"
        ]
    
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """
        MySQL doesn't support native sequences like PostgreSQL.
        This is typically implemented using auto-increment columns or custom tables.
        """
        # For MySQL, we return None as there's no direct sequence support
        # The application would need to use auto-increment or a custom sequence table
        return None
    
class SqliteSqlGenerator(SqlGenerator):
    """
    SQLite-specific SQL generator implementation.
    
    This class provides SQL generation tailored to SQLite's dialect and features.
    """
    
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQLite-specific upsert SQL for an entity."""
        fields_str = ', '.join(fields)
        placeholders = ', '.join(['?'] * len(fields))
        
        return f"INSERT OR REPLACE INTO {entity_name} ({fields_str}) VALUES ({placeholders})"
    
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate SQLite-specific CREATE TABLE SQL."""
        column_defs = []
        for name, type_name in columns:
            if name == 'id':
                column_defs.append(f"id TEXT PRIMARY KEY")
            else:
                column_defs.append(f"{name} TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name} (
                {', '.join(column_defs)}
            )
        """
    
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """Generate SQLite-specific SQL for creating a metadata table."""
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                name TEXT PRIMARY KEY,
                type TEXT
            )
        """
    
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate SQLite-specific history table SQL."""
        column_defs = [f"{name} TEXT" for name, _ in columns]
        column_defs.append("version INTEGER")
        column_defs.append("history_timestamp TEXT")
        column_defs.append("history_user_id TEXT")
        column_defs.append("history_comment TEXT")
        
        # SQLite's PRIMARY KEY syntax
        return f"""
            CREATE TABLE IF NOT EXISTS {entity_name}_history (
                {', '.join(column_defs)},
                PRIMARY KEY (id, version)
            )
        """
    
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """Get SQL to list all tables in SQLite."""
        return (
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
            ('%_meta',)
        )
    
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a SQLite table."""
        return (
            f"PRAGMA table_info({table_name})",
            ()
        )
    
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """Generate SQLite-specific upsert SQL for a metadata table."""
        return f"INSERT OR REPLACE INTO {entity_name}_meta VALUES (?, ?)"
    
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """Generate SQL to add a column to an existing SQLite table."""
        # SQLite doesn't support ADD COLUMN IF NOT EXISTS, so the caller must check
        return f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT"
    
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a table exists in SQLite."""
        return (
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
    
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a column exists in a SQLite table."""
        # SQLite requires checking the table_info PRAGMA result
        return (
            f"PRAGMA table_info({table_name})",
            ()
        )
        # Note: Caller will need to check if column_name is in the results
    
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """Generate SQL to retrieve an entity by ID in SQLite."""
        query = f"SELECT * FROM {entity_name} WHERE id = ?"
        
        if not include_deleted:
            query += " AND deleted_at IS NULL"
            
        return query
    
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """Generate SQL to retrieve the history of an entity in SQLite."""
        return (
            f"SELECT * FROM {entity_name}_history WHERE id = ? ORDER BY version DESC",
            (id,)
        )
    
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """Generate SQL to retrieve a specific version of an entity in SQLite."""
        return (
            f"SELECT * FROM {entity_name}_history WHERE id = ? AND version = ?",
            (id, version)
        )
    
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """Generate SQL for soft-deleting an entity in SQLite."""
        return f"UPDATE {entity_name} SET deleted_at = ?, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """Generate SQL for restoring a soft-deleted entity in SQLite."""
        return f"UPDATE {entity_name} SET deleted_at = NULL, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """Generate SQL for counting entities in SQLite."""
        query = f"SELECT COUNT(*) FROM {entity_name}"
        conditions = []
        
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        return query
    
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """Generate SQL for a flexible query in SQLite."""
        query = f"SELECT * FROM {entity_name}"
        conditions = []
        
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        if order_by:
            query += f" ORDER BY {order_by}"
            
        if limit is not None:
            query += f" LIMIT {limit}"
            
        if offset is not None:
            query += f" OFFSET {offset}"
            
        return query
    
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQL for updating specific fields of an entity in SQLite."""
        set_clause = ", ".join([f"{field} = ?" for field in fields])
        return f"UPDATE {entity_name} SET {set_clause}, updated_at = ?, updated_by = ? WHERE id = ?"
    
    def get_pragma_or_settings_sql(self) -> List[str]:
        """Get optimal SQLite settings using PRAGMAs."""
        return [
            "PRAGMA journal_mode = WAL",
            "PRAGMA synchronous = NORMAL",
            "PRAGMA foreign_keys = ON",
            "PRAGMA cache_size = -8000"  # Negative means kibibytes
        ]
    
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """
        SQLite doesn't support native sequences like PostgreSQL.
        This is typically implemented using rowid or custom tables.
        """
        # For SQLite, we return None as there's no direct sequence support
        return None

class SqlGeneratorFactory:
    """
    Factory class for creating database-specific SQL generators.
    
    This class centralizes the logic for instantiating the appropriate
    SQL generator based on the database type, following the factory pattern.
    """
    
    _generators = {}  # Cache of generator instances
    
    @classmethod
    def get_generator(cls, db_type: str) -> SqlGenerator:
        """
        Get or create a SQL generator for the specified database type.
        
        Args:
            db_type: Database type ('postgres', 'mysql', 'sqlite')
            
        Returns:
            An appropriate SqlGenerator implementation
            
        Raises:
            ValueError: If the database type is not supported
        """
        db_type = db_type.lower()
        
        # Check cache first
        if db_type in cls._generators:
            return cls._generators[db_type]
        
        # Create a new generator
        if db_type == 'postgres':
            generator = PostgresSqlGenerator()
        elif db_type == 'mysql':
            generator = MySqlSqlGenerator()
        elif db_type == 'sqlite':
            generator = SqliteSqlGenerator()
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
        
        # Cache and return
        cls._generators[db_type] = generator
        return generator
    
class EntityUtils:
    """
    Shared utility methods for entity operations.
    
    This mixin class provides common functionality needed by both database-level
    and connection-level entity operations, including serialization/deserialization,
    type handling, and entity preparation.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_serializers()
        self._custom_serializers = {}
        self._custom_deserializers = {}
    
    def _init_serializers(self):
        """Initialize standard serializers and deserializers for different types."""
        # Type serializers (Python type -> string)
        self._serializers = {
            'dict': lambda v: json.dumps(v) if v is not None else None,
            'list': lambda v: json.dumps(v) if v is not None else None,
            'set': lambda v: json.dumps(list(v)) if v is not None else None,
            'tuple': lambda v: json.dumps(list(v)) if v is not None else None,
            'datetime': lambda v: v.isoformat() if v is not None else None,
            'date': lambda v: v.isoformat() if v is not None else None,
            'time': lambda v: v.isoformat() if v is not None else None,
            'bytes': lambda v: v.hex() if v is not None else None,
            'bool': lambda v: str(v).lower() if v is not None else None,
            'int': lambda v: str(v) if v is not None else None,
            'float': lambda v: str(v) if v is not None else None,
        }
        
        # Type deserializers (string -> Python type)
        self._deserializers = {
            'dict': lambda v: json.loads(v) if v else {},
            'list': lambda v: json.loads(v) if v else [],
            'set': lambda v: set(json.loads(v)) if v else set(),
            'tuple': lambda v: tuple(json.loads(v)) if v else (),
            'datetime': lambda v: datetime.datetime.fromisoformat(v) if v else None,
            'date': lambda v: datetime.date.fromisoformat(v) if v else None,
            'time': lambda v: datetime.time.fromisoformat(v) if v else None,
            'bytes': lambda v: bytes.fromhex(v) if v else None,
            'int': lambda v: int(v) if v and v.strip() else 0,
            'float': lambda v: float(v) if v and v.strip() else 0.0,
            'bool': lambda v: v.lower() in ('true', '1', 'yes', 'y', 't') if v else False,
        }
    
    def register_custom_serializer(self, type_name: str, serializer_func, deserializer_func):
        """
        Register custom serialization functions for handling non-standard types.
        
        Args:
            type_name: String identifier for the type
            serializer_func: Function that converts the type to a string
            deserializer_func: Function that converts a string back to the type
        """
        self._custom_serializers[type_name] = serializer_func
        self._custom_deserializers[type_name] = deserializer_func
    
    def _infer_type(self, value: Any) -> str:
        """
        Infer the type of a value as a string.
        
        Args:
            value: Any Python value
            
        Returns:
            String identifier for the type
        """
        if value is None:
            return 'str'  # Default to string for None values
        
        python_type = type(value).__name__
        
        # Check for custom type
        for type_name, serializer in self._custom_serializers.items():
            try:
                if isinstance(value, eval(type_name)):
                    return type_name
            except (NameError, TypeError):
                # Type might not be importable here - try duck typing
                try:
                    # Try to apply serializer as a test
                    serializer(value)
                    return type_name
                except Exception:
                    pass
        
        # Map Python types to our type system
        type_map = {
            'dict': 'dict',
            'list': 'list',
            'tuple': 'tuple',
            'set': 'set',
            'int': 'int',
            'float': 'float',
            'bool': 'bool',
            'str': 'str',
            'bytes': 'bytes',
            'datetime': 'datetime',
            'date': 'date',
            'time': 'time',
        }
        
        return type_map.get(python_type, 'str')
    
    def _serialize_value(self, value: Any, value_type: Optional[str] = None) -> str:
        """
        Serialize a value based on its type.
        
        Args:
            value: Value to serialize
            value_type: Optional explicit type, if None will be inferred
            
        Returns:
            String representation of the value
        """
        if value is None:
            return None
        
        # Determine type if not provided
        if value_type is None:
            value_type = self._infer_type(value)
        
        # Check for custom serializer first
        if value_type in self._custom_serializers:
            try:
                return self._custom_serializers[value_type](value)
            except Exception as e:
                logger.warning(f"Custom serializer for {value_type} failed: {e}")
                # Fall back to string conversion
        
        # Use standard serializer if available
        serializer = self._serializers.get(value_type)
        if serializer:
            try:
                return serializer(value)
            except Exception as e:
                logger.warning(f"Standard serializer for {value_type} failed: {e}")
                # Fall back to string conversion
        
        # Default fallback
        return str(value)
    
    def _deserialize_value(self, value: Optional[str], value_type: str) -> Any:
        """
        Deserialize a value based on its type.
        
        Args:
            value: String representation of a value
            value_type: Type of the value
            
        Returns:
            Python object of the appropriate type
        """
        if value is None:
            return None
        
        # Check for custom deserializer first
        if value_type in self._custom_deserializers:
            try:
                return self._custom_deserializers[value_type](value)
            except Exception as e:
                logger.warning(f"Custom deserializer for {value_type} failed: {e}")
                # Fall back to returning the raw value
        
        # Use standard deserializer if available
        deserializer = self._deserializers.get(value_type)
        if deserializer:
            try:
                return deserializer(value)
            except Exception as e:
                logger.warning(f"Standard deserializer for {value_type} failed: {e}")
                # Fall back to returning the raw value
        
        # Default fallback
        return value
    
    def _serialize_entity(self, entity: Dict[str, Any], meta: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
        """
        Serialize all values in an entity to strings.
        
        Args:
            entity: Dictionary with entity data
            meta: Optional metadata with field types
            
        Returns:
            Dictionary with all values serialized to strings
        """
        result = {}
        
        for key, value in entity.items():
            value_type = meta.get(key, None) if meta else None
            
            try:
                result[key] = self._serialize_value(value, value_type)
            except Exception as e:
                logger.error(f"Error serializing field '{key}': {e}")
                # Use string representation as fallback
                result[key] = str(value) if value is not None else None
        
        return result
    
    def _deserialize_entity(self, entity_name: str, entity: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """
        Deserialize entity values based on metadata.
        
        Args:
            entity_name: Name of the entity for metadata lookup
            entity: Dictionary with string values
            
        Returns:
            Dictionary with values converted to appropriate Python types
        """
        result = {}
        
        # Get type information for this entity
        meta = self._meta_cache.get(entity_name, {})
        
        for key, value in entity.items():
            value_type = meta.get(key, 'str')
            
            try:
                result[key] = self._deserialize_value(value, value_type)
            except Exception as e:
                logger.error(f"Error deserializing field '{key}' as {value_type}: {e}")
                # Use the raw value as a fallback
                result[key] = value
        
        return result
    
    def _prepare_entity(self, entity_name: str, entity: Dict[str, Any], 
                       user_id: Optional[str] = None, comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Prepare an entity for storage by adding required fields.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity data
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            Entity with added/updated system fields
        """
        now = datetime.datetime.utcnow().isoformat()
        result = entity.copy()
        
        # Add ID if missing
        if 'id' not in result or not result['id']:
            result['id'] = str(uuid.uuid4())
        
        # Add timestamps
        if 'created_at' not in result:
            result['created_at'] = now
        
        result['updated_at'] = now
        
        # Add user_id if provided
        if user_id is not None:
            result['updated_by'] = user_id
            
            if 'created_by' not in result:
                result['created_by'] = user_id
        
        # Add comment if provided
        if comment is not None:
            result['update_comment'] = comment
        
        return result
    
    def to_json(self, entity: Dict[str, Any]) -> str:
        """
        Convert an entity to a JSON string.
        
        Args:
            entity: Entity dictionary
            
        Returns:
            JSON string representation
        """
        return json.dumps(entity, default=str)
    
    def from_json(self, json_str: str) -> Dict[str, Any]:
        """
        Convert a JSON string to an entity dictionary.
        
        Args:
            json_str: JSON string
            
        Returns:
            Entity dictionary
        """
        return json.loads(json_str)
    
    async def _internal_operation(self, is_async: bool, func_sync, func_async, *args, **kwargs):
        """
        Execute an operation in either sync or async mode.
        
        This internal helper method allows implementing a function once and then
        exposing it as both sync and async methods.
        
        Args:
            is_async: Whether to execute in async mode
            func_sync: Synchronous function to call
            func_async: Asynchronous function to call
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Result of the function call
        """
        if is_async:
            return await func_async(*args, **kwargs)
        else:
            return func_sync(*args, **kwargs)
    
    def _create_sync_method(self, internal_method, *args, **kwargs):
        """
        Create a synchronous wrapper for an internal method.
        
        Args:
            internal_method: Coroutine that implements the operation
            *args, **kwargs: Default arguments to pass to the method
            
        Returns:
            Synchronous function that executes the internal method
        """
        def sync_method(*method_args, **method_kwargs):
            combined_args = args + method_args
            combined_kwargs = {**kwargs, **method_kwargs}
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop in this thread, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(
                internal_method(is_async=False, *combined_args, **combined_kwargs)
            )
        
        return sync_method
    
    def _create_async_method(self, internal_method, *args, **kwargs):
        """
        Create an asynchronous wrapper for an internal method.
        
        Args:
            internal_method: Coroutine that implements the operation
            *args, **kwargs: Default arguments to pass to the method
            
        Returns:
            Asynchronous function that executes the internal method
        """
        async def async_method(*method_args, **method_kwargs):
            combined_args = args + method_args
            combined_kwargs = {**kwargs, **method_kwargs}
            return await internal_method(is_async=True, *combined_args, **combined_kwargs)
        
        return async_method
    
class EntityManager:
    """
    Core class for managing entities in the database.
    
    This class provides a unified interface for CRUD operations on entities,
    with both synchronous and asynchronous methods. It uses SqlGeneratorFactory
    to get the appropriate SQL generator for the database type, and implements
    the coroutine pattern to reduce code duplication.
    """
    
    def __init__(self, database: BaseDatabase):
        """
        Initialize the entity manager.
        
        Args:
            database: Database instance to use for operations
        """
        self._db = database
        
        # Detect database type
        self._db_type = self._detect_db_type()
        
        # Get SQL generator
        self._sql_generator = SqlGeneratorFactory.get_generator(self._db_type)
        
        # Metadata caches
        self._meta_cache = {}  # entity_name -> {field_name: type}
        self._keys_cache = {}  # entity_name -> [field_names]
        self._types_cache = {}  # entity_name -> [field_types]
        self._history_enabled = set()  # entity_names with history tracking
        
        # Mix in utility methods from EntityUtils
        self._utils = EntityUtils()  # Composition instead of inheritance
        
        # Try to load metadata
        if not self.is_environment_async():
            try:
                self.load_all_metadata_sync()
            except Exception as e:
                logger.warning(f"Metadata load failed in sync mode: {str(e)}")
    
    def _detect_db_type(self) -> str:
        """
        Detect the database type from the database instance.
        
        Returns:
            String identifier for the database type ('postgres', 'mysql', 'sqlite')
        """
        # We could use isinstance() checks, but to avoid circular imports,
        # we'll check the class name
        class_name = self._db.__class__.__name__.lower()
        
        if 'postgres' in class_name:
            return 'postgres'
        elif 'mysql' in class_name or 'mariadb' in class_name:
            return 'mysql'
        elif 'sqlite' in class_name:
            return 'sqlite'
        else:
            # Default to PostgreSQL as a safeguard
            logger.warning(f"Unknown database class: {class_name}, defaulting to PostgreSQL")
            return 'postgres'
    
    def is_environment_async(self) -> bool:
        """
        Determine if the current environment supports async/await.
        
        Returns:
            True if running in an async environment, False otherwise
        """
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False
    
    # -------------------- METADATA OPERATIONS --------------------
    
    async def _impl_load_all_metadata(self, is_async: bool) -> None:
        """
        Internal implementation for loading all entity metadata from the database.
        
        Args:
            is_async: Whether to use async or sync operations
        """
        try:
            # Get the connection
            if is_async:
                conn_ctx = self._db.async_connection()
            else:
                conn_ctx = self._db.sync_connection()
            
            async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
                # Get list tables SQL
                sql, params = self._sql_generator.get_list_tables_sql()
                
                # Execute and normalize results
                if is_async:
                    tables = await conn.execute_async(sql, params)
                else:
                    tables = conn.execute_sync(sql, params)
                
                # Process each metadata table
                for table_row in tables:
                    table = table_row[0]
                    if not table.endswith("_meta"):
                        continue
                    
                    entity_name = table[:-5]  # Remove _meta suffix
                    
                    # Get metadata for this entity
                    if is_async:
                        meta_rows = await conn.execute_async(f"SELECT name, type FROM {table}")
                    else:
                        meta_rows = conn.execute_sync(f"SELECT name, type FROM {table}")
                    
                    # Build metadata cache
                    meta = {name: typ for name, typ in meta_rows}
                    self._meta_cache[entity_name] = meta
                    self._keys_cache[entity_name] = list(meta.keys())
                    self._types_cache[entity_name] = list(meta.values())
                    
                    # Check if history table exists
                    check_sql, check_params = self._sql_generator.get_check_table_exists_sql(f"{entity_name}_history")
                    
                    if is_async:
                        history_rows = await conn.execute_async(check_sql, check_params)
                    else:
                        history_rows = conn.execute_sync(check_sql, check_params)
                    
                    if history_rows:
                        self._history_enabled.add(entity_name)
            
            # Close connection if using sync mode (async context manager handles it automatically)
            if not is_async:
                conn_ctx.__exit__(None, None, None)
                
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
            raise
    
    def load_all_metadata_sync(self) -> None:
        """
        Load all entity metadata from the database (synchronous version).
        
        This method reads all metadata tables from the database and builds
        in-memory caches of entity schemas and history settings.
        """
        # Create a synchronous wrapper for the internal implementation
        return self._utils._create_sync_method(self._impl_load_all_metadata)()
    
    async def load_all_metadata_async(self) -> None:
        """
        Load all entity metadata from the database (asynchronous version).
        
        This method reads all metadata tables from the database and builds
        in-memory caches of entity schemas and history settings.
        """
        # Create an asynchronous wrapper for the internal implementation
        return await self._utils._create_async_method(self._impl_load_all_metadata)()
    
    # -------------------- ENTITY OPERATIONS --------------------
    
    async def _impl_save_entity(self, entity_name: str, entity: Dict[str, Any], 
                               is_async: bool, user_id: Optional[str] = None, 
                               comment: Optional[str] = None) -> str:
        """
        Internal implementation for saving an entity to the database.
        
        Args:
            entity_name: Name of the entity
            entity: Entity dictionary
            is_async: Whether to use async or sync operations
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            ID of the saved entity
        """
        try:
            # Get the connection with transaction
            if is_async:
                conn_ctx = self._db.async_transaction()
            else:
                conn_ctx = self._db.sync_transaction()
            
            async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
                # Ensure tables exist
                await self._impl_ensure_table(entity_name, entity, is_async, conn)
                
                # Prepare entity with timestamps and ID
                prepared_entity = self._utils._prepare_entity(entity_name, entity, user_id, comment)
                
                # Get current metadata
                meta = self._meta_cache.get(entity_name, {})
                
                # Serialize values
                serialized = self._utils._serialize_entity(prepared_entity, meta)
                
                # Get fields and values
                fields = list(serialized.keys())
                values = [serialized[field] for field in fields]
                
                # Generate upsert SQL
                upsert_sql = self._sql_generator.get_upsert_sql(entity_name, fields)
                
                # Execute upsert
                if is_async:
                    await conn.execute_async(upsert_sql, tuple(values))
                else:
                    conn.execute_sync(upsert_sql, tuple(values))
                
                # Save to history if enabled
                if entity_name in self._history_enabled:
                    await self._impl_save_history(entity_name, serialized, is_async, conn, user_id, comment)
                
                return prepared_entity["id"]
                
            # Close connection if using sync mode (async context manager handles it automatically)
            if not is_async:
                conn_ctx.__exit__(None, None, None)
                
        except Exception as e:
            logger.error(f"Error saving entity {entity_name}: {e}")
            raise
    
    def save_entity_sync(self, entity_name: str, entity: Dict[str, Any], 
                        user_id: Optional[str] = None, comment: Optional[str] = None) -> str:
        """
        Save an entity to the database (synchronous version).
        
        Args:
            entity_name: Name of the entity
            entity: Entity dictionary
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            ID of the saved entity
        """
        return self._utils._create_sync_method(self._impl_save_entity, entity_name, entity, user_id=user_id, comment=comment)()
    
    async def save_entity_async(self, entity_name: str, entity: Dict[str, Any], 
                              user_id: Optional[str] = None, comment: Optional[str] = None) -> str:
        """
        Save an entity to the database (asynchronous version).
        
        Args:
            entity_name: Name of the entity
            entity: Entity dictionary
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            ID of the saved entity
        """
        return await self._utils._create_async_method(self._impl_save_entity, entity_name, entity, user_id=user_id, comment=comment)()
    
    async def _impl_get_entity(self, entity_name: str, id: str, is_async: bool,
                              deserialize: bool = True, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Internal implementation for getting an entity by ID.
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            is_async: Whether to use async or sync operations
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Entity dictionary or None if not found
        """
        try:
            # Get the connection
            if is_async:
                conn_ctx = self._db.async_connection()
            else:
                conn_ctx = self._db.sync_connection()
            
            async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
                # Build query
                query = self._sql_generator.get_entity_by_id_sql(entity_name, include_deleted)
                params = (id,)
                
                # Execute query
                if is_async:
                    result = await conn.execute_async(query, params)
                else:
                    result = conn.execute_sync(query, params)
                
                if not result:
                    return None
                
                # Get column names - only if needed for deserialization
                columns = []
                if deserialize:
                    cols_sql, cols_params = self._sql_generator.get_list_columns_sql(entity_name)
                    
                    if is_async:
                        col_info = await conn.execute_async(cols_sql, cols_params)
                    else:
                        col_info = conn.execute_sync(cols_sql, cols_params)
                    
                    # Handle database-specific column info format
                    if self._db_type == 'sqlite':
                        columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
                    else:
                        # PostgreSQL, MySQL
                        columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
                
                # Convert to dictionary
                entity = dict(zip(columns, result[0])) if columns else dict(enumerate(result[0]))
                
                # Deserialize if requested
                if deserialize:
                    return self._utils._deserialize_entity(entity_name, entity)
                
                return entity
                
            # Close connection if using sync mode (async context manager handles it automatically)
            if not is_async:
                conn_ctx.__exit__(None, None, None)
                
        except Exception as e:
            logger.error(f"Error getting entity {entity_name} with ID {id}: {e}")
            raise
    
    def get_entity_sync(self, entity_name: str, id: str, deserialize: bool = True, 
                     include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get an entity by ID (synchronous version).
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Entity dictionary or None if not found
        """
        return self._utils._create_sync_method(
            self._impl_get_entity, 
            entity_name, 
            id, 
            deserialize=deserialize, 
            include_deleted=include_deleted
        )()
    
    async def get_entity_async(self, entity_name: str, id: str, deserialize: bool = True, 
                             include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get an entity by ID (asynchronous version).
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Entity dictionary or None if not found
        """
        return await self._utils._create_async_method(
            self._impl_get_entity, 
            entity_name, 
            id, 
            deserialize=deserialize, 
            include_deleted=include_deleted
        )()
    
    # -------------------- HISTORY OPERATIONS --------------------
    
    async def _impl_save_history(self, entity_name: str, entity: Dict[str, Optional[str]],
                               is_async: bool, conn, user_id: Optional[str] = None, 
                               comment: Optional[str] = None) -> None:
        """
        Internal implementation for saving entity history.
        
        Args:
            entity_name: Name of the entity
            entity: Serialized entity dictionary
            is_async: Whether to use async or sync operations
            conn: Database connection
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
        """
        try:
            # Get current version
            version_query = f"SELECT MAX(version) FROM {entity_name}_history WHERE id = ?"
            
            if is_async:
                current_version = await conn.execute_async(version_query, (entity["id"],))
            else:
                current_version = conn.execute_sync(version_query, (entity["id"],))
            
            version = 1
            if current_version and current_version[0] and current_version[0][0]:
                version = current_version[0][0] + 1
            
            # Add history fields
            history_entity = entity.copy()
            history_entity["version"] = str(version)
            history_entity["history_timestamp"] = datetime.datetime.utcnow().isoformat()
            history_entity["history_user_id"] = user_id
            history_entity["history_comment"] = comment
            
            # Get fields and values
            fields = list(history_entity.keys())
            values = [history_entity[field] for field in fields]
            
            # Insert into history table
            fields_str = ', '.join(fields)
            placeholders = ', '.join(['?'] * len(fields))
            
            hist_sql = f"INSERT INTO {entity_name}_history ({fields_str}) VALUES ({placeholders})"
            
            if is_async:
                await conn.execute_async(hist_sql, tuple(values))
            else:
                conn.execute_sync(hist_sql, tuple(values))
                
        except Exception as e:
            logger.error(f"Error saving history for {entity_name}: {e}")
            raise

    async def _impl_enable_history(self, entity_name: str, is_async: bool) -> None:
        """
        Internal implementation for enabling history tracking for an entity.
        
        Args:
            entity_name: Name of the entity
            is_async: Whether to use async or sync operations
        """
        try:
            # Get the connection with transaction
            if is_async:
                conn_ctx = self._db.async_transaction()
            else:
                conn_ctx = self._db.sync_transaction()
            
            async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
                # First make sure the main table exists
                check_sql, check_params = self._sql_generator.get_check_table_exists_sql(entity_name)
                
                if is_async:
                    table_exists = await conn.execute_async(check_sql, check_params)
                else:
                    table_exists = conn.execute_sync(check_sql, check_params)
                
                if not table_exists:
                    raise ValueError(f"Cannot enable history for non-existent entity '{entity_name}'")
                
                # Check if history table exists
                hist_check_sql, hist_params = self._sql_generator.get_check_table_exists_sql(f"{entity_name}_history")
                
                if is_async:
                    history_exists = await conn.execute_async(hist_check_sql, hist_params)
                else:
                    history_exists = conn.execute_sync(hist_check_sql, hist_params)
                
                if not history_exists:
                    # Get columns from the main table
                    columns = []
                    cols_sql, cols_params = self._sql_generator.get_list_columns_sql(entity_name)
                    
                    if is_async:
                        col_info = await conn.execute_async(cols_sql, cols_params)
                    else:
                        col_info = conn.execute_sync(cols_sql, cols_params)
                    
                    # Process column info based on database type
                    if self._db_type == 'sqlite':
                        columns = [(col[1], col[2]) for col in col_info]  # (name, type)
                    else:
                        # PostgreSQL, MySQL
                        columns = [(col[0], col[1]) for col in col_info]  # (name, type)
                    
                    # Create the history table
                    create_sql = self._sql_generator.get_create_history_table_sql(entity_name, columns)
                    
                    if is_async:
                        await conn.execute_async(create_sql)
                    else:
                        conn.execute_sync(create_sql)
                    
                    self._history_enabled.add(entity_name)
                
            # Close connection if using sync mode (async context manager handles it automatically)
            if not is_async:
                conn_ctx.__exit__(None, None, None)
                
        except Exception as e:
            logger.error(f"Error enabling history for {entity_name}: {e}")
            raise
    
    def enable_history_sync(self, entity_name: str) -> None:
        """
        Enable history tracking for an entity (synchronous version).
        
        Args:
            entity_name: Name of the entity
        """
        return self._utils._create_sync_method(self._impl_enable_history, entity_name)()
    
    async def enable_history_async(self, entity_name: str) -> None:
        """
        Enable history tracking for an entity (asynchronous version).
        
        Args:
            entity_name: Name of the entity
        """
        return await self._utils._create_async_method(self._impl_enable_history, entity_name)()
    
    # -------------------- TABLE OPERATIONS --------------------
    
    async def _impl_ensure_table(self, entity_name: str, entity: Dict[str, Any], 
                                is_async: bool, conn) -> None:
        """
        Internal implementation for ensuring an entity table exists with required columns.
        
        Args:
            entity_name: Name of the entity
            entity: Entity dictionary
            is_async: Whether to use async or sync operations
            conn: Database connection
        """
        try:
            # Check if table exists
            check_sql, check_params = self._sql_generator.get_check_table_exists_sql(entity_name)
            
            if is_async:
                table_exists = await conn.execute_async(check_sql, check_params)
            else:
                table_exists = conn.execute_sync(check_sql, check_params)
            
            if not table_exists:
                # Create the table with basic columns
                columns = [
                    ("id", "TEXT"),
                    ("created_at", "TEXT"),
                    ("updated_at", "TEXT"),
                    ("deleted_at", "TEXT")
                ]
                create_sql = self._sql_generator.get_create_table_sql(entity_name, columns)
                
                if is_async:
                    await conn.execute_async(create_sql)
                else:
                    conn.execute_sync(create_sql)
            
            # Check if metadata table exists
            meta_check_sql, meta_params = self._sql_generator.get_check_table_exists_sql(f"{entity_name}_meta")
            
            if is_async:
                meta_exists = await conn.execute_async(meta_check_sql, meta_params)
            else:
                meta_exists = conn.execute_sync(meta_check_sql, meta_params)
            
            if not meta_exists:
                # Create metadata table
                meta_sql = self._sql_generator.get_create_meta_table_sql(entity_name)
                
                if is_async:
                    await conn.execute_async(meta_sql)
                else:
                    conn.execute_sync(meta_sql)
                
                # Add basic metadata
                upsert_meta_sql = self._sql_generator.get_meta_upsert_sql(entity_name)
                
                basic_meta = [
                    ("id", "str"),
                    ("created_at", "datetime"),
                    ("updated_at", "datetime"),
                    ("deleted_at", "datetime")
                ]
                
                for name, typ in basic_meta:
                    if is_async:
                        await conn.execute_async(upsert_meta_sql, (name, typ))
                    else:
                        conn.execute_sync(upsert_meta_sql, (name, typ))
                
                # Update cache
                self._meta_cache[entity_name] = {
                    "id": "str",
                    "created_at": "datetime",
                    "updated_at": "datetime",
                    "deleted_at": "datetime"
                }
                self._keys_cache[entity_name] = ["id", "created_at", "updated_at", "deleted_at"]
                self._types_cache[entity_name] = ["str", "datetime", "datetime", "datetime"]
            
            # Load metadata if not in cache
            if entity_name not in self._meta_cache:
                if is_async:
                    meta_rows = await conn.execute_async(f"SELECT name, type FROM {entity_name}_meta")
                else:
                    meta_rows = conn.execute_sync(f"SELECT name, type FROM {entity_name}_meta")
                
                meta = {name: typ for name, typ in meta_rows}
                self._meta_cache[entity_name] = meta
                self._keys_cache[entity_name] = list(meta.keys())
                self._types_cache[entity_name] = list(meta.values())
            
            # Get existing columns in the table
            cols_sql, cols_params = self._sql_generator.get_list_columns_sql(entity_name)
            
            if is_async:
                col_info = await conn.execute_async(cols_sql, cols_params)
            else:
                col_info = conn.execute_sync(cols_sql, cols_params)
            
            # Process column info based on database type
            existing_columns = []
            if self._db_type == 'sqlite':
                existing_columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
            else:
                # PostgreSQL, MySQL
                existing_columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
            
            # Check for missing columns and add them
            for field, value in entity.items():
                if field not in existing_columns:
                    # Add column to table
                    await self._impl_add_column_if_not_exists(
                        entity_name, field, value, is_async, conn, existing_columns
                    )
                else:
                    # Column exists - ensure type consistency
                    self._check_field_type_consistency(entity_name, field, value)
                    
        except Exception as e:
            logger.error(f"Error ensuring table for {entity_name}: {e}")
            raise
    
    async def _impl_add_column_if_not_exists(self, entity_name: str, field: str, 
                                          value: Any, is_async: bool, conn, 
                                          existing_columns: List[str]) -> None:
        """
        Internal implementation for adding a column to a table if it doesn't exist.
        
        Args:
            entity_name: Name of the entity
            field: Field (column) name
            value: Example value for type inference
            is_async: Whether to use async or sync operations
            conn: Database connection
            existing_columns: List of existing column names
        """
        try:
            # Infer field type
            field_type = self._utils._infer_type(value)
            
            # Add column if it doesn't exist
            if field not in existing_columns:
                # Different databases have different approaches to adding columns
                if self._db_type == 'postgres':
                    # PostgreSQL supports IF NOT EXISTS
                    add_col_sql = self._sql_generator.get_add_column_sql(entity_name, field)
                    
                    if is_async:
                        await conn.execute_async(add_col_sql)
                    else:
                        conn.execute_sync(add_col_sql)
                        
                elif self._db_type in ('mysql', 'sqlite'):
                    # MySQL and SQLite don't support IF NOT EXISTS for columns
                    # Column existence was already checked with existing_columns
                    add_col_sql = self._sql_generator.get_add_column_sql(entity_name, field)
                    
                    if is_async:
                        await conn.execute_async(add_col_sql)
                    else:
                        conn.execute_sync(add_col_sql)
            
            # Update metadata
            if field not in self._meta_cache.get(entity_name, {}):
                meta_sql = self._sql_generator.get_meta_upsert_sql(entity_name)
                
                if is_async:
                    await conn.execute_async(meta_sql, (field, field_type))
                else:
                    conn.execute_sync(meta_sql, (field, field_type))
                
                # Update cache
                if entity_name in self._meta_cache:
                    self._meta_cache[entity_name][field] = field_type
                    self._keys_cache[entity_name].append(field)
                    self._types_cache[entity_name].append(field_type)
                    
        except Exception as e:
            logger.error(f"Error adding column {field} to {entity_name}: {e}")
            raise
    
    def _check_field_type_consistency(self, entity_name: str, field: str, value: Any) -> None:
        """
        Check that the type of a field is consistent with its stored metadata.
        
        Args:
            entity_name: Name of the entity
            field: Field name
            value: Value to check
            
        Raises:
            Exception: If the type is inconsistent
        """
        if value is None:
            return  # None values don't trigger type consistency checks
        
        # Get stored type information
        stored_type = self._meta_cache.get(entity_name, {}).get(field)
        
        if stored_type is None:
            return  # No stored type yet, so no inconsistency
        
        # Infer type from current value
        current_type = self._utils._infer_type(value)
        
        # Check if types are compatible
        if stored_type != current_type:
            raise Exception(
                f"Type mismatch for field '{field}' in entity '{entity_name}': "
                f"stored as '{stored_type}', but provided value is '{current_type}'"
            )
                
    # -------------------- DELETE OPERATIONS --------------------
    
    # Continuing from where we left off in the DELETE OPERATIONS section

async def _impl_delete_entity(self, entity_name: str, id: str, is_async: bool,
                           permanent: bool = False, user_id: Optional[str] = None, 
                           comment: Optional[str] = None) -> bool:
    """
    Internal implementation for deleting an entity.
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        is_async: Whether to use async or sync operations
        permanent: Whether to permanently delete the entity
        user_id: Optional ID of the user making the change
        comment: Optional comment about the deletion
        
    Returns:
        True if entity was deleted, False if not found
    """
    try:
        # Get the connection with transaction
        if is_async:
            conn_ctx = self._db.async_transaction()
        else:
            conn_ctx = self._db.sync_transaction()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Check if entity exists
            query = f"SELECT COUNT(*) FROM {entity_name} WHERE id = ?"
            params = (id,)
            
            if is_async:
                result = await conn.execute_async(query, params)
            else:
                result = conn.execute_sync(query, params)
            
            if not result or result[0][0] == 0:
                return False
            
            if permanent:
                # Permanent delete
                delete_sql = f"DELETE FROM {entity_name} WHERE id = ?"
                
                if is_async:
                    await conn.execute_async(delete_sql, (id,))
                else:
                    conn.execute_sync(delete_sql, (id,))
            else:
                # Soft delete
                now = datetime.datetime.utcnow().isoformat()
                soft_delete_sql = self._sql_generator.get_soft_delete_sql(entity_name)
                
                if is_async:
                    await conn.execute_async(soft_delete_sql, (now, now, user_id, id))
                else:
                    conn.execute_sync(soft_delete_sql, (now, now, user_id, id))
                
                # Save to history if enabled
                if entity_name in self._history_enabled:
                    # Get the updated entity
                    entity_query = f"SELECT * FROM {entity_name} WHERE id = ?"
                    
                    if is_async:
                        result = await conn.execute_async(entity_query, (id,))
                    else:
                        result = conn.execute_sync(entity_query, (id,))
                    
                    if result:
                        # Get column names
                        cols_sql, cols_params = self._sql_generator.get_list_columns_sql(entity_name)
                        
                        if is_async:
                            col_info = await conn.execute_async(cols_sql, cols_params)
                        else:
                            col_info = conn.execute_sync(cols_sql, cols_params)
                        
                        # Process column info based on database type
                        columns = []
                        if self._db_type == 'sqlite':
                            columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
                        else:
                            # PostgreSQL, MySQL
                            columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
                        
                        # Convert to dictionary
                        serialized = dict(zip(columns, result[0]))
                        
                        # Save to history with "deleted" comment
                        delete_comment = comment or "Entity deleted"
                        await self._impl_save_history(entity_name, serialized, is_async, conn, user_id, delete_comment)
            
            return True
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error deleting entity {entity_name} with ID {id}: {e}")
        raise

def delete_entity_sync(self, entity_name: str, id: str, permanent: bool = False,
                     user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
    """
    Delete an entity from the database (synchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        permanent: Whether to permanently delete the entity
        user_id: Optional ID of the user making the change
        comment: Optional comment about the deletion
        
    Returns:
        True if entity was deleted, False if not found
    """
    return self._utils._create_sync_method(
        self._impl_delete_entity,
        entity_name,
        id,
        permanent=permanent,
        user_id=user_id,
        comment=comment
    )()

async def delete_entity_async(self, entity_name: str, id: str, permanent: bool = False,
                           user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
    """
    Delete an entity from the database (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        permanent: Whether to permanently delete the entity
        user_id: Optional ID of the user making the change
        comment: Optional comment about the deletion
        
    Returns:
        True if entity was deleted, False if not found
    """
    return await self._utils._create_async_method(
        self._impl_delete_entity,
        entity_name,
        id,
        permanent=permanent,
        user_id=user_id,
        comment=comment
    )()

# -------------------- RESTORE OPERATIONS --------------------

async def _impl_restore_entity(self, entity_name: str, id: str, is_async: bool,
                            user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
    """
    Internal implementation for restoring a soft-deleted entity.
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        is_async: Whether to use async or sync operations
        user_id: Optional ID of the user making the change
        comment: Optional comment about the restoration
        
    Returns:
        True if entity was restored, False if not found or not deleted
    """
    try:
        # Get the connection with transaction
        if is_async:
            conn_ctx = self._db.async_transaction()
        else:
            conn_ctx = self._db.sync_transaction()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Check if entity exists and is deleted
            query = f"SELECT COUNT(*) FROM {entity_name} WHERE id = ? AND deleted_at IS NOT NULL"
            params = (id,)
            
            if is_async:
                result = await conn.execute_async(query, params)
            else:
                result = conn.execute_sync(query, params)
            
            if not result or result[0][0] == 0:
                return False
            
            # Update the entity
            now = datetime.datetime.utcnow().isoformat()
            restore_sql = self._sql_generator.get_restore_entity_sql(entity_name)
            
            if is_async:
                await conn.execute_async(restore_sql, (now, user_id, id))
            else:
                conn.execute_sync(restore_sql, (now, user_id, id))
            
            # Save to history if enabled
            if entity_name in self._history_enabled:
                # Get the updated entity
                entity_query = f"SELECT * FROM {entity_name} WHERE id = ?"
                
                if is_async:
                    result = await conn.execute_async(entity_query, (id,))
                else:
                    result = conn.execute_sync(entity_query, (id,))
                
                if result:
                    # Get column names
                    cols_sql, cols_params = self._sql_generator.get_list_columns_sql(entity_name)
                    
                    if is_async:
                        col_info = await conn.execute_async(cols_sql, cols_params)
                    else:
                        col_info = conn.execute_sync(cols_sql, cols_params)
                    
                    # Process column info based on database type
                    columns = []
                    if self._db_type == 'sqlite':
                        columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
                    else:
                        # PostgreSQL, MySQL
                        columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
                    
                    # Convert to dictionary
                    serialized = dict(zip(columns, result[0]))
                    
                    # Save to history with "restored" comment
                    restore_comment = comment or "Entity restored"
                    await self._impl_save_history(entity_name, serialized, is_async, conn, user_id, restore_comment)
            
            return True
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error restoring entity {entity_name} with ID {id}: {e}")
        raise

def restore_entity_sync(self, entity_name: str, id: str, 
                      user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
    """
    Restore a soft-deleted entity (synchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        user_id: Optional ID of the user making the change
        comment: Optional comment about the restoration
        
    Returns:
        True if entity was restored, False if not found or not deleted
    """
    return self._utils._create_sync_method(
        self._impl_restore_entity,
        entity_name,
        id,
        user_id=user_id,
        comment=comment
    )()

async def restore_entity_async(self, entity_name: str, id: str,
                            user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
    """
    Restore a soft-deleted entity (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        user_id: Optional ID of the user making the change
        comment: Optional comment about the restoration
        
    Returns:
        True if entity was restored, False if not found or not deleted
    """
    return await self._utils._create_async_method(
        self._impl_restore_entity,
        entity_name,
        id,
        user_id=user_id,
        comment=comment
    )()

# -------------------- QUERY OPERATIONS --------------------

async def _impl_get_entities(self, entity_name: str, is_async: bool,
                          where_clause: Optional[str] = None,
                          params: Optional[tuple] = None,
                          order_by: Optional[str] = None,
                          limit: Optional[int] = None,
                          offset: Optional[int] = None,
                          deserialize: bool = True,
                          include_deleted: bool = False) -> List[Dict[str, Any]]:
    """
    Internal implementation for getting entities with flexible query options.
    
    Args:
        entity_name: Name of the entity
        is_async: Whether to use async or sync operations
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        deserialize: Whether to deserialize values to Python types
        include_deleted: Whether to include soft-deleted entities
        
    Returns:
        List of entity dictionaries
    """
    try:
        # Get the connection
        if is_async:
            conn_ctx = self._db.async_connection()
        else:
            conn_ctx = self._db.sync_connection()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Build query
            query = self._sql_generator.get_query_builder_sql(
                entity_name,
                where_clause,
                order_by,
                limit,
                offset,
                include_deleted
            )
            
            # Execute query
            if is_async:
                result = await conn.execute_async(query, params or ())
            else:
                result = conn.execute_sync(query, params or ())
            
            if not result:
                return []
            
            # Get column names once - only if needed for deserialization
            columns = []
            if deserialize:
                cols_sql, cols_params = self._sql_generator.get_list_columns_sql(entity_name)
                
                if is_async:
                    col_info = await conn.execute_async(cols_sql, cols_params)
                else:
                    col_info = conn.execute_sync(cols_sql, cols_params)
                
                # Handle database-specific column info format
                if self._db_type == 'sqlite':
                    columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
                else:
                    # PostgreSQL, MySQL
                    columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
            
            # Process results
            entities = []
            for row in result:
                # Convert to dictionary
                entity = dict(zip(columns, row)) if columns else dict(enumerate(row))
                
                # Deserialize if requested
                if deserialize:
                    entity = self._utils._deserialize_entity(entity_name, entity)
                
                entities.append(entity)
            
            return entities
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error getting entities for {entity_name}: {e}")
        raise

def get_entities_sync(self, entity_name: str, where_clause: Optional[str] = None,
                   params: Optional[tuple] = None, order_by: Optional[str] = None,
                   limit: Optional[int] = None, offset: Optional[int] = None,
                   deserialize: bool = True, include_deleted: bool = False) -> List[Dict[str, Any]]:
    """
    Get entities with flexible query options (synchronous version).
    
    Args:
        entity_name: Name of the entity
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        deserialize: Whether to deserialize values to Python types
        include_deleted: Whether to include soft-deleted entities
        
    Returns:
        List of entity dictionaries
    """
    return self._utils._create_sync_method(
        self._impl_get_entities,
        entity_name,
        where_clause=where_clause,
        params=params,
        order_by=order_by,
        limit=limit,
        offset=offset,
        deserialize=deserialize,
        include_deleted=include_deleted
    )()

async def get_entities_async(self, entity_name: str, where_clause: Optional[str] = None,
                         params: Optional[tuple] = None, order_by: Optional[str] = None,
                         limit: Optional[int] = None, offset: Optional[int] = None,
                         deserialize: bool = True, include_deleted: bool = False) -> List[Dict[str, Any]]:
    """
    Get entities with flexible query options (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        deserialize: Whether to deserialize values to Python types
        include_deleted: Whether to include soft-deleted entities
        
    Returns:
        List of entity dictionaries
    """
    return await self._utils._create_async_method(
        self._impl_get_entities,
        entity_name,
        where_clause=where_clause,
        params=params,
        order_by=order_by,
        limit=limit,
        offset=offset,
        deserialize=deserialize,
        include_deleted=include_deleted
    )()

async def _impl_count_entities(self, entity_name: str, is_async: bool,
                            where_clause: Optional[str] = None,
                            params: Optional[tuple] = None,
                            include_deleted: bool = False) -> int:
    """
    Internal implementation for counting entities.
    
    Args:
        entity_name: Name of the entity
        is_async: Whether to use async or sync operations
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        include_deleted: Whether to include soft-deleted entities
        
    Returns:
        Number of entities matching the criteria
    """
    try:
        # Get the connection
        if is_async:
            conn_ctx = self._db.async_connection()
        else:
            conn_ctx = self._db.sync_connection()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Build query
            query = self._sql_generator.get_count_entities_sql(
                entity_name,
                where_clause,
                include_deleted
            )
            
            # Execute query
            if is_async:
                result = await conn.execute_async(query, params or ())
            else:
                result = conn.execute_sync(query, params or ())
            
            if not result:
                return 0
            
            return result[0][0]
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error counting entities for {entity_name}: {e}")
        raise

def count_entities_sync(self, entity_name: str, where_clause: Optional[str] = None,
                     params: Optional[tuple] = None, include_deleted: bool = False) -> int:
    """
    Count entities matching criteria (synchronous version).
    
    Args:
        entity_name: Name of the entity
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        include_deleted: Whether to include soft-deleted entities
        
    Returns:
        Number of entities matching the criteria
    """
    return self._utils._create_sync_method(
        self._impl_count_entities,
        entity_name,
        where_clause=where_clause,
        params=params,
        include_deleted=include_deleted
    )()

async def count_entities_async(self, entity_name: str, where_clause: Optional[str] = None,
                           params: Optional[tuple] = None, include_deleted: bool = False) -> int:
    """
    Count entities matching criteria (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        include_deleted: Whether to include soft-deleted entities
        
    Returns:
        Number of entities matching the criteria
    """
    return await self._utils._create_async_method(
        self._impl_count_entities,
        entity_name,
        where_clause=where_clause,
        params=params,
        include_deleted=include_deleted
    )()

# -------------------- UPDATE OPERATIONS --------------------

async def _impl_update_entity_fields(self, entity_name: str, id: str, fields: Dict[str, Any],
                                 is_async: bool, user_id: Optional[str] = None,
                                 comment: Optional[str] = None) -> bool:
    """
    Internal implementation for updating specific fields of an entity.
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        fields: Dictionary of field names and values to update
        is_async: Whether to use async or sync operations
        user_id: Optional ID of the user making the change
        comment: Optional comment about the update
        
    Returns:
        True if entity was updated, False if not found
    """
    try:
        # Get the connection with transaction
        if is_async:
            conn_ctx = self._db.async_transaction()
        else:
            conn_ctx = self._db.sync_transaction()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Check if entity exists
            query = f"SELECT COUNT(*) FROM {entity_name} WHERE id = ? AND deleted_at IS NULL"
            params = (id,)
            
            if is_async:
                result = await conn.execute_async(query, params)
            else:
                result = conn.execute_sync(query, params)
            
            if not result or result[0][0] == 0:
                return False
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
            # Serialize field values
            serialized_fields = {}
            for field, value in fields.items():
                field_type = meta.get(field, None)
                serialized_fields[field] = self._utils._serialize_value(value, field_type)
                
                # Check type consistency
                self._check_field_type_consistency(entity_name, field, value)
            
            # Generate update SQL
            field_names = list(serialized_fields.keys())
            update_sql = self._sql_generator.get_update_fields_sql(entity_name, field_names)
            
            # Build parameters
            now = datetime.datetime.utcnow().isoformat()
            params = [serialized_fields[field] for field in field_names]
            params.extend([now, user_id, id])  # Add updated_at, updated_by, and id
            
            # Execute update
            if is_async:
                await conn.execute_async(update_sql, tuple(params))
            else:
                conn.execute_sync(update_sql, tuple(params))
            
            # Save to history if enabled
            if entity_name in self._history_enabled:
                # Get the updated entity
                entity_query = f"SELECT * FROM {entity_name} WHERE id = ?"
                
                if is_async:
                    result = await conn.execute_async(entity_query, (id,))
                else:
                    result = conn.execute_sync(entity_query, (id,))
                
                if result:
                    # Get column names
                    cols_sql, cols_params = self._sql_generator.get_list_columns_sql(entity_name)
                    
                    if is_async:
                        col_info = await conn.execute_async(cols_sql, cols_params)
                    else:
                        col_info = conn.execute_sync(cols_sql, cols_params)
                    
                    # Process column info based on database type
                    columns = []
                    if self._db_type == 'sqlite':
                        columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
                    else:
                        # PostgreSQL, MySQL
                        columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
                    
                    # Convert to dictionary
                    serialized = dict(zip(columns, result[0]))
                    
                    # Save to history
                    update_comment = comment or f"Updated fields: {', '.join(field_names)}"
                    await self._impl_save_history(entity_name, serialized, is_async, conn, user_id, update_comment)
            
            return True
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error updating fields for entity {entity_name} with ID {id}: {e}")
        raise

def update_entity_fields_sync(self, entity_name: str, id: str, fields: Dict[str, Any],
                           user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
    """
    Update specific fields of an entity (synchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        fields: Dictionary of field names and values to update
        user_id: Optional ID of the user making the change
        comment: Optional comment about the update
        
    Returns:
        True if entity was updated, False if not found
    """
    return self._utils._create_sync_method(
        self._impl_update_entity_fields,
        entity_name,
        id,
        fields,
        user_id=user_id,
        comment=comment
    )()

async def update_entity_fields_async(self, entity_name: str, id: str, fields: Dict[str, Any],
                                 user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
    """
    Update specific fields of an entity (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        fields: Dictionary of field names and values to update
        user_id: Optional ID of the user making the change
        comment: Optional comment about the update
        
    Returns:
        True if entity was updated, False if not found
    """
    return await self._utils._create_async_method(
        self._impl_update_entity_fields,
        entity_name,
        id,
        fields,
        user_id=user_id,
        comment=comment
    )()

# -------------------- HISTORY OPERATIONS --------------------

async def _impl_get_entity_history(self, entity_name: str, id: str, is_async: bool,
                               limit: Optional[int] = None, 
                               offset: Optional[int] = None,
                               deserialize: bool = True) -> List[Dict[str, Any]]:
    """
    Internal implementation for getting the history of an entity.
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        is_async: Whether to use async or sync operations
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        deserialize: Whether to deserialize values to Python types
        
    Returns:
        List of entity history dictionaries
    """
    try:
        # Check if history is enabled
        if entity_name not in self._history_enabled:
            raise ValueError(f"History not enabled for entity '{entity_name}'")
        
        # Get the connection
        if is_async:
            conn_ctx = self._db.async_connection()
        else:
            conn_ctx = self._db.sync_connection()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Build query
            sql, params = self._sql_generator.get_entity_history_sql(entity_name, id)
            
            # Add limit and offset if provided
            if limit is not None:
                sql += f" LIMIT {limit}"
            
            if offset is not None:
                if self._db_type == 'mysql':
                    # MySQL uses LIMIT offset, limit syntax
                    if ' LIMIT ' in sql:
                        sql = sql.replace(' LIMIT ', f' LIMIT {offset}, ')
                    else:
                        sql += f" LIMIT {offset}, 18446744073709551615"  # MySQL's max BIGINT
                else:
                    # PostgreSQL and SQLite use OFFSET
                    sql += f" OFFSET {offset}"
            
            # Execute query
            if is_async:
                result = await conn.execute_async(sql, params)
            else:
                result = conn.execute_sync(sql, params)
            
            if not result:
                return []
            
            # Get column names
            cols_sql, cols_params = self._sql_generator.get_list_columns_sql(f"{entity_name}_history")
            
            if is_async:
                col_info = await conn.execute_async(cols_sql, cols_params)
            else:
                col_info = conn.execute_sync(cols_sql, cols_params)
            
            # Process column info based on database type
            columns = []
            if self._db_type == 'sqlite':
                columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
            else:
                # PostgreSQL, MySQL
                columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
            
            # Process results
            history = []
            for row in result:
                # Convert to dictionary
                entry = dict(zip(columns, row))
                
                # Deserialize if requested
                if deserialize:
                    # Extract regular fields (exclude history-specific fields)
                    entity_fields = {k: v for k, v in entry.items() 
                                if k not in ('version', 'history_timestamp', 'history_user_id', 'history_comment')}
                    
                    deserialized = self._utils._deserialize_entity(entity_name, entity_fields)
                    
                    # Add history-specific fields back
                    for k in ('version', 'history_timestamp', 'history_user_id', 'history_comment'):
                        if k in entry:
                            deserialized[k] = entry[k]
                    
                    history.append(deserialized)
                else:
                    history.append(entry)
            
            return history
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error getting history for entity {entity_name} with ID {id}: {e}")
        raise

def get_entity_history_sync(self, entity_name: str, id: str, limit: Optional[int] = None,
                         offset: Optional[int] = None, deserialize: bool = True) -> List[Dict[str, Any]]:
    """
    Get the history of an entity (synchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        deserialize: Whether to deserialize values to Python types
        
    Returns:
        List of entity history dictionaries
    """
    return self._utils._create_sync_method(
        self._impl_get_entity_history,
        entity_name,
        id,
        limit=limit,
        offset=offset,
        deserialize=deserialize
    )()

async def get_entity_history_async(self, entity_name: str, id: str, limit: Optional[int] = None,
                               offset: Optional[int] = None, deserialize: bool = True) -> List[Dict[str, Any]]:
    """
    Get the history of an entity (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        deserialize: Whether to deserialize values to Python types
        
    Returns:
        List of entity history dictionaries
    """
    return await self._utils._create_async_method(
        self._impl_get_entity_history,
        entity_name,
        id,
        limit=limit,
        offset=offset,
        deserialize=deserialize
    )()

async def _impl_get_entity_version(self, entity_name: str, id: str, version: int, is_async: bool,
                                deserialize: bool = True) -> Optional[Dict[str, Any]]:
    """
    Internal implementation for getting a specific version of an entity.
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        version: Version number
        is_async: Whether to use async or sync operations
        deserialize: Whether to deserialize values to Python types
        
    Returns:
        Entity version dictionary or None if not found
    """
    try:
        # Check if history is enabled
        if entity_name not in self._history_enabled:
            raise ValueError(f"History not enabled for entity '{entity_name}'")
        
        # Get the connection
        if is_async:
            conn_ctx = self._db.async_connection()
        else:
            conn_ctx = self._db.sync_connection()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Build query
            sql, params = self._sql_generator.get_entity_version_sql(entity_name, id, version)
            
            # Execute query
            if is_async:
                result = await conn.execute_async(sql, params)
            else:
                result = conn.execute_sync(sql, params)
            
            if not result:
                return None
            
            # Get column names
            cols_sql, cols_params = self._sql_generator.get_list_columns_sql(f"{entity_name}_history")
            
            if is_async:
                col_info = await conn.execute_async(cols_sql, cols_params)
            else:
                col_info = conn.execute_sync(cols_sql, cols_params)
            
            # Process column info based on database type
            columns = []
            if self._db_type == 'sqlite':
                columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
            else:
                # PostgreSQL, MySQL
                columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
            
            # Convert to dictionary
            entry = dict(zip(columns, result[0]))
            
            # Deserialize if requested
            if deserialize:
                # Extract regular fields (exclude history-specific fields)
                entity_fields = {k: v for k, v in entry.items() 
                            if k not in ('version', 'history_timestamp', 'history_user_id', 'history_comment')}
                
                deserialized = self._utils._deserialize_entity(entity_name, entity_fields)
                
                # Add history-specific fields back
                for k in ('version', 'history_timestamp', 'history_user_id', 'history_comment'):
                    if k in entry:
                        deserialized[k] = entry[k]
                
                return deserialized
            else:
                return entry
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error getting entity version for {entity_name} with ID {id} and version {version}: {e}")
        raise

def get_entity_version_sync(self, entity_name: str, id: str, version: int, 
                         deserialize: bool = True) -> Optional[Dict[str, Any]]:
    """
    Get a specific version of an entity (synchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        version: Version number
        deserialize: Whether to deserialize values to Python types
        
    Returns:
        Entity version dictionary or None if not found
    """
    return self._utils._create_sync_method(
        self._impl_get_entity_version,
        entity_name,
        id,
        version,
        deserialize=deserialize
    )()

async def get_entity_version_async(self, entity_name: str, id: str, version: int,
                               deserialize: bool = True) -> Optional[Dict[str, Any]]:
    """
    Get a specific version of an entity (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        version: Version number
        deserialize: Whether to deserialize values to Python types
        
    Returns:
        Entity version dictionary or None if not found
    """
    return await self._utils._create_async_method(
        self._impl_get_entity_version,
        entity_name,
        id,
        version,
        deserialize=deserialize
    )()

# -------------------- SCHEMA OPERATIONS --------------------

async def _impl_get_entity_schema(self, entity_name: str, is_async: bool) -> Dict[str, str]:
    """
    Internal implementation for getting the schema of an entity.
    
    Args:
        entity_name: Name of the entity
        is_async: Whether to use async or sync operations
        
    Returns:
        Dictionary mapping field names to their types
    """
    try:
        # Check if metadata is already in cache
        if entity_name in self._meta_cache:
            return self._meta_cache[entity_name].copy()
        
        # Get the connection
        if is_async:
            conn_ctx = self._db.async_connection()
        else:
            conn_ctx = self._db.sync_connection()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Check if metadata table exists
            meta_check_sql, meta_params = self._sql_generator.get_check_table_exists_sql(f"{entity_name}_meta")
            
            if is_async:
                meta_exists = await conn.execute_async(meta_check_sql, meta_params)
            else:
                meta_exists = conn.execute_sync(meta_check_sql, meta_params)
            
            if not meta_exists:
                raise ValueError(f"Entity '{entity_name}' does not exist")
            
            # Get metadata
            if is_async:
                meta_rows = await conn.execute_async(f"SELECT name, type FROM {entity_name}_meta")
            else:
                meta_rows = conn.execute_sync(f"SELECT name, type FROM {entity_name}_meta")
            
            # Build metadata dictionary
            meta = {name: typ for name, typ in meta_rows}
            
            # Cache metadata
            self._meta_cache[entity_name] = meta
            self._keys_cache[entity_name] = list(meta.keys())
            self._types_cache[entity_name] = list(meta.values())
            
            return meta.copy()
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error getting schema for entity {entity_name}: {e}")
        raise

def get_entity_schema_sync(self, entity_name: str) -> Dict[str, str]:
    """
    Get the schema of an entity (synchronous version).
    
    Args:
        entity_name: Name of the entity
        
    Returns:
        Dictionary mapping field names to their types
    """
    return self._utils._create_sync_method(
        self._impl_get_entity_schema,
        entity_name
    )()

async def get_entity_schema_async(self, entity_name: str) -> Dict[str, str]:
    """
    Get the schema of an entity (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        
    Returns:
        Dictionary mapping field names to their types
    """
    return await self._utils._create_async_method(
        self._impl_get_entity_schema,
        entity_name
    )()

async def _impl_list_all_entities(self, is_async: bool) -> List[str]:
    """
    Internal implementation for listing all entity names.
    
    Args:
        is_async: Whether to use async or sync operations
        
    Returns:
        List of entity names
    """
    try:
        # Get the connection
        if is_async:
            conn_ctx = self._db.async_connection()
        else:
            conn_ctx = self._db.sync_connection()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Get list tables SQL
            sql, params = self._sql_generator.get_list_tables_sql()
            
            # Execute and normalize results
            if is_async:
                tables = await conn.execute_async(sql, params)
            else:
                tables = conn.execute_sync(sql, params)
            
            # Process metadata tables to get entity names
            entity_names = []
            for table_row in tables:
                table = table_row[0]
                if table.endswith("_meta"):
                    entity_name = table[:-5]  # Remove _meta suffix
                    entity_names.append(entity_name)
            
            return sorted(entity_names)
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error listing entities: {e}")
        raise

def list_all_entities_sync(self) -> List[str]:
    """
    List all entity names (synchronous version).
    
    Returns:
        List of entity names
    """
    return self._utils._create_sync_method(
        self._impl_list_all_entities
    )()

async def list_all_entities_async(self) -> List[str]:
    """
    List all entity names (asynchronous version).
    
    Returns:
        List of entity names
    """
    return await self._utils._create_async_method(
        self._impl_list_all_entities
    )()

# -------------------- UTILITY METHODS --------------------

def create_entity_model(self, entity_name: str, include_id: bool = True) -> type:
    """
    Dynamically create a data class model for an entity.
    
    Args:
        entity_name: Name of the entity
        include_id: Whether to include the ID field
        
    Returns:
        A dynamically created dataclass type for the entity
    """
    # Get entity schema
    schema = self.get_entity_schema_sync(entity_name)
    
    # Prepare annotations
    annotations = {}
    for field, field_type in schema.items():
        # Skip ID if not requested
        if field == 'id' and not include_id:
            continue
        
        # Map string type names to Python types
        py_type = {
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'dict': dict,
            'list': list,
            'set': set,
            'tuple': tuple,
            'datetime': 'datetime.datetime',
            'date': 'datetime.date',
            'time': 'datetime.time',
            'bytes': bytes,
        }.get(field_type, Any)
        
        # Add field annotation
        annotations[field] = Optional[py_type]
    
    # Create a dynamic dataclass
    entity_cls = type(
        f"{entity_name.capitalize()}Entity",
        (),
        {
            "__annotations__": annotations,
            **{field: None for field in annotations},
            "__repr__": lambda self: f"{entity_name.capitalize()}Entity({', '.join(f'{k}={v!r}' for k, v in self.__dict__.items())})"
        }
    )
    
    # Apply dataclass decorator
    import dataclasses
    return dataclasses.dataclass(entity_cls)

def entity_to_dict(self, entity_obj: Any) -> Dict[str, Any]:
    """
    Convert an entity object to a dictionary.
    
    Args:
        entity_obj: Entity object (typically a dataclass instance)
        
    Returns:
        Dictionary representation of the entity
    """
    if hasattr(entity_obj, "__dict__"):
        # Filter out None values and private attributes
        return {k: v for k, v in entity_obj.__dict__.items() 
                if not k.startswith("_") and v is not None}
    else:
        raise ValueError("Object is not a valid entity (no __dict__ attribute)")

def dict_to_entity(self, entity_dict: Dict[str, Any], entity_class: type) -> Any:
    """
    Convert a dictionary to an entity object.
    
    Args:
        entity_dict: Dictionary with entity data
        entity_class: Entity class to instantiate
        
    Returns:
        Entity object
    """
    # Create a new instance of the entity class
    entity_obj = entity_class()
    
    # Set attributes from dictionary
    for key, value in entity_dict.items():
        setattr(entity_obj, key, value)
    
    return entity_obj

# -------------------- BULK OPERATIONS --------------------

async def _impl_save_entities_bulk(self, entity_name: str, entities: List[Dict[str, Any]], 
                                is_async: bool, user_id: Optional[str] = None, 
                                comment: Optional[str] = None) -> List[str]:
    """
    Internal implementation for saving multiple entities in a single transaction.
    
    Args:
        entity_name: Name of the entity
        entities: List of entity dictionaries
        is_async: Whether to use async or sync operations
        user_id: Optional ID of the user making the change
        comment: Optional comment about the change
        
    Returns:
        List of saved entity IDs
    """
    if not entities:
        return []
    
    try:
        # Get the connection with transaction
        if is_async:
            conn_ctx = self._db.async_transaction()
        else:
            conn_ctx = self._db.sync_transaction()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Ensure table exists based on the first entity
            await self._impl_ensure_table(entity_name, entities[0], is_async, conn)
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
            # Process each entity
            saved_ids = []
            for entity in entities:
                # Prepare entity with timestamps and ID
                prepared_entity = self._utils._prepare_entity(entity_name, entity, user_id, comment)
                saved_ids.append(prepared_entity["id"])
                
                # Serialize values
                serialized = self._utils._serialize_entity(prepared_entity, meta)
                
                # Get fields and values
                fields = list(serialized.keys())
                values = [serialized[field] for field in fields]
                
                # Generate upsert SQL
                upsert_sql = self._sql_generator.get_upsert_sql(entity_name, fields)
                
                # Execute upsert
                if is_async:
                    await conn.execute_async(upsert_sql, tuple(values))
                else:
                    conn.execute_sync(upsert_sql, tuple(values))
                
                # Save to history if enabled
                if entity_name in self._history_enabled:
                    await self._impl_save_history(entity_name, serialized, is_async, conn, user_id, comment)
            
            return saved_ids
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error bulk saving entities {entity_name}: {e}")
        raise

def save_entities_bulk_sync(self, entity_name: str, entities: List[Dict[str, Any]],
                         user_id: Optional[str] = None, comment: Optional[str] = None) -> List[str]:
    """
    Save multiple entities in a single transaction (synchronous version).
    
    Args:
        entity_name: Name of the entity
        entities: List of entity dictionaries
        user_id: Optional ID of the user making the change
        comment: Optional comment about the change
        
    Returns:
        List of saved entity IDs
    """
    return self._utils._create_sync_method(
        self._impl_save_entities_bulk,
        entity_name,
        entities,
        user_id=user_id,
        comment=comment
    )()

async def save_entities_bulk_async(self, entity_name: str, entities: List[Dict[str, Any]],
                               user_id: Optional[str] = None, comment: Optional[str] = None) -> List[str]:
    """
    Save multiple entities in a single transaction (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        entities: List of entity dictionaries
        user_id: Optional ID of the user making the change
        comment: Optional comment about the change
        
    Returns:
        List of saved entity IDs
    """
    return await self._utils._create_async_method(
        self._impl_save_entities_bulk,
        entity_name,
        entities,
        user_id=user_id,
        comment=comment
    )()

async def _impl_delete_entities_bulk(self, entity_name: str, ids: List[str], is_async: bool,
                                  permanent: bool = False, user_id: Optional[str] = None, 
                                  comment: Optional[str] = None) -> int:
    """
    Internal implementation for deleting multiple entities in a single transaction.
    
    Args:
        entity_name: Name of the entity
        ids: List of entity IDs to delete
        is_async: Whether to use async or sync operations
        permanent: Whether to permanently delete the entities
        user_id: Optional ID of the user making the change
        comment: Optional comment about the deletion
        
    Returns:
        Number of entities deleted
    """
    if not ids:
        return 0
    
    try:
        # Get the connection with transaction
        if is_async:
            conn_ctx = self._db.async_transaction()
        else:
            conn_ctx = self._db.sync_transaction()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Check which entities exist
            id_list = ', '.join(['?'] * len(ids))
            query = f"SELECT id FROM {entity_name} WHERE id IN ({id_list})"
            
            if is_async:
                result = await conn.execute_async(query, tuple(ids))
            else:
                result = conn.execute_sync(query, tuple(ids))
            
            # Extract the IDs that exist
            existing_ids = [row[0] for row in result] if result else []
            
            if not existing_ids:
                return 0
            
            # Prepare ID placeholders for the query
            id_placeholders = ', '.join(['?'] * len(existing_ids))
            
            if permanent:
                # Permanent delete
                delete_sql = f"DELETE FROM {entity_name} WHERE id IN ({id_placeholders})"
                
                if is_async:
                    await conn.execute_async(delete_sql, tuple(existing_ids))
                else:
                    conn.execute_sync(delete_sql, tuple(existing_ids))
            else:
                # Soft delete
                now = datetime.datetime.utcnow().isoformat()
                
                # For soft delete, we need to update each entity individually to add to history
                for entity_id in existing_ids:
                    soft_delete_sql = self._sql_generator.get_soft_delete_sql(entity_name)
                    
                    if is_async:
                        await conn.execute_async(soft_delete_sql, (now, now, user_id, entity_id))
                    else:
                        conn.execute_sync(soft_delete_sql, (now, now, user_id, entity_id))
                    
                    # Save to history if enabled
                    if entity_name in self._history_enabled:
                        # Get the updated entity
                        entity_query = f"SELECT * FROM {entity_name} WHERE id = ?"
                        
                        if is_async:
                            entity_result = await conn.execute_async(entity_query, (entity_id,))
                        else:
                            entity_result = conn.execute_sync(entity_query, (entity_id,))
                        
                        if entity_result:
                            # Get column names
                            cols_sql, cols_params = self._sql_generator.get_list_columns_sql(entity_name)
                            
                            if is_async:
                                col_info = await conn.execute_async(cols_sql, cols_params)
                            else:
                                col_info = conn.execute_sync(cols_sql, cols_params)
                            
                            # Process column info based on database type
                            columns = []
                            if self._db_type == 'sqlite':
                                columns = [col[1] for col in col_info]  # SQLite: col[1] is column name
                            else:
                                # PostgreSQL, MySQL
                                columns = [col[0] for col in col_info]  # Standard SQL: col[0] is column name
                            
                            # Convert to dictionary
                            serialized = dict(zip(columns, entity_result[0]))
                            
                            # Save to history with "deleted" comment
                            delete_comment = comment or "Entity deleted in bulk operation"
                            await self._impl_save_history(entity_name, serialized, is_async, conn, user_id, delete_comment)
            
            return len(existing_ids)
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error bulk deleting entities {entity_name}: {e}")
        raise

def delete_entities_bulk_sync(self, entity_name: str, ids: List[str], permanent: bool = False,
                           user_id: Optional[str] = None, comment: Optional[str] = None) -> int:
    """
    Delete multiple entities in a single transaction (synchronous version).
    
    Args:
        entity_name: Name of the entity
        ids: List of entity IDs to delete
        permanent: Whether to permanently delete the entities
        user_id: Optional ID of the user making the change
        comment: Optional comment about the deletion
        
    Returns:
        Number of entities deleted
    """
    return self._utils._create_sync_method(
        self._impl_delete_entities_bulk,
        entity_name,
        ids,
        permanent=permanent,
        user_id=user_id,
        comment=comment
    )()

async def delete_entities_bulk_async(self, entity_name: str, ids: List[str], permanent: bool = False,
                                 user_id: Optional[str] = None, comment: Optional[str] = None) -> int:
    """
    Delete multiple entities in a single transaction (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        ids: List of entity IDs to delete
        permanent: Whether to permanently delete the entities
        user_id: Optional ID of the user making the change
        comment: Optional comment about the deletion
        
    Returns:
        Number of entities deleted
    """
    return await self._utils._create_async_method(
        self._impl_delete_entities_bulk,
        entity_name,
        ids,
        permanent=permanent,
        user_id=user_id,
        comment=comment
    )()

# -------------------- ADVANCED QUERY OPERATIONS --------------------

def query_builder(self, entity_name: str) -> 'EntityQueryBuilder':
    """
    Create a fluent query builder for an entity.
    
    This method returns a query builder object that provides a fluent interface
    for constructing complex queries with filtering, sorting, and pagination.
    
    Args:
        entity_name: Name of the entity to query
        
    Returns:
        An EntityQueryBuilder instance
    """
    from .query_builder import EntityQueryBuilder
    return EntityQueryBuilder(self, entity_name)

# -------------------- IMPORT/EXPORT OPERATIONS --------------------

async def _impl_export_entities(self, entity_name: str, is_async: bool, 
                             where_clause: Optional[str] = None,
                             params: Optional[tuple] = None,
                             order_by: Optional[str] = None,
                             limit: Optional[int] = None,
                             offset: Optional[int] = None,
                             include_deleted: bool = False,
                             format: str = 'json') -> Union[str, bytes]:
    """
    Internal implementation for exporting entities to various formats.
    
    Args:
        entity_name: Name of the entity
        is_async: Whether to use async or sync operations
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        include_deleted: Whether to include soft-deleted entities
        format: Export format ('json', 'csv', 'yaml')
        
    Returns:
        Exported data as string or bytes
    """
    # Get entities
    entities = await self._impl_get_entities(
        entity_name, 
        is_async,
        where_clause, 
        params, 
        order_by, 
        limit, 
        offset, 
        True,  # Always deserialize
        include_deleted
    )
    
    # Export based on format
    if format.lower() == 'json':
        import json
        return json.dumps(entities, default=str, indent=2)
    
    elif format.lower() == 'csv':
        import csv
        import io
        
        if not entities:
            return ""
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=entities[0].keys())
        writer.writeheader()
        
        for entity in entities:
            # Convert values to strings for CSV compatibility
            row = {}
            for key, value in entity.items():
                if isinstance(value, (dict, list, set, tuple)):
                    row[key] = json.dumps(value)
                else:
                    row[key] = str(value) if value is not None else ""
            
            writer.writerow(row)
        
        return output.getvalue()
    
    elif format.lower() == 'yaml':
        try:
            import yaml
            return yaml.dump(entities, default_flow_style=False)
        except ImportError:
            raise ValueError("PyYAML library not installed. Install with 'pip install pyyaml'")
    
    else:
        raise ValueError(f"Unsupported export format: {format}")

def export_entities_sync(self, entity_name: str, where_clause: Optional[str] = None,
                      params: Optional[tuple] = None, order_by: Optional[str] = None,
                      limit: Optional[int] = None, offset: Optional[int] = None,
                      include_deleted: bool = False, format: str = 'json') -> Union[str, bytes]:
    """
    Export entities to various formats (synchronous version).
    
    Args:
        entity_name: Name of the entity
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        include_deleted: Whether to include soft-deleted entities
        format: Export format ('json', 'csv', 'yaml')
        
    Returns:
        Exported data as string or bytes
    """
    return self._utils._create_sync_method(
        self._impl_export_entities,
        entity_name,
        where_clause=where_clause,
        params=params,
        order_by=order_by,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
        format=format
    )()

async def export_entities_async(self, entity_name: str, where_clause: Optional[str] = None,
                            params: Optional[tuple] = None, order_by: Optional[str] = None,
                            limit: Optional[int] = None, offset: Optional[int] = None,
                            include_deleted: bool = False, format: str = 'json') -> Union[str, bytes]:
    """
    Export entities to various formats (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        where_clause: Optional WHERE clause (without the 'WHERE' keyword)
        params: Optional parameters for the WHERE clause
        order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
        limit: Optional LIMIT value
        offset: Optional OFFSET value
        include_deleted: Whether to include soft-deleted entities
        format: Export format ('json', 'csv', 'yaml')
        
    Returns:
        Exported data as string or bytes
    """
    return await self._utils._create_async_method(
        self._impl_export_entities,
        entity_name,
        where_clause=where_clause,
        params=params,
        order_by=order_by,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
        format=format
    )()

async def _impl_import_entities(self, entity_name: str, data: Union[str, bytes], is_async: bool,
                             format: str = 'json', user_id: Optional[str] = None,
                             comment: Optional[str] = None) -> List[str]:
    """
    Internal implementation for importing entities from various formats.
    
    Args:
        entity_name: Name of the entity
        data: Data to import
        is_async: Whether to use async or sync operations
        format: Import format ('json', 'csv', 'yaml')
        user_id: Optional ID of the user making the change
        comment: Optional comment about the import
        
    Returns:
        List of imported entity IDs
    """
    # Parse data based on format
    if format.lower() == 'json':
        import json
        entities = json.loads(data)
        if not isinstance(entities, list):
            entities = [entities]
    
    elif format.lower() == 'csv':
        import csv
        import io
        
        # Parse CSV
        csv_data = io.StringIO(data if isinstance(data, str) else data.decode('utf-8'))
        reader = csv.DictReader(csv_data)
        
        # Get entity schema for type conversion
        schema = await self._impl_get_entity_schema(entity_name, is_async)
        
        entities = []
        for row in reader:
            entity = {}
            for key, value in row.items():
                if not value:  # Skip empty values
                    continue
                
                # Convert based on schema type
                field_type = schema.get(key, 'str')
                if field_type == 'int':
                    entity[key] = int(value)
                elif field_type == 'float':
                    entity[key] = float(value)
                elif field_type == 'bool':
                    entity[key] = value.lower() in ('true', 'yes', '1', 't', 'y')
                elif field_type == 'dict' or field_type == 'list':
                    import json
                    try:
                        entity[key] = json.loads(value)
                    except json.JSONDecodeError:
                        # If not valid JSON, store as string
                        entity[key] = value
                else:
                    entity[key] = value
            
            if entity:  # Only add non-empty entities
                entities.append(entity)
    
    elif format.lower() == 'yaml':
        try:
            import yaml
            entities = yaml.safe_load(data)
            if not isinstance(entities, list):
                entities = [entities]
        except ImportError:
            raise ValueError("PyYAML library not installed. Install with 'pip install pyyaml'")
    
    else:
        raise ValueError(f"Unsupported import format: {format}")
    
    # Save entities in bulk
    return await self._impl_save_entities_bulk(entity_name, entities, is_async, user_id, comment)

def import_entities_sync(self, entity_name: str, data: Union[str, bytes], 
                      format: str = 'json', user_id: Optional[str] = None,
                      comment: Optional[str] = None) -> List[str]:
    """
    Import entities from various formats (synchronous version).
    
    Args:
        entity_name: Name of the entity
        data: Data to import
        format: Import format ('json', 'csv', 'yaml')
        user_id: Optional ID of the user making the change
        comment: Optional comment about the import
        
    Returns:
        List of imported entity IDs
    """
    return self._utils._create_sync_method(
        self._impl_import_entities,
        entity_name,
        data,
        format=format,
        user_id=user_id,
        comment=comment
    )()

async def import_entities_async(self, entity_name: str, data: Union[str, bytes],
                            format: str = 'json', user_id: Optional[str] = None,
                            comment: Optional[str] = None) -> List[str]:
    """
    Import entities from various formats (asynchronous version).
    
    Args:
        entity_name: Name of the entity
        data: Data to import
        format: Import format ('json', 'csv', 'yaml')
        user_id: Optional ID of the user making the change
        comment: Optional comment about the import
        
    Returns:
        List of imported entity IDs
    """
    return await self._utils._create_async_method(
        self._impl_import_entities,
        entity_name,
        data,
        format=format,
        user_id=user_id,
        comment=comment
    )()

# -------------------- TRANSACTION OPERATIONS --------------------

def transaction_sync(self) -> 'EntityTransaction':
    """
    Create a synchronous transaction context manager.
    
    This method returns a context manager that can be used to group
    multiple entity operations into a single transaction.
    
    Returns:
        EntityTransaction instance for synchronous operations
    """
    from .transaction import EntityTransaction
    return EntityTransaction(self, is_async=False)

def transaction_async(self) -> 'AsyncEntityTransaction':
    """
    Create an asynchronous transaction context manager.
    
    This method returns a context manager that can be used to group
    multiple entity operations into a single transaction.
    
    Returns:
        AsyncEntityTransaction instance for asynchronous operations
    """
    from .transaction import AsyncEntityTransaction
    return AsyncEntityTransaction(self, is_async=True)

# -------------------- MIGRATION OPERATIONS --------------------

async def _impl_run_migrations(self, migrations_path: str, is_async: bool) -> None:
    """
    Internal implementation for running migrations.
    
    Args:
        migrations_path: Path to migration files
        is_async: Whether to use async or sync operations
    """
    import os
    import re
    
    try:
        # Get the connection with transaction
        if is_async:
            conn_ctx = self._db.async_transaction()
        else:
            conn_ctx = self._db.sync_transaction()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Create migrations table if it doesn't exist
            create_sql = """
                CREATE TABLE IF NOT EXISTS _migrations (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    applied_at TEXT
                )
            """
            
            if is_async:
                await conn.execute_async(create_sql)
            else:
                conn.execute_sync(create_sql)
                
            # Get list of applied migrations
            query = "SELECT id FROM _migrations"
            
            if is_async:
                result = await conn.execute_async(query)
            else:
                result = conn.execute_sync(query)
                
            applied_migrations = set(row[0] for row in result) if result else set()
            
            # Get list of migration files
            migration_files = []
            migration_re = re.compile(r"^(\d+)_(.+)\.sql$")
            
            for file_name in os.listdir(migrations_path):
                match = migration_re.match(file_name)
                if match:
                    migration_id = match.group(1)
                    migration_name = match.group(2)
                    
                    if migration_id not in applied_migrations:
                        migration_files.append((migration_id, migration_name, file_name))
            
            # Sort migrations by ID
            migration_files.sort(key=lambda x: x[0])
            
            # Apply pending migrations
            for migration_id, migration_name, file_name in migration_files:
                # Read migration file
                file_path = os.path.join(migrations_path, file_name)
                with open(file_path, 'r') as f:
                    migration_sql = f.read()
                
                # Split into individual statements (naive approach)
                statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]
                
                # Execute statements
                for stmt in statements:
                    if is_async:
                        await conn.execute_async(stmt)
                    else:
                        conn.execute_sync(stmt)
                
                # Record migration as applied
                now = datetime.datetime.utcnow().isoformat()
                insert_sql = "INSERT INTO _migrations VALUES (?, ?, ?)"
                
                if is_async:
                    await conn.execute_async(insert_sql, (migration_id, migration_name, now))
                else:
                    conn.execute_sync(insert_sql, (migration_id, migration_name, now))
                    
                logger.info(f"Applied migration {migration_id}: {migration_name}")
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        raise

def run_migrations_sync(self, migrations_path: str) -> None:
    """
    Run database migrations (synchronous version).
    
    This method applies any pending SQL migration files from the specified directory.
    Migration files should be named in the format: "001_migration_name.sql".
    
    Args:
        migrations_path: Path to migration files
    """
    return self._utils._create_sync_method(
        self._impl_run_migrations,
        migrations_path
    )()

async def run_migrations_async(self, migrations_path: str) -> None:
    """
    Run database migrations (asynchronous version).
    
    This method applies any pending SQL migration files from the specified directory.
    Migration files should be named in the format: "001_migration_name.sql".
    
    Args:
        migrations_path: Path to migration files
    """
    return await self._utils._create_async_method(
        self._impl_run_migrations,
        migrations_path
    )()

# -------------------- SEQUENCE OPERATIONS --------------------

async def _impl_get_next_sequence_value(self, sequence_name: str, is_async: bool) -> Optional[int]:
    """
    Internal implementation for getting the next value from a sequence.
    
    Args:
        sequence_name: Name of the sequence
        is_async: Whether to use async or sync operations
        
    Returns:
        Next sequence value or None if sequences are not supported
    """
    # Get SQL for next sequence value
    sql = self._sql_generator.get_next_sequence_value_sql(sequence_name)
    
    # If sequences are not supported, use our own implementation
    if sql is None:
        return await self._impl_get_next_sequence_value_custom(sequence_name, is_async)
    
    try:
        # Get the connection
        if is_async:
            conn_ctx = self._db.async_connection()
        else:
            conn_ctx = self._db.sync_connection()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Execute query
            if is_async:
                result = await conn.execute_async(sql)
            else:
                result = conn.execute_sync(sql)
            
            # Extract value
            if result and result[0] and result[0][0]:
                return int(result[0][0])
            
            return None
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error getting next sequence value for {sequence_name}: {e}")
        raise

async def _impl_get_next_sequence_value_custom(self, sequence_name: str, is_async: bool) -> int:
    """
    Custom implementation for sequences using a table.
    
    This is used for databases that don't support native sequences.
    
    Args:
        sequence_name: Name of the sequence
        is_async: Whether to use async or sync operations
        
    Returns:
        Next sequence value
    """
    try:
        # Get the connection with transaction
        if is_async:
            conn_ctx = self._db.async_transaction()
        else:
            conn_ctx = self._db.sync_transaction()
        
        async with conn_ctx if is_async else contextlib.nullcontext(conn_ctx.__enter__()) as conn:
            # Create sequences table if it doesn't exist
            create_sql = """
                CREATE TABLE IF NOT EXISTS _sequences (
                    name TEXT PRIMARY KEY,
                    value INTEGER
                )
            """
            
            if is_async:
                await conn.execute_async(create_sql)
            else:
                conn.execute_sync(create_sql)
            
            # Get current value
            query = "SELECT value FROM _sequences WHERE name = ?"
            
            if is_async:
                result = await conn.execute_async(query, (sequence_name,))
            else:
                result = conn.execute_sync(query, (sequence_name,))
            
            # Initialize if not exists
            if not result or not result[0]:
                # Insert initial value
                insert_sql = "INSERT INTO _sequences VALUES (?, 1)"
                
                if is_async:
                    await conn.execute_async(insert_sql, (sequence_name,))
                else:
                    conn.execute_sync(insert_sql, (sequence_name,))
                
                return 1
            
            # Increment value
            current_value = int(result[0][0])
            next_value = current_value + 1
            
            update_sql = "UPDATE _sequences SET value = ? WHERE name = ?"
            
            if is_async:
                await conn.execute_async(update_sql, (next_value, sequence_name))
            else:
                conn.execute_sync(update_sql, (next_value, sequence_name))
            
            return next_value
            
        # Close connection if using sync mode (async context manager handles it automatically)
        if not is_async:
            conn_ctx.__exit__(None, None, None)
            
    except Exception as e:
        logger.error(f"Error getting next custom sequence value for {sequence_name}: {e}")
        raise

def get_next_sequence_value_sync(self, sequence_name: str) -> Optional[int]:
    """
    Get the next value from a sequence (synchronous version).
    
    If the database doesn't support native sequences, this will use
    a custom implementation with a table.
    
    Args:
        sequence_name: Name of the sequence
        
    Returns:
        Next sequence value or None if sequences are not supported
    """
    return self._utils._create_sync_method(
        self._impl_get_next_sequence_value,
        sequence_name
    )()

async def get_next_sequence_value_async(self, sequence_name: str) -> Optional[int]:
    """
    Get the next value from a sequence (asynchronous version).
    
    If the database doesn't support native sequences, this will use
    a custom implementation with a table.
    
    Args:
        sequence_name: Name of the sequence
        
    Returns:
        Next sequence value or None if sequences are not supported
    """
    return await self._utils._create_async_method(
        self._impl_get_next_sequence_value,
        sequence_name
    )()

# -------------------- CONNECTION POOL OPERATIONS --------------------

def get_connection_pool_stats(self) -> Dict[str, Any]:
    """
    Get statistics about the database connection pool.
    
    Returns:
        Dictionary with pool statistics
    """
    if hasattr(self._db, 'get_pool_stats'):
        return self._db.get_pool_stats()
    else:
        return {
            'connections': 'unknown',
            'idle': 'unknown',
            'busy': 'unknown',
            'max': 'unknown'
        }

# -------------------- REFLECTION OPERATIONS --------------------

def get_supported_features(self) -> Dict[str, bool]:
    """
    Get a dictionary of supported features for the current database.
    
    Returns:
        Dictionary mapping feature names to boolean support indicators
    """
    features = {
        'sequences': self._sql_generator.get_next_sequence_value_sql('test') is not None,
        'transactions': hasattr(self._db, 'async_transaction') or hasattr(self._db, 'sync_transaction'),
        'history': True,
        'soft_delete': True,
        'schema_validation': True,
        'bulk_operations': True,
        'async': hasattr(self._db, 'async_connection'),
        'sync': hasattr(self._db, 'sync_connection'),
    }
    
    return features

async def get_database_info(self) -> Dict[str, Any]:
    """
    Get information about the database.
    
    Returns:
        Dictionary with database information
    """
    try:
        if self.is_environment_async():
            conn_ctx = self._db.async_connection()
            async with conn_ctx as conn:
                if self._db_type == 'postgres':
                    result = await conn.execute_async("SELECT version()")
                elif self._db_type == 'mysql':
                    result = await conn.execute_async("SELECT version()")
                elif self._db_type == 'sqlite':
                    result = await conn.execute_async("SELECT sqlite_version()")
                else:
                    result = [('unknown',)]
        else:
            conn_ctx = self._db.sync_connection()
            with conn_ctx as conn:
                if self._db_type == 'postgres':
                    result = conn.execute_sync("SELECT version()")
                elif self._db_type == 'mysql':
                    result = conn.execute_sync("SELECT version()")
                elif self._db_type == 'sqlite':
                    result = conn.execute_sync("SELECT sqlite_version()")
                else:
                    result = [('unknown',)]
        
        version = result[0][0] if result and result[0] else 'unknown'
        
        return {
            'type': self._db_type,
            'version': version,
            'features': self.get_supported_features(),
            'connection_pool': self.get_connection_pool_stats()
        }
    except Exception as e:
        logger.error(f"Error getting database info: {e}")
        return {
            'type': self._db_type,
            'version': 'unknown',
            'features': self.get_supported_features(),
            'error': str(e)
        }