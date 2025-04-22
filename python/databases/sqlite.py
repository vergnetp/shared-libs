import os, inspect
import sqlite3
import aiosqlite
from ..errors import TrackError
from .base import Database

class SqliteDatabase(Database):
    def __init__(self, database: str, alias: str = None, env: str = 'prod'):
        print("Database class info:")
        print(f"  - Module: {Database.__module__}")
        print(f"  - Defined in: {inspect.getfile(Database)}")
        print(f"  - Init signature: {inspect.signature(Database.__init__)}")
        super().__init__(
            database,
            None,
            None,
            None,
            None,
            alias,
            env
        )   

        # Sync connection
        self._conn = sqlite3.connect(self.database())
        self._cursor = self._conn.cursor()

        # Async connection
        self._async_conn = None       

    def is_connected(self) -> bool:
        try:
            self._conn.execute("SELECT 1")
            return True
        except:
            return False
        
    def type(self) -> str:
        return "sqlite"

    def placeholder(self) -> str:
        return "?"

    # region --- Sync methods ---
    def begin_transaction(self) -> None:
        self._conn.execute("BEGIN")

    def commit_transaction(self) -> None:
        self._conn.commit()

    def rollback_transaction(self) -> None:
        self._conn.rollback()

    def execute_sql(self, sql: str, parameters=()) -> list:
        if not self.is_connected():
            raise TrackError(Exception("Lost SQLite connection"))
        self._cursor.execute(sql, parameters)
        return self._cursor.fetchall()

    def executemany_sql(self, sql: str, parameters_list: list) -> None:
        if not self.is_connected():
            raise TrackError(Exception("Lost SQLite connection"))
        self._cursor.executemany(sql, parameters_list)

    def _close(self) -> None:
        self._cursor.close()
        self._conn.close()
    
    def clear_all(self) -> None:
        try:           
            self.close()
            os.remove(self.database())
        except Exception as e:
            raise TrackError(e)        
    # endregion ----------

    # region --- Async methods ---
    async def _init_async(self):
        if not self._async_conn:
            self._async_conn = await aiosqlite.connect(self.database())           

    async def begin_transaction_async(self) -> None:
        await self._init_async()
        await self._async_conn.execute("BEGIN")

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
        self._async_conn = None

    async def clear_all_async(self) -> None:
        try:            
            await self.close_async()
            if os.path.exists(self.database()):
                os.remove(self.database())            
        except Exception as e:
            raise TrackError(e)
    # endregion ----------