import os
import uuid
import asyncio
import contextlib
import functools
from typing import Callable, Awaitable, Optional, Tuple, List, Any, Dict, final, Union
import nest_asyncio
import re
from abc import ABC, abstractmethod
from ..errors import TrackError
from .. import log as logger
from .. import utils

def _run_sync(coro):
    """
    Safely run a coroutine from a synchronous context.
    
    This handles both cases: when called from within an event loop
    and when called from outside an event loop.
    """
    try:
        loop = asyncio.get_running_loop()
        # Patch the loop so we can nest safely
        nest_asyncio.apply(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No running loop
        return asyncio.run(coro)
    
class Database(ABC):
    """
    Abstract base class for database implementations.
    Provides common functionality for database operations with
    both synchronous and asynchronous interfaces.
    """
    
    def __init__(self, database: str, host: str=None, port: int=None, 
                 user: str=None, password: str=None, alias: str = None, 
                 env: str = 'prod'):
        """
        Initialize the database connection.
        
        Args:
            database: Database name
            host: Database server hostname (not used for SQLite)
            port: Database server port (not used for SQLite)
            user: Username for authentication (not used for SQLite)
            password: Password for authentication (not used for SQLite)
            alias: Friendly name for this database connection
            env: Environment name (prod, dev, test)
        """
        self.__host = host
        self.__port = port
        self.__database = database
        self.__user = user
        self.__password = password
        self.__env = env
        self.__alias = alias or database or f'{self.type()}_database'
        
        # Metadata cache
        self.__meta_cache = {}
        self.__keys_cache = {}
        self.__types_cache = {}
        self.__meta_versions = {}

        # Buffered transaction support
        self._tx_active = False
        self._tx_started = False
        self._tx_buffer = []
        self._tx_buffer_async = []
        
        
    def config(self):
        """Return the database configuration dict"""
        return {
            'host': self.__host,
            'port': self.__port,
            'database': self.__database,
            'user': self.__user,
            'password': self.__password
        }
    
    def database(self):
        """Return the database name"""
        return self.__database
    
    def alias(self):
        """Return the database alias"""
        return self.__alias
    
    def host(self):
        """Return the database host"""
        return self.__host
    
    def port(self):
        """Return the database port"""
        return self.__port
    
    def env(self):
        """Return the database environment"""
        return self.__env
    
    @abstractmethod
    def type(self) -> str:
        """Return the database type (sqlite, mysql, postgres, etc.)"""
        pass

    @abstractmethod
    def placeholder(self, is_async: bool=True) -> str:
        """Return the placeholder string for parameterized queries"""
        pass
       
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the database connection is active"""
        pass
  
    @abstractmethod
    def execute_sql(self, sql: str, parameters=()) -> list:
        """Execute a SQL query with parameters"""
        pass
    
    @abstractmethod
    def executemany_sql(self, sql: str, parameters_list: list) -> None:
        """Execute a SQL query multiple times with different parameters"""
        pass

    @abstractmethod
    async def execute_sql_async(self, sql: str, parameters=()) -> list:
        """Execute a SQL query with parameters async"""
        pass
    
    @abstractmethod
    async def executemany_sql_async(self, sql: str, parameters_list: list) -> None:
        """Execute a SQL query multiple times with different parameters async"""
        pass
   
    @abstractmethod
    def _close(self) -> None:
        """Close the database connection"""
        pass
    
    @abstractmethod
    def clear_all(self) -> None:
        """Clear all data in the database"""
        pass

    @abstractmethod
    async def _close_async(self) -> None:
        """Close the database connection async"""
        pass
    
    @abstractmethod
    async def clear_all_async(self) -> None:
        """Clear all data in the database async"""
        pass


    @abstractmethod
    def begin_transaction_real(self):
        pass

    @abstractmethod
    def rollback_transaction_real(self):
        pass

    @abstractmethod
    def commit_transaction_real(self):
        pass

    def begin_transaction(self):
        if self._tx_active:
            raise RuntimeError("Nested transactions are not supported.")
        self._tx_active = True
        self._tx_started = False
        self._tx_buffer = []

    def commit_transaction(self):
        if not self._tx_active:
            return
        if not self._tx_started:
            self.begin_transaction_real()
            self._tx_started = True
        for entity_name, entity in self._tx_buffer:
            self.save_entities(entity_name, [entity], auto_commit=False)
        self.commit_transaction_real()
        self._tx_buffer.clear()
        self._tx_active = False
        self._tx_started = False

    def rollback_transaction(self):
        if not self._tx_active:
            return
        if self._tx_started:
            self.rollback_transaction_real()
        self._tx_buffer.clear()
        self._tx_active = False
        self._tx_started = False


 



    async def begin_transaction_async(self) -> None:
        if self._tx_active:
            raise RuntimeError("Nested transactions are not supported.")
        self._tx_active = True
        self._tx_started = False
        self._tx_buffer_async = []

    @abstractmethod
    async def begin_transaction_real_async(self):
        pass
    
    @abstractmethod
    async def commit_transaction_real_async(self):
        pass

    async def commit_transaction_async(self) -> None:
        if not self._tx_active:
            return
        if not self._tx_started:
            await self.begin_transaction_real_async()
            self._tx_started = True
        for entity_name, entity in self._tx_buffer_async:
            await self.save_entities_async(entity_name, [entity], auto_commit=False)
        await self.commit_transaction_real_async()
        self._tx_buffer_async.clear()
        self._tx_active = False
        self._tx_started = False
    
    async def rollback_transaction_async(self) -> None:
        if not self._tx_active:
            return
        if self._tx_started:
            await self.rollback_transaction_real_async()
        self._tx_buffer_async.clear()
        self._tx_active = False
        self._tx_started = False

    @abstractmethod
    async def rollback_transaction_real_async(self):
        pass
    



    # region --- CONTEXT MANAGERS ---
    @contextlib.contextmanager
    def transaction(self):
        """
        Context manager for database transactions.
        
        Usage:
            with db.transaction():
                db.execute_sql("INSERT INTO users VALUES ('user1', 'name1')")
                db.execute_sql("INSERT INTO profiles VALUES ('user1', 'bio')")
        
        If any operation within the block fails, the transaction is rolled back.
        Otherwise, it is committed when exiting the block.
        """
        if self._tx_active:
            raise RuntimeError("Nested transactions are not supported.")
        self.begin_transaction()
        try:
            yield self
            self.commit_transaction()
        except Exception:
            self.rollback_transaction()
            raise  

    def async_transaction(self, func):
        """
        Decorator for async functions to run within a transaction.
        
        Usage:
            @db.async_transaction
            async def create_user(user_data):
                await db.execute_sql_async(...)
                await db.execute_sql_async(...)
        
        If the function raises an exception, the transaction is rolled back.
        Otherwise, it is committed when the function completes.
        """
        @contextlib.asynccontextmanager
        async def async_transaction_context():
            if self._tx_active:
                raise RuntimeError("Nested transactions are not supported.")
            await self.begin_transaction_async()
            try:
                yield self
                await self.commit_transaction_async()
            except Exception:
                await self.rollback_transaction_async()
                raise
                            
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with async_transaction_context():
                return await func(*args, **kwargs)
        return wrapper
    # endregion -------------------
    
    # region --- HELPERS ----------
    @staticmethod
    def _sanitize_identifier(name: str) -> str:
        """
        Safely sanitize an SQL identifier to prevent SQL injection.
        
        Args:
            name: The identifier to sanitize
            
        Returns:
            The sanitized identifier
            
        Raises:
            ValueError: If the identifier contains unsafe characters
        """
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            raise ValueError(f"Unsafe SQL identifier: {name}")
        return name

    def _placeholders(self, count: int, is_async: bool=True) -> str:
        """
        Generate SQL placeholders for parameterized queries.
        
        Args:
            count: Number of placeholders to generate
            is_async: Whether this is for async queries
            
        Returns:
            String of placeholders separated by commas
        """
        if self.type() == "postgres":
            if is_async:
                return ", ".join(f"${i+1}" for i in range(count))
            else:
                return ", ".join([self.placeholder(False)] * count)
        else:
            return ", ".join([self.placeholder(is_async)] * count)
    
    def _get_keys_and_types(self, entity_name: str) -> Tuple[List[str], List[str]]:
        """
        Get the keys and types for an entity from metadata.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Tuple of (keys, types)
        """
        meta = self._get_entity_metadata(entity_name)
        return list(meta.keys()), list(meta.values())

    async def _get_keys_and_types_async(self, entity_name: str) -> Tuple[List[str], List[str]]:
        """
        Get the keys and types for an entity from metadata (async version).
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Tuple of (keys, types)
        """
        meta = await self._get_entity_metadata_async(entity_name)
        return list(meta.keys()), list(meta.values())

    def _prepare_entity_data(self, entity: dict) -> dict:
        """
        Prepare entity data before saving.
        Can be overridden by subclasses to add timestamps, etc.
        
        Args:
            entity: The entity data
            
        Returns:
            Prepared entity data
        """
        return entity

    async def _run_metadata_flow(self, entity_name: str, executor: Callable[..., Awaitable], is_async: bool = True):
        """
        Run the metadata retrieval flow.
        
        Args:
            entity_name: Name of the entity
            executor: Function to execute SQL
            is_async: Whether this is async mode
            
        Returns:
            Entity metadata
            
        Raises:
            TrackError: On database errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            if is_async:               
                version_row = await executor(
                    f"SELECT version FROM _meta_version WHERE entity_name = {self.placeholder(is_async)}",
                    (entity_name,)
                )
            else:
                version_row = executor(
                    f"SELECT version FROM _meta_version WHERE entity_name = {self.placeholder(is_async)}", 
                    (entity_name,)
                )
            version = version_row[0][0] if version_row else 0

            # Cache hit - return immediately if version matches
            if self.__meta_versions.get(entity_name) == version:
                return self.__meta_cache[entity_name]

            # Get fresh metadata
            query = f"SELECT name, type FROM {entity_name}_meta"
            if is_async:
                if self.type() == 'postgres':
                    query += f" -- {uuid.uuid4()}"
                rows = await executor(query)
            else:
                rows = executor(query)
                
            # Update cache
            meta = {name: typ for name, typ in rows}
            self.__meta_cache[entity_name] = meta
            self.__keys_cache[entity_name] = list(meta.keys())
            self.__types_cache[entity_name] = list(meta.values())
            self.__meta_versions[entity_name] = version
            return meta
        except Exception as e:
            raise TrackError(e)

    def _get_entity_metadata(self, entity_name: str):
        """
        Get entity metadata synchronously.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Entity metadata dictionary
        """
        return _run_sync(self._run_metadata_flow(entity_name, self.execute_sql, is_async=False))

    async def _get_entity_metadata_async(self, entity_name: str):
        """
        Get entity metadata asynchronously.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Entity metadata dictionary
        """
        return await self._run_metadata_flow(entity_name, self.execute_sql_async, is_async=True)

    async def _run_version_bump(self, entity_name: str, executor: Callable[..., Awaitable], is_async: bool = True):
        """
        Increment the metadata version for an entity.
        
        Args:
            entity_name: Name of the entity
            executor: Function to execute SQL
            is_async: Whether this is async mode
            
        Raises:
            TrackError: On database errors
        """
        pl = self.placeholder(is_async)
        
        # Use different SQL syntax based on database type
        if self.type() == 'mysql':
            sql = f"""
                INSERT INTO _meta_version (entity_name, version)
                VALUES ({pl}, 1)
                AS new ON DUPLICATE KEY UPDATE version = new.version + 1
                """
        elif self.type() == 'postgres':
            # For PostgreSQL, qualify the column reference to avoid ambiguity
            sql = f"""
                INSERT INTO _meta_version (entity_name, version)
                VALUES ({pl}, 1)
                ON CONFLICT(entity_name) DO UPDATE SET version = _meta_version.version + 1
                -- {uuid.uuid4()}
                """
        else:  # sqlite
            # For SQLite, use REPLACE
            sql = f"""
                INSERT OR REPLACE INTO _meta_version (entity_name, version)
                VALUES ({pl}, COALESCE((SELECT version FROM _meta_version WHERE entity_name = '{entity_name}') + 1, 1))
                """
            
        try:
            if is_async:
                await executor(sql, (entity_name,))
            else:
                executor(sql, (entity_name,))
        except Exception as e:
            raise TrackError(e)

    def _bump_entity_version(self, entity_name: str) -> None:
        """
        Increment entity version synchronously.
        
        Args:
            entity_name: Name of the entity
        """
        _run_sync(self._run_version_bump(entity_name, self.execute_sql, is_async=False))

    async def _bump_entity_version_async(self, entity_name: str) -> None:
        """
        Increment entity version asynchronously.
        
        Args:
            entity_name: Name of the entity
        """
        await self._run_version_bump(entity_name, self.execute_sql_async, is_async=True)

    async def _run_ensure_tables(self, entity_name: str, executor: Callable[..., Awaitable], is_async: bool = True):
        """
        Ensure required tables exist.
        
        Args:
            entity_name: Name of the entity
            executor: Function to execute SQL
            is_async: Whether this is async mode
            
        Raises:
            TrackError: On database errors
        """
        if is_async:
            logger.debug("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
        try:            
            entity_name = self._sanitize_identifier(entity_name)
            
            # Create _meta_version table if needed
            meta_version_sql = """
                CREATE TABLE IF NOT EXISTS _meta_version (
                    entity_name VARCHAR(255) PRIMARY KEY,
                    version INTEGER
                )"""
            
            # Add UUID comment for PostgreSQL if async
            if is_async and self.type() == 'postgres':
                meta_version_sql += f" -- {uuid.uuid4()}"
                
            # Execute metadata version table creation
            if is_async:
                await executor(meta_version_sql)
            else:
                executor(meta_version_sql)
                
            # Create entity metadata table
            meta_table_sql = f'CREATE TABLE IF NOT EXISTS {entity_name}_meta (name VARCHAR(255) {"PRIMARY KEY" if self.type() == "sqlite" else ",PRIMARY KEY (name)"}, type VARCHAR(255))'
            if is_async and self.type() == 'postgres':
                meta_table_sql += f' -- {uuid.uuid4()}'
                
            # Execute entity metadata table creation
            if is_async:
                await executor(meta_table_sql)
            else:
                executor(meta_table_sql)
            
            # Create entity table
            create_sql = f"CREATE TABLE IF NOT EXISTS {entity_name} (id VARCHAR(255) {'PRIMARY KEY' if self.type() == 'sqlite' else ',PRIMARY KEY (id)'})"
            if is_async and self.type() == 'postgres':
                create_sql += f' -- {uuid.uuid4()}'
                
            # Execute entity table creation
            if is_async:
                await executor(create_sql)
            else:
                executor(create_sql)
        except Exception as e:
            raise TrackError(e)

    def _ensure_tables_exist(self, entity_name: str) -> None:
        """
        Ensure required tables exist synchronously.
        
        Args:
            entity_name: Name of the entity
        """
        _run_sync(self._run_ensure_tables(entity_name, self.execute_sql, is_async=False))

    async def _ensure_tables_exist_async(self, entity_name: str) -> None:
        """
        Ensure required tables exist asynchronously.
        
        Args:
            entity_name: Name of the entity
        """
        await self._run_ensure_tables(entity_name, self.execute_sql_async, is_async=True)

    async def _run_deserialize(self, entity_name: str, values, keys, types, cast, fetch_keys_types):
        """
        Deserialize database values into entity dictionary.
        
        Args:
            entity_name: Name of the entity
            values: Values from database
            keys: Entity field keys
            types: Entity field types
            cast: Whether to cast values to their types
            fetch_keys_types: Function to get keys and types
            
        Returns:
            Entity dictionary
        """
        if keys is None or types is None:
            keys, types = await fetch_keys_types(entity_name) if asyncio.iscoroutinefunction(fetch_keys_types) else fetch_keys_types(entity_name)
        return {
            key: utils.safe_deserialize(value, target_type) if cast else value
            for key, value, target_type in zip(keys, values, types)
        }

    def _db_values_to_entity(self, entity_name, values, keys=None, types=None, cast=False):
        """
        Convert database values to entity dictionary synchronously.
        
        Args:
            entity_name: Name of the entity
            values: Values from database
            keys: Entity field keys
            types: Entity field types
            cast: Whether to cast values to their types
            
        Returns:
            Entity dictionary
            
        Raises:
            TrackError: On conversion errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            return _run_sync(self._run_deserialize(entity_name, values, keys, types, cast, self._get_keys_and_types))
        except Exception as e:
            raise TrackError(e)

    async def _db_values_to_entity_async(self, entity_name, values, keys=None, types=None, cast=False):
        """
        Convert database values to entity dictionary asynchronously.
        
        Args:
            entity_name: Name of the entity
            values: Values from database
            keys: Entity field keys
            types: Entity field types
            cast: Whether to cast values to their types
            
        Returns:
            Entity dictionary
            
        Raises:
            TrackError: On conversion errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            return await self._run_deserialize(entity_name, values, keys, types, cast, self._get_keys_and_types_async)
        except Exception as e:
            raise TrackError(e)

    async def _run_metadata_schema_check(self, entity_name: str, keys, sample_values, get_metadata, executor, bump_version, is_async: bool):
        """
        Check and update metadata schema for entity.
        
        Args:
            entity_name: Name of the entity
            keys: Entity field keys
            sample_values: Sample values for type inference
            get_metadata: Function to get metadata
            executor: Function to execute SQL
            bump_version: Function to bump version
            is_async: Whether this is async mode
            
        Raises:
            TrackError: On database errors
        """
        try:            
            meta = await get_metadata(entity_name) if is_async else get_metadata(entity_name)

            changes_made = False  # Track if we made any schema changes

            for key in keys:
                sample_value = sample_values.get(key)
                if key not in meta and sample_value is not None:
                    typ = str(type(sample_value))

                    if self.type() == 'sqlite':
                        insert_sql = f"INSERT OR REPLACE INTO {entity_name}_meta VALUES ({self._placeholders(2, is_async)})"
                    elif self.type() == 'postgres':
                        insert_sql = f"INSERT INTO {entity_name}_meta VALUES ({self._placeholders(2, is_async)}) ON CONFLICT(name) DO UPDATE SET type=EXCLUDED.type -- {uuid.uuid4()}"
                    else:
                        insert_sql = f"INSERT INTO {entity_name}_meta VALUES ({self._placeholders(2, is_async)}) AS new ON DUPLICATE KEY UPDATE type=new.type"

                    if is_async:
                        await executor(insert_sql, (key, typ))
                        if key != 'id':
                            alter_sql = f"ALTER TABLE {entity_name} ADD {key} TEXT"
                            if self.type() == 'postgres':
                                alter_sql += f" -- {uuid.uuid4()}"
                            logger.debug(f"[DDL] Running ALTER TABLE: {alter_sql}")
                            await executor(alter_sql)
                    else:
                        executor(insert_sql, (key, typ))
                        if key != 'id':
                            executor(f"ALTER TABLE {entity_name} ADD {key} TEXT")

                    changes_made = True

            if changes_made:
                await bump_version(entity_name) if is_async else bump_version(entity_name)
                # Only reload metadata if there were changes
                meta = await get_metadata(entity_name) if is_async else get_metadata(entity_name)

        except Exception as e:
            raise TrackError(e)
    
    def _ensure_metadata_and_schema(self, entity_name, keys, sample_values):
        """
        Ensure metadata and schema match entity synchronously.
        
        Args:
            entity_name: Name of the entity
            keys: Entity field keys
            sample_values: Sample values for type inference
        """
        _run_sync(self._run_metadata_schema_check(
            entity_name, keys, sample_values,
            self._get_entity_metadata, self.execute_sql, self._bump_entity_version,
            is_async=False
        ))

    async def _ensure_metadata_and_schema_async(self, entity_name, keys, sample_values):
        """
        Ensure metadata and schema match entity asynchronously.
        
        Args:
            entity_name: Name of the entity
            keys: Entity field keys
            sample_values: Sample values for type inference
        """
        await self._run_metadata_schema_check(
            entity_name, keys, sample_values,
            self._get_entity_metadata_async, self.execute_sql_async, self._bump_entity_version_async,
            is_async=True
        )

    async def _run_fetch(self, entity_name, filter_clause, single, cast, ensure_tables, get_keys_types, fetch_rows, convert_row, is_async, parameters=()):
        """
        Fetch entities from database.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause
            single: Whether to return single entity
            cast: Whether to cast values to their types
            ensure_tables: Function to ensure tables exist
            get_keys_types: Function to get keys and types
            fetch_rows: Function to fetch rows
            convert_row: Function to convert row to entity
            is_async: Whether this is async mode
            parameters: Query parameters
            
        Returns:
            Entity or list of entities
            
        Raises:
            TrackError: On database errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            await ensure_tables(entity_name) if is_async else ensure_tables(entity_name)
            keys, types = await get_keys_types(entity_name) if is_async else get_keys_types(entity_name)
            where_clause = f"WHERE {filter_clause}" if filter_clause else ''
            sql = f"SELECT {','.join(keys)} FROM {entity_name} {where_clause}"
            if is_async and self.type() == 'postgres':
                sql += f" -- {uuid.uuid4()}"
                
            # Handle query parameters
            if parameters:
                rows = await fetch_rows(sql, parameters) if is_async else fetch_rows(sql, parameters)
            else:
                rows = await fetch_rows(sql) if is_async else fetch_rows(sql)
                
            # Process results
            results = []
            for row in rows:
                entity = await convert_row(entity_name, row, keys, types, cast) if is_async else convert_row(entity_name, row, keys, types, cast)
                results.append(entity)
                
            # Return appropriate result
            if single:
                return results[0] if results else None
            return results
        except Exception as e:
            raise TrackError(e)

    def _fetch_data(self, entity_name, filter_clause=None, single=False, cast=False, parameters=()):
        """
        Fetch entities from database synchronously.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause
            single: Whether to return single entity
            cast: Whether to cast values to their types
            parameters: Query parameters
            
        Returns:
            Entity or list of entities
        """
        return _run_sync(self._run_fetch(
            entity_name, filter_clause, single, cast,
            self._ensure_tables_exist, self._get_keys_and_types,
            lambda sql, params=parameters: self.execute_sql(sql, params) if params else self.execute_sql(sql), 
            self._db_values_to_entity, is_async=False, parameters=parameters
        ))

    async def _fetch_data_async(self, entity_name, filter_clause=None, single=False, cast=False, parameters=()):
        """
        Fetch entities from database asynchronously.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause
            single: Whether to return single entity
            cast: Whether to cast values to their types
            parameters: Query parameters
            
        Returns:
            Entity or list of entities
        """
        return await self._run_fetch(
            entity_name, filter_clause, single, cast,
            self._ensure_tables_exist_async, self._get_keys_and_types_async,
            lambda sql, params=parameters: self.execute_sql_async(sql, params) if params else self.execute_sql_async(sql), 
            self._db_values_to_entity_async, is_async=True, parameters=parameters
        )

    async def _run_save_entities(self, entity_name, entities, chunk_size, ensure_tables, ensure_schema, executor, executemany, is_async):
        """
        Save entities to database.
        
        Args:
            entity_name: Name of the entity
            entities: List of entities to save
            chunk_size: Size of chunks for batch operations
            ensure_tables: Function to ensure tables exist
            ensure_schema: Function to ensure schema
            executor: Function to execute single SQL
            executemany: Function to execute batch SQL
            is_async: Whether this is async mode
            
        Raises:
            TrackError: On database errors
        """
        try:
            if not entities:
                return
                
            entity_name = self._sanitize_identifier(entity_name)

            await ensure_tables(entity_name) if is_async else ensure_tables(entity_name)

            entities = [self._prepare_entity_data(e) for e in entities]
            keys = sorted(set(k for e in entities for k in e.keys()))
            sample_values = {k: e.get(k) for e in entities for k in keys if e.get(k) is not None}

            await ensure_schema(entity_name, keys, sample_values) if is_async else ensure_schema(entity_name, keys, sample_values)

            or_replace = 'OR REPLACE' if self.type() == 'sqlite' else ''
            insert_sql = f"INSERT {or_replace} INTO {entity_name} ({','.join(keys)}) VALUES({self._placeholders(len(keys), is_async)})"
            
            # Add appropriate upsert clause for database type
            if self.type() == 'sqlite':
                # SQLite uses OR REPLACE which is already in the insert_sql
                pass
            elif self.type() == 'postgres':
                # PostgreSQL style ON CONFLICT
                # Only update non-created fields
                update_keys = [key for key in keys if key != 'created']
                if update_keys:  # Only add the clause if we have keys to update
                    duplicates = [f'{key}=EXCLUDED.{key}' for key in update_keys]
                    insert_sql += f" ON CONFLICT(id) DO UPDATE SET {', '.join(duplicates)}"
                    if is_async:
                        insert_sql += f" -- {uuid.uuid4()}"
            else:
                # MySQL style ON DUPLICATE KEY UPDATE
                # Only update non-created fields
                update_keys = [key for key in keys if key != 'created']
                if update_keys:  # Only add the clause if we have keys to update
                    alias = "new"
                    duplicates = [f'{key}={alias}.{key}' for key in update_keys]
                    insert_sql += f" AS {alias} ON DUPLICATE KEY UPDATE {', '.join(duplicates)}"

            values_list = [tuple(str(e.get(k, '')) for k in keys) for e in entities]

            for i in range(0, len(values_list), chunk_size):
                chunk = values_list[i:i + chunk_size]
                try:
                    await executemany(insert_sql, chunk) if is_async else executemany(insert_sql, chunk)
                except (NotImplementedError, AttributeError):
                    for row in chunk:        
                        await executor(insert_sql, row) if is_async else executor(insert_sql, row)
        except Exception as e:
            raise TrackError(e)
    # endregion --------------------------------------

    # region --- PUBLIC API METHODS ---
    # Public API methods for entity operations
    def save_entity(self, entity_name: str, entity: dict, auto_commit: bool = True) -> None:
        """
        Save an entity to the database.
        
        Args:
            entity_name: Name of the entity
            entity: Entity data
            auto_commit: Whether to auto-commit the transaction
        """
        if self._tx_active and not self._tx_started:
            self._tx_buffer.append((entity_name, entity))
            return
        self.save_entities(entity_name, [entity], auto_commit)
    
    def save_entities(self, entity_name: str, entities: list, auto_commit: bool = True, chunk_size: int = 100) -> None:
        """
        Save multiple entities to the database.
        
        Args:
            entity_name: Name of the entity
            entities: List of entity data
            auto_commit: Whether to auto-commit the transaction
            chunk_size: Size of chunks for batch operations
        """
        if not entities:
            return
            
        with self.transaction() if auto_commit else contextlib.nullcontext():
            _run_sync(self._run_save_entities(
                entity_name, entities, chunk_size,
                self._ensure_tables_exist, self._ensure_metadata_and_schema,
                self.execute_sql, self.executemany_sql, is_async=False
            ))
    
    async def save_entity_async(self, entity_name: str, entity: dict, auto_commit: bool = True) -> None:
        if self._tx_active and not self._tx_started:
            self._tx_buffer_async.append((entity_name, entity))
            return
        await self.save_entities_async(entity_name, [entity], auto_commit)
    
    async def save_entities_async(self, entity_name: str, entities: list, auto_commit: bool = True, chunk_size: int = 100) -> None:
        """
        Save multiple entities to the database asynchronously.
        
        Args:
            entity_name: Name of the entity
            entities: List of entity data
            auto_commit: Whether to auto-commit the transaction
            chunk_size: Size of chunks for batch operations
        """
        if not entities:
            return
            
        # Use the async transaction context manager for safety
        @self.async_transaction
        async def _save_with_transaction():
            await self._run_save_entities(
                entity_name, entities, chunk_size,
                self._ensure_tables_exist_async, self._ensure_metadata_and_schema_async,
                self.execute_sql_async, self.executemany_sql_async, is_async=True
            )
            
        if auto_commit:
            await _save_with_transaction()
        else:
            await self._run_save_entities(
                entity_name, entities, chunk_size,
                self._ensure_tables_exist_async, self._ensure_metadata_and_schema_async,
                self.execute_sql_async, self.executemany_sql_async, is_async=True
            )
    
    def get_entity(self, entity_name: str, entity_id: str, cast: bool = False) -> dict:
        """
        Get a single entity by ID.
        
        Args:
            entity_name: Name of the entity
            entity_id: ID of the entity
            cast: Whether to cast values to their types
            
        Returns:
            Entity dictionary or None if not found
        """
        return self._fetch_data(entity_name, f"id = {self.placeholder(False)}", True, cast, (entity_id,))
    
    def get_entities(self, entity_name: str, filter_clause: str = None, cast: bool = False, parameters: tuple = ()) -> list:
        """
        Get entities matching a filter.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause
            cast: Whether to cast values to their types
            parameters: Query parameters for the filter
            
        Returns:
            List of entity dictionaries
        """
        return self._fetch_data(entity_name, filter_clause, False, cast, parameters)
    
    async def get_entity_async(self, entity_name: str, entity_id: str, cast: bool = False) -> dict:
        """
        Get a single entity by ID asynchronously.
        
        Args:
            entity_name: Name of the entity
            entity_id: ID of the entity
            cast: Whether to cast values to their types
            
        Returns:
            Entity dictionary or None if not found
        """
        return await self._fetch_data_async(entity_name, f"id = {self.placeholder(True)}", True, cast, (entity_id,))
    
    async def get_entities_async(self, entity_name: str, filter_clause: str = None, cast: bool = False, parameters: tuple = ()) -> list:
        """
        Get entities matching a filter asynchronously.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause
            cast: Whether to cast values to their types
            parameters: Query parameters for the filter
            
        Returns:
            List of entity dictionaries
        """
        return await self._fetch_data_async(entity_name, filter_clause, False, cast, parameters)
   
    def delete_entity(self, entity_name: str, entity_id: str, auto_commit: bool = True) -> bool:
        """
        Delete an entity by ID.
        
        Args:
            entity_name: Name of the entity
            entity_id: ID of the entity to delete
            auto_commit: Whether to auto-commit the transaction
            
        Returns:
            True if entity was deleted, False if entity not found
            
        Raises:
            TrackError: On database errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            
            # Make sure the table exists
            self._ensure_tables_exist(entity_name)
            
            # Use transaction if requested
            cm = self.transaction() if auto_commit else contextlib.nullcontext()
            with cm:
                # Delete the entity
                result = self.execute_sql(
                    f"DELETE FROM {entity_name} WHERE id = {self.placeholder(False)}", 
                    (entity_id,)
                )
                # For some database implementations like SQLite, 
                # execute_sql doesn't return affected rows, so we check manually
                check = self.get_entity(entity_name, entity_id)
                return check is None
        except Exception as e:
            raise TrackError(e)
    
    async def delete_entity_async(self, entity_name: str, entity_id: str, auto_commit: bool = True) -> bool:
        """
        Delete an entity by ID asynchronously.
        
        Args:
            entity_name: Name of the entity
            entity_id: ID of the entity to delete
            auto_commit: Whether to auto-commit the transaction
            
        Returns:
            True if entity was deleted, False if entity not found
            
        Raises:
            TrackError: On database errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            
            # Make sure the table exists
            await self._ensure_tables_exist_async(entity_name)
            
            # Delete function with transaction
            @self.async_transaction
            async def _delete_with_transaction():
                await self.execute_sql_async(
                    f"DELETE FROM {entity_name} WHERE id = {self.placeholder(True)}", 
                    (entity_id,)
                )
                check = await self.get_entity_async(entity_name, entity_id)
                return check is None
                
            # Delete function without transaction
            async def _delete_without_transaction():
                await self.execute_sql_async(
                    f"DELETE FROM {entity_name} WHERE id = {self.placeholder(True)}", 
                    (entity_id,)
                )
                check = await self.get_entity_async(entity_name, entity_id)
                return check is None
                
            # Use appropriate function based on auto_commit
            return await _delete_with_transaction() if auto_commit else await _delete_without_transaction()
        except Exception as e:
            raise TrackError(e)
    
    def delete_entities(self, entity_name: str, filter_clause: str = None, parameters: tuple = (), auto_commit: bool = True) -> int:
        """
        Delete entities matching a filter.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause (if None, deletes all entities)
            parameters: Query parameters for the filter
            auto_commit: Whether to auto-commit the transaction
            
        Returns:
            Number of entities deleted (approximate)
            
        Raises:
            TrackError: On database errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            
            # Make sure the table exists
            self._ensure_tables_exist(entity_name)
            
            # Count entities before deletion for return value
            count_query = f"SELECT COUNT(*) FROM {entity_name}"
            if filter_clause:
                count_query += f" WHERE {filter_clause}"
                
            count_result = self.execute_sql(count_query, parameters)
            count = count_result[0][0] if count_result else 0
            
            # Use transaction if requested
            cm = self.transaction() if auto_commit else contextlib.nullcontext()
            with cm:
                # Delete entities
                delete_query = f"DELETE FROM {entity_name}"
                if filter_clause:
                    delete_query += f" WHERE {filter_clause}"
                    
                self.execute_sql(delete_query, parameters)
                
            return count
        except Exception as e:
            raise TrackError(e)
            
    async def delete_entities_async(self, entity_name: str, filter_clause: str = None, parameters: tuple = (), auto_commit: bool = True) -> int:
        """
        Delete entities matching a filter asynchronously.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause (if None, deletes all entities)
            parameters: Query parameters for the filter
            auto_commit: Whether to auto-commit the transaction
            
        Returns:
            Number of entities deleted (approximate)
            
        Raises:
            TrackError: On database errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            
            # Make sure the table exists
            await self._ensure_tables_exist_async(entity_name)
            
            # Count entities before deletion for return value
            count_query = f"SELECT COUNT(*) FROM {entity_name}"
            if filter_clause:
                count_query += f" WHERE {filter_clause}"
                
            if self.type() == 'postgres':
                count_query += f" -- {uuid.uuid4()}"
                
            count_result = await self.execute_sql_async(count_query, parameters)
            count = count_result[0][0] if count_result else 0
            
            # Delete function with transaction
            @self.async_transaction
            async def _delete_with_transaction():
                delete_query = f"DELETE FROM {entity_name}"
                if filter_clause:
                    delete_query += f" WHERE {filter_clause}"
                    
                if self.type() == 'postgres':
                    delete_query += f" -- {uuid.uuid4()}"
                    
                await self.execute_sql_async(delete_query, parameters)
                return count
                
            # Delete function without transaction
            async def _delete_without_transaction():
                delete_query = f"DELETE FROM {entity_name}"
                if filter_clause:
                    delete_query += f" WHERE {filter_clause}"
                    
                if self.type() == 'postgres':
                    delete_query += f" -- {uuid.uuid4()}"
                    
                await self.execute_sql_async(delete_query, parameters)
                return count
                
            # Use appropriate function based on auto_commit
            return await _delete_with_transaction() if auto_commit else await _delete_without_transaction()
        except Exception as e:
            raise TrackError(e)
    
    def count_entities(self, entity_name: str, filter_clause: str = None, parameters: tuple = ()) -> int:
        """
        Count entities matching a filter.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause (if None, counts all entities)
            parameters: Query parameters for the filter
            
        Returns:
            Number of entities matching the filter
            
        Raises:
            TrackError: On database errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            
            # Make sure the table exists
            self._ensure_tables_exist(entity_name)
            
            # Build and execute query
            count_query = f"SELECT COUNT(*) FROM {entity_name}"
            if filter_clause:
                count_query += f" WHERE {filter_clause}"
                
            count_result = self.execute_sql(count_query, parameters)
            return count_result[0][0] if count_result else 0
        except Exception as e:
            raise TrackError(e)
            
    async def count_entities_async(self, entity_name: str, filter_clause: str = None, parameters: tuple = ()) -> int:
        """
        Count entities matching a filter asynchronously.
        
        Args:
            entity_name: Name of the entity
            filter_clause: SQL WHERE clause (if None, counts all entities)
            parameters: Query parameters for the filter
            
        Returns:
            Number of entities matching the filter
            
        Raises:
            TrackError: On database errors
        """
        try:
            entity_name = self._sanitize_identifier(entity_name)
            
            # Make sure the table exists
            await self._ensure_tables_exist_async(entity_name)
            
            # Build and execute query
            count_query = f"SELECT COUNT(*) FROM {entity_name}"
            if filter_clause:
                count_query += f" WHERE {filter_clause}"
                
            if self.type() == 'postgres':
                count_query += f" -- {uuid.uuid4()}"
                
            count_result = await self.execute_sql_async(count_query, parameters)
            return count_result[0][0] if count_result else 0
        except Exception as e:
            raise TrackError(e)
    # endregion -----------------------------------

    # region --- FINAL FUNCTIONS ------
    @final
    def __enter__(self) -> "Database":
        """
        Enter context manager.
        
        Returns:
            Self for use in with statement
        """
        return self

    @final
    def __del__(self):
        """Close resources on object destruction."""
        # Only perform synchronous cleanup - don't try to use async methods
        try:
            if hasattr(self, '_close'):  # Check if attribute exists in case of partial initialization
                self._close()
        except Exception as e:
            # Use print instead of logger during __del__ as logger might be unavailable
            print(f"Error during database cleanup: {e}")

    @final
    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """
        Exit context manager.
        
        Args:
            exc_type: Exception type if raised
            exc_value: Exception value if raised
            traceback: Traceback if exception raised
            
        Returns:
            False to propagate exceptions
        """
        # Use synchronous close for context manager
        try:
            self.close(exc_type and exc_value)
        except Exception as e:
            logger.debug(f"Error during context manager exit for {self.alias()}: {e}")
        return False  # Don't suppress exceptions
    
    @final
    def close(self, error: Optional[Exception] = None) -> None:
        """
        Close the connection safely.
        Also ensure any pending work is committed or rolled back appropriately.
        
        Args:
            error: Exception if closing due to error
        """
        try:
            if error is None:
                self.commit_transaction()
            else:
                self.rollback_transaction()
            self._close()
            logger.debug(f"{self.alias()} database closed")
        except Exception as e:
            logger.error(f'Error closing connection for {self.alias()}: {e}')

    @final
    async def close_async(self, error: Optional[Exception] = None) -> None:
        """
        Close the async connection safely.
        Also ensure any pending work is committed or rolled back appropriately.
        
        Args:
            error: Exception if closing due to error
        """
        try:
            # Skip if event loop is closed
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                logger.debug(f"Cannot close {self.alias()} async: no running event loop")
                return

            if error is None:
                await self.commit_transaction_async()
            else:
                await self.rollback_transaction_async()
            await self._close_async()
            logger.debug(f"{self.alias()} async database closed")
        except Exception as e:
            logger.error(f'Error closing async connection for {self.alias()}: {e}')
    # endregion --- FINAL FUNCTIONS ------

