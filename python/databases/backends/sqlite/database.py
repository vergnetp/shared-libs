
from typing import Dict
import sqlite3

from ...database import ConnectionManager
from .pools import SqlitePoolManager
from .connections import SqliteSyncConnection, SqliteAsyncConnection
from ...config import DatabaseConfig

class SqliteDatabase(ConnectionManager):
    """
    SQLite implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for SQLite using sqlite3 for synchronous operations
    and aiosqlite for asynchronous operations.
    
    Usage:
        db = SqliteDatabase(DatabaseConfig(
            database="path/to/my_database.db"
        ))
        
        # Synchronous
        with db.sync_connection() as conn:
            conn.execute("SELECT * FROM users")
            
        # Asynchronous
        async with db.async_connection() as conn:
            await conn.execute("SELECT * FROM users")
    """

    def __init__(self, config: DatabaseConfig):
        super().__init__(config) 
        self._pool_manager = None
        
    # region -- Implementation of Abstract methods ---------
    @property
    def pool_manager(self):
        if not self._pool_manager:
            self._pool_manager = SqlitePoolManager(self.config)
        return self._pool_manager
    
    def _create_sync_connection(self, config: DatabaseConfig):
        """
        Creates a raw sqlite3 connection.
        
        Args:
            config (DatabaseConfig): Database configuration.
            
        Returns:
            A new sqlite3 connection.
            
        Note:
            For SQLite, only the 'database' parameter is used, which should
            be the path to the database file.
        """       
        return sqlite3.connect(config["database"])        
    
    def _wrap_async_connection(self, raw_conn, config: DatabaseConfig):
        """
        Wraps a raw aiosqlite connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw aiosqlite connection.
            config (DatabaseConfig): Database configuration.
            
        Returns:
            SqliteAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return SqliteAsyncConnection(raw_conn, config)

    def _wrap_sync_connection(self, raw_conn, config: DatabaseConfig):
        """
        Wraps a raw sqlite3 connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw sqlite3 connection.
            config (DatabaseConfig): Database configuration.
            
        Returns:
            SqliteSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return SqliteSyncConnection(raw_conn, config)
    # endregion
