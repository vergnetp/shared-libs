from typing import Dict
import pymysql

from ...database import ConnectionManager
from .pools import MySqlPoolManager
from .connections import MysqlSyncConnection, MysqlAsyncConnection
from ...config import DatabaseConfig

class MySqlDatabase(ConnectionManager):
    """
    MySQL implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for MySQL using pymysql for synchronous operations
    and aiomysql for asynchronous operations.
    
    Usage:
        db = MySqlDatabase(DatabaseConfig(
            database="my_database",
            host="localhost",
            user="root",
            password="secret"
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
            self._pool_manager = MySqlPoolManager(self.config)
        return self._pool_manager
    
    def _create_sync_connection(self, config: DatabaseConfig):
        """
        Creates a raw pymysql connection.
        
        Args:
            config (DatabaseConfig): Database configuration.
            
        Returns:
            A new pymysql connection.
        """        
        return pymysql.connect(
                host=config.host(),
                port=config.port(),
                user=config.user(),
                password=config.password(),
                database=config.database()
            )        
    
    def _wrap_async_connection(self, raw_conn, config: DatabaseConfig):
        """
        Wraps a raw aiomysql connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw aiomysql connection.
            config (DatabaseConfig): Database configuration.
            
        Returns:
            MysqlAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return MysqlAsyncConnection(raw_conn, config)

    def _wrap_sync_connection(self, raw_conn, config: DatabaseConfig):
        """
        Wraps a raw pymysql connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw pymysql connection.
            config (DatabaseConfig): Database configuration.
            
        Returns:
            MysqlSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return MysqlSyncConnection(raw_conn, config)
    # endregion
