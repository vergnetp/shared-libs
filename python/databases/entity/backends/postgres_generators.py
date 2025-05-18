import re
from typing import Dict, Tuple, List, Any, Optional
from ...sql import SqlGenerator
from ..sql import SqlEntityGenerator

class PostgresSqlGenerator(SqlGenerator, SqlEntityGenerator):
    """
    PostgreSQL-specific SQL generator implementation.
    
    This class provides SQL generation tailored to PostgreSQL's dialect and features.
    """
    def __init__(self, is_async):
        self._is_async = is_async
    
    def escape_identifier(self, identifier: str) -> str:
        """Escape a column or table name for PostgreSQL."""
        return f"\"{identifier}\""
    
    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """Convert standard ? placeholders to PostgreSQL $1, $2, etc. format"""        
            
        if self._is_async:           
            # Use regex to safely replace placeholders with indexed parameters
            placeholder_pattern = r'(?<!\?)\?(?!\?)'  # Match ? but not ?? (escaped ?)
            param_index = 0
            
            def replace_placeholder(match):
                nonlocal param_index
                param_index += 1
                return f"${param_index}"
                
            new_sql = re.sub(placeholder_pattern, replace_placeholder, sql)
            
            # Handle escaped ?? placeholders (convert back to single ?)
            new_sql = new_sql.replace('??', '?')            
        else:            
            # For sync connections, replace ? with ? but handle escaped ?? properly
            new_sql = ''
            i = 0
            while i < len(sql):
                if i+1 < len(sql) and sql[i:i+2] == '??':
                    new_sql += '?'  # Replace ?? with single ?
                    i += 2
                elif sql[i] == '?':
                    new_sql += '?'  # Replace ? with ?
                    i += 1
                else:
                    new_sql += sql[i]
                    i += 1                  
        return new_sql, params or []    
    
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate PostgreSQL-specific upsert SQL for an entity.""" 
        fields_str = ', '.join([f"[{field}]" for field in fields])
        placeholders = ', '.join(['?'] * len(fields))
        update_clause = ', '.join([f"[{field}]=EXCLUDED.[{field}]" for field in fields if field != 'id'])
        
        return f"INSERT INTO [{entity_name}] ({fields_str}) VALUES ({placeholders}) ON CONFLICT([id]) DO UPDATE SET {update_clause}"
    
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate PostgreSQL-specific CREATE TABLE SQL."""
        column_defs = []
        for name, type_name in columns:
            if name == 'id':
                column_defs.append(f"[id] TEXT PRIMARY KEY")
            else:
                column_defs.append(f"[{name}] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}] (
                {', '.join(column_defs)}
            )
        """
    
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """Generate PostgreSQL-specific SQL for creating a metadata table."""
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_meta] (
                [name] TEXT PRIMARY KEY,
                [type] TEXT
            )
        """
    
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate PostgreSQL-specific history table SQL."""
        column_defs = [f"[{name}] TEXT" for name, _ in columns]
        column_defs.append("[version] INTEGER")
        column_defs.append("[history_timestamp] TEXT")
        column_defs.append("[history_user_id] TEXT")
        column_defs.append("[history_comment] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_history] (
                {', '.join(column_defs)},
                PRIMARY KEY ([id], [version])
            )
        """
    
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """Get SQL to list all tables in PostgreSQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name LIKE ?",
            ('%_meta',)
        )
    
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a PostgreSQL table."""
        return (
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? "
            "ORDER BY ordinal_position",  # Order by the column's position
            (table_name,)
        )
    
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """Generate PostgreSQL-specific upsert SQL for a metadata table."""
        return f"INSERT INTO [{entity_name}_meta] VALUES (?, ?) ON CONFLICT([name]) DO UPDATE SET [type]=EXCLUDED.[type]"
    
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """Generate SQL to add a column to an existing PostgreSQL table."""
        return f"ALTER TABLE [{table_name}] ADD COLUMN IF NOT EXISTS [{column_name}] TEXT"
    
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a table exists in PostgreSQL."""
        return (
            "SELECT table_name FROM information_schema.tables WHERE table_name = ?",
            (table_name,)
        )
    
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a column exists in a PostgreSQL table."""
        return (
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
            (table_name, column_name)
        )
    
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """Generate SQL to retrieve an entity by ID in PostgreSQL."""
        query = f"SELECT * FROM [{entity_name}] WHERE [id] = ?"
        
        if not include_deleted:
            query += " AND [deleted_at] IS NULL"
            
        return query
    
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """Generate SQL to retrieve the history of an entity in PostgreSQL."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? ORDER BY [version] DESC",
            (id,)
        )
    
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """Generate SQL to retrieve a specific version of an entity in PostgreSQL."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? AND [version] = ?",
            (id, version)
        )
    
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """Generate SQL for soft-deleting an entity in PostgreSQL."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = ?, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """Generate SQL for restoring a soft-deleted entity in PostgreSQL."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = NULL, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """Generate SQL for counting entities in PostgreSQL."""
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
        """Generate SQL for a flexible query in PostgreSQL."""
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
            query += f" OFFSET {offset}"
            
        return query
    
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQL for updating specific fields of an entity in PostgreSQL."""
        set_clause = ", ".join([f"[{field}] = ?" for field in fields])
        return f"UPDATE [{entity_name}] SET {set_clause}, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_pragma_or_settings_sql(self) -> List[str]:
        """Get optimal PostgreSQL settings."""
        return [
            "SET TIME ZONE 'UTC'",
            "SET application_name = 'EntityManager'"
        ]
    
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """Generate SQL to get the next value from a PostgreSQL sequence."""
        return f"SELECT nextval('{sequence_name}')"
