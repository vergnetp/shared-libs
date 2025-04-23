import psycopg2
import asyncpg
from ..errors import TrackError
from .base import Database

class PostgresDatabase(Database):
    def __init__(self, database: str, host: str=None, port: int=None, user: str=None, password: str=None, alias: str = None, env: str = 'prod'):
        super().__init__(database, host, port, user, password, alias, env)   

        # Sync
        cfg = self.config().copy()
        cfg["dbname"] = cfg.pop("database")
        self._conn = psycopg2.connect(**cfg)
        # Set autocommit to True before setting session isolation level
        self._conn.autocommit = True
        self._conn.set_session(isolation_level='REPEATABLE READ')
        
        # Create the schema if it doesn't exist and set it
        self._cursor = self._conn.cursor()
        self._cursor.execute("CREATE SCHEMA IF NOT EXISTS public")
        self._cursor.execute("SET search_path TO public")
        
        # After setting session parameters and schema, set autocommit back to False
        self._conn.autocommit = False

        # Async
        self._pool = None
        self._async_conn = None
        self._async_tx = None

    def is_connected(self) -> bool:
        try:
            self._cursor.execute("SELECT 1")
            return True
        except:
            return False

    def type(self) -> str:
        return "postgres"

    def placeholder(self, is_async: bool=True) -> str:
        if is_async:
            return '$1'
        else:
            return "%s"

    # --- region Sync methods ---
    def begin_transaction(self) -> None:
        # Reset any existing transaction
        if self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            self._conn.rollback()
        
        # Make sure autocommit is off
        self._conn.autocommit = False
        
        # Explicitly start a transaction block
        self._cursor.execute("select 1")
        
        # Set search path
        self._cursor.execute("SET search_path TO public")
        
    def commit_transaction(self) -> None:
        self._conn.commit()

    def rollback_transaction(self) -> None:
        print('ROLLED BACK???')
        if self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            self._conn.rollback()
            print('ROLLED BACK!!!!')
        else:
            print('NO TRANSACTION')

    def execute_sql(self, sql: str, parameters=()) -> list:
        if not self.is_connected():
            raise TrackError(Exception("Lost Postgres connection"))
        # Ensure schema is set correctly before each execution
        self._cursor.execute("SET search_path TO public")
        self._cursor.execute(sql, parameters)
        if self._cursor.description:  # Only fetch if there's a result set
            return self._cursor.fetchall()
        return []

    def executemany_sql(self, sql: str, parameters_list: list) -> None:
        if not self.is_connected():
            raise TrackError(Exception("Lost Postgres connection"))
        # Ensure schema is set correctly before each execution
        self._cursor.execute("SET search_path TO public")
        self._cursor.executemany(sql, parameters_list)

    def _close(self) -> None:
        self._cursor.close()
        self._conn.close()

    def clear_all(self) -> None:
        try:
            # End any current transaction
            self._conn.rollback()
            
            # Set autocommit to True to avoid transaction issues
            original_autocommit = self._conn.autocommit
            self._conn.autocommit = True
            
            # First check if the public schema exists before trying to drop it
            self._cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'public'")
            schema_exists = self._cursor.fetchone() is not None
            
            if schema_exists:
                self._cursor.execute('DROP SCHEMA public CASCADE')
                
            # Always create the schema
            self._cursor.execute('CREATE SCHEMA public')
            self._cursor.execute('SET search_path TO public')
            
            # Restore original autocommit state
            self._conn.autocommit = original_autocommit
        except Exception as e:
            # Try to restore the original autocommit state
            try:
                self._conn.autocommit = original_autocommit
            except:
                pass
            raise TrackError(e)

    # endregion ----------

    # --- region Async methods ---

    async def _init_async(self):
        if self._pool is None:
            self._pool = await asyncpg.create_pool(**self.config())
        if self._async_conn is None:
            self._async_conn = await self._pool.acquire()
        # Create schema if not exists and always ensure schema is set correctly
        await self._async_conn.execute('CREATE SCHEMA IF NOT EXISTS public')
        await self._async_conn.execute('SET search_path TO public')

    async def begin_transaction_async(self) -> None:
        await self._init_async()
        self._async_tx = self._async_conn.transaction()
        await self._async_tx.start()

    async def commit_transaction_async(self) -> None:
        if self._async_tx:
            await self._async_tx.commit()
            self._async_tx = None

    async def rollback_transaction_async(self) -> None:
        if self._async_tx:
            await self._async_tx.rollback()
            self._async_tx = None

    async def execute_sql_async(self, sql: str, parameters=()) -> list:
        await self._init_async()
        # Ensure schema is set correctly before each execution
        await self._async_conn.execute('SET search_path TO public')
        return await self._async_conn.fetch(sql, *parameters)

    async def executemany_sql_async(self, sql: str, parameters_list: list) -> None:
        await self._init_async()
        # Ensure schema is set correctly before execution
        await self._async_conn.execute('SET search_path TO public')
        for params in parameters_list:
            await self._async_conn.execute(sql, *params)

    async def _close_async(self) -> None:
        if self._async_conn:
            await self._pool.release(self._async_conn)
        if self._pool:
            await self._pool.close()
        self._async_tx = None
        self._async_conn = None
        self._pool = None

    async def clear_all_async(self) -> None:
        try:
            # Ensure no active transaction
            if self._async_tx:
                await self._async_tx.rollback()
                self._async_tx = None
                
            await self._init_async()
            
            # Check if public schema exists before trying to drop it
            exists = await self._async_conn.fetchval("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'public')")
            
            if exists:
                await self._async_conn.execute('DROP SCHEMA public CASCADE')
                
            # Always create the schema
            await self._async_conn.execute('CREATE SCHEMA public')
            await self._async_conn.execute('SET search_path TO public')
        except Exception as e:
            raise TrackError(e)

    # endregion ----------