from .config import DatabaseConfig
from .database import ConnectionManager
from .backends import PostgresDatabase, MySqlDatabase, SqliteDatabase

class DatabaseFactory:
    '''Factory to create a DAL to specific backends. Currently support 'postgres', 'mysql' and 'sqlite'.'''
    @staticmethod
    def create_database(db_type: str, db_config: DatabaseConfig) -> ConnectionManager:
        """Factory method to create the appropriate database instance"""
        if db_type.lower() == 'postgres':    
            return PostgresDatabase(**db_config.config())
        elif db_type.lower() == 'mysql':
            return MySqlDatabase(**db_config.config())
        elif db_type.lower() == 'sqlite':
            return SqliteDatabase(**db_config.config())
        else:
            raise ValueError(f"Unsupported database type: {db_type}")