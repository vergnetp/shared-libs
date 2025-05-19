from typing import Dict
import psycopg2

from ...database import ConnectionManager
from .pools import PostgresPoolManager
from .connections import PostgresSyncConnection, PostgresAsyncConnection
  
class PostgresDatabase(ConnectionManager):
    """
    PostgreSQL implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for PostgreSQL using psycopg2 for synchronous operations
    and asyncpg for asynchronous operations.
    
    Usage:
        db = PostgresDatabase(
            database="my_database",
            host="localhost",
            user="postgres",
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
            self._pool_manager = PostgresPoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw psycopg2 connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new psycopg2 connection.
        """
        return psycopg2.connect(**config)
          
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw asyncpg connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw asyncpg connection.
            
        Returns:
            PostgresAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return PostgresAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw psycopg2 connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw psycopg2 connection.
            
        Returns:
            PostgresSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return PostgresSyncConnection(raw_conn)
    # endregion
