# This is the base class exposing all the methods that any DataBase class will fulfill

import os
import uuid
from typing import Callable, Awaitable, Optional, Tuple, List, Any, final
import asyncio, re
import nest_asyncio
from abc import ABC, abstractmethod
from ..errors import TrackError
from .. import log as logger
from .. import utils

def _run_sync(coro):
    try:
        loop = asyncio.get_running_loop()
        nest_asyncio.apply(loop)  # ← patch the loop so we can nest safely
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
    
class Database(ABC):
    def __init__(self, database: str, host: str=None, port: int=None, user: str=None, password: str=None, alias: str = None, env: str = 'prod'):
        self.__host = host
        self.__port = port
        self.__database = database
        self.__user = user
        self.__password = password
        self.__env = env
        self.__alias = alias or database or f'self.type()_database'
        self.__meta_cache = {}
        self.__keys_cache = {}
        self.__types_cache = {}
        self.__meta_versions = {}

    # region --- HELPERS --------------
    @staticmethod
    def _sanitize_identifier(name: str) -> str:
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            raise ValueError(f"Unsafe SQL identifier: {name}")
        return name

    def placeholders(self, count: int, is_async: bool=True) -> str:
        if self.type() == "postgres":
            if is_async:
                return ", ".join(f"${i+1}" for i in range(count))
            else:
                return ", ".join([self.placeholder(False)] * count)
        else:
            return ", ".join([self.placeholder(is_async)] * count)
    
    def _get_keys_and_types(self, entity_name: str) -> Tuple[List[str], List[str]]:
        meta = self._get_entity_metadata(entity_name)
        return list(meta.keys()), list(meta.values())

    async def _get_keys_and_types_async(self, entity_name: str) -> Tuple[List[str], List[str]]:
        meta = await self._get_entity_metadata_async(entity_name)
        return list(meta.keys()), list(meta.values())

    def _prepare_entity_data(self, entity: dict) -> dict:
        return entity

    async def _run_metadata_flow(self, entity_name: str, executor: Callable[..., Awaitable], is_async: bool = True):
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

            if self.__meta_versions.get(entity_name) == version:
                return self.__meta_cache[entity_name]

            rows = await executor(f"SELECT name, type FROM {entity_name}_meta -- {uuid.uuid4()}") if is_async else executor(f"SELECT name, type FROM {entity_name}_meta")
            meta = {name: typ for name, typ in rows}
            self.__meta_cache[entity_name] = meta
            self.__keys_cache[entity_name] = list(meta.keys())
            self.__types_cache[entity_name] = list(meta.values())
            self.__meta_versions[entity_name] = version
            return meta
        except Exception as e:
            raise TrackError(e)

    def _get_entity_metadata(self, entity_name: str):
        return _run_sync(self._run_metadata_flow(entity_name, self.execute_sql, is_async=False))

    async def _get_entity_metadata_async(self, entity_name: str):
        return await self._run_metadata_flow(entity_name, self.execute_sql_async, is_async=True)

    async def _run_version_bump(self, entity_name: str, executor: Callable[..., Awaitable], is_async: bool = True):
        pl = self.placeholder(is_async)
        
        # Use different SQL syntax based on database type
        if self.type() == 'mysql':
            sql = f"""
                INSERT INTO _meta_version (entity_name, version)
                VALUES ({pl}, 1)
                ON DUPLICATE KEY UPDATE version = version + 1
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
                VALUES ({pl}, COALESCE((SELECT version FROM _meta_version WHERE entity_name = {pl}) + 1, 1))
                """
            
        try:
            if is_async:
                await executor(sql, (entity_name,))
            else:
                executor(sql, (entity_name,))
        except Exception as e:
            raise TrackError(e)

    def _bump_entity_version(self, entity_name: str) -> None:
       _run_sync(self._run_version_bump(entity_name, self.execute_sql, is_async=False))

    async def _bump_entity_version_async(self, entity_name: str) -> None:
        await self._run_version_bump(entity_name, self.execute_sql_async, is_async=True)

    async def _run_ensure_tables(self, entity_name: str, executor: Callable[..., Awaitable], is_async: bool = True):
        try:
            entity_name = self._sanitize_identifier(entity_name)
            if is_async:
                await executor("""
                    CREATE TABLE IF NOT EXISTS _meta_version (
                        entity_name VARCHAR(255) PRIMARY KEY,
                        version INTEGER
                    ) -- {uuid.uuid4()}""")
            else:
                executor("""
                CREATE TABLE IF NOT EXISTS _meta_version (
                    entity_name VARCHAR(255) PRIMARY KEY,
                    version INTEGER
                )""")
                
            meta_table_sql = f'create table if not exists {entity_name}_meta (name varchar(255) {"PRIMARY KEY" if self.type() == "sqlite" else ",PRIMARY KEY (name)"}, type varchar(255))'
            if is_async and self.type() == 'postgres':
                meta_table_sql += f' -- {uuid.uuid4()}'
                
            await executor(meta_table_sql) if is_async else executor(meta_table_sql)
            
            create_sql = f"create table if not exists {entity_name} (id VARCHAR(255) {'PRIMARY KEY' if self.type() == 'sqlite' else ',PRIMARY KEY (id)'})"
            if is_async and self.type() == 'postgres':
                create_sql += f' -- {uuid.uuid4()}'
                
            await executor(create_sql) if is_async else executor(create_sql)
        except Exception as e:
            raise TrackError(e)

    def _ensure_tables_exist(self, entity_name: str) -> None:
        _run_sync(self._run_ensure_tables(entity_name, self.execute_sql, is_async=False))

    async def _ensure_tables_exist_async(self, entity_name: str) -> None:
        await self._run_ensure_tables(entity_name, self.execute_sql_async, is_async=True)

    async def _run_deserialize(self, entity_name: str, values, keys, types, cast, fetch_keys_types):
        if keys is None or types is None:
            keys, types = await fetch_keys_types(entity_name) if asyncio.iscoroutinefunction(fetch_keys_types) else fetch_keys_types(entity_name)
        return {
            key: utils.safe_deserialize(value, target_type) if cast else value
            for key, value, target_type in zip(keys, values, types)
        }

    def _db_values_to_entity(self, entity_name, values, keys=None, types=None, cast=False):
        try:
            entity_name = self._sanitize_identifier(entity_name)
            return _run_sync(self._run_deserialize(entity_name, values, keys, types, cast, self._get_keys_and_types))
        except Exception as e:
            raise TrackError(e)

    async def _db_values_to_entity_async(self, entity_name, values, keys=None, types=None, cast=False):
        try:
            entity_name = self._sanitize_identifier(entity_name)
            return await self._run_deserialize(entity_name, values, keys, types, cast, self._get_keys_and_types_async)
        except Exception as e:
            raise TrackError(e)

    async def _run_metadata_schema_check(self, entity_name: str, keys, sample_values, get_metadata, executor, bump_version, is_async: bool):
        try:
            pl = self.placeholder(is_async)
            meta = await get_metadata(entity_name) if is_async else get_metadata(entity_name)

            for key in keys:
                sample_value = sample_values.get(key)
                if key not in meta and sample_value is not None:
                    typ = str(type(sample_value))
                    
                    # Build SQL based on database type
                    if self.type() == 'sqlite':
                        insert_sql = f"INSERT OR REPLACE INTO {entity_name}_meta VALUES ({self.placeholders(2, is_async)})"
                    elif self.type() == 'postgres':
                        insert_sql = f"INSERT INTO {entity_name}_meta VALUES ({self.placeholders(2, is_async)}) ON CONFLICT(name) DO UPDATE SET type=EXCLUDED.type -- {uuid.uuid4()}"
                    else:  # mysql
                        insert_sql = f"INSERT INTO {entity_name}_meta VALUES ({self.placeholders(2, is_async)}) ON DUPLICATE KEY UPDATE type=VALUES(type)"
                    
                    if is_async:                 
                        await executor(insert_sql, (key, typ))
                        if key != 'id':
                            alter_sql = f"ALTER TABLE {entity_name} ADD {key} TEXT"
                            if is_async and self.type() == 'postgres':
                                alter_sql += f" -- {uuid.uuid4()}"
                            await executor(alter_sql)
                        await bump_version(entity_name)
                    else:
                        executor(insert_sql, (key, typ))
                        if key != 'id':
                            executor(f"ALTER TABLE {entity_name} ADD {key} TEXT")
                        bump_version(entity_name)
        except Exception as e:
            raise TrackError(e)
    
    def _ensure_metadata_and_schema(self, entity_name, keys, sample_values):
        _run_sync(self._run_metadata_schema_check(
            entity_name, keys, sample_values,
            self._get_entity_metadata, self.execute_sql, self._bump_entity_version,
            is_async=False
        ))

    async def _ensure_metadata_and_schema_async(self, entity_name, keys, sample_values):
        await self._run_metadata_schema_check(
            entity_name, keys, sample_values,
            self._get_entity_metadata_async, self.execute_sql_async, self._bump_entity_version_async,
            is_async=True
        )

    async def _run_fetch(self, entity_name, filter, single, cast, ensure_tables, get_keys_types, fetch_rows, convert_row, is_async):
        try:
            entity_name = self._sanitize_identifier(entity_name)
            await ensure_tables(entity_name) if is_async else ensure_tables(entity_name)
            keys, types = await get_keys_types(entity_name) if is_async else get_keys_types(entity_name)
            where_clause = f"WHERE {filter}" if filter else ''
            sql = f"SELECT {','.join(keys)} FROM {entity_name} {where_clause}"
            if is_async and self.type() == 'postgres':
                sql += f" -- {uuid.uuid4()}"
            rows = await fetch_rows(sql) if is_async else fetch_rows(sql)
            results = [await convert_row(entity_name, row, keys, types, cast) if is_async else convert_row(entity_name, row, keys, types, cast) for row in rows]
            if single and len(results) == 0:
                return None
            return results[0] if single and results else results
        except Exception as e:
            raise TrackError(e)

    def _fetch_data(self, entity_name, filter=None, single=False, cast=False):
        return _run_sync(self._run_fetch(
            entity_name, filter, single, cast,
            self._ensure_tables_exist, self._get_keys_and_types,
            self.execute_sql, self._db_values_to_entity, is_async=False
        ))

    async def _fetch_data_async(self, entity_name, filter=None, single=False, cast=False):
        return await self._run_fetch(
            entity_name, filter, single, cast,
            self._ensure_tables_exist_async, self._get_keys_and_types_async,
            self.execute_sql_async, self._db_values_to_entity_async, is_async=True
        )

    async def _run_save_entities(self, entity_name, entities, chunk_size, ensure_tables, ensure_schema, executor, executemany, is_async):
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
            insert_sql = f"INSERT {or_replace} INTO {entity_name} ({','.join(keys)}) VALUES({self.placeholders(len(keys), is_async)})"
            
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
                    duplicates = [f'{key}=VALUES({key})' for key in update_keys]
                    insert_sql += f" ON DUPLICATE KEY UPDATE {', '.join(duplicates)}"

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

    # region --- FINAL FUNCTIONS ------
    @final
    def __enter__(self) -> "Database":
        return self

    @final
    def __del__(self):       
        # Only perform synchronous cleanup - don't try to use async methods
        try:
            if hasattr(self, '_close'):  # Check if attribute exists in case of partial initialization
                self._close()
        except Exception as e:
            # Use print instead of logger during __del__ as logger might be unavailable
            print(f"Error during database cleanup: {e}")

    @final
    def __exit__(self, exc_type, exc_value, traceback) -> None:      
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

    @final
    def env(self) -> str:
        """
        Returns the environment
        """        
        return self.__env        
    
    @final 
    def alias(self) -> str:
        """
        Returns the alias
        """
        return self.__alias

    @final
    def database(self): 
        return self.__database

    @final
    def config(self) -> dict:
        """
        Returns the database configuration dictionary (database, host, port, user, password)
        """
        return {
        "host": self.__host,
        "port": self.__port,
        "database": self.__database,
        "user": self.__user,
        "password": self.__password,
        }
    
    @final
    def save_entities(self, entity_name, entities, chunk_size=500, auto_commit=True):
        # Start a transaction if auto_commit is True
        internal_transaction = auto_commit
        try:
            if internal_transaction:
                self.begin_transaction()
                
            _run_sync(self._run_save_entities(
                entity_name, entities, chunk_size,
                self._ensure_tables_exist, self._ensure_metadata_and_schema,
                self.execute_sql, self.executemany_sql, is_async=False
            ))
            
            # Commit only if we started the transaction
            if internal_transaction:
                self.commit_transaction()
        except Exception as e:
            # Rollback only if we started the transaction
            if internal_transaction:
                self.rollback_transaction()
            raise TrackError(e)

    @final
    async def save_entities_async(self, entity_name, entities, chunk_size=500, auto_commit=True):
        # Start a transaction if auto_commit is True
        internal_transaction = auto_commit
        try:
            if internal_transaction:
                await self.begin_transaction_async()
                
            await self._run_save_entities(
                entity_name, entities, chunk_size,
                self._ensure_tables_exist_async, self._ensure_metadata_and_schema_async,
                self.execute_sql_async, self.executemany_sql_async, is_async=True
            )
            
            # Commit only if we started the transaction
            if internal_transaction:
                await self.commit_transaction_async()
        except Exception as e:
            # Rollback only if we started the transaction
            if internal_transaction:
                await self.rollback_transaction_async()
            raise TrackError(e)

    @final
    def save_entity(self, entity_name, entity, auto_commit=True):
        self.save_entities(
            entity_name, 
            [entity.__dict__ if not isinstance(entity, dict) else entity],
            auto_commit=auto_commit
        )

    @final
    async def save_entity_async(self, entity_name, entity, auto_commit=True):
        await self.save_entities_async(
            entity_name, 
            [entity.__dict__ if not isinstance(entity, dict) else entity],
            auto_commit=auto_commit
        )

    @final
    def get_entity(self, entity_name, id, cast=False):
        return self._fetch_data(entity_name, f"id = '{id}'", single=True, cast=cast)

    @final
    async def get_entity_async(self, entity_name, id, cast=False):
        return await self._fetch_data_async(entity_name, f"id = '{id}'", single=True, cast=cast)

    @final
    def get_entities(self, entity_name, filter=None, cast=False):
        return self._fetch_data(entity_name, filter, single=False, cast=cast)

    @final
    async def get_entities_async(self, entity_name, filter=None, cast=False):
        return await self._fetch_data_async(entity_name, filter, single=False, cast=cast)
    # endregion --- FINAL FUNCTIONS ---

    # region --- ABSTRACT FUNCTIONS ---
    @abstractmethod
    def type(self) -> str:
        """
        Returns the type of database ('sqlite', 'mysql'...).
        """
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def placeholder(self, is_async: bool=True) -> str:
        """
        Returns the SQL placeholder for the given database.
        """        
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def clear_all(self) -> None:
        """
        Drop and recreate the entire database.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    async def clear_all_async(self) -> None:
        """
        Drop and recreate the entire database.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def _close(self) -> None:
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    async def _close_async(self) -> None:
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def begin_transaction(self) -> None:
        """
        Begin the transaction.
        """
        raise NotImplementedError("Subclasses must implement this method.")
      
    @abstractmethod
    def commit_transaction(self) -> None:
        """
        Commit the transaction.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def rollback_transaction(self) -> None:
        """
        Rollback the transaction.
        """
        raise NotImplementedError("Subclasses must implement this method.")
    
    @abstractmethod
    def execute_sql(self, sql: str, parameters: Tuple[Any, ...] = ()) -> List[Any]:
        """
        Internal method to execute a SQL query with optional parameters.
        Handles errors by raising TrackError if a failure occurs.

        Args:
            sql (str): The SQL query to execute.
            parameters (tuple): Parameters to safely inject into the query.

        Returns:
            list: Result of the query (typically rows from a SELECT query).

        Raises:
            TrackError: If there is a failure executing the query (rollback all pending sqls)
        """
        raise NotImplementedError("Subclasses must implement this method.")
    
    @abstractmethod
    def executemany_sql(self, sql: str, parameters_list: List[Tuple[Any, ...]]) -> None:
        """
        Internal method to execute a SQL query with optional parameters.
        Handles errors by raising TrackError if a failure occurs.

        Assumes an open transaction is already active from the calling method.
        Rolls back the entire transaction if this batch fails.

        Args:
            sql (str): The SQL query to execute.
            parameters_list (List[Tuple]): List of parameters to safely inject into the query.

        Returns:
            None

        Raises:
            TrackError: If there is a failure executing the query (rollback all pending sqls)
        """
        raise NotImplementedError("Subclasses must implement this method.")        

    @abstractmethod
    async def begin_transaction_async(self) -> None:
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    async def commit_transaction_async(self) -> None:
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    async def rollback_transaction_async(self) -> None:
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    async def execute_sql_async(self, sql: str, parameters: Tuple[Any, ...] = ()) -> List[Any]:
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    async def executemany_sql_async(self, sql: str, parameters_list: List[Tuple[Any, ...]]) -> None:
        raise NotImplementedError("Subclasses must implement this method.")

    # endregion -----------------------