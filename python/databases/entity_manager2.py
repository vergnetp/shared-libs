"""
Refactored EntityManager implementation with functionality split between
database-level and connection-level operations.
"""
import json
import uuid
import datetime
import contextlib
from typing import Dict, List, Any, Optional, Tuple, Union, Set
from .. import log as logger

# -----------------------------------------------------------------
# Shared functionality - can be inherited by both connections and DB
# -----------------------------------------------------------------

class EntityUtils:
    """Shared utility methods for entity operations."""
    
    def _infer_type(self, value: Any) -> str:
        """Infer the type of a value as a string."""
        if value is None:
            return 'str'  # Default to string for None values
        
        python_type = type(value).__name__
        
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
        """Serialize a value based on its type."""
        if value is None:
            return None
        
        # Determine type if not provided
        if value_type is None:
            value_type = self._infer_type(value)
        
        # Use serializer if available, otherwise convert to string
        serializer = self._serializers.get(value_type)
        if serializer:
            return serializer(value)
        
        return str(value)
    
    def _deserialize_value(self, value: Optional[str], value_type: str) -> Any:
        """Deserialize a value based on its type."""
        if value is None:
            return None
        
        # Use deserializer if available, otherwise return as is
        deserializer = self._deserializers.get(value_type)
        if deserializer:
            return deserializer(value)
        
        return value
    
    def _serialize_entity(self, entity: Dict[str, Any], meta: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
        """Serialize all values in an entity to strings."""
        result = {}
        
        for key, value in entity.items():
            value_type = meta.get(key, None) if meta else None
            result[key] = self._serialize_value(value, value_type)
        
        return result
    
    def _deserialize_entity(self, entity_name: str, entity: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Deserialize entity values based on metadata."""
        result = {}
        
        # Get type information for this entity
        meta = self._meta_cache.get(entity_name, {})
        
        for key, value in entity.items():
            value_type = meta.get(key, 'str')
            result[key] = self._deserialize_value(value, value_type)
        
        return result
    
    def _prepare_entity(self, entity_name: str, entity: Dict[str, Any], 
                       user_id: Optional[str] = None, comment: Optional[str] = None) -> Dict[str, Any]:
        """Prepare an entity for storage by adding required fields."""
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
    
    def _get_sql_for_list_tables(self, is_async: bool = False) -> Tuple[str, tuple]:
        """Get SQL to list all tables based on database type."""
        if self._db_type == 'sqlite':
            return "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", ('%_meta',)
        elif self._db_type == 'postgres':
            return ("SELECT table_name FROM information_schema.tables "
                   "WHERE table_schema='public' AND table_name LIKE ?"), ('%_meta',)
        elif self._db_type == 'mysql':
            return ("SELECT table_name FROM information_schema.tables "
                   "WHERE table_schema=DATABASE() AND table_name LIKE ?"), ('%_meta',)
        else:
            # Default to SQLite syntax
            return "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", ('%_meta',)
    
    def _get_sql_for_list_columns(self, table_name: str, is_async: bool = False) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a table based on database type."""
        if self._db_type == 'sqlite':
            return f"PRAGMA table_info({table_name})", ()
        elif self._db_type == 'postgres':
            return ("SELECT column_name, data_type FROM information_schema.columns "
                   "WHERE table_name = ?"), (table_name,)
        elif self._db_type == 'mysql':
            return ("SELECT column_name, data_type FROM information_schema.columns "
                   "WHERE table_name = ? AND table_schema = DATABASE()"), (table_name,)
        else:
            # Default to SQLite syntax
            return f"PRAGMA table_info({table_name})", ()
    
    def _get_upsert_sql(self, entity_name: str, fields: List[str], is_async: bool = False) -> str:
        """Generate database-specific upsert SQL for an entity."""
        fields_str = ', '.join(fields)
        placeholders = ', '.join(['?'] * len(fields))
        
        if self._db_type == 'sqlite':
            return f"INSERT OR REPLACE INTO {entity_name} ({fields_str}) VALUES ({placeholders})"
        
        elif self._db_type == 'postgres':
            update_clause = ', '.join([f"{field}=EXCLUDED.{field}" for field in fields if field != 'id'])
            return f"INSERT INTO {entity_name} ({fields_str}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {update_clause}"
        
        else:  # MySQL and others
            update_clause = ', '.join([f"{field}=VALUES({field})" for field in fields if field != 'id'])
            return f"INSERT INTO {entity_name} ({fields_str}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    
    def _get_meta_upsert_sql(self, entity_name: str, is_async: bool = False) -> str:
        """Generate database-specific upsert SQL for a metadata table."""
        placeholders = '?, ?'
        
        if self._db_type == 'sqlite':
            return f"INSERT OR REPLACE INTO {entity_name}_meta VALUES ({placeholders})"
        
        elif self._db_type == 'postgres':
            # Add a UUID to prevent query caching issues with prepared statements
            return f"INSERT INTO {entity_name}_meta VALUES ({placeholders}) ON CONFLICT(name) DO UPDATE SET type=EXCLUDED.type -- {uuid.uuid4()}"
        
        else:  # MySQL and others
            return f"INSERT INTO {entity_name}_meta VALUES ({placeholders}) AS new ON DUPLICATE KEY UPDATE type=new.type"
    
    def to_json(self, entity: Dict[str, Any]) -> str:
        """
        Convert an entity to a JSON string.
        """
        return json.dumps(entity, default=str)
    
    def from_json(self, json_str: str) -> Dict[str, Any]:
        """
        Convert a JSON string to an entity dictionary.
        """
        return json.loads(json_str)

# -----------------------------------------------------------------
# Database-level entity operations - stay with BaseDatabase
# -----------------------------------------------------------------

class DatabaseEntityMixin(EntityUtils):
    """
    Database-level entity management capabilities.
    
    These methods handle schema operations, metadata, and other operations
    that don't need to be done within a transaction context.
    """

    def __init__(self, *args, **kwargs):
        # Initialize parent class first
        super().__init__(*args, **kwargs)
        
        # Entity metadata caches
        self._meta_cache: Dict[str, Dict[str, str]] = {}  # entity_name -> {field_name: type}
        self._keys_cache: Dict[str, List[str]] = {}       # entity_name -> [field_names]
        self._types_cache: Dict[str, List[str]] = {}      # entity_name -> [field_types]
        self._history_enabled: Set[str] = set()           # entity_names with history tracking
        
        # Database type detection (to handle SQL dialect differences)
        self._db_type = self._detect_db_type()
        
        # Field serializers/deserializers
        self._init_serializers()
        
        # Try to load metadata if we're in a sync environment
        if not self.is_environment_async():
            try:
                self._load_all_metadata_sync()
            except Exception as e:
                logger.warning(f"Metadata load failed in sync mode: {str(e)}")
    
    def _detect_db_type(self) -> str:
        """Detect the database type from the class name."""
        class_name = self.__class__.__name__.lower()
        if 'sqlite' in class_name:
            return 'sqlite'
        elif 'postgres' in class_name:
            return 'postgres'
        elif 'mysql' in class_name or 'mariadb' in class_name:
            return 'mysql'
        else:
            return 'unknown'
    
    def _init_serializers(self):
        """Initialize serializers and deserializers for different types."""
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
    
    def _load_all_metadata_sync(self):
        """Load all entity metadata from the database (synchronous version)."""
        with self.sync_connection() as conn:
            # Get all metadata tables
            sql, params = self._get_sql_for_list_tables()
            tables = conn.execute_sync(sql, params)
            
            for table_row in tables:
                table = table_row[0]
                if not table.endswith("_meta"):
                    continue
                
                entity_name = table[:-5]  # Remove _meta suffix
                
                # Get metadata for this entity
                meta_rows = conn.execute_sync(f"SELECT name, type FROM {table}")
                
                # Build metadata cache
                meta = {name: typ for name, typ in meta_rows}
                self._meta_cache[entity_name] = meta
                self._keys_cache[entity_name] = list(meta.keys())
                self._types_cache[entity_name] = list(meta.values())
                
                # Check if history table exists
                history_check_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
                if self._db_type != 'sqlite':
                    history_check_sql = "SELECT table_name FROM information_schema.tables WHERE table_name=?"
                
                history_rows = conn.execute_sync(history_check_sql, (f"{entity_name}_history",))
                
                if history_rows:
                    self._history_enabled.add(entity_name)
    
    async def _load_all_metadata_async(self):
        """Load all entity metadata from the database (asynchronous version)."""
        async with self.async_connection() as conn:
            # Get all metadata tables
            sql, params = self._get_sql_for_list_tables(is_async=True)
            tables = await conn.execute_async(sql, params)
            
            for table_row in tables:
                table = table_row[0]
                if not table.endswith("_meta"):
                    continue
                
                entity_name = table[:-5]  # Remove _meta suffix
                
                # Get metadata for this entity
                meta_rows = await conn.execute_async(f"SELECT name, type FROM {table}")
                
                # Build metadata cache
                meta = {name: typ for name, typ in meta_rows}
                self._meta_cache[entity_name] = meta
                self._keys_cache[entity_name] = list(meta.keys())
                self._types_cache[entity_name] = list(meta.values())
                
                # Check if history table exists
                history_check_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
                if self._db_type != 'sqlite':
                    history_check_sql = "SELECT table_name FROM information_schema.tables WHERE table_name=?"
                
                history_rows = await conn.execute_async(history_check_sql, (f"{entity_name}_history",))
                
                if history_rows:
                    self._history_enabled.add(entity_name)
    
    def enable_history_sync(self, entity_name: str) -> None:
        """Enable history tracking for an entity (sync version)."""
        with self.sync_connection() as conn:
            # First make sure the main table exists
            check_table_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            if self._db_type != 'sqlite':
                check_table_sql = "SELECT table_name FROM information_schema.tables WHERE table_name=?"
                
            table_exists = conn.execute_sync(check_table_sql, (entity_name,))
            
            if not table_exists:
                raise ValueError(f"Cannot enable history for non-existent entity '{entity_name}'")
            
            # Check if history table exists
            history_exists = conn.execute_sync(check_table_sql, (f"{entity_name}_history",))
            
            if not history_exists:
                # Get columns from the main table
                columns = []
                if self._db_type == 'sqlite':
                    columns_data = conn.execute_sync(f"PRAGMA table_info({entity_name})")
                    columns = [(col[1], col[2]) for col in columns_data]  # (name, type)
                else:
                    # PostgreSQL, MySQL
                    columns_data = conn.execute_sync(
                        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?",
                        (entity_name,)
                    )
                    columns = [(col[0], col[1]) for col in columns_data]  # (name, type)
                
                # Create the history table with the same schema plus history fields
                column_defs = [f"{name} TEXT" for name, _ in columns]
                column_defs.append("version INTEGER")
                column_defs.append("history_timestamp TEXT")
                column_defs.append("history_user_id TEXT")
                column_defs.append("history_comment TEXT")
                
                # Create the history table
                conn.execute_sync(f"""
                    CREATE TABLE {entity_name}_history (
                        {', '.join(column_defs)},
                        PRIMARY KEY (id, version)
                    )
                """)
                
                self._history_enabled.add(entity_name)
    
    async def enable_history_async(self, entity_name: str) -> None:
        """Enable history tracking for an entity (async version)."""
        async with self.async_connection() as conn:
            # First make sure the main table exists
            check_table_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            if self._db_type != 'sqlite':
                check_table_sql = "SELECT table_name FROM information_schema.tables WHERE table_name=?"
                
            table_exists = await conn.execute_async(check_table_sql, (entity_name,))
            
            if not table_exists:
                raise ValueError(f"Cannot enable history for non-existent entity '{entity_name}'")
            
            # Check if history table exists
            history_exists = await conn.execute_async(check_table_sql, (f"{entity_name}_history",))
            
            if not history_exists:
                # Get columns from the main table
                columns = []
                if self._db_type == 'sqlite':
                    columns_data = await conn.execute_async(f"PRAGMA table_info({entity_name})")
                    columns = [(col[1], col[2]) for col in columns_data]  # (name, type)
                else:
                    # PostgreSQL, MySQL
                    columns_data = await conn.execute_async(
                        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?",
                        (entity_name,)
                    )
                    columns = [(col[0], col[1]) for col in columns_data]  # (name, type)
                
                # Create the history table with the same schema plus history fields
                column_defs = [f"{name} TEXT" for name, _ in columns]
                column_defs.append("version INTEGER")
                column_defs.append("history_timestamp TEXT")
                column_defs.append("history_user_id TEXT")
                column_defs.append("history_comment TEXT")
                
                # Create the history table
                await conn.execute_async(f"""
                    CREATE TABLE {entity_name}_history (
                        {', '.join(column_defs)},
                        PRIMARY KEY (id, version)
                    )
                """)
                
                self._history_enabled.add(entity_name)
                
    def list_entities_sync(self) -> List[str]:
        """
        List all entity names in the database.
        
        Returns:
            List of entity names
        """
        with self.sync_connection() as conn:
            if self._db_type == 'sqlite':
                tables = conn.execute_sync(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%_meta' AND name NOT LIKE '%_history'"
                )
            else:
                tables = conn.execute_sync(
                    "SELECT table_name FROM information_schema.tables WHERE table_name NOT LIKE '%_meta' AND table_name NOT LIKE '%_history'"
                )
            
            return [table[0] for table in tables]
    
    async def list_entities_async(self) -> List[str]:
        """
        List all entity names in the database (async version).
        
        Returns:
            List of entity names
        """
        async with self.async_connection() as conn:
            if self._db_type == 'sqlite':
                tables = await conn.execute_async(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%_meta' AND name NOT LIKE '%_history'"
                )
            else:
                tables = await conn.execute_async(
                    "SELECT table_name FROM information_schema.tables WHERE table_name NOT LIKE '%_meta' AND table_name NOT LIKE '%_history'"
                )
            
            return [table[0] for table in tables]
    
    def get_entity_schema_sync(self, entity_name: str) -> Dict[str, str]:
        """
        Get the schema (field names and types) of an entity.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Dictionary mapping field names to their types
        """
        # Load metadata if needed
        if entity_name not in self._meta_cache:
            self._load_all_metadata_sync()
        
        return self._meta_cache.get(entity_name, {})
    
    async def get_entity_schema_async(self, entity_name: str) -> Dict[str, str]:
        """
        Get the schema (field names and types) of an entity (async version).
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Dictionary mapping field names to their types
        """
        # Load metadata if needed
        if entity_name not in self._meta_cache:
            try:
                await self._load_all_metadata_async()
            except Exception as e:
                logger.warning(f"Failed to load metadata asynchronously: {e}")
        
        return self._meta_cache.get(entity_name, {})
        
    def rollback_to_version_sync(self, entity_name: str, id: str, version: int, 
                               user_id: Optional[str] = None, comment: Optional[str] = "Rollback") -> bool:
        """
        Rollback an entity to a previous version.
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            version: Version number to rollback to
            user_id: Optional ID of the user making the change
            comment: Optional comment about the rollback
            
        Returns:
            True if entity was rolled back, False if not found or version invalid
        """
        if entity_name not in self._history_enabled:
            raise ValueError(f"History not enabled for entity '{entity_name}'")
        
        with self.sync_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Get the specified version
            result = conn.execute_sync(
                f"SELECT * FROM {entity_name}_history WHERE id = ? AND version = ?",
                (id, version)
            )
            
            if not result:
                return False
            
            # Get column names for history table
            columns = []
            if self._db_type == 'sqlite':
                col_info = conn.execute_sync(f"PRAGMA table_info({entity_name}_history)")
                columns = [col[1] for col in col_info]
            else:
                col_info = conn.execute_sync(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (f"{entity_name}_history",)
                )
                columns = [col[0] for col in col_info]
            
            # Convert history row to dictionary
            history_entity = dict(zip(columns, result[0]))
            
            # Extract fields that belong to the main entity (remove history-specific fields)
            main_entity = {k: v for k, v in history_entity.items() 
                         if k not in ('version', 'history_timestamp', 'history_user_id', 'history_comment')}
            
            # Add timestamps and user_id
            now = datetime.datetime.utcnow().isoformat()
            main_entity['updated_at'] = now
            if user_id:
                main_entity['updated_by'] = user_id
            
            # Get fields and values for the main entity
            fields = list(main_entity.keys())
            values = [main_entity[field] for field in fields]
            
            # Generate upsert SQL
            upsert_sql = self._get_upsert_sql(entity_name, fields)
            
            # Execute upsert
            conn.execute_sync(upsert_sql, tuple(values))
            
            # Save to history
            main_entity['update_comment'] = comment or f"Rollback to version {version}"
            conn.save_history(entity_name, main_entity, user_id, main_entity['update_comment'])
            
            return True
    
    async def rollback_to_version_async(self, entity_name: str, id: str, version: int, 
                                      user_id: Optional[str] = None, comment: Optional[str] = "Rollback") -> bool:
        """
        Rollback an entity to a previous version (async version).
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            version: Version number to rollback to
            user_id: Optional ID of the user making the change
            comment: Optional comment about the rollback
            
        Returns:
            True if entity was rolled back, False if not found or version invalid
        """
        if entity_name not in self._history_enabled:
            raise ValueError(f"History not enabled for entity '{entity_name}'")
        
        async with self.async_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Get the specified version
            result = await conn.execute_async(
                f"SELECT * FROM {entity_name}_history WHERE id = ? AND version = ?",
                (id, version)
            )
            
            if not result:
                return False
            
            # Get column names for history table
            columns = []
            if self._db_type == 'sqlite':
                col_info = await conn.execute_async(f"PRAGMA table_info({entity_name}_history)")
                columns = [col[1] for col in col_info]
            else:
                col_info = await conn.execute_async(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (f"{entity_name}_history",)
                )
                columns = [col[0] for col in col_info]
            
            # Convert history row to dictionary
            history_entity = dict(zip(columns, result[0]))
            
            # Extract fields that belong to the main entity (remove history-specific fields)
            main_entity = {k: v for k, v in history_entity.items() 
                         if k not in ('version', 'history_timestamp', 'history_user_id', 'history_comment')}
            
            # Add timestamps and user_id
            now = datetime.datetime.utcnow().isoformat()
            main_entity['updated_at'] = now
            if user_id:
                main_entity['updated_by'] = user_id
            
            # Get fields and values for the main entity
            fields = list(main_entity.keys())
            values = [main_entity[field] for field in fields]
            
            # Generate upsert SQL
            upsert_sql = self._get_upsert_sql(entity_name, fields, is_async=True)
            
            # Execute upsert
            await conn.execute_async(upsert_sql, tuple(values))
            
            # Save to history
            main_entity['update_comment'] = comment or f"Rollback to version {version}"
            await conn.save_history(entity_name, main_entity, user_id, main_entity['update_comment'])
            
            return True
    
    def entity_exists_sync(self, entity_name: str, id: str, include_deleted: bool = False) -> bool:
        """
        Check if an entity exists by ID.
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            True if entity exists, False otherwise
        """
        with self.sync_connection() as conn:
            query = f"SELECT COUNT(*) FROM {entity_name} WHERE id = ?"
            params = [id]
            
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            
            result = conn.execute_sync(query, tuple(params))
            
            if not result:
                return False
                
            return result[0][0] > 0
    
    async def entity_exists_async(self, entity_name: str, id: str, include_deleted: bool = False) -> bool:
        """
        Check if an entity exists by ID (async version).
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            True if entity exists, False otherwise
        """
        async with self.async_connection() as conn:
            query = f"SELECT COUNT(*) FROM {entity_name} WHERE id = ?"
            params = [id]
            
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            
            result = await conn.execute_async(query, tuple(params))
            
            if not result:
                return False
                
            return result[0][0] > 0
    
def restore_entity_sync(self, entity_name: str, id: str, 
                      user_id: Optional[str] = None, comment: Optional[str] = "Restored") -> bool:
    """
    Restore a soft-deleted entity.
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        user_id: Optional ID of the user making the change
        comment: Optional comment about the restoration
        
    Returns:
        True if entity was restored, False if not found or not deleted
    """
    with self.sync_transaction() as conn:
        # Check if entity exists and is deleted
        entity_deleted = conn.execute_sync(
            f"SELECT COUNT(*) FROM {entity_name} WHERE id = ? AND deleted_at IS NOT NULL",
            (id,)
        )
        
        if not entity_deleted or entity_deleted[0][0] == 0:
            return False
        
        # Update the entity
        now = datetime.datetime.utcnow().isoformat()
        conn.execute_sync(
            f"UPDATE {entity_name} SET deleted_at = NULL, updated_at = ?, updated_by = ? WHERE id = ?",
            (now, user_id, id)
        )
        
        # Save to history if enabled
        if entity_name in self._history_enabled:
            # Get the updated entity
            result = conn.execute_sync(
                f"SELECT * FROM {entity_name} WHERE id = ?",
                (id,)
            )
            
            if result:
                # Get column names
                columns = []
                if self._db_type == 'sqlite':
                    col_info = conn.execute_sync(f"PRAGMA table_info({entity_name})")
                    columns = [col[1] for col in col_info]
                else:
                    col_info = conn.execute_sync(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                        (entity_name,)
                    )
                    columns = [col[0] for col in col_info]
                
                # Convert to dictionary
                serialized = dict(zip(columns, result[0]))
                
                # Save to history
                conn.save_history(entity_name, serialized, user_id, comment)
        
        return True

async def restore_entity_async(self, entity_name: str, id: str, 
                             user_id: Optional[str] = None, comment: Optional[str] = "Restored") -> bool:
    """
    Restore a soft-deleted entity (async version).
    
    Args:
        entity_name: Name of the entity
        id: Entity ID
        user_id: Optional ID of the user making the change
        comment: Optional comment about the restoration
        
    Returns:
        True if entity was restored, False if not found or not deleted
    """
    async with self.async_transaction() as conn:
        # Check if entity exists and is deleted
        entity_deleted = await conn.execute_async(
            f"SELECT COUNT(*) FROM {entity_name} WHERE id = ? AND deleted_at IS NOT NULL",
            (id,)
        )
        
        if not entity_deleted or entity_deleted[0][0] == 0:
            return False
        
        # Update the entity
        now = datetime.datetime.utcnow().isoformat()
        await conn.execute_async(
            f"UPDATE {entity_name} SET deleted_at = NULL, updated_at = ?, updated_by = ? WHERE id = ?",
            (now, user_id, id)
        )
        
        # Save to history if enabled
        if entity_name in self._history_enabled:
            # Get the updated entity
            result = await conn.execute_async(
                f"SELECT * FROM {entity_name} WHERE id = ?",
                (id,)
            )
            
            if result:
                # Get column names
                columns = []
                if self._db_type == 'sqlite':
                    col_info = await conn.execute_async(f"PRAGMA table_info({entity_name})")
                    columns = [col[1] for col in col_info]
                else:
                    col_info = await conn.execute_async(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                        (entity_name,)
                    )
                    columns = [col[0] for col in col_info]
                
                # Convert to dictionary
                serialized = dict(zip(columns, result[0]))
                
                # Save to history
                await conn.save_history(entity_name, serialized, user_id, comment)
        
        return True


# -----------------------------------------------------------------
# Connection-level entity operations - added to connection classes
# -----------------------------------------------------------------

class ConnectionEntityMixin(EntityUtils):
    """
    Mixin class that adds entity operations to connection classes.
    
    These methods operate within the current transaction context of the connection,
    ensuring proper atomicity of operations.
    """
    
    def _check_field_type_consistency(self, entity_name: str, field: str, value: Any) -> None:
        """
        Check that the type of a field is consistent with its stored metadata.
        Raises Exception if the types are inconsistent.
        """
        if value is None:
            return  # None values don't trigger type consistency checks
        
        # Get stored type information
        stored_type = self._db._meta_cache.get(entity_name, {}).get(field)
        
        if stored_type is None:
            return  # No stored type yet, so no inconsistency
        
        # Infer type from current value
        current_type = self._infer_type(value)
        
        # Check if types are compatible
        if stored_type != current_type:
            raise Exception(
                f"Type mismatch for field '{field}' in entity '{entity_name}': "
                f"stored as '{stored_type}', but provided value is '{current_type}'"
            )
    
    def _ensure_table_sync(self, entity_name: str, entity: Dict[str, Any]) -> None:
        """Ensure entity table exists with all required columns."""
        # Check if table exists
        check_table_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        if self._db._db_type != 'sqlite':
            check_table_sql = "SELECT table_name FROM information_schema.tables WHERE table_name=?"
            
        table_exists = self.execute_sync(check_table_sql, (entity_name,))
        
        if not table_exists:
            # Create the table with basic columns
            self.execute_sync(f"""
                CREATE TABLE {entity_name} (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    updated_at TEXT,
                    deleted_at TEXT NULL
                )
            """)
        
        # Check if metadata table exists
        meta_exists = self.execute_sync(check_table_sql, (f"{entity_name}_meta",))
        
        if not meta_exists:
            # Create metadata table
            primary_key = "PRIMARY KEY" if self._db._db_type == 'sqlite' else "PRIMARY KEY"
            self.execute_sync(f"""
                CREATE TABLE {entity_name}_meta (
                    name TEXT {primary_key},
                    type TEXT
                )
            """)
            
            # Add basic metadata
            meta_sql = self._db._get_meta_upsert_sql(entity_name)
            self.execute_sync(meta_sql, ("id", "str"))
            self.execute_sync(meta_sql, ("created_at", "datetime"))
            self.execute_sync(meta_sql, ("updated_at", "datetime"))
            self.execute_sync(meta_sql, ("deleted_at", "datetime"))
            
            # Update cache
            self._db._meta_cache[entity_name] = {
                "id": "str",
                "created_at": "datetime",
                "updated_at": "datetime",
                "deleted_at": "datetime"
            }
            self._db._keys_cache[entity_name] = ["id", "created_at", "updated_at", "deleted_at"]
            self._db._types_cache[entity_name] = ["str", "datetime", "datetime", "datetime"]
        
        # Load metadata if not in cache
        if entity_name not in self._db._meta_cache:
            meta_rows = self.execute_sync(f"SELECT name, type FROM {entity_name}_meta")
            meta = {name: typ for name, typ in meta_rows}
            self._db._meta_cache[entity_name] = meta
            self._db._keys_cache[entity_name] = list(meta.keys())
            self._db._types_cache[entity_name] = list(meta.values())
        
        # Get existing columns in the table
        existing_columns = []
        if self._db._db_type == 'sqlite':
            columns = self.execute_sync(f"PRAGMA table_info({entity_name})")
            existing_columns = [col[1] for col in columns]  # SQLite: col[1] is column name
        else:
            # PostgreSQL, MySQL
            columns = self.execute_sync(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (entity_name,)
            )
            existing_columns = [col[0] for col in columns]  # Standard SQL: col[0] is column name
        
        # Check for missing columns and add them
        for field, value in entity.items():
            if field not in existing_columns:
                # Add column to table using database-specific ALTER IF NOT EXISTS
                self._add_column_if_not_exists_sync(entity_name, field, value)
            else:
                # Column exists - ensure type consistency
                self._check_field_type_consistency(entity_name, field, value)
    
    def _add_column_if_not_exists_sync(self, entity_name: str, field: str, value: Any) -> None:
        """Add a column to a table if it doesn't exist, using database-specific syntax."""
        field_type = self._infer_type(value)
        
        if self._db._db_type == 'sqlite':
            # SQLite doesn't support ADD IF NOT EXISTS, so check first
            column_exists = self.execute_sync(
                f"PRAGMA table_info({entity_name})", 
                ()
            )
            column_exists = any(col[1] == field for col in column_exists)
            
            if not column_exists:
                self.execute_sync(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
        
        elif self._db._db_type == 'postgres':
            # PostgreSQL supports IF NOT EXISTS
            self.execute_sync(f"ALTER TABLE {entity_name} ADD COLUMN IF NOT EXISTS {field} TEXT")
        
        else:  # MySQL
            # Check if column exists
            column_exists = self.execute_sync(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
                (entity_name, field)
            )
            
            if not column_exists or column_exists[0][0] == 0:
                self.execute_sync(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
        
        # Update metadata
        if field not in self._db._meta_cache.get(entity_name, {}):
            meta_sql = self._db._get_meta_upsert_sql(entity_name)
            self.execute_sync(meta_sql, (field, field_type))
            
            # Update cache
            if entity_name in self._db._meta_cache:
                self._db._meta_cache[entity_name][field] = field_type
                self._db._keys_cache[entity_name].append(field)
                self._db._types_cache[entity_name].append(field_type)
    
    async def _ensure_table_async(self, entity_name: str, entity: Dict[str, Any]) -> None:
        """Ensure entity table exists with all required columns (async version)."""
        # Check if table exists
        check_table_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        if self._db._db_type != 'sqlite':
            check_table_sql = "SELECT table_name FROM information_schema.tables WHERE table_name=?"
            
        table_exists = await self.execute_async(check_table_sql, (entity_name,))
        
        if not table_exists:
            # Create the table with basic columns
            await self.execute_async(f"""
                CREATE TABLE {entity_name} (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    updated_at TEXT,
                    deleted_at TEXT NULL
                )
            """)
        
        # Check if metadata table exists
        meta_exists = await self.execute_async(check_table_sql, (f"{entity_name}_meta",))
        
        if not meta_exists:
            # Create metadata table
            primary_key = "PRIMARY KEY" if self._db._db_type == 'sqlite' else "PRIMARY KEY"
            await self.execute_async(f"""
                CREATE TABLE {entity_name}_meta (
                    name TEXT {primary_key},
                    type TEXT
                )
            """)
            
            # Add basic metadata
            meta_sql = self._db._get_meta_upsert_sql(entity_name, is_async=True)
            await self.execute_async(meta_sql, ("id", "str"))
            await self.execute_async(meta_sql, ("created_at", "datetime"))
            await self.execute_async(meta_sql, ("updated_at", "datetime"))
            await self.execute_async(meta_sql, ("deleted_at", "datetime"))
            
            # Update cache
            self._db._meta_cache[entity_name] = {
                "id": "str",
                "created_at": "datetime",
                "updated_at": "datetime",
                "deleted_at": "datetime"
            }
            self._db._keys_cache[entity_name] = ["id", "created_at", "updated_at", "deleted_at"]
            self._db._types_cache[entity_name] = ["str", "datetime", "datetime", "datetime"]
        
        # Load metadata if not in cache
        if entity_name not in self._db._meta_cache:
            meta_rows = await self.execute_async(f"SELECT name, type FROM {entity_name}_meta")
            meta = {name: typ for name, typ in meta_rows}
            self._db._meta_cache[entity_name] = meta
            self._db._keys_cache[entity_name] = list(meta.keys())
            self._db._types_cache[entity_name] = list(meta.values())
        
        # Get existing columns in the table
        existing_columns = []
        if self._db._db_type == 'sqlite':
            columns = await self.execute_async(f"PRAGMA table_info({entity_name})")
            existing_columns = [col[1] for col in columns]  # SQLite: col[1] is column name
        else:
            # PostgreSQL, MySQL
            columns = await self.execute_async(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (entity_name,)
            )
            existing_columns = [col[0] for col in columns]  # Standard SQL: col[0] is column name
        
        # Check for missing columns and add them
        for field, value in entity.items():
            if field not in existing_columns:
                # Add column to table using database-specific ALTER IF NOT EXISTS
                await self._add_column_if_not_exists_async(entity_name, field, value)
            else:
                # Column exists - ensure type consistency
                self._check_field_type_consistency(entity_name, field, value)
    
    async def _add_column_if_not_exists_async(self, entity_name: str, field: str, value: Any) -> None:
        """Add a column to a table if it doesn't exist (async version)."""
        field_type = self._infer_type(value)
        
        if self._db._db_type == 'sqlite':
            # SQLite doesn't support ADD IF NOT EXISTS, so check first
            column_exists = await self.execute_async(
                f"PRAGMA table_info({entity_name})", 
                ()
            )
            column_exists = any(col[1] == field for col in column_exists)
            
            if not column_exists:
                await self.execute_async(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
        
        elif self._db._db_type == 'postgres':
            # PostgreSQL supports IF NOT EXISTS
            await self.execute_async(f"ALTER TABLE {entity_name} ADD COLUMN IF NOT EXISTS {field} TEXT")
        
        else:  # MySQL
            # Check if column exists
            column_exists = await self.execute_async(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
                (entity_name, field)
            )
            
            if not column_exists or column_exists[0][0] == 0:
                await self.execute_async(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
        
        # Update metadata
        if field not in self._db._meta_cache.get(entity_name, {}):
            meta_sql = self._db._get_meta_upsert_sql(entity_name, is_async=True)
            await self.execute_async(meta_sql, (field, field_type))
            
            # Update cache
            if entity_name in self._db._meta_cache:
                self._db._meta_cache[entity_name][field] = field_type
                self._db._keys_cache[entity_name].append(field)
                self._db._types_cache[entity_name].append(field_type)
    
    def save_history(self, entity_name: str, entity: Dict[str, Optional[str]],
                   user_id: Optional[str] = None, comment: Optional[str] = None) -> None:
        """Save an entity to history table."""
        # Get current version
        current_version = self.execute_sync(
            f"SELECT MAX(version) FROM {entity_name}_history WHERE id = ?",
            (entity["id"],)
        )
        
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
        
        self.execute_sync(
            f"INSERT INTO {entity_name}_history ({fields_str}) VALUES ({placeholders})",
            tuple(values)
        )
    
    async def save_history(self, entity_name: str, entity: Dict[str, Optional[str]],
                         user_id: Optional[str] = None, comment: Optional[str] = None) -> None:
        """Save an entity to history table (async version)."""
        # Get current version
        current_version = await self.execute_async(
            f"SELECT MAX(version) FROM {entity_name}_history WHERE id = ?",
            (entity["id"],)
        )
        
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
        
        await self.execute_async(
            f"INSERT INTO {entity_name}_history ({fields_str}) VALUES ({placeholders})",
            tuple(values)
        )
    
    # ---- CORE ENTITY OPERATIONS ----
    
    def save_entity(self, entity_name: str, entity: Dict[str, Any], 
                  user_id: Optional[str] = None, comment: Optional[str] = None) -> str:
        """
        Save an entity to the database. Creates or updates as needed.
        
        Args:
            entity_name: Name of the entity
            entity: Entity dictionary
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            ID of the saved entity
        """
        # Ensure tables exist
        self._ensure_table_sync(entity_name, entity)
        
        # Prepare entity with timestamps and ID
        prepared_entity = self._db._prepare_entity(entity_name, entity, user_id, comment)
        
        # Get current metadata
        meta = self._db._meta_cache.get(entity_name, {})
        
        # Serialize values
        serialized = self._db._serialize_entity(prepared_entity, meta)
        
        # Get fields and values
        fields = list(serialized.keys())
        values = [serialized[field] for field in fields]
        
        # Generate upsert SQL
        upsert_sql = self._db._get_upsert_sql(entity_name, fields)
        
        # Execute upsert
        self.execute_sync(upsert_sql, tuple(values))
        
        # Save to history if enabled
        if entity_name in self._db._history_enabled:
            self.save_history(entity_name, serialized, user_id, comment)
        
        return prepared_entity["id"]
    
    async def save_entity(self, entity_name: str, entity: Dict[str, Any], 
                        user_id: Optional[str] = None, comment: Optional[str] = None) -> str:
        """
        Save an entity to the database. Creates or updates as needed (async version).
        
        Args:
            entity_name: Name of the entity
            entity: Entity dictionary
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            ID of the saved entity
        """
        # Ensure tables exist
        await self._ensure_table_async(entity_name, entity)
        
        # Prepare entity with timestamps and ID
        prepared_entity = self._db._prepare_entity(entity_name, entity, user_id, comment)
        
        # Get current metadata
        meta = self._db._meta_cache.get(entity_name, {})
        
        # Serialize values
        serialized = self._db._serialize_entity(prepared_entity, meta)
        
        # Get fields and values
        fields = list(serialized.keys())
        values = [serialized[field] for field in fields]
        
        # Generate upsert SQL
        upsert_sql = self._db._get_upsert_sql(entity_name, fields, is_async=True)
        
        # Execute upsert
        await self.execute_async(upsert_sql, tuple(values))
        
        # Save to history if enabled
        if entity_name in self._db._history_enabled:
            await self.save_history(entity_name, serialized, user_id, comment)
        
        return prepared_entity["id"]
    
    def get_entity(self, entity_name: str, id: str, deserialize: bool = True, 
                 include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get an entity by ID.
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Entity dictionary or None if not found
        """
        # Build query
        query = f"SELECT * FROM {entity_name} WHERE id = ?"
        params = [id]
        
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        
        # Execute query
        result = self.execute_sync(query, tuple(params))
        
        if not result:
            return None
        
        # Get column names
        columns = []
        if self._db._db_type == 'sqlite':
            col_info = self.execute_sync(f"PRAGMA table_info({entity_name})")
            columns = [col[1] for col in col_info]  # column name is at index 1
        else:
            # PostgreSQL, MySQL
            col_info = self.execute_sync(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (entity_name,)
            )
            columns = [col[0] for col in col_info]
        
        # Convert to dictionary
        entity = dict(zip(columns, result[0]))
        
        # Deserialize if requested
        if deserialize:
            return self._db._deserialize_entity(entity_name, entity)
        
        return entity
    
    async def get_entity(self, entity_name: str, id: str, deserialize: bool = True, 
                       include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get an entity by ID (async version).
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Entity dictionary or None if not found
        """
        # Build query
        query = f"SELECT * FROM {entity_name} WHERE id = ?"
        params = [id]
        
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        
        # Execute query
        result = await self.execute_async(query, tuple(params))
        
        if not result:
            return None
        
        # Get column names
        columns = []
        if self._db._db_type == 'sqlite':
            col_info = await self.execute_async(f"PRAGMA table_info({entity_name})")
            columns = [col[1] for col in col_info]  # column name is at index 1
        else:
            # PostgreSQL, MySQL
            col_info = await self.execute_async(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (entity_name,)
            )
            columns = [col[0] for col in col_info]
        
        # Convert to dictionary
        entity = dict(zip(columns, result[0]))
        
        # Deserialize if requested
        if deserialize:
            return self._db._deserialize_entity(entity_name, entity)
        
        return entity

    # Additional connection entity methods would be implemented here:
    # - get_entity_by
    # - get_entities
    # - count_entities
    # - delete_entity
    # - update_entity_fields
    # - save_entities
    # - get_entity_history
    # - Query builder methods


# -----------------------------------------------------------------
# Initialization for SyncConnection and AsyncConnection classes
# -----------------------------------------------------------------

# Add abstract methods to SyncConnection
from abc import abstractmethod

class SyncConnection(ABC, BaseConnection):
    """
    Abstract base class defining the interface for synchronous database connections.
    """
    
    @abstractmethod
    def save_entity(self, entity_name: str, entity: Dict[str, Any], 
                   user_id: Optional[str] = None, comment: Optional[str] = None) -> str:
        """
        Save an entity to the database. Creates or updates as needed.
        """
        pass
    
    @abstractmethod
    def get_entity(self, entity_name: str, id: str, deserialize: bool = True, 
                 include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get an entity by ID.
        """
        pass
    
    # Additional abstract entity methods...

class AsyncConnection(BaseConnection, ABC):
    """
    Abstract base class defining the interface for asynchronous database connections.
    """
    
    @abstractmethod
    async def save_entity(self, entity_name: str, entity: Dict[str, Any], 
                        user_id: Optional[str] = None, comment: Optional[str] = None) -> str:
        """
        Save an entity to the database asynchronously. Creates or updates as needed.
        """
        pass
    
    @abstractmethod
    async def get_entity(self, entity_name: str, id: str, deserialize: bool = True, 
                       include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get an entity by ID asynchronously.
        """
        pass
    
    # Additional abstract entity methods...


# -----------------------------------------------------------------
# Implementation for concrete connection classes
# -----------------------------------------------------------------

class PostgresSyncConnection(SyncConnection, ConnectionEntityMixin):
    """PostgreSQL implementation of the SyncConnection interface with entity support."""
    
    def __init__(self, conn, db):
        SyncConnection.__init__(self, conn)
        self._db = db  # Reference to the database instance for metadata access
    
    # Implement entity methods from ConnectionEntityMixin
    # The mixin provides implementations but needs references to _db

class PostgresAsyncConnection(AsyncConnection, ConnectionEntityMixin):
    """PostgreSQL implementation of the AsyncConnection interface with entity support."""
    
    def __init__(self, conn, db):
        AsyncConnection.__init__(self, conn)
        self._db = db  # Reference to the database instance for metadata access
    
    # Implement entity methods from ConnectionEntityMixin

# Similarly for MySQL and SQLite connection classes