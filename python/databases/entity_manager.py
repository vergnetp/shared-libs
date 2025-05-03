import json
import uuid
import datetime
import contextlib
from typing import Dict, List, Any, Optional, Tuple, Union, Set
from .. import log as logger

class EntityManager:
    """
    Mixin that adds entity management capabilities to database classes.
    
    Provides methods to save, retrieve, and manage entities with automatic
    schema creation, soft deletion, history tracking, and serialization.
    
    This mixin should be used with BaseDatabase subclasses to add entity
    management capabilities. It supports both sync and async operations.

    Important MySQL Transaction Limitations:
    --------------------------------------
    When using MySQL, be aware that DDL operations (like ALTER TABLE) cause
    an implicit commit, which breaks transaction atomicity. This has a critical
    consequence:
    
    If you save multiple entities within a transaction and later roll back,
    any data saved BEFORE a schema change operation will be committed and 
    persist in the database, despite the rollback. For example:
    
    1. Begin transaction
    2. Save entity A (creates id='1', name='Phil')
    3. Save entity B with a new field (triggers schema change)
    4. Save entity C
    5. Roll back transaction
    
    Result: Entity A's data will still be in the database! Only entities B and C
    will be rolled back correctly.
    
    This happens because MySQL's implicit commit for DDL operations effectively
    commits all previous data operations as well.
    
    Mitigation strategies:
    1. Perform schema changes outside of data transactions when possible
    2. Consider using PostgreSQL which supports transactional DDL operations
    3. Be careful about transaction boundaries and entity ordering
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
    
    # ---- region DATABASE DIALECT HELPERS ----
    
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
    
    # endregion ----------------------------

    # ---- METADATA LOADING METHODS ----
    
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
    
    # endregion ------------------------

    # ---- region SERIALIZATION HELPERS ----
    
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
    
    # endregion ---------------------------

    # ---- region ENTITY TABLE MANAGEMENT ----
    
    def _check_field_type_consistency(self, entity_name: str, field: str, value: Any) -> None:
        """
        Check that the type of a field is consistent with its stored metadata.
        Raises Exception if the types are inconsistent.
        """
        if value is None:
            return  # None values don't trigger type consistency checks
        
        # Get stored type information
        stored_type = self._meta_cache.get(entity_name, {}).get(field)
        
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
        """Ensure entity table exists with all required columns (sync version)."""
        with self.sync_connection() as conn:
            # Check if table exists
            check_table_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            if self._db_type != 'sqlite':
                check_table_sql = "SELECT table_name FROM information_schema.tables WHERE table_name=?"
                
            table_exists = conn.execute_sync(check_table_sql, (entity_name,))
            
            if not table_exists:
                # Create the table with basic columns
                conn.execute_sync(f"""
                    CREATE TABLE {entity_name} (
                        id TEXT PRIMARY KEY,
                        created_at TEXT,
                        updated_at TEXT,
                        deleted_at TEXT NULL
                    )
                """)
            
            # Check if metadata table exists
            meta_exists = conn.execute_sync(check_table_sql, (f"{entity_name}_meta",))
            
            if not meta_exists:
                # Create metadata table
                primary_key = "PRIMARY KEY" if self._db_type == 'sqlite' else "PRIMARY KEY"
                conn.execute_sync(f"""
                    CREATE TABLE {entity_name}_meta (
                        name TEXT {primary_key},
                        type TEXT
                    )
                """)
                
                # Add basic metadata
                meta_sql = self._get_meta_upsert_sql(entity_name)
                conn.execute_sync(meta_sql, ("id", "str"))
                conn.execute_sync(meta_sql, ("created_at", "datetime"))
                conn.execute_sync(meta_sql, ("updated_at", "datetime"))
                conn.execute_sync(meta_sql, ("deleted_at", "datetime"))
                
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
            meta_rows = conn.execute_sync(f"SELECT name, type FROM {entity_name}_meta")
            meta = {name: typ for name, typ in meta_rows}
            self._meta_cache[entity_name] = meta
            self._keys_cache[entity_name] = list(meta.keys())
            self._types_cache[entity_name] = list(meta.values())
        
        # Get existing columns in the table
        existing_columns = []
        if self._db_type == 'sqlite':
            columns = conn.execute_sync(f"PRAGMA table_info({entity_name})")
            existing_columns = [col[1] for col in columns]  # SQLite: col[1] is column name
        else:
            # PostgreSQL, MySQL
            columns = conn.execute_sync(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (entity_name,)
            )
            existing_columns = [col[0] for col in columns]  # Standard SQL: col[0] is column name
        
        # Check for missing columns and add them
        for field, value in entity.items():
            if field not in existing_columns:
                # Add column to table using database-specific ALTER IF NOT EXISTS
                self._add_column_if_not_exists_sync(conn, entity_name, field, value)
            else:
                # Column exists - ensure type consistency
                self._check_field_type_consistency(entity_name, field, value)

    def _add_column_if_not_exists_sync(self, conn, entity_name: str, field: str, value: Any) -> None:
        """Add a column to a table if it doesn't exist, using database-specific syntax."""
        field_type = self._infer_type(value)
        
        if self._db_type == 'sqlite':
            # SQLite doesn't support ADD IF NOT EXISTS, so check first
            column_exists = conn.execute_sync(
                f"PRAGMA table_info({entity_name})", 
                ()
            )
            column_exists = any(col[1] == field for col in column_exists)
            
            if not column_exists:
                conn.execute_sync(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
        
        elif self._db_type == 'postgres':
            # PostgreSQL supports IF NOT EXISTS
            conn.execute_sync(f"ALTER TABLE {entity_name} ADD COLUMN IF NOT EXISTS {field} TEXT")
        
        elif self._db_type == 'mysql':
            # MySQL 8.0+ supports IF NOT EXISTS
            # For older versions, we need to check if the column exists first
            if self._mysql_version_supports_if_not_exists():
                conn.execute_sync(f"ALTER TABLE {entity_name} ADD COLUMN IF NOT EXISTS {field} TEXT")
            else:
                # Check if column exists
                column_exists = conn.execute_sync(
                    "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
                    (entity_name, field)
                )
                
                if not column_exists or column_exists[0][0] == 0:
                    conn.execute_sync(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
        
        else:
            # For unknown databases, use a safe approach
            try:
                conn.execute_sync(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
            except Exception as e:
                if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                    raise  # Re-raise if it's not a "column already exists" error
        
        # Update metadata
        if field not in self._meta_cache.get(entity_name, {}):
            meta_sql = self._get_meta_upsert_sql(entity_name)
            conn.execute_sync(meta_sql, (field, field_type))
            
            # Update cache
            if entity_name in self._meta_cache:
                self._meta_cache[entity_name][field] = field_type
                self._keys_cache[entity_name].append(field)
                self._types_cache[entity_name].append(field_type)

    def _mysql_version_supports_if_not_exists(self) -> bool:
        """Check if the MySQL version supports IF NOT EXISTS in ALTER TABLE ADD COLUMN."""
        if not hasattr(self, '_mysql_if_not_exists_supported'):
            with self.sync_connection() as conn:
                try:
                    version = conn.execute_sync("SELECT VERSION()")
                    if version and version[0]:
                        # Parse major version number
                        major_version = int(version[0][0].split('.')[0])
                        self._mysql_if_not_exists_supported = major_version >= 8
                    else:
                        self._mysql_if_not_exists_supported = False
                except Exception:
                    # If we can't determine version, assume not supported
                    self._mysql_if_not_exists_supported = False
        
        return self._mysql_if_not_exists_supported

    async def _ensure_table_async(self, entity_name: str, entity: Dict[str, Any]) -> None:
        """Ensure entity table exists with all required columns (async version)."""
        async with self.async_connection() as conn:
            # Check if table exists
            check_table_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            if self._db_type != 'sqlite':
                check_table_sql = "SELECT table_name FROM information_schema.tables WHERE table_name=?"
                
            table_exists = await conn.execute_async(check_table_sql, (entity_name,))
            
            if not table_exists:
                # Create the table with basic columns
                await conn.execute_async(f"""
                    CREATE TABLE {entity_name} (
                        id TEXT PRIMARY KEY,
                        created_at TEXT,
                        updated_at TEXT,
                        deleted_at TEXT NULL
                    )
                """)
            
            # Check if metadata table exists
            meta_exists = await conn.execute_async(check_table_sql, (f"{entity_name}_meta",))
            
            if not meta_exists:
                # Create metadata table
                primary_key = "PRIMARY KEY" if self._db_type == 'sqlite' else "PRIMARY KEY"
                await conn.execute_async(f"""
                    CREATE TABLE {entity_name}_meta (
                        name TEXT {primary_key},
                        type TEXT
                    )
                """)
                
                # Add basic metadata
                meta_sql = self._get_meta_upsert_sql(entity_name, is_async=True)
                await conn.execute_async(meta_sql, ("id", "str"))
                await conn.execute_async(meta_sql, ("created_at", "datetime"))
                await conn.execute_async(meta_sql, ("updated_at", "datetime"))
                await conn.execute_async(meta_sql, ("deleted_at", "datetime"))
                
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
                meta_rows = await conn.execute_async(f"SELECT name, type FROM {entity_name}_meta")
                meta = {name: typ for name, typ in meta_rows}
                self._meta_cache[entity_name] = meta
                self._keys_cache[entity_name] = list(meta.keys())
                self._types_cache[entity_name] = list(meta.values())
            
            # Get existing columns in the table
            existing_columns = []
            if self._db_type == 'sqlite':
                columns = await conn.execute_async(f"PRAGMA table_info({entity_name})")
                existing_columns = [col[1] for col in columns]  # SQLite: col[1] is column name
            else:
                # PostgreSQL, MySQL
                columns = await conn.execute_async(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (entity_name,)
                )
                existing_columns = [col[0] for col in columns]  # Standard SQL: col[0] is column name
            
            # Check for missing columns and add them
            for field, value in entity.items():
                if field not in existing_columns:
                    # Add column to table using database-specific ALTER IF NOT EXISTS
                    await self._add_column_if_not_exists_async(conn, entity_name, field, value)
                else:
                    # Column exists - ensure type consistency
                    self._check_field_type_consistency(entity_name, field, value)

    async def _add_column_if_not_exists_async(self, conn, entity_name: str, field: str, value: Any) -> None:
        """Add a column to a table if it doesn't exist, using database-specific syntax (async version)."""
        field_type = self._infer_type(value)
        
        if self._db_type == 'sqlite':
            # SQLite doesn't support ADD IF NOT EXISTS, so check first
            column_exists = await conn.execute_async(
                f"PRAGMA table_info({entity_name})", 
                ()
            )
            column_exists = any(col[1] == field for col in column_exists)
            
            if not column_exists:
                await conn.execute_async(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
        
        elif self._db_type == 'postgres':
            # PostgreSQL supports IF NOT EXISTS
            await conn.execute_async(f"ALTER TABLE {entity_name} ADD COLUMN IF NOT EXISTS {field} TEXT")
        
        elif self._db_type == 'mysql':
            # MySQL 8.0+ supports IF NOT EXISTS
            # For older versions, we need to check if the column exists first
            if self._mysql_version_supports_if_not_exists():
                await conn.execute_async(f"ALTER TABLE {entity_name} ADD COLUMN IF NOT EXISTS {field} TEXT")
            else:
                # Check if column exists
                column_exists = await conn.execute_async(
                    "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
                    (entity_name, field)
                )
                
                if not column_exists or column_exists[0][0] == 0:
                    await conn.execute_async(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
        
        else:
            # For unknown databases, use a safe approach
            try:
                await conn.execute_async(f"ALTER TABLE {entity_name} ADD COLUMN {field} TEXT")
            except Exception as e:
                if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                    raise  # Re-raise if it's not a "column already exists" error
        
        # Update metadata
        if field not in self._meta_cache.get(entity_name, {}):
            meta_sql = self._get_meta_upsert_sql(entity_name, is_async=True)
            await conn.execute_async(meta_sql, (field, field_type))
            
            # Update cache
            if entity_name in self._meta_cache:
                self._meta_cache[entity_name][field] = field_type
                self._keys_cache[entity_name].append(field)
                self._types_cache[entity_name].append(field_type)

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
    
    # endregion ------------------------------

    # ---- region HISTORY TRACKING METHODS ----
    
    def _save_history_sync(self, conn, entity_name: str, entity: Dict[str, Optional[str]],
                          user_id: Optional[str] = None, comment: Optional[str] = None) -> None:
        """Save an entity to history table (sync version)."""
        # Get current version
        current_version = conn.execute_sync(
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
        
        conn.execute_sync(
            f"INSERT INTO {entity_name}_history ({fields_str}) VALUES ({placeholders})",
            tuple(values)
        )
    
    async def _save_history_async(self, conn, entity_name: str, entity: Dict[str, Optional[str]],
                                user_id: Optional[str] = None, comment: Optional[str] = None) -> None:
        """Save an entity to history table (async version)."""
        # Get current version
        current_version = await conn.execute_async(
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
        
        await conn.execute_async(
            f"INSERT INTO {entity_name}_history ({fields_str}) VALUES ({placeholders})",
            tuple(values)
        )
    
    # endregion ------------------------------

    # ---- region ENTITY OPERATIONS (SYNCHRONOUS) ----
    
    def save_entity_sync(self, entity_name: str, entity: Dict[str, Any], 
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
        with self.sync_transaction() as conn:
            # Ensure tables exist
            self._ensure_table_sync(entity_name, entity)
            
            # Prepare entity with timestamps and ID
            prepared_entity = self._prepare_entity(entity_name, entity, user_id, comment)
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
            # Serialize values
            serialized = self._serialize_entity(prepared_entity, meta)
            
            # Get fields and values
            fields = list(serialized.keys())
            values = [serialized[field] for field in fields]
            
            # Generate upsert SQL
            upsert_sql = self._get_upsert_sql(entity_name, fields)
            
            # Execute upsert
            conn.execute_sync(upsert_sql, tuple(values))
            
            # Save to history if enabled
            if entity_name in self._history_enabled:
                self._save_history_sync(conn, entity_name, serialized, user_id, comment)
            
            return prepared_entity["id"]
    
    def get_entity_sync(self, entity_name: str, id: str, deserialize: bool = True, 
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
        with self.sync_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Build query
            query = f"SELECT * FROM {entity_name} WHERE id = ?"
            params = [id]
            
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            
            # Execute query
            result = conn.execute_sync(query, tuple(params))
            
            if not result:
                return None
            
            # Get column names
            columns = []
            if self._db_type == 'sqlite':
                col_info = conn.execute_sync(f"PRAGMA table_info({entity_name})")
                columns = [col[1] for col in col_info]  # column name is at index 1
            else:
                # PostgreSQL, MySQL
                col_info = conn.execute_sync(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (entity_name,)
                )
                columns = [col[0] for col in col_info]
            
            # Convert to dictionary
            entity = dict(zip(columns, result[0]))
            
            # Deserialize if requested
            if deserialize:
                return self._deserialize_entity(entity_name, entity)
            
            return entity
    
    def get_entity_by_sync(self, entity_name: str, field: str, value: Any, 
                         deserialize: bool = True, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get an entity by field value.
        
        Args:
            entity_name: Name of the entity
            field: Field name to search by
            value: Value to search for
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Entity dictionary or None if not found
        """
        with self.sync_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Get the field type
            field_type = self._meta_cache.get(entity_name, {}).get(field, self._infer_type(value))
            
            # Serialize the search value
            serialized_value = self._serialize_value(value, field_type)
            
            # Build query
            query = f"SELECT * FROM {entity_name} WHERE {field} = ?"
            params = [serialized_value]
            
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            
            # Execute query
            result = conn.execute_sync(query, tuple(params))
            
            if not result:
                return None
            
            # Get column names
            columns = []
            if self._db_type == 'sqlite':
                col_info = conn.execute_sync(f"PRAGMA table_info({entity_name})")
                columns = [col[1] for col in col_info]  # column name is at index 1
            else:
                # PostgreSQL, MySQL
                col_info = conn.execute_sync(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (entity_name,)
                )
                columns = [col[0] for col in col_info]
            
            # Convert to dictionary
            entity = dict(zip(columns, result[0]))
            
            # Deserialize if requested
            if deserialize:
                return self._deserialize_entity(entity_name, entity)
            
            return entity
    
    def get_entities_sync(self, entity_name: str, conditions: Optional[Dict[str, Any]] = None,
                         limit: int = 100, offset: int = 0, deserialize: bool = True,
                         include_deleted: bool = False, order_by: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get multiple entities with optional filtering.
        
        Args:
            entity_name: Name of the entity
            conditions: Dictionary of field-value pairs for filtering
            limit: Maximum number of entities to return
            offset: Number of entities to skip
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            order_by: Optional field to order by (prefix with - for DESC)
            
        Returns:
            List of entity dictionaries
        """
        with self.sync_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Build query
            query = f"SELECT * FROM {entity_name}"
            params = []
            
            # Add conditions
            where_clauses = []
            if conditions:
                for field, value in conditions.items():
                    # Get field type and serialize value
                    field_type = self._meta_cache.get(entity_name, {}).get(field, self._infer_type(value))
                    serialized_value = self._serialize_value(value, field_type)
                    
                    where_clauses.append(f"{field} = ?")
                    params.append(serialized_value)
            
            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            # Add ordering
            if order_by:
                if order_by.startswith('-'):
                    query += f" ORDER BY {order_by[1:]} DESC"
                else:
                    query += f" ORDER BY {order_by} ASC"
            
            # Add pagination
            query += f" LIMIT {limit} OFFSET {offset}"
            
            # Execute query
            result = conn.execute_sync(query, tuple(params))
            
            if not result:
                return []
            
            # Get column names
            columns = []
            if self._db_type == 'sqlite':
                col_info = conn.execute_sync(f"PRAGMA table_info({entity_name})")
                columns = [col[1] for col in col_info]  # column name is at index 1
            else:
                # PostgreSQL, MySQL
                col_info = conn.execute_sync(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (entity_name,)
                )
                columns = [col[0] for col in col_info]
            
            # Convert to dictionaries
            entities = []
            for row in result:
                entity = dict(zip(columns, row))
                
                # Deserialize if requested
                if deserialize:
                    entity = self._deserialize_entity(entity_name, entity)
                
                entities.append(entity)
            
            return entities
    
    def count_entities_sync(self, entity_name: str, conditions: Optional[Dict[str, Any]] = None,
                          include_deleted: bool = False) -> int:
        """
        Count entities with optional filtering.
        
        Args:
            entity_name: Name of the entity
            conditions: Dictionary of field-value pairs for filtering
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Count of matching entities
        """
        with self.sync_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Build query
            query = f"SELECT COUNT(*) FROM {entity_name}"
            params = []
            
            # Add conditions
            where_clauses = []
            if conditions:
                for field, value in conditions.items():
                    # Get field type and serialize value
                    field_type = self._meta_cache.get(entity_name, {}).get(field, self._infer_type(value))
                    serialized_value = self._serialize_value(value, field_type)
                    
                    where_clauses.append(f"{field} = ?")
                    params.append(serialized_value)
            
            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            # Execute query
            result = conn.execute_sync(query, tuple(params))
            
            if not result:
                return 0
            
            return result[0][0]
    
    def delete_entity_sync(self, entity_name: str, id: str, 
                         soft_delete: bool = True, user_id: Optional[str] = None, 
                         comment: Optional[str] = "Deleted") -> bool:
        """
        Delete an entity by ID.
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            soft_delete: Whether to use soft deletion (update deleted_at)
            user_id: Optional ID of the user making the change
            comment: Optional comment about the deletion
            
        Returns:
            True if entity was deleted, False if not found
        """
        with self.sync_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Check if entity exists
            entity_exists = conn.execute_sync(
                f"SELECT COUNT(*) FROM {entity_name} WHERE id = ?",
                (id,)
            )
            
            if not entity_exists or entity_exists[0][0] == 0:
                return False
            
            if soft_delete:
                # Soft delete by updating deleted_at
                now = datetime.datetime.utcnow().isoformat()
                
                # Update the entity
                conn.execute_sync(
                    f"UPDATE {entity_name} SET deleted_at = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                    (now, now, user_id, id)
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
                        self._save_history_sync(conn, entity_name, serialized, user_id, comment or "Deleted")
            else:
                # Hard delete
                conn.execute_sync(
                    f"DELETE FROM {entity_name} WHERE id = ?",
                    (id,)
                )
                
                # Also delete from history if enabled
                if entity_name in self._history_enabled:
                    conn.execute_sync(
                        f"DELETE FROM {entity_name}_history WHERE id = ?",
                        (id,)
                    )
            
            return True
    
    def save_entities_sync(self, entity_name: str, entities: List[Dict[str, Any]],
                         user_id: Optional[str] = None, comment: Optional[str] = None) -> List[str]:
        """
        Save multiple entities in a single transaction.
        
        Args:
            entity_name: Name of the entity
            entities: List of entity dictionaries
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            List of saved entity IDs
        """
        ids = []
        
        with self.sync_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Ensure tables exist
            if entities:
                self._ensure_table_sync(entity_name, entities[0])
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
            # Save each entity
            for entity in entities:
                # Prepare entity with timestamps and ID
                prepared_entity = self._prepare_entity(entity_name, entity, user_id, comment)
                
                # Serialize values
                serialized = self._serialize_entity(prepared_entity, meta)
                
                # Get fields and values
                fields = list(serialized.keys())
                values = [serialized[field] for field in fields]
                
                # Generate upsert SQL
                upsert_sql = self._get_upsert_sql(entity_name, fields)
                
                # Execute upsert
                conn.execute_sync(upsert_sql, tuple(values))
                
                # Save to history if enabled
                if entity_name in self._history_enabled:
                    self._save_history_sync(conn, entity_name, serialized, user_id, comment)
                
                ids.append(prepared_entity["id"])
            
        return ids
    
    def get_entity_history_sync(self, entity_name: str, id: str, 
                             limit: int = 100, offset: int = 0,
                             deserialize: bool = True) -> List[Dict[str, Any]]:
        """
        Get the history of an entity.
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            limit: Maximum number of history entries to return
            offset: Number of history entries to skip
            deserialize: Whether to deserialize values to Python types
            
        Returns:
            List of entity history entries, ordered by version (newest first)
        """
        if entity_name not in self._history_enabled:
            raise ValueError(f"History not enabled for entity '{entity_name}'")
        
        with self.sync_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Build query
            query = f"SELECT * FROM {entity_name}_history WHERE id = ? ORDER BY version DESC LIMIT {limit} OFFSET {offset}"
            
            # Execute query
            result = conn.execute_sync(query, (id,))
            
            if not result:
                return []
            
            # Get column names
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
            
            # Convert to dictionaries
            history = []
            for row in result:
                entity = dict(zip(columns, row))
                
                # Deserialize if requested
                if deserialize:
                    entity = self._deserialize_entity(entity_name, entity)
                
                history.append(entity)
            
            return history
    
    def update_entity_fields_sync(self, entity_name: str, id: str, fields: Dict[str, Any],
                                user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
        """
        Update specific fields of an entity.
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            fields: Dictionary of field-value pairs to update
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            True if entity was updated, False if not found
        """
        with self.sync_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                self._load_all_metadata_sync()
            
            # Check if entity exists
            entity_exists = conn.execute_sync(
                f"SELECT COUNT(*) FROM {entity_name} WHERE id = ?",
                (id,)
            )
            
            if not entity_exists or entity_exists[0][0] == 0:
                return False
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
            # Add timestamps and user_id
            update_fields = fields.copy()
            update_fields['updated_at'] = datetime.datetime.utcnow()
            if user_id:
                update_fields['updated_by'] = user_id
            if comment:
                update_fields['update_comment'] = comment
            
            # Serialize values
            serialized = {}
            for field, value in update_fields.items():
                field_type = meta.get(field, self._infer_type(value))
                serialized[field] = self._serialize_value(value, field_type)
            
            # Build SET clause and parameters
            set_clause = ', '.join([f"{field} = ?" for field in serialized.keys()])
            params = list(serialized.values())
            params.append(id)  # For the WHERE clause
            
            # Execute update
            conn.execute_sync(
                f"UPDATE {entity_name} SET {set_clause} WHERE id = ?",
                tuple(params)
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
                    serialized_entity = dict(zip(columns, result[0]))
                    
                    # Save to history
                    self._save_history_sync(conn, entity_name, serialized_entity, user_id, comment)
            
            return True
        
# ---- region ENTITY OPERATIONS (ASYNCHRONOUS) ----
    
    async def save_entity_async(self, entity_name: str, entity: Dict[str, Any], 
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
        async with self.async_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Ensure tables exist
            await self._ensure_table_async(entity_name, entity)
            
            # Prepare entity with timestamps and ID
            prepared_entity = self._prepare_entity(entity_name, entity, user_id, comment)
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
            # Serialize values
            serialized = self._serialize_entity(prepared_entity, meta)
            
            # Get fields and values
            fields = list(serialized.keys())
            values = [serialized[field] for field in fields]
            
            # Generate upsert SQL
            upsert_sql = self._get_upsert_sql(entity_name, fields, is_async=True)
            
            # Execute upsert
            await conn.execute_async(upsert_sql, tuple(values))
            
            # Save to history if enabled
            if entity_name in self._history_enabled:
                await self._save_history_async(conn, entity_name, serialized, user_id, comment)
            
            return prepared_entity["id"]
    
    async def get_entity_async(self, entity_name: str, id: str, deserialize: bool = True, 
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
        async with self.async_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Build query
            query = f"SELECT * FROM {entity_name} WHERE id = ?"
            params = [id]
            
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            
            # Execute query
            result = await conn.execute_async(query, tuple(params))
            
            if not result:
                return None
            
            # Get column names
            columns = []
            if self._db_type == 'sqlite':
                col_info = await conn.execute_async(f"PRAGMA table_info({entity_name})")
                columns = [col[1] for col in col_info]  # column name is at index 1
            else:
                # PostgreSQL, MySQL
                col_info = await conn.execute_async(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (entity_name,)
                )
                columns = [col[0] for col in col_info]
            
            # Convert to dictionary
            entity = dict(zip(columns, result[0]))
            
            # Deserialize if requested
            if deserialize:
                return self._deserialize_entity(entity_name, entity)
            
            return entity
    
    async def get_entity_by_async(self, entity_name: str, field: str, value: Any, 
                                deserialize: bool = True, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get an entity by field value (async version).
        
        Args:
            entity_name: Name of the entity
            field: Field name to search by
            value: Value to search for
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Entity dictionary or None if not found
        """
        async with self.async_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Get the field type
            field_type = self._meta_cache.get(entity_name, {}).get(field, self._infer_type(value))
            
            # Serialize the search value
            serialized_value = self._serialize_value(value, field_type)
            
            # Build query
            query = f"SELECT * FROM {entity_name} WHERE {field} = ?"
            params = [serialized_value]
            
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            
            # Execute query
            result = await conn.execute_async(query, tuple(params))
            
            if not result:
                return None
            
            # Get column names
            columns = []
            if self._db_type == 'sqlite':
                col_info = await conn.execute_async(f"PRAGMA table_info({entity_name})")
                columns = [col[1] for col in col_info]  # column name is at index 1
            else:
                # PostgreSQL, MySQL
                col_info = await conn.execute_async(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (entity_name,)
                )
                columns = [col[0] for col in col_info]
            
            # Convert to dictionary
            entity = dict(zip(columns, result[0]))
            
            # Deserialize if requested
            if deserialize:
                return self._deserialize_entity(entity_name, entity)
            
            return entity
    
    async def get_entities_async(self, entity_name: str, conditions: Optional[Dict[str, Any]] = None,
                               limit: int = 100, offset: int = 0, deserialize: bool = True,
                               include_deleted: bool = False, order_by: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get multiple entities with optional filtering (async version).
        
        Args:
            entity_name: Name of the entity
            conditions: Dictionary of field-value pairs for filtering
            limit: Maximum number of entities to return
            offset: Number of entities to skip
            deserialize: Whether to deserialize values to Python types
            include_deleted: Whether to include soft-deleted entities
            order_by: Optional field to order by (prefix with - for DESC)
            
        Returns:
            List of entity dictionaries
        """
        async with self.async_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Build query
            query = f"SELECT * FROM {entity_name}"
            params = []
            
            # Add conditions
            where_clauses = []
            if conditions:
                for field, value in conditions.items():
                    # Get field type and serialize value
                    field_type = self._meta_cache.get(entity_name, {}).get(field, self._infer_type(value))
                    serialized_value = self._serialize_value(value, field_type)
                    
                    where_clauses.append(f"{field} = ?")
                    params.append(serialized_value)
            
            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            # Add ordering
            if order_by:
                if order_by.startswith('-'):
                    query += f" ORDER BY {order_by[1:]} DESC"
                else:
                    query += f" ORDER BY {order_by} ASC"
            
            # Add pagination
            query += f" LIMIT {limit} OFFSET {offset}"
            
            # Execute query
            result = await conn.execute_async(query, tuple(params))
            
            if not result:
                return []
            
            # Get column names
            columns = []
            if self._db_type == 'sqlite':
                col_info = await conn.execute_async(f"PRAGMA table_info({entity_name})")
                columns = [col[1] for col in col_info]  # column name is at index 1
            else:
                # PostgreSQL, MySQL
                col_info = await conn.execute_async(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (entity_name,)
                )
                columns = [col[0] for col in col_info]
            
            # Convert to dictionaries
            entities = []
            for row in result:
                entity = dict(zip(columns, row))
                
                # Deserialize if requested
                if deserialize:
                    entity = self._deserialize_entity(entity_name, entity)
                
                entities.append(entity)
            
            return entities
    
    async def count_entities_async(self, entity_name: str, conditions: Optional[Dict[str, Any]] = None,
                                 include_deleted: bool = False) -> int:
        """
        Count entities with optional filtering (async version).
        
        Args:
            entity_name: Name of the entity
            conditions: Dictionary of field-value pairs for filtering
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Count of matching entities
        """
        async with self.async_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Build query
            query = f"SELECT COUNT(*) FROM {entity_name}"
            params = []
            
            # Add conditions
            where_clauses = []
            if conditions:
                for field, value in conditions.items():
                    # Get field type and serialize value
                    field_type = self._meta_cache.get(entity_name, {}).get(field, self._infer_type(value))
                    serialized_value = self._serialize_value(value, field_type)
                    
                    where_clauses.append(f"{field} = ?")
                    params.append(serialized_value)
            
            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            # Execute query
            result = await conn.execute_async(query, tuple(params))
            
            if not result:
                return 0
            
            return result[0][0]
    
    async def delete_entity_async(self, entity_name: str, id: str, 
                                soft_delete: bool = True, user_id: Optional[str] = None, 
                                comment: Optional[str] = "Deleted") -> bool:
        """
        Delete an entity by ID (async version).
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            soft_delete: Whether to use soft deletion (update deleted_at)
            user_id: Optional ID of the user making the change
            comment: Optional comment about the deletion
            
        Returns:
            True if entity was deleted, False if not found
        """
        async with self.async_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Check if entity exists
            entity_exists = await conn.execute_async(
                f"SELECT COUNT(*) FROM {entity_name} WHERE id = ?",
                (id,)
            )
            
            if not entity_exists or entity_exists[0][0] == 0:
                return False
            
            if soft_delete:
                # Soft delete by updating deleted_at
                now = datetime.datetime.utcnow().isoformat()
                
                # Update the entity
                await conn.execute_async(
                    f"UPDATE {entity_name} SET deleted_at = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                    (now, now, user_id, id)
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
                        await self._save_history_async(conn, entity_name, serialized, user_id, comment or "Deleted")
            else:
                # Hard delete
                await conn.execute_async(
                    f"DELETE FROM {entity_name} WHERE id = ?",
                    (id,)
                )
                
                # Also delete from history if enabled
                if entity_name in self._history_enabled:
                    await conn.execute_async(
                        f"DELETE FROM {entity_name}_history WHERE id = ?",
                        (id,)
                    )
            
            return True
    
    async def save_entities_async(self, entity_name: str, entities: List[Dict[str, Any]],
                                user_id: Optional[str] = None, comment: Optional[str] = None) -> List[str]:
        """
        Save multiple entities in a single transaction (async version).
        
        Args:
            entity_name: Name of the entity
            entities: List of entity dictionaries
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            List of saved entity IDs
        """
        ids = []
        
        async with self.async_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Ensure tables exist
            if entities:
                await self._ensure_table_async(entity_name, entities[0])
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
            # Save each entity
            for entity in entities:
                # Prepare entity with timestamps and ID
                prepared_entity = self._prepare_entity(entity_name, entity, user_id, comment)
                
                # Serialize values
                serialized = self._serialize_entity(prepared_entity, meta)
                
                # Get fields and values
                fields = list(serialized.keys())
                values = [serialized[field] for field in fields]
                
                # Generate upsert SQL
                upsert_sql = self._get_upsert_sql(entity_name, fields, is_async=True)
                
                # Execute upsert
                await conn.execute_async(upsert_sql, tuple(values))
                
                # Save to history if enabled
                if entity_name in self._history_enabled:
                    await self._save_history_async(conn, entity_name, serialized, user_id, comment)
                
                ids.append(prepared_entity["id"])
            
        return ids
    
    async def get_entity_history_async(self, entity_name: str, id: str, 
                                     limit: int = 100, offset: int = 0,
                                     deserialize: bool = True) -> List[Dict[str, Any]]:
        """
        Get the history of an entity (async version).
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            limit: Maximum number of history entries to return
            offset: Number of history entries to skip
            deserialize: Whether to deserialize values to Python types
            
        Returns:
            List of entity history entries, ordered by version (newest first)
        """
        if entity_name not in self._history_enabled:
            raise ValueError(f"History not enabled for entity '{entity_name}'")
        
        async with self.async_connection() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Build query
            query = f"SELECT * FROM {entity_name}_history WHERE id = ? ORDER BY version DESC LIMIT {limit} OFFSET {offset}"
            
            # Execute query
            result = await conn.execute_async(query, (id,))
            
            if not result:
                return []
            
            # Get column names
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
            
            # Convert to dictionaries
            history = []
            for row in result:
                entity = dict(zip(columns, row))
                
                # Deserialize if requested
                if deserialize:
                    entity = self._deserialize_entity(entity_name, entity)
                
                history.append(entity)
            
            return history
    
    async def update_entity_fields_async(self, entity_name: str, id: str, fields: Dict[str, Any],
                                       user_id: Optional[str] = None, comment: Optional[str] = None) -> bool:
        """
        Update specific fields of an entity (async version).
        
        Args:
            entity_name: Name of the entity
            id: Entity ID
            fields: Dictionary of field-value pairs to update
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            True if entity was updated, False if not found
        """
        async with self.async_transaction() as conn:
            # Load metadata if needed
            if entity_name not in self._meta_cache:
                try:
                    await self._load_all_metadata_async()
                except Exception as e:
                    logger.warning(f"Failed to load metadata asynchronously: {e}")
            
            # Check if entity exists
            entity_exists = await conn.execute_async(
                f"SELECT COUNT(*) FROM {entity_name} WHERE id = ?",
                (id,)
            )
            
            if not entity_exists or entity_exists[0][0] == 0:
                return False
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
            # Add timestamps and user_id
            update_fields = fields.copy()
            update_fields['updated_at'] = datetime.datetime.utcnow()
            if user_id:
                update_fields['updated_by'] = user_id
            if comment:
                update_fields['update_comment'] = comment
            
            # Serialize values
            serialized = {}
            for field, value in update_fields.items():
                field_type = meta.get(field, self._infer_type(value))
                serialized[field] = self._serialize_value(value, field_type)
            
            # Build SET clause and parameters
            set_clause = ', '.join([f"{field} = ?" for field in serialized.keys()])
            params = list(serialized.values())
            params.append(id)  # For the WHERE clause
            
            # Execute update
            await conn.execute_async(
                f"UPDATE {entity_name} SET {set_clause} WHERE id = ?",
                tuple(params)
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
                    serialized_entity = dict(zip(columns, result[0]))
                    
                    # Save to history
                    await self._save_history_async(conn, entity_name, serialized_entity, user_id, comment)
            
            return True
    
    # endregion ----------------------------

    # ---- region SERIALIZATION HELPER METHODS ----
    
    def to_json(self, entity: Dict[str, Any]) -> str:
        """
        Convert an entity to a JSON string.
        
        Args:
            entity: Entity dictionary
            
        Returns:
            JSON string representation of the entity
        """
        return json.dumps(entity, default=str)
    
    def from_json(self, json_str: str) -> Dict[str, Any]:
        """
        Convert a JSON string to an entity dictionary.
        
        Args:
            json_str: JSON string to convert
            
        Returns:
            Entity dictionary
        """
        return json.loads(json_str)
    
    # endregion -----------------------------

    # ---- region CONVENIENCE METHODS ----
    
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
                    self._save_history_sync(conn, entity_name, serialized, user_id, comment)
            
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
                    await self._save_history_async(conn, entity_name, serialized, user_id, comment)
            
            return True
    
    # ---- region RAW SQL EXECUTION ----
    
    def execute_raw_sql_sync(self, sql: str, params: Optional[Tuple] = None) -> List[Tuple]:
        """
        Execute raw SQL directly (sync version).
        
        This method allows falling back to direct SQL execution when needed
        for complex queries or operations not covered by the entity methods.
        
        Args:
            sql: Raw SQL query
            params: Query parameters
            
        Returns:
            Query result rows
        """
        with self.sync_connection() as conn:
            return conn.execute_sync(sql, params)
    
    async def execute_raw_sql_async(self, sql: str, params: Optional[Tuple] = None) -> List[Tuple]:
        """
        Execute raw SQL directly (async version).
        
        This method allows falling back to direct SQL execution when needed
        for complex queries or operations not covered by the entity methods.
        
        Args:
            sql: Raw SQL query
            params: Query parameters
            
        Returns:
            Query result rows
        """
        async with self.async_connection() as conn:
            return await conn.execute_async(sql, params)
    
    # endregion -----------------------------

    # ---- region DATABASE INTROSPECTION ----
    
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
    
    # endregion ------------------------------

    # ---- region QUERY BUILDER METHODS ----

    def query_builder_sync(self, entity_name: str) -> 'EntityQueryBuilder':
        """
        Create a query builder for fluent querying.
        
        The query builder provides a more fluent interface for constructing
        queries with conditions, ordering, and pagination.
        
        Args:
            entity_name: Name of the entity to query
            
        Returns:
            EntityQueryBuilder instance for chaining query operations
        """
        return EntityQueryBuilder(self, entity_name, is_async=False)
    
    def query_builder_async(self, entity_name: str) -> 'AsyncEntityQueryBuilder':
        """
        Create an async query builder for fluent querying.
        
        The async query builder provides a more fluent interface for constructing
        queries with conditions, ordering, and pagination, with async execution.
        
        Args:
            entity_name: Name of the entity to query
            
        Returns:
            AsyncEntityQueryBuilder instance for chaining query operations
        """
        return AsyncEntityQueryBuilder(self, entity_name)
    
    # endregion ------------------------------

    # ---- region VERSIONING ----
    
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
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
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
            self._save_history_sync(conn, entity_name, main_entity, user_id, main_entity['update_comment'])
            
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
            
            # Get current metadata
            meta = self._meta_cache.get(entity_name, {})
            
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
            await self._save_history_async(conn, entity_name, main_entity, user_id, main_entity['update_comment'])
            
            return True
    
    # endregion ------------------------------

# ---- Query Builder Classes ----

class EntityQueryBuilder:
    """
    Fluent query builder for synchronous entity operations.
    
    This class provides a chainable API for building and executing
    entity queries with conditions, ordering, and pagination.
    
    Example:
        db.query_builder_sync("users")
          .where("age", ">", 18)
          .where("status", "active")
          .order_by("created_at", "DESC")
          .limit(10)
          .execute()
    """
    
    def __init__(self, db: EntityManager, entity_name: str, is_async: bool = False):
        self.db = db
        self.entity_name = entity_name
        self.conditions = []
        self.order_clauses = []
        self.limit_value = 100
        self.offset_value = 0
        self.include_deleted_value = False
        self.is_async = is_async
    
    def where(self, field: str, operator_or_value, value=None):
        """
        Add a WHERE condition to the query.
        
        Can be called in two ways:
        - where("field", "value") -> field = value
        - where("field", "operator", "value") -> field operator value
        
        Args:
            field: Field name
            operator_or_value: Operator (=, >, <, etc.) or value
            value: Value if operator is provided, None otherwise
            
        Returns:
            Self for chaining
        """
        if value is None:
            # Simple equality: where("field", "value")
            self.conditions.append({"field": field, "op": "=", "value": operator_or_value})
        else:
            # Custom operator: where("field", "operator", "value")
            self.conditions.append({"field": field, "op": operator_or_value, "value": value})
        return self
    
    def order_by(self, field: str, direction: str = "ASC"):
        """
        Add an ORDER BY clause to the query.
        
        Args:
            field: Field name to order by
            direction: Sort direction ("ASC" or "DESC")
            
        Returns:
            Self for chaining
        """
        self.order_clauses.append({"field": field, "direction": direction})
        return self
    
    def limit(self, limit: int):
        """
        Set the LIMIT value for the query.
        
        Args:
            limit: Maximum number of rows to return
            
        Returns:
            Self for chaining
        """
        self.limit_value = limit
        return self
    
    def offset(self, offset: int):
        """
        Set the OFFSET value for the query.
        
        Args:
            offset: Number of rows to skip
            
        Returns:
            Self for chaining
        """
        self.offset_value = offset
        return self
    
    def include_deleted(self, include: bool = True):
        """
        Include soft-deleted entities in the query results.
        
        Args:
            include: Whether to include soft-deleted entities
            
        Returns:
            Self for chaining
        """
        self.include_deleted_value = include
        return self
    
    def build_query(self):
        """
        Build the SQL query and parameters.
        
        Returns:
            Tuple of (sql, params)
        """
        # Start with base query
        sql = f"SELECT * FROM {self.entity_name}"
        params = []
        
        # Add WHERE conditions
        where_clauses = []
        for condition in self.conditions:
            field = condition["field"]
            op = condition["op"]
            value = condition["value"]
            
            # Get field type and serialize value
            field_type = self.db._meta_cache.get(self.entity_name, {}).get(field, self.db._infer_type(value))
            serialized_value = self.db._serialize_value(value, field_type)
            
            where_clauses.append(f"{field} {op} ?")
            params.append(serialized_value)
        
        # Add deleted_at check if not including deleted
        if not self.include_deleted_value:
            where_clauses.append("deleted_at IS NULL")
        
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        
        # Add ORDER BY
        if self.order_clauses:
            order_parts = []
            for order in self.order_clauses:
                order_parts.append(f"{order['field']} {order['direction']}")
            sql += " ORDER BY " + ", ".join(order_parts)
        
        # Add LIMIT and OFFSET
        sql += f" LIMIT {self.limit_value} OFFSET {self.offset_value}"
        
        return sql, params
    
    def execute(self) -> List[Dict[str, Any]]:
        """
        Execute the query and return the results.
        
        Returns:
            List of entity dictionaries
        """
        sql, params = self.build_query()
        
        with self.db.sync_connection() as conn:
            result = conn.execute_sync(sql, tuple(params))
            
            if not result:
                return []
            
            # Get column names
            columns = []
            if self.db._db_type == 'sqlite':
                col_info = conn.execute_sync(f"PRAGMA table_info({self.entity_name})")
                columns = [col[1] for col in col_info]
            else:
                col_info = conn.execute_sync(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (self.entity_name,)
                )
                columns = [col[0] for col in col_info]
            
            # Convert to dictionaries
            entities = []
            for row in result:
                entity = dict(zip(columns, row))
                
                # Deserialize values
                deserialized = self.db._deserialize_entity(self.entity_name, entity)
                entities.append(deserialized)
            
            return entities
    
    def count(self) -> int:
        """
        Count the number of entities matching the query conditions.
        
        Returns:
            Count of matching entities
        """
        # Start with base query but use COUNT(*)
        sql = f"SELECT COUNT(*) FROM {self.entity_name}"
        params = []
        
        # Add WHERE conditions
        where_clauses = []
        for condition in self.conditions:
            field = condition["field"]
            op = condition["op"]
            value = condition["value"]
            
            # Get field type and serialize value
            field_type = self.db._meta_cache.get(self.entity_name, {}).get(field, self.db._infer_type(value))
            serialized_value = self.db._serialize_value(value, field_type)
            
            where_clauses.append(f"{field} {op} ?")
            params.append(serialized_value)
        
        # Add deleted_at check if not including deleted
        if not self.include_deleted_value:
            where_clauses.append("deleted_at IS NULL")
        
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        
        with self.db.sync_connection() as conn:
            result = conn.execute_sync(sql, tuple(params))
            
            if not result:
                return 0
            
            return result[0][0]
    
    def first(self) -> Optional[Dict[str, Any]]:
        """
        Get the first entity matching the query conditions.
        
        Returns:
            Entity dictionary or None if not found
        """
        # Limit to 1 result
        self.limit_value = 1
        result = self.execute()
        
        if not result:
            return None
        
        return result[0]


class AsyncEntityQueryBuilder:
    """
    Fluent query builder for asynchronous entity operations.
    
    This class provides a chainable API for building and executing
    entity queries with conditions, ordering, and pagination.
    
    Example:
        await db.query_builder_async("users")
               .where("age", ">", 18)
               .where("status", "active")
               .order_by("created_at", "DESC")
               .limit(10)
               .execute()
    """
    
    def __init__(self, db: EntityManager, entity_name: str):
        self.db = db
        self.entity_name = entity_name
        self.conditions = []
        self.order_clauses = []
        self.limit_value = 100
        self.offset_value = 0
        self.include_deleted_value = False
    
    def where(self, field: str, operator_or_value, value=None):
        """
        Add a WHERE condition to the query.
        
        Can be called in two ways:
        - where("field", "value") -> field = value
        - where("field", "operator", "value") -> field operator value
        
        Args:
            field: Field name
            operator_or_value: Operator (=, >, <, etc.) or value
            value: Value if operator is provided, None otherwise
            
        Returns:
            Self for chaining
        """
        if value is None:
            # Simple equality: where("field", "value")
            self.conditions.append({"field": field, "op": "=", "value": operator_or_value})
        else:
            # Custom operator: where("field", "operator", "value")
            self.conditions.append({"field": field, "op": operator_or_value, "value": value})
        return self
    
    def order_by(self, field: str, direction: str = "ASC"):
        """
        Add an ORDER BY clause to the query.
        
        Args:
            field: Field name to order by
            direction: Sort direction ("ASC" or "DESC")
            
        Returns:
            Self for chaining
        """
        self.order_clauses.append({"field": field, "direction": direction})
        return self
    
    def limit(self, limit: int):
        """
        Set the LIMIT value for the query.
        
        Args:
            limit: Maximum number of rows to return
            
        Returns:
            Self for chaining
        """
        self.limit_value = limit
        return self
    
    def offset(self, offset: int):
        """
        Set the OFFSET value for the query.
        
        Args:
            offset: Number of rows to skip
            
        Returns:
            Self for chaining
        """
        self.offset_value = offset
        return self
    
    def include_deleted(self, include: bool = True):
        """
        Include soft-deleted entities in the query results.
        
        Args:
            include: Whether to include soft-deleted entities
            
        Returns:
            Self for chaining
        """
        self.include_deleted_value = include
        return self
    
    def build_query(self):
        """
        Build the SQL query and parameters.
        
        Returns:
            Tuple of (sql, params)
        """
        # Start with base query
        sql = f"SELECT * FROM {self.entity_name}"
        params = []
        
        # Add WHERE conditions
        where_clauses = []
        for condition in self.conditions:
            field = condition["field"]
            op = condition["op"]
            value = condition["value"]
            
            # Get field type and serialize value
            field_type = self.db._meta_cache.get(self.entity_name, {}).get(field, self.db._infer_type(value))
            serialized_value = self.db._serialize_value(value, field_type)
            
            where_clauses.append(f"{field} {op} ?")
            params.append(serialized_value)
        
        # Add deleted_at check if not including deleted
        if not self.include_deleted_value:
            where_clauses.append("deleted_at IS NULL")
        
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        
        # Add ORDER BY
        if self.order_clauses:
            order_parts = []
            for order in self.order_clauses:
                order_parts.append(f"{order['field']} {order['direction']}")
            sql += " ORDER BY " + ", ".join(order_parts)
        
        # Add LIMIT and OFFSET
        sql += f" LIMIT {self.limit_value} OFFSET {self.offset_value}"
        
        return sql, params
    
    async def execute(self) -> List[Dict[str, Any]]:
        """
        Execute the query and return the results.
        
        Returns:
            List of entity dictionaries
        """
        sql, params = self.build_query()
        
        async with self.db.async_connection() as conn:
            result = await conn.execute_async(sql, tuple(params))
            
            if not result:
                return []
            
            # Get column names
            columns = []
            if self.db._db_type == 'sqlite':
                col_info = await conn.execute_async(f"PRAGMA table_info({self.entity_name})")
                columns = [col[1] for col in col_info]
            else:
                col_info = await conn.execute_async(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (self.entity_name,)
                )
                columns = [col[0] for col in col_info]
            
            # Convert to dictionaries
            entities = []
            for row in result:
                entity = dict(zip(columns, row))
                
                # Deserialize values
                deserialized = self.db._deserialize_entity(self.entity_name, entity)
                entities.append(deserialized)
            
            return entities
    
    async def count(self) -> int:
        """
        Count the number of entities matching the query conditions.
        
        Returns:
            Count of matching entities
        """
        # Start with base query but use COUNT(*)
        sql = f"SELECT COUNT(*) FROM {self.entity_name}"
        params = []
        
        # Add WHERE conditions
        where_clauses = []
        for condition in self.conditions:
            field = condition["field"]
            op = condition["op"]
            value = condition["value"]
            
            # Get field type and serialize value
            field_type = self.db._meta_cache.get(self.entity_name, {}).get(field, self.db._infer_type(value))
            serialized_value = self.db._serialize_value(value, field_type)
            
            where_clauses.append(f"{field} {op} ?")
            params.append(serialized_value)
        
        # Add deleted_at check if not including deleted
        if not self.include_deleted_value:
            where_clauses.append("deleted_at IS NULL")
        
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        
        async with self.db.async_connection() as conn:
            result = await conn.execute_async(sql, tuple(params))
            
            if not result:
                return 0
            
            return result[0][0]
    
    async def first(self) -> Optional[Dict[str, Any]]:
        """
        Get the first entity matching the query conditions.
        
        Returns:
            Entity dictionary or None if not found
        """
        # Limit to 1 result
        self.limit_value = 1
        result = await self.execute()
        
        if not result:
            return None
        
        return result[0]