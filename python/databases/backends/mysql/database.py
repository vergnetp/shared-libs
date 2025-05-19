from typing import Dict
import pymysql

from ...database import ConnectionManager
from .pools import MySqlPoolManager
from .connections import MysqlSyncConnection, MysqlAsyncConnection


class MySqlDatabase(ConnectionManager):
    """
    MySQL implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for MySQL using pymysql for synchronous operations
    and aiomysql for asynchronous operations.
    
    Usage:
        db = MySqlDatabase(
            database="my_database",
            host="localhost",
            user="root",
            password="secret"
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
            self._pool_manager = MySqlPoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw pymysql connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new pymysql connection.
        """        
        return pymysql.connect(**config)        
    
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw aiomysql connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw aiomysql connection.
            
        Returns:
            MysqlAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return MysqlAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw pymysql connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw pymysql connection.
            
        Returns:
            MysqlSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return MysqlSyncConnection(raw_conn)
    # endregion
