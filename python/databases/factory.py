def DatabaseFactory(db_type: str, **kwargs):
    if db_type == "sqlite":
        from .sqlite import SqliteDatabase
        return SqliteDatabase(**kwargs)
    elif db_type == "mysql":
        from .mysql import MySqlDatabase
        return MySqlDatabase(**kwargs)
    elif db_type == "postgres":
        from .postgres import PostgresDatabase
        return PostgresDatabase(**kwargs)
    else:
        raise ValueError(f"Unsupported db_type: {db_type}")