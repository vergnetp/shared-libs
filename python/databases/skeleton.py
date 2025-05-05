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
    
    def register_serializer(self, type_name: str, serializer_func, deserializer_func):
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
    
    def _to_json(self, entity: Dict[str, Any]) -> str:
        """
        Convert an entity to a JSON string.
        
        Args:
            entity: Entity dictionary
            
        Returns:
            JSON string representation
        """
        return json.dumps(entity, default=str)
    
    def _from_json(self, json_str: str) -> Dict[str, Any]:
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
    

class EntityAsyncMixin(EntityUtils):
    """
    Mixin that adds entity operations to async connections.
    
    This mixin provides async methods for entity CRUD operations,
    leveraging the EntityUtils serialization/deserialization
    and the AsyncConnection database operations.
    """
    
    # Meta cache to optimize metadata lookups
    _meta_cache = {}
    
    # Core CRUD operations
    
    @async_method
    @with_timeout
    @auto_transaction
    async def get_entity(self, entity_name: str, entity_id: str, 
                         include_deleted: bool = False, 
                         deserialize: bool = False) -> Optional[Dict[str, Any]]:
        """
        Fetch an entity by ID.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to fetch
            include_deleted: Whether to include soft-deleted entities
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            Entity dictionary or None if not found
        """
        # Generate the SQL
        sql = self.parameter_converter.get_entity_by_id_sql(entity_name, include_deleted)
        
        # Execute the query
        result = await self.execute(sql, (entity_id,))
        
        # Return None if no entity found
        if not result or len(result) == 0:
            return None
            
        # Convert the first row to a dictionary
        entity_dict = dict(zip([col[0] for col in result.description], result[0]))
        
        # Deserialize if requested
        if deserialize:
            return await self._deserialize_entity(entity_name, entity_dict)
        
        return entity_dict
    
    @async_method
    @with_timeout
    @auto_transaction
    async def save_entity(self, entity_name: str, entity: Dict[str, Any], 
                        user_id: Optional[str] = None, 
                        comment: Optional[str] = None,
                        timeout: Optional[float] = 60) -> Dict[str, Any]:
        """
        Save an entity (create or update).
        
        Args:
            entity_name: Name of the entity type
            entity: Entity data dictionary
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            timeout: Optional timeout in seconds for the operation (defaults to 60)
            
        Returns:
            The saved entity with updated fields
        """
        async def perform_save():
            # Prepare entity with timestamps, IDs, etc.
            prepared_entity = self._prepare_entity(entity_name, entity, user_id, comment)
            
            # Ensure schema exists (will be a no-op if already exists)
            await self._ensure_entity_schema(entity_name, prepared_entity)
            
            # Update metadata based on entity fields
            await self._update_entity_metadata(entity_name, prepared_entity)
            
            # Serialize the entity to string values
            meta = await self._get_entity_metadata(entity_name)
            serialized = self._serialize_entity(prepared_entity, meta)
            
            # Always use targeted upsert with exactly the fields provided
            # (plus system fields added by _prepare_entity)
            fields = list(serialized.keys())
            sql = self.parameter_converter.get_upsert_sql(entity_name, fields)
            
            # Execute the upsert
            params = tuple(serialized[field] for field in fields)
            await self.execute(sql, params)
            
            # Add to history
            await self._add_to_history(entity_name, serialized, user_id, comment)
            
            # Return the prepared entity
            return prepared_entity        

        try:
            return await asyncio.wait_for(perform_save(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"save_entity operation for {entity_name} timed out after {timeout:.1f}s")
        
    
    @async_method
    @with_timeout
    @auto_transaction
    async def save_entities(self, entity_name: str, entities: List[Dict[str, Any]],
                        user_id: Optional[str] = None,
                        comment: Optional[str] = None,
                        timeout: Optional[float] = 60) -> List[Dict[str, Any]]:
        """
        Save multiple entities in a single transaction with batch operations.
        
        Args:
            entity_name: Name of the entity type
            entities: List of entity data dictionaries
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            timeout: Optional timeout in seconds for the entire operation (defaults to 60)
            
        Returns:
            List of saved entities with their IDs
        """
        if not entities:
            return []
        
        async def perform_batch_save():
            # Prepare all entities and collect fields
            prepared_entities = []
            all_fields = set()
            
            for entity in entities:
                prepared = self._prepare_entity(entity_name, entity, user_id, comment)
                prepared_entities.append(prepared)
                all_fields.update(prepared.keys())
            
            # Ensure schema exists and can accommodate all fields
            await self._ensure_entity_schema(entity_name, {field: None for field in all_fields})
            
            # Update metadata for all fields at once
            meta = {}
            for entity in prepared_entities:
                for field_name, value in entity.items():
                    if field_name not in meta:
                        meta[field_name] = self._infer_type(value)
            
            # Batch update the metadata
            meta_params = [(field_name, field_type) for field_name, field_type in meta.items()]
            if meta_params:
                sql = self.parameter_converter.get_meta_upsert_sql(entity_name)
                await self.executemany(sql, meta_params)
            
            # Add all entities to the database with batch upsert
            fields = list(all_fields)
            sql = self.parameter_converter.get_upsert_sql(entity_name, fields)
            
            # Prepare parameters for batch upsert
            batch_params = []
            for entity in prepared_entities:
                params = tuple(entity.get(field, None) for field in fields)
                batch_params.append(params)
            
            # Execute batch upsert
            await self.executemany(sql, batch_params)
            
            # Get all entity IDs for history lookup
            entity_ids = [entity['id'] for entity in prepared_entities]
            
            # Single query to get all existing versions
            versions = {}
            if entity_ids:
                placeholders = ','.join(['?'] * len(entity_ids))
                version_sql = f"SELECT id, MAX(version) as max_version FROM {entity_name}_history WHERE id IN ({placeholders}) GROUP BY id"
                version_results = await self.execute(version_sql, tuple(entity_ids))
                
                # Create a dictionary of id -> current max version
                versions = {row[0]: row[1] for row in version_results if row[1] is not None}
            
            # Prepare history entries
            now = datetime.datetime.utcnow().isoformat()
            history_fields = list(all_fields) + ['version', 'history_timestamp', 'history_user_id', 'history_comment']
            history_sql = f"INSERT INTO {entity_name}_history ({', '.join(history_fields)}) VALUES ({', '.join(['?'] * len(history_fields))})"
            
            history_params = []
            for entity in prepared_entities:
                history_entry = entity.copy()
                entity_id = entity['id']
                
                # Get next version (default to 1 if no previous versions exist)
                next_version = (versions.get(entity_id, 0) or 0) + 1
                
                history_entry['version'] = next_version
                history_entry['history_timestamp'] = now
                history_entry['history_user_id'] = user_id
                history_entry['history_comment'] = comment
                
                # Create params tuple with all fields in the correct order
                params = tuple(history_entry.get(field, None) for field in history_fields)
                history_params.append(params)
            
            # Execute batch history insert
            await self.executemany(history_sql, history_params)
            
            return prepared_entities
        
        try:
            return await asyncio.wait_for(perform_batch_save(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"save_entities operation timed out after {timeout:.1f}s")

    
    @async_method
    @with_timeout
    @auto_transaction
    async def delete_entity(self, entity_name: str, entity_id: str, 
                           user_id: Optional[str] = None, 
                           permanent: bool = False) -> bool:
        """
        Delete an entity by ID.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to delete
            user_id: Optional ID of the user making the change
            permanent: Whether to permanently delete (true) or soft delete (false)
            
        Returns:
            True if deletion was successful
        """
        # Get current entity state for history
        current_entity = None
        if not permanent:
            current_entity = await self.get_entity(entity_name, entity_id, include_deleted=True)
            if not current_entity:
                return False
        
        # For permanent deletion, use a direct DELETE
        if permanent:
            sql = f"DELETE FROM {entity_name} WHERE id = ?"
            result = await self.execute(sql, (entity_id,))
            return result.rowcount > 0
        
        # For soft deletion, use an UPDATE
        now = datetime.datetime.utcnow().isoformat()
        sql = self.parameter_converter.get_soft_delete_sql(entity_name)
        result = await self.execute(sql, (now, now, user_id, entity_id))
        
        # Add to history if soft-deleted
        if result.rowcount > 0 and current_entity:
            # Update the entity with deletion info
            current_entity['deleted_at'] = now
            current_entity['updated_at'] = now
            if user_id:
                current_entity['updated_by'] = user_id
                
            # Serialize and add to history
            meta = await self._get_entity_metadata(entity_name)
            serialized = self._serialize_entity(current_entity, meta)
            await self._add_to_history(entity_name, serialized, user_id, "Soft deleted")
                
        return result.rowcount > 0
    
    @async_method
    @with_timeout
    @auto_transaction
    async def restore_entity(self, entity_name: str, entity_id: str, 
                            user_id: Optional[str] = None) -> bool:
        """
        Restore a soft-deleted entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to restore
            user_id: Optional ID of the user making the change
            
        Returns:
            True if restoration was successful
        """
        # Check if entity exists and is deleted
        current_entity = await self.get_entity(entity_name, entity_id, include_deleted=True)
        if not current_entity or current_entity.get('deleted_at') is None:
            return False
            
        # Update timestamps
        now = datetime.datetime.utcnow().isoformat()
        
        # Generate restore SQL
        sql = self.parameter_converter.get_restore_entity_sql(entity_name)
        result = await self.execute(sql, (now, user_id, entity_id))
        
        # Add to history if restored
        if result.rowcount > 0:
            # Update the entity with restoration info
            current_entity['deleted_at'] = None
            current_entity['updated_at'] = now
            if user_id:
                current_entity['updated_by'] = user_id
                
            # Serialize and add to history
            meta = await self._get_entity_metadata(entity_name)
            serialized = self._serialize_entity(current_entity, meta)
            await self._add_to_history(entity_name, serialized, user_id, "Restored")
                
        return result.rowcount > 0
    
    # Query operations
    
    @async_method
    @with_timeout
    @auto_transaction
    async def find_entities(self, entity_name: str, where_clause: Optional[str] = None,
                          params: Optional[Tuple] = None, order_by: Optional[str] = None,
                          limit: Optional[int] = None, offset: Optional[int] = None,
                          include_deleted: bool = False, deserialize: bool = False) -> List[Dict[str, Any]]:
        """
        Query entities with flexible filtering.
        
        Args:
            entity_name: Name of the entity type
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            params: Parameters for the WHERE clause
            order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
            limit: Optional LIMIT value
            offset: Optional OFFSET value
            include_deleted: Whether to include soft-deleted entities
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            List of entity dictionaries
        """
        # Generate query SQL
        sql = self.parameter_converter.get_query_builder_sql(
            entity_name, where_clause, order_by, limit, offset, include_deleted
        )
        
        # Execute the query
        result = await self.execute(sql, params or ())
        
        # If no results, return empty list
        if not result:
            return []
            
        # Get field names from result description
        field_names = [col[0] for col in result.description]
        
        # Convert rows to dictionaries
        entities = []
        for row in result:
            entity_dict = dict(zip(field_names, row))
            
            # Deserialize if requested
            if deserialize:
                entity_dict = await self._deserialize_entity(entity_name, entity_dict)
                
            entities.append(entity_dict)
            
        return entities
    
    @async_method
    @with_timeout
    @auto_transaction
    async def count_entities(self, entity_name: str, where_clause: Optional[str] = None,
                           params: Optional[Tuple] = None, 
                           include_deleted: bool = False) -> int:
        """
        Count entities matching criteria.
        
        Args:
            entity_name: Name of the entity type
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            params: Parameters for the WHERE clause
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Count of matching entities
        """
        # Generate count SQL
        sql = self.parameter_converter.get_count_entities_sql(
            entity_name, where_clause, include_deleted
        )
        
        # Execute the query
        result = await self.execute(sql, params or ())
        
        # Return the count
        if result and len(result) > 0:
            return result[0][0]
        return 0
    
    # History operations
    
    @async_method
    @with_timeout
    @auto_transaction
    async def get_entity_history(self, entity_name: str, entity_id: str, 
                                deserialize: bool = False) -> List[Dict[str, Any]]:
        """
        Get the history of an entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            List of historical versions
        """
        # Generate SQL
        sql, params = self.parameter_converter.get_entity_history_sql(entity_name, entity_id)
        
        # Execute the query
        result = await self.execute(sql, params)
        
        # If no results, return empty list
        if not result:
            return []
            
        # Get field names from result description
        field_names = [col[0] for col in result.description]
        
        # Convert rows to dictionaries
        history_entries = []
        for row in result:
            entity_dict = dict(zip(field_names, row))
            
            # Deserialize if requested
            if deserialize:
                entity_dict = await self._deserialize_entity(entity_name, entity_dict)
                
            history_entries.append(entity_dict)
            
        return history_entries
    
    @async_method
    @with_timeout
    @auto_transaction
    async def get_entity_by_version(self, entity_name: str, entity_id: str, 
                               version: int, deserialize: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get a specific version of an entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity
            version: Version number to retrieve
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            Entity version or None if not found
        """
        # Generate SQL
        sql, params = self.parameter_converter.get_entity_version_sql(entity_name, entity_id, version)
        
        # Execute the query
        result = await self.execute(sql, params)
        
        # Return None if no entity found
        if not result or len(result) == 0:
            return None
            
        # Convert the first row to a dictionary
        field_names = [col[0] for col in result.description]
        entity_dict = dict(zip(field_names, result[0]))
        
        # Deserialize if requested
        if deserialize:
            return await self._deserialize_entity(entity_name, entity_dict)
            
        return entity_dict
    
    # Schema operations
    
    @async_method
    @auto_transaction
    async def _ensure_entity_schema(self, entity_name: str, sample_entity: Optional[Dict[str, Any]] = None) -> None:
        """
        Ensure entity tables and metadata exist.
        
        Args:
            entity_name: Name of the entity type
            sample_entity: Optional example entity to infer schema
        """
        # Check if the main table exists
        main_exists_sql, main_params = self.parameter_converter.get_check_table_exists_sql(entity_name)
        main_result = await self.execute(main_exists_sql, main_params)
        main_exists = main_result and len(main_result) > 0
        
        # Check if the meta table exists
        meta_exists_sql, meta_params = self.parameter_converter.get_check_table_exists_sql(f"{entity_name}_meta")
        meta_result = await self.execute(meta_exists_sql, meta_params)
        meta_exists = meta_result and len(meta_result) > 0
        
        # Check if the history table exists
        history_exists_sql, history_params = self.parameter_converter.get_check_table_exists_sql(f"{entity_name}_history")
        history_result = await self.execute(history_exists_sql, history_params)
        history_exists = history_result and len(history_result) > 0
        
        # Get columns if the main table exists
        columns = []
        if main_exists:
            columns_sql, columns_params = self.parameter_converter.get_list_columns_sql(entity_name)
            columns_result = await self.execute(columns_sql, columns_params)
            if columns_result:
                columns = [(row[0], row[1]) for row in columns_result]
        
        # Create main table if needed
        if not main_exists:
            # Default columns if no sample entity
            if not sample_entity:
                default_columns = [
                    ("id", "TEXT"),
                    ("created_at", "TEXT"),
                    ("created_by", "TEXT"),
                    ("updated_at", "TEXT"),
                    ("updated_by", "TEXT"),
                    ("deleted_at", "TEXT")
                ]
                main_sql = self.parameter_converter.get_create_table_sql(entity_name, default_columns)
            else:
                # Use sample entity to determine columns
                columns = [(field, "TEXT") for field in sample_entity.keys()]
                # Ensure required columns exist
                req_columns = ["id", "created_at", "created_by", "updated_at", "updated_by", "deleted_at"]
                for col in req_columns:
                    if col not in sample_entity:
                        columns.append((col, "TEXT"))
                main_sql = self.parameter_converter.get_create_table_sql(entity_name, columns)
                
            await self.execute(main_sql, ())
            
            # Update columns for history table creation
            if not columns:
                columns = [(col, "TEXT") for col in req_columns]
            
        # Create meta table if needed
        if not meta_exists:
            meta_sql = self.parameter_converter.get_create_meta_table_sql(entity_name)
            await self.execute(meta_sql, ())
            
        # Create history table if needed
        if not history_exists:
            # Get current columns if table exists and columns empty
            if not columns and main_exists:
                columns_sql, columns_params = self.parameter_converter.get_list_columns_sql(entity_name)
                columns_result = await self.execute(columns_sql, columns_params)
                if columns_result:
                    columns = [(row[0], row[1]) for row in columns_result]
                
            # Create history table with current columns plus history-specific ones
            history_sql = self.parameter_converter.get_create_history_table_sql(entity_name, columns)
            await self.execute(history_sql, ())
            
        # Update metadata if sample entity provided
        if sample_entity:
            await self._update_entity_metadata(entity_name, sample_entity)
    
    @async_method
    @auto_transaction
    async def _update_entity_metadata(self, entity_name: str, entity: Dict[str, Any]) -> None:
        """
        Update metadata table based on entity fields.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity dictionary with fields to register
        """
        # Ensure tables exist
        main_exists_sql, main_params = self.parameter_converter.get_check_table_exists_sql(f"{entity_name}_meta")
        meta_exists = bool(await self.execute(main_exists_sql, main_params))
        
        if not meta_exists:
            meta_sql = self.parameter_converter.get_create_meta_table_sql(entity_name)
            await self.execute(meta_sql, ())
        
        # Get existing metadata
        meta = await self._get_entity_metadata(entity_name, use_cache=False)
        
        # Check each field in the entity
        for field_name, value in entity.items():
            # Skip if already in metadata with same type
            if field_name in meta:
                continue
                
            # Determine the type
            value_type = self._infer_type(value)
            
            # Add to metadata
            sql = self.parameter_converter.get_meta_upsert_sql(entity_name)
            await self.execute(sql, (field_name, value_type))
            
            # Update cache
            meta[field_name] = value_type
            
        # Update cache
        self._meta_cache[entity_name] = meta
    
    # Utility methods
    
    @async_method
    async def _get_entity_metadata(self, entity_name: str, use_cache: bool = True) -> Dict[str, str]:
        """
        Get metadata for an entity type.
        
        Args:
            entity_name: Name of the entity type
            use_cache: Whether to use cached metadata
            
        Returns:
            Dictionary of field names to types
        """
        # Check cache first if enabled
        if use_cache and entity_name in self._meta_cache:
            return self._meta_cache[entity_name]
            
        # Check if meta table exists
        meta_exists_sql, meta_params = self.parameter_converter.get_check_table_exists_sql(f"{entity_name}_meta")
        meta_exists = bool(await self.execute(meta_exists_sql, meta_params))
        
        # Return empty dict if table doesn't exist
        if not meta_exists:
            self._meta_cache[entity_name] = {}
            return {}
            
        # Query metadata
        result = await self.execute(f"SELECT name, type FROM {entity_name}_meta", ())
        
        # Process results
        meta = {}
        for row in result:
            meta[row[0]] = row[1]
            
        # Cache results
        self._meta_cache[entity_name] = meta
        return meta
    
    @async_method
    @auto_transaction
    async def _add_to_history(self, entity_name: str, entity: Dict[str, Any], 
                             user_id: Optional[str] = None, 
                             comment: Optional[str] = None) -> None:
        """
        Add an entry to entity history.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity dictionary to record
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
        """
        # Ensure entity has required fields
        if 'id' not in entity:
            return
            
        # Get the current highest version
        history_sql = f"SELECT MAX(version) FROM {entity_name}_history WHERE id = ?"
        version_result = await self.execute(history_sql, (entity['id'],))
        
        # Calculate the next version number
        next_version = 1
        if version_result and version_result[0][0] is not None:
            next_version = version_result[0][0] + 1
            
        # Prepare history entry
        history_entry = entity.copy()
        now = datetime.datetime.utcnow().isoformat()
        
        # Add history-specific fields
        history_entry['version'] = next_version
        history_entry['history_timestamp'] = now
        history_entry['history_user_id'] = user_id
        history_entry['history_comment'] = comment
        
        # Generate insert SQL
        fields = list(history_entry.keys())
        placeholders = ', '.join(['?'] * len(fields))
        history_sql = f"INSERT INTO {entity_name}_history ({', '.join(fields)}) VALUES ({placeholders})"
        
        # Execute insert
        params = tuple(history_entry[field] for field in fields)
        await self.execute(history_sql, params)
    
    @async_method
    async def _deserialize_entity(self, entity_name: str, entity: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """
        Deserialize entity values based on metadata.
        
        Args:
            entity_name: Name of the entity for metadata lookup
            entity: Dictionary with string values
            
        Returns:
            Dictionary with values converted to appropriate Python types
        """
        # For history tables, use the base entity metadata
        meta_entity_name = entity_name
        if entity_name.endswith('_history'):
            meta_entity_name = entity_name[:-8]  # Remove _history suffix
            
        # Get type information for this entity
        meta = await self._get_entity_metadata(meta_entity_name)
        
        # Deserialize each field
        result = {}
        for key, value in entity.items():
            value_type = meta.get(key, 'str')
            
            try:
                result[key] = self._deserialize_value(value, value_type)
            except Exception as e:
                logger.error(f"Error deserializing field '{key}' as {value_type}: {e}")
                # Use the raw value as a fallback
                result[key] = value
        
        return result
    

class EntitySyncMixin(EntityUtils):
    """
    Mixin that adds entity operations to sync connections.
    
    This mixin provides sync methods for entity operations by wrapping
    the async versions from EntityAsyncMixin using the _create_sync_method utility.
    """
    
    # Meta cache to optimize metadata lookups (shared with async mixin)
    _meta_cache = {}
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_sync_methods()
    
    def _create_sync_methods(self):
        """
        Create sync versions of all entity operations by wrapping the async methods.
        """
        # Create sync versions of all entity methods from EntityAsyncMixin
        method_names = [
            # CRUD operations
            'get_entity',
            'save_entity',
            'save_entities',
            'delete_entity',
            'restore_entity',
            
            # Query operations
            'find_entities',
            'count_entities',
            
            # History operations
            'get_entity_history',
            'get_entity_by_version',
            
            # Schema operations
            '_ensure_entity_schema',
            '_update_entity_metadata',
            
            # Utility methods
            '_get_entity_metadata',
            '_add_to_history',
            '_deserialize_entity'
        ]
        
        # Get the async mixin methods from a temporary EntityAsyncMixin instance
        async_mixin = EntityAsyncMixin()
        
        # Create sync versions of all methods
        for method_name in method_names:
            if hasattr(async_mixin, method_name) and callable(getattr(async_mixin, method_name)):
                async_method = getattr(async_mixin, method_name)
                sync_method = self._create_sync_method(async_method)
                setattr(self, method_name, sync_method)