
from typing import Tuple, List, Any, Optional
from ...generators import SqlGenerator
from ...entity.generators import SqlEntityGenerator

class MySqlSqlGenerator(SqlGenerator, SqlEntityGenerator):
    """
    MySQL-specific SQL generator implementation.
    
    This class provides SQL generation tailored to MySQL's dialect and features.
    """
    
    def escape_identifier(self, identifier: str) -> str:
        """Escape a column or table name for MySQL."""
        return f"`{identifier}`"
    
    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """Convert standard ? placeholders to MySQL %s placeholders."""
        # For MySQL, replace ? with %s but handle escaped ?? properly
        new_sql = ''
        i = 0
        while i < len(sql):
            if i+1 < len(sql) and sql[i:i+2] == '??':
                new_sql += '?'  # Replace ?? with single ? (literal question mark, not a parameter)
                i += 2
            elif sql[i] == '?':
                new_sql += '%s'  # Replace ? with %s for MySQL parameters
                i += 1
            else:
                new_sql += sql[i]
                i += 1
        
        if not params:
            return new_sql, []
        
        return new_sql, params or []
    
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate MySQL-specific upsert SQL for an entity."""
        fields_str = ', '.join([f"[{field}]" for field in fields])
        placeholders = ', '.join(['?'] * len(fields))
        
        # Fix: Use the alias syntax instead of VALUES()
        update_clause = ', '.join([f"[{field}]=new_data.[{field}]" for field in fields if field != 'id'])
        
        return f"INSERT INTO [{entity_name}] ({fields_str}) VALUES ({placeholders}) AS new_data ON DUPLICATE KEY UPDATE {update_clause}"
    
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate MySQL-specific CREATE TABLE SQL."""
        column_defs = []
        for name, type_name in columns:
            if name == 'id':
                column_defs.append(f"[id] VARCHAR(36) PRIMARY KEY")
            else:
                column_defs.append(f"[{name}] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}] (
                {', '.join(column_defs)}
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """Generate MySQL-specific SQL for creating a metadata table."""
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_meta] (
                [name] VARCHAR(255) PRIMARY KEY,
                [type] VARCHAR(50)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate MySQL-specific history table SQL."""
        column_defs = []
        for name, _ in columns:
            if name == 'id':
                column_defs.append(f"[id] VARCHAR(36)")
            else:
                column_defs.append(f"[{name}] TEXT")
                
        column_defs.append("[version] INT")
        column_defs.append("[history_timestamp] TEXT")
        column_defs.append("[history_user_id] TEXT")
        column_defs.append("[history_comment] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_history] (
                {', '.join(column_defs)},
                PRIMARY KEY ([id], [version])
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """Get SQL to list all tables in MySQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=DATABASE() AND table_name LIKE ?",
            ('%_meta',)
        )
    
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a MySQL table."""
        return (
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? AND table_schema = DATABASE() "
            "ORDER BY ordinal_position",  # Order by the column's position
            (table_name,)
        )
    
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """Generate MySQL-specific upsert SQL for a metadata table."""
        return f"INSERT INTO [{entity_name}_meta] VALUES (?, ?) AS new ON DUPLICATE KEY UPDATE [type]=new.[type]"
    
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """Generate SQL to add a column to an existing MySQL table."""
        # MySQL doesn't support IF NOT EXISTS for columns, so the caller must check first
        return f"ALTER TABLE [{table_name}] ADD COLUMN [{column_name}] TEXT"
    
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a table exists in MySQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = ?",
            (table_name,)
        )
    
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a column exists in a MySQL table."""
        return (
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ? AND table_schema = DATABASE()",
            (table_name, column_name)
        )
    
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """Generate SQL to retrieve an entity by ID in MySQL."""
        query = f"SELECT * FROM [{entity_name}] WHERE [id] = ?"
        
        if not include_deleted:
            query += " AND [deleted_at] IS NULL"
            
        return query
    
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """Generate SQL to retrieve the history of an entity in MySQL."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? ORDER BY [version] DESC",
            (id,)
        )
    
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """Generate SQL to retrieve a specific version of an entity in MySQL."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? AND [version] = ?",
            (id, version)
        )
    
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """Generate SQL for soft-deleting an entity in MySQL."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = ?, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """Generate SQL for restoring a soft-deleted entity in MySQL."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = NULL, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """Generate SQL for counting entities in MySQL."""
        query = f"SELECT COUNT(*) FROM [{entity_name}]"
        conditions = []
        
        if not include_deleted:
            conditions.append("[deleted_at] IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        return query
    
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """Generate SQL for a flexible query in MySQL."""
        query = f"SELECT * FROM [{entity_name}]"
        conditions = []
        
        if not include_deleted:
            conditions.append("[deleted_at] IS NULL")
            
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
        set_clause = ", ".join([f"[{field}] = ?" for field in fields])
        return f"UPDATE [{entity_name}] SET {set_clause}, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
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
