import threading
import itertools
from typing import Dict, Any
import psycopg2
import asyncpg

from ....resilience import retry_with_backoff
from ....utils import async_method
from .... import log as logger

from ...connections import SyncConnection, AsyncConnection
from .generators import PostgresSqlGenerator
from ...config import DatabaseConfig

from ...entity.mixins import EntitySyncMixin, EntityAsyncMixin

class PostgresSyncConnection(SyncConnection, EntitySyncMixin):
    """
    PostgreSQL implementation of the SyncConnection interface.
    
    This class wraps a raw psycopg2 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw psycopg2 connection object.
    """
    def __init__(self, conn, config: DatabaseConfig):
        super().__init__(conn, config)   
        logger.debug("postgres init")     
        self._cursor = self._conn.cursor()       
        self._prepared_counter = self.ThreadSafeCounter()
        self._sql_generator = None

    class ThreadSafeCounter:
        def __init__(self, start=0, step=1):
            self.counter = itertools.count(start, step)
            self.lock = threading.Lock()
            
        def next(self):
            with self.lock:
                return next(self.counter)
        
    @property
    def sql_generator(self) -> PostgresSqlGenerator:
        """Returns the PostgreSQL parameter converter."""
        if not  self._sql_generator:
            self._sql_generator = PostgresSqlGenerator(False)
        return  self._sql_generator
    
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """Prepare a statement using psycopg2"""
        logger.debug("postgres _prepare_statement") 
        stmt_name = f"prep_{self._prepared_counter.next()}" 
        
        # Prepare the statement
        self._cursor.execute(f"PREPARE {stmt_name} AS {native_sql}")
        return stmt_name
    
    @retry_with_backoff(
        max_retries=3, 
        exceptions=(
            psycopg2.OperationalError,
            psycopg2.InterfaceError,
            psycopg2.InternalError
        )
    )
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using psycopg2"""
        try:           
            # Handle the empty parameters case properly
            if not params or len(params) == 0:
                self._cursor.execute(f"EXECUTE {statement}")
            else:
                placeholders = ','.join(['?'] * len(params))
                self._cursor.execute(f"EXECUTE {statement} ({placeholders})", params)
                
            return self._cursor.fetchall()  # Return raw results
        except Exception as e:
            logger.error(f"Error executing statement: {e}")
            raise
  
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        Note:
            In psycopg2, transactions are started implicitly with the first query,
            so this method is a no-op for compatibility.
        """
        # psycopg2 starts transaction implicitly on execute
        pass

    def commit_transaction(self):
        """
        Commits the current transaction.
        
        This permanently applies all changes made since the transaction began.
        """
        self._conn.commit()

    def rollback_transaction(self):
        """
        Rolls back the current transaction.
        
        This discards all changes made since the transaction began.
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
        cursor.execute("SHOW server_version;")
        server_version = cursor.fetchone()[0]

        import psycopg2
        driver_version = f"psycopg2 {psycopg2.__version__}"

        return {           
            "db_server_version": server_version,
            "db_driver": driver_version
        }

class PostgresAsyncConnection(AsyncConnection, EntityAsyncMixin):
    """
    PostgreSQL implementation of the AsyncConnection interface.
    
    This class wraps a raw asyncpg connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw asyncpg connection object.
    """
    def __init__(self, conn, config: DatabaseConfig):
        super().__init__(conn, config)        
        self._tx = None 
        self._sql_generator = None

    @property
    def sql_generator(self) -> PostgresSqlGenerator:
        """Returns the PostgreSQL parameter converter."""
        if not  self._sql_generator:
            self._sql_generator = PostgresSqlGenerator(True)
        return  self._sql_generator

    @retry_with_backoff(
        exceptions=(
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            asyncpg.exceptions.ConnectionFailureError
        )
    )
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """Prepare a statement using asyncpg"""
        try:
            return await self._conn.prepare(native_sql)
        except Exception as e:
            logger.error(f'Error while Postgres async driver tried to prepare this: {native_sql}: {e}')
            raise

    
    @retry_with_backoff(
        exceptions=(
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            asyncpg.exceptions.TooManyConnectionsError,
            asyncpg.exceptions.ConnectionFailureError
        )
    )
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using asyncpg"""
        return await statement.fetch(*(params or []))
    
    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""       
        return self._conn.is_in_transaction()

    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        if self._tx is None:
            self._tx = self._conn.transaction()
            await self._tx.start()

    @async_method
    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.commit()
            self._tx = None

    @async_method
    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.rollback()
            self._tx = None

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
        version_tuple = self._conn.get_server_version()
        server_version = ".".join(str(v) for v in version_tuple[:2])

        import asyncpg
        driver_version = f"asyncpg {asyncpg.__version__}"

        return {      
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    