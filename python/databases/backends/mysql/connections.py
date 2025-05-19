from typing import Dict, Any

from ....resilience import retry_with_backoff
from ....utils import async_method

from ...connections import SyncConnection, AsyncConnection
from .generators import MySqlSqlGenerator

from ...entity.mixins import EntitySyncMixin, EntityAsyncMixin

class MysqlSyncConnection(SyncConnection, EntitySyncMixin):
    """
    MySQL implementation of the SyncConnection interface.
    
    This class wraps a raw pymysql connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw pymysql connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)       
        self._cursor = self._conn.cursor()
        self._sql_generator = None

    @property
    def sql_generator(self) -> MySqlSqlGenerator:
        """Returns the MySql parameter converter."""
        if not self._sql_generator:
            self._sql_generator = MySqlSqlGenerator()
        return self._sql_generator
    
    @retry_with_backoff()
    def _prepare_statement_sync(self, converted_sql: str) -> Any:
        """
        MySQL with pymysql doesn't have true prepared statements API
        so we just return the SQL for later execution
        """
        return converted_sql  # Just return the converted SQL

    @retry_with_backoff()
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a statement using pymysql"""
        # statement is just the SQL string
        self._cursor.execute(statement, params or ())
        return self._cursor.fetchall()  # Return raw results

     
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return not self._conn.get_autocommit()

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        self._conn.begin()

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
        cursor.execute("SELECT VERSION();")
        server_version = cursor.fetchone()[0]

        module = type(self._conn).__module__.split(".")[0]
        driver_version = f"{module} {__import__(module).__version__}"

        return {
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    
class MysqlAsyncConnection(AsyncConnection, EntityAsyncMixin):
    """
    MySQL implementation of the AsyncConnection interface.
    
    This class wraps a raw aiomysql connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw aiomysql connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)        
        self._sql_generator = None

    @property
    def sql_generator(self) -> MySqlSqlGenerator:
        """Returns the MySql parameter converter."""
        if not self._sql_generator:
            self._sql_generator = MySqlSqlGenerator()
        return self._sql_generator

    @retry_with_backoff()
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """
        MySQL with aiomysql doesn't have true prepared statements API
        so we just return the SQL for later execution
        """
        return native_sql
    
    @retry_with_backoff()
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a statement using aiomysql"""
        # statement is just the SQL string
        async with self._conn.cursor() as cursor:
            await cursor.execute(statement, params or ())
            return await cursor.fetchall()   
 
    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return not self._conn.get_autocommit()
    
    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed,
        regardless of whether you've explicitly started a transaction.
        """
        await self._conn.begin()

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
    
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed, and any previous insert/update would not be rolled back.
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
        async with self._conn.cursor() as cursor:
            await cursor.execute("SELECT VERSION();")
            row = await cursor.fetchone()
            server_version = row[0]

        import aiomysql
        driver_version = f"aiomysql {aiomysql.__version__}"

        return {           
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    