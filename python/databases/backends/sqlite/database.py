
from typing import Dict
import sqlite3

from ...database import ConnectionManager
from .pools import SqlitePoolManager
from .connections import SqliteSyncConnection, SqliteAsyncConnection

class SqliteDatabase(ConnectionManager):
    """
    SQLite implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for SQLite using sqlite3 for synchronous operations
    and aiosqlite for asynchronous operations.
    
    Usage:
        db = SqliteDatabase(
            database="path/to/my_database.db"
        )
        
        # Synchronous
        with db.sync_connection() as conn:
            conn.execute("SELECT * FROM users")
            
        # Asynchronous
        async with db.async_connection() as conn:
            await conn.execute("SELECT * FROM users")
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs) 
        self._pool_manager = None
        
    # region -- Implementation of Abstract methods ---------
    @property
    def pool_manager(self):
        if not self._pool_manager:
            self._pool_manager = SqlitePoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw sqlite3 connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new sqlite3 connection.
            
        Note:
            For SQLite, only the 'database' parameter is used, which should
            be the path to the database file.
        """       
        return sqlite3.connect(config["database"])        
    
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw aiosqlite connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw aiosqlite connection.
            
        Returns:
            SqliteAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return SqliteAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw sqlite3 connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw sqlite3 connection.
            
        Returns:
            SqliteSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return SqliteSyncConnection(raw_conn)
    # endregion
