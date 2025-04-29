import os
import sqlite3
import aiosqlite
from typing import Optional, Tuple, List, Any, Dict
from ..errors import TrackError
from .base import Database
from .. import log as logger

class SqliteDatabase(Database):
    """SQLite database implementation supporting both sync and async operations."""
    
    def __init__(self, database: str, alias: str = None, env: str = 'prod'):
        """
        Initialize a SQLite database connection.
        
        Args:
            database: Path to the SQLite database file
            alias: Friendly name for this database connection
            env: Environment name (prod, dev, test)
        """
        # Initialize the base class
        super().__init__(
            database,  # database path
            None,      # host (not used for SQLite)
            None,      # port (not used for SQLite)
            None,      # user (not used for SQLite)
            None,      # password (not used for SQLite)
            alias,     # alias
            env        # environment
        )   

        # Create our own metadata cache to avoid private attribute issues
        self.meta_cache = {}
        self.meta_versions = {}

        # Ensure directory for database file exists
        db_dir = os.path.dirname(self.database())
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # Sync connection setup
        self._sync_tx_active = False
        self._conn = sqlite3.connect(self.database())
        self._conn.row_factory = sqlite3.Row
        self._cursor = self._conn.cursor()

        # Enable foreign keys
        self._cursor.execute("PRAGMA foreign_keys = ON")

        # Async connection (initialized on demand)
        self._async_conn = None
        self._async_tx_active = False

    def is_connected(self) -> bool:
        """
        Check if the database connection is active.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            self._conn.execute("SELECT 1")
            return True
        except:
            return False
        
    def type(self) -> str:
        """
        Get the database type.
        
        Returns:
            'sqlite'
        """
        return "sqlite"

    def placeholder(self, is_async: bool=True) -> str:
        """
        Get the parameter placeholder for SQLite.
        
        Args:
            is_async: Whether this is for async operations (ignored for SQLite)
            
        Returns:
            '?' placeholder
        """
        return "?"

    # region --- Sync methods ---
    def begin_transaction(self) -> None:
        """Begin a new transaction."""
        if not self._sync_tx_active:
            self._conn.execute("BEGIN")
            self._sync_tx_active = True
            logger.debug(f"Transaction started for {self.alias()}")

    def commit_transaction(self) -> None:
        """Commit the current transaction."""
        if self._sync_tx_active:
            self._conn.commit()
            self._sync_tx_active = False
            logger.debug(f"Transaction committed for {self.alias()}")

    def rollback_transaction(self) -> None:
        """Roll back the current transaction."""
        if self._sync_tx_active:
            self._conn.rollback()
            self._sync_tx_active = False
            logger.debug(f"Transaction rolled back for {self.alias()}")

    def execute_sql(self, sql: str, parameters=()) -> list:
        """
        Execute a SQL query with parameters.
        
        Args:
            sql: SQL query
            parameters: Query parameters
            
        Returns:
            List of rows
            
        Raises:
            TrackError: On database errors
        """
        if not self.is_connected():
            raise TrackError(Exception("Lost SQLite connection"))
        try:            
            self._cursor.execute(sql, parameters)
            return self._cursor.fetchall() or []
        except Exception as e:
            logger.error(f'Error executing sqlite sql: {sql} parameters: {parameters} error: {e}')
            raise TrackError(e)

    def executemany_sql(self, sql: str, parameters_list: list) -> None:
        """
        Execute a SQL query multiple times with different parameters.
        
        Args:
            sql: SQL query
            parameters_list: List of parameter tuples
            
        Raises:
            TrackError: On database errors
        """
        if not self.is_connected():
            raise TrackError(Exception("Lost SQLite connection"))
        try:           
            self._cursor.executemany(sql, parameters_list)
        except Exception as e:
            logger.error(f'Error executing sqlite executemany: {sql} error: {e}')
            raise TrackError(e)

    def _close(self) -> None:
        """Close the synchronous database connection."""
        try:
            if self._cursor:
                self._cursor.close()
                self._cursor = None
            if self._conn:
                self._conn.close()
                self._conn = None
            self._sync_tx_active = False
        except Exception as e:
            logger.debug(f"Error closing SQLite connection: {e}")
    
    def clear_all(self) -> None:
        """
        Clear all data in the database by removing the file.
        
        Raises:
            TrackError: On file operation errors
        """
        try:
            # Close all connections
            self.close()
            
            # Remove the database file if it exists
            db_path = self.database()
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except Exception as e:
                    logger.error(f"Failed to remove database file: {e}")
                    raise TrackError(e)
                
            # Re-initialize the connection
            self._conn = sqlite3.connect(db_path)
            self._conn.row_factory = sqlite3.Row
            self._cursor = self._conn.cursor()
            
            # Enable foreign keys
            self._cursor.execute("PRAGMA foreign_keys = ON")
            
            # Reset metadata cache
            self.meta_cache = {}
            self.meta_versions = {}
        except Exception as e:
            raise TrackError(e)
    # endregion ----------

    # region --- Improved metadata handling ---
    def _ensure_tables_exist(self, entity_name: str) -> None:
        """
        Ensure required tables exist for the entity.
        
        Args:
            entity_name: Name of the entity
            
        This method is overridden to handle SQLite-specific behavior.
        """
        entity_name = self._sanitize_identifier(entity_name)
        
        # Create _meta_version table if needed
        self.execute_sql("""
            CREATE TABLE IF NOT EXISTS _meta_version (
                entity_name VARCHAR(255) PRIMARY KEY,
                version INTEGER
            )
        """)
        
        # Create entity metadata table
        self.execute_sql(f"""
            CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                name VARCHAR(255) PRIMARY KEY,
                type VARCHAR(255)
            )
        """)
        
        # Create entity table
        self.execute_sql(f"""
            CREATE TABLE IF NOT EXISTS {entity_name} (
                id VARCHAR(255) PRIMARY KEY
            )
        """)
        
        # Insert 'id' into metadata if not exists
        result = self.execute_sql(f"SELECT COUNT(*) FROM {entity_name}_meta WHERE name = ?", ('id',))
        if result and result[0][0] == 0:
            self.execute_sql(f"INSERT INTO {entity_name}_meta VALUES (?, ?)", ('id', str(type(''))))
    
    def _get_entity_metadata(self, entity_name: str) -> dict:
        """
        Get entity metadata.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Dictionary mapping field names to types
            
        This method is overridden to ensure consistent behavior in transactions.
        """
        entity_name = self._sanitize_identifier(entity_name)
        
        # Make sure tables exist (idempotent)
        self._ensure_tables_exist(entity_name)
        
        try:
            # Get metadata version
            version_rows = self.execute_sql(f"SELECT version FROM _meta_version WHERE entity_name = ?", (entity_name,))
            version = version_rows[0][0] if version_rows else 0
            
            # Check if we have a cached version that matches
            cached_version = self.meta_versions.get(entity_name)
            if cached_version is not None and cached_version == version:
                return self.meta_cache[entity_name]
            
            # Get metadata fields
            rows = self.execute_sql(f"SELECT name, type FROM {entity_name}_meta")
            
            # Create metadata dictionary
            meta = {name: typ for name, typ in rows}
            
            # Cache metadata
            self.meta_cache[entity_name] = meta
            self.meta_versions[entity_name] = version
            
            # Always have at least the id field
            if 'id' not in meta:
                meta['id'] = str(type(''))
                # Add id to metadata table
                self.execute_sql(f"INSERT INTO {entity_name}_meta VALUES (?, ?)", ('id', meta['id']))
            
            return meta
        except Exception as e:
            logger.error(f"Error getting entity metadata for {entity_name}: {e}")
            # Return minimal metadata in case of error
            return {'id': str(type(''))}
    
    def _get_keys_and_types(self, entity_name: str) -> Tuple[List[str], List[str]]:
        """
        Get the keys and types for an entity from metadata.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Tuple of (keys, types)
            
        This is overridden to ensure at least the id field is included.
        """
        meta = self._get_entity_metadata(entity_name)
        if not meta or len(meta) == 0:
            # Ensure we at least have an id field
            meta = {'id': str(type(''))}
        keys = list(meta.keys())
        types = [meta[k] for k in keys]
        return keys, types
    # endregion

    # region --- Async methods ---
    async def _init_async(self):
        """Initialize the async connection if needed."""
        if not self._async_conn:
            self._async_conn = await aiosqlite.connect(self.database())
            self._async_conn.row_factory = aiosqlite.Row
            # Enable foreign keys
            await self._async_conn.execute("PRAGMA foreign_keys = ON")

    async def begin_transaction_async(self) -> None:
        """Begin a new transaction asynchronously."""
        await self._init_async()
        if not self._async_tx_active:
            await self._async_conn.execute("BEGIN")
            self._async_tx_active = True
            logger.debug(f"Async transaction started for {self.alias()}")

    async def commit_transaction_async(self) -> None:
        """Commit the current transaction asynchronously."""
        if self._async_conn and self._async_tx_active:
            await self._async_conn.commit()
            self._async_tx_active = False
            logger.debug(f"Async transaction committed for {self.alias()}")

    async def rollback_transaction_async(self) -> None:
        """Roll back the current transaction asynchronously."""
        if self._async_conn and self._async_tx_active:
            await self._async_conn.rollback()
            self._async_tx_active = False
            logger.debug(f"Async transaction rolled back for {self.alias()}")

    async def execute_sql_async(self, sql: str, parameters=()) -> list:
        """
        Execute a SQL query with parameters asynchronously.
        
        Args:
            sql: SQL query
            parameters: Query parameters
            
        Returns:
            List of rows
            
        Raises:
            TrackError: On database errors
        """
        await self._init_async()
        try:            
            async with self._async_conn.execute(sql, parameters) as cursor:
                rows = await cursor.fetchall()
                return list(rows) if rows else []
        except Exception as e:
            logger.error(f'Error executing async sqlite sql: {sql} parameters: {parameters} error: {e}')
            raise TrackError(e)

    async def executemany_sql_async(self, sql: str, parameters_list: list) -> None:
        """
        Execute a SQL query multiple times with different parameters asynchronously.
        
        Args:
            sql: SQL query
            parameters_list: List of parameter tuples
            
        Raises:
            TrackError: On database errors
        """
        await self._init_async()
        try:            
            async with self._async_conn.cursor() as cursor:
                await cursor.executemany(sql, parameters_list)
        except Exception as e:
            logger.error(f'Error executing async sqlite executemany: {sql} error: {e}')
            raise TrackError(e)

    async def _ensure_tables_exist_async(self, entity_name: str) -> None:
        """
        Ensure required tables exist for the entity asynchronously.
        
        Args:
            entity_name: Name of the entity
        """
        entity_name = self._sanitize_identifier(entity_name)
        
        # Create _meta_version table if needed
        await self.execute_sql_async("""
            CREATE TABLE IF NOT EXISTS _meta_version (
                entity_name VARCHAR(255) PRIMARY KEY,
                version INTEGER
            )
        """)
        
        # Create entity metadata table
        await self.execute_sql_async(f"""
            CREATE TABLE IF NOT EXISTS {entity_name}_meta (
                name VARCHAR(255) PRIMARY KEY,
                type VARCHAR(255)
            )
        """)
        
        # Create entity table
        await self.execute_sql_async(f"""
            CREATE TABLE IF NOT EXISTS {entity_name} (
                id VARCHAR(255) PRIMARY KEY
            )
        """)
        
        # Insert 'id' into metadata if not exists
        result = await self.execute_sql_async(f"SELECT COUNT(*) FROM {entity_name}_meta WHERE name = ?", ('id',))
        if result and result[0][0] == 0:
            await self.execute_sql_async(f"INSERT INTO {entity_name}_meta VALUES (?, ?)", ('id', str(type(''))))

    async def _get_entity_metadata_async(self, entity_name: str) -> dict:
        """
        Get entity metadata asynchronously.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Dictionary mapping field names to types
        """
        entity_name = self._sanitize_identifier(entity_name)
        
        # Make sure tables exist (idempotent)
        await self._ensure_tables_exist_async(entity_name)
        
        try:
            # Get metadata version
            version_rows = await self.execute_sql_async(f"SELECT version FROM _meta_version WHERE entity_name = ?", (entity_name,))
            version = version_rows[0][0] if version_rows else 0
            
            # Check if we have a cached version that matches
            cached_version = self.meta_versions.get(entity_name)
            if cached_version is not None and cached_version == version:
                return self.meta_cache[entity_name]
            
            # Get metadata fields
            rows = await self.execute_sql_async(f"SELECT name, type FROM {entity_name}_meta")
            
            # Create metadata dictionary
            meta = {name: typ for name, typ in rows}
            
            # Cache metadata
            self.meta_cache[entity_name] = meta
            self.meta_versions[entity_name] = version
            
            # Always have at least the id field
            if 'id' not in meta:
                meta['id'] = str(type(''))
                # Add id to metadata table
                await self.execute_sql_async(f"INSERT INTO {entity_name}_meta VALUES (?, ?)", ('id', meta['id']))
            
            return meta
        except Exception as e:
            logger.error(f"Error getting async entity metadata for {entity_name}: {e}")
            # Return minimal metadata in case of error
            return {'id': str(type(''))}

    async def _get_keys_and_types_async(self, entity_name: str) -> Tuple[List[str], List[str]]:
        """
        Get the keys and types for an entity from metadata asynchronously.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Tuple of (keys, types)
        """
        meta = await self._get_entity_metadata_async(entity_name)
        if not meta or len(meta) == 0:
            # Ensure we at least have an id field
            meta = {'id': str(type(''))}
        keys = list(meta.keys())
        types = [meta[k] for k in keys]
        return keys, types

    async def _close_async(self) -> None:
        """Close the asynchronous database connection."""
        try:
            if self._async_conn:
                if self._async_tx_active:
                    await self._async_conn.rollback()
                    self._async_tx_active = False
                await self._async_conn.close()
                self._async_conn = None
                logger.debug(f"{self.alias()} async database closed")
        except Exception as e:
            logger.debug(f"Error closing async SQLite connection: {e}")

    async def clear_all_async(self) -> None:
        """
        Clear all data in the database by removing the file asynchronously.
        
        Raises:
            TrackError: On file operation errors
        """
        try:
            # Close async connection
            if self._async_conn:
                if self._async_tx_active:
                    await self._async_conn.rollback()
                    self._async_tx_active = False
                await self._async_conn.close()
                self._async_conn = None
            
            # Use sync method to remove the file and re-initialize 
            # since we need file system operations
            self.clear_all()
            
            # Async connection will be re-initialized on next use
            self._async_conn = None
        except Exception as e:
            raise TrackError(e)
    # endregion ----------