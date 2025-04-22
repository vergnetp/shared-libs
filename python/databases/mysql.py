import pymysql
import aiomysql
from ..errors import TrackError
from .base import Database

class MySqlDatabase(Database):
    def __init__(self, database: str, host: str=None, port: int=None, user: str=None, password: str=None, alias: str = None, env: str = 'prod'):
        super().__init__(database, host, port, user, password, alias, env)

        # Sync connection
        self._conn = pymysql.connect(**self.config())
        self._cursor = self._conn.cursor()

        # Async connection (init in async flow)
        self._pool = None
        self._async_conn = None      

    def is_connected(self) -> bool:
        try:
            self._conn.ping(reconnect=True)
            return True
        except:
            return False

    def type(self) -> str:
        return "mysql"

    def placeholder(self) -> str:
        return "%s"

    # region --- Sync methods ---
    def begin_transaction(self) -> None:
        self._conn.begin()

    def commit_transaction(self) -> None:
        self._conn.commit()

    def rollback_transaction(self) -> None:
        self._conn.rollback()

    def execute_sql(self, sql: str, parameters=()) -> list:
        if not self.is_connected():
            raise TrackError(Exception("Lost MySQL connection"))
        self._cursor.execute(sql, parameters)
        return self._cursor.fetchall()

    def executemany_sql(self, sql: str, parameters_list: list) -> None:
        if not self.is_connected():
            raise TrackError(Exception("Lost MySQL connection"))
        self._cursor.executemany(sql, parameters_list)

    def _close(self) -> None:
        self._cursor.close()
        self._conn.close()
    
    def clear_all(self) -> None:
        try:            
            db_name = self.config().get("database")  # updated
            self.execute_sql(f'DROP DATABASE IF EXISTS {db_name}')
            self.execute_sql(f'CREATE DATABASE {db_name}')
        except Exception as e:
            raise TrackError(e)
    # endregion ----------

    # region --- Async methods ---
    async def _init_async(self):
        if self._pool is None:
            cfg = self.config().copy()
            cfg["db"] = cfg.pop("database")
            self._pool = await aiomysql.create_pool(**cfg)
        if self._async_conn is None:
            self._async_conn = await self._pool.acquire()
          
    async def begin_transaction_async(self) -> None:
        await self._init_async()
        await self._async_conn.begin()

    async def commit_transaction_async(self) -> None:
        await self._init_async()
        await self._async_conn.commit()

    async def rollback_transaction_async(self) -> None:
        await self._init_async()
        await self._async_conn.rollback()

    async def execute_sql_async(self, sql: str, parameters=()) -> list:
        await self._init_async()
        async with self._async_conn.cursor() as cursor:
            await cursor.execute(sql, parameters)
            return await cursor.fetchall()

    async def executemany_sql_async(self, sql: str, parameters_list: list) -> None:
        await self._init_async()
        async with self._async_conn.cursor() as cursor:
            await cursor.executemany(sql, parameters_list)

    async def _close_async(self) -> None:
        if self._async_conn:
            await self._pool.release(self._async_conn)
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()       
        self._async_conn = None
        self._pool = None
    
    async def clear_all_async(self) -> None:
        try:            
            db_name = self.config().get("database")  # updated
            await self.execute_sql_async(f'DROP DATABASE IF EXISTS {db_name}')
            await self.execute_sql_async(f'CREATE DATABASE {db_name}')
        except Exception as e:
            raise TrackError(e)