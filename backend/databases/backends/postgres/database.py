from typing import Dict
import psycopg2

from ...database import ConnectionManager
from .pools import PostgresPoolManager
from .connections import PostgresSyncConnection, PostgresAsyncConnection
from ...config import DatabaseConfig
  
class PostgresDatabase(ConnectionManager):
    """
    PostgreSQL implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for PostgreSQL using psycopg2 for synchronous operations
    and asyncpg for asynchronous operations.
    
    Usage:
        db = PostgresDatabase(DatabaseConfig(
            database="my_database",
            host="localhost",
            user="postgres",
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
            self._pool_manager = PostgresPoolManager(self.config)
        return self._pool_manager
    
    def _create_sync_connection(self, config: DatabaseConfig):
        """
        Creates a raw psycopg2 connection.
        
        Args:
            config (DatabaseConfig): Database configuration.
            
        Returns:
            A new psycopg2 connection.
        """
        return psycopg2.connect(
                host=config.host(),
                port=config.port(),
                user=config.user(),
                password=config.password(),
                database=config.database()
            )
          
    def _wrap_async_connection(self, raw_conn, config: DatabaseConfig):
        """
        Wraps a raw asyncpg connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw asyncpg connection.
            config (DatabaseConfig): Database configuration.
            
        Returns:
            PostgresAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return PostgresAsyncConnection(raw_conn, config)

    def _wrap_sync_connection(self, raw_conn, config: DatabaseConfig):
        """
        Wraps a raw psycopg2 connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw psycopg2 connection.
            config (DatabaseConfig): Database configuration.
            
        Returns:
            PostgresSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return PostgresSyncConnection(raw_conn, config)
    # endregion
