from typing import Dict, Any

from ....resilience import retry_with_backoff
from ....utils import async_method

from ...connections import SyncConnection, AsyncConnection
from .generators import SqliteSqlGenerator

from ...entity.mixins import EntitySyncMixin, EntityAsyncMixin

class SqliteSyncConnection(SyncConnection, EntitySyncMixin):
    """
    SQLite implementation of the SyncConnection interface.
    
    This class wraps a raw sqlite3 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw sqlite3 connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)
        self._cursor = self._conn.cursor()
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqliteSqlGenerator:
        """Returns the SQL parameter converter."""
        if not self._sql_generator:
            self._sql_generator = SqliteSqlGenerator()
        return self._sql_generator

    @retry_with_backoff()
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """
        SQLite with sqlite3 doesn't have a separate prepare API,
        so we just return the SQL for later execution
        """
        return native_sql  # Just return the SQL string
    
    @retry_with_backoff()
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a statement using sqlite3"""
        # statement is the SQL string
        self._cursor.execute(statement, params or ())
        return self._cursor.fetchall()  # Return raw results
        
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return self._conn.in_transaction

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        self._conn.execute("BEGIN")

    def commit_transaction(self):
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        self._conn.commit()

    def rollback_transaction(self):
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        self._conn.rollback()

    def close(self):
        """
        Closes the database connection and cursor.
        
        This releases all resources used by the connection. The connection
        should not be used after calling this method.
        """
        self._cursor.close()
        self._conn.close()

    def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        cursor = self._conn.cursor()
        cursor.execute("SELECT sqlite_version();")
        server_version = cursor.fetchone()[0]

        import sqlite3
        driver_version = f"sqlite3 {sqlite3.sqlite_version}"

        return {          
            "db_server_version": server_version,
            "db_driver": driver_version
        }
           
class SqliteAsyncConnection(AsyncConnection, EntityAsyncMixin):
    """
    SQLite implementation of the AsyncConnection interface.
    
    This class wraps a raw aiosqlite connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw aiosqlite connection object.
    """
    def __init__(self, conn):
        super().__init__(conn) 
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqliteSqlGenerator:
        """Returns the SQL parameter converter."""
        if not self._sql_generator:
            self._sql_generator = SqliteSqlGenerator()
        return self._sql_generator
  
    @retry_with_backoff()
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """
        SQLite with aiosqlite doesn't have a separate prepare API, so returning the sql        
        """       
        return native_sql
    
    @retry_with_backoff()
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using aiosqlite"""
        async with self._conn.execute(statement, params or ()) as cursor:
            return await cursor.fetchall()

    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        # aiosqlite allows checking transaction status via in_transaction property
        return self._conn.in_transaction

    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        await self._conn.execute("BEGIN")

    @async_method
    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        await self._conn.commit()

    @async_method
    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        """
        await self._conn.rollback()

    @async_method
    async def close(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

    @async_method
    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        async with self._conn.execute("SELECT sqlite_version();") as cursor:
            row = await cursor.fetchone()
            server_version = row[0]

        import aiosqlite
        driver_version = f"aiosqlite {aiosqlite.__version__}"

        return {
            "db_server_version": server_version,
            "db_driver": driver_version
        }
 