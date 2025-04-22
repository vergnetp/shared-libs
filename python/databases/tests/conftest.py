import pytest
import time
import pymysql
from ..sqlite import SqliteDatabase
from ..mysql import MySqlDatabase
from ..postgres import PostgresDatabase

@pytest.fixture(scope="session")
def mysql_config():
    return dict(host="localhost", port=3307, user="test", password="test", database="testdb_mysql")

@pytest.fixture(scope="session")
def postgres_config():
    return dict(host="localhost", port=5433, user="test", password="test", database="testdb_postgres")

@pytest.fixture
def sqlite_db(tmp_path):
    db = SqliteDatabase(database=str(tmp_path / "test.db"), env="test")
    yield db
    db.clear_all()

@pytest.fixture
def mysql_db(mysql_config):
    retries = 10
    delay = 2
    db = None

    for i in range(retries):
        try:
            db = MySqlDatabase(**mysql_config, env="test")
            break
        except pymysql.err.OperationalError as e:
            print(f"MySQL not ready yet (try {i+1}/{retries}): {e}")
            time.sleep(delay)
    else:
        raise RuntimeError("MySQL failed to connect after retries.")

    yield db
    try:
        db.clear_all()
    except Exception as e:
        print(f"Error while closing connection of {db.database()}: {e}")

@pytest.fixture
def postgres_db(postgres_config):
    retries = 10
    delay = 2
    for i in range(retries):
        try:
            db = PostgresDatabase(**postgres_config, env="test")
            break
        except Exception as e:
            print(f"Postgres not ready yet (try {i+1}/{retries}): {e}")
            time.sleep(delay)
    else:
        raise RuntimeError("Postgres failed to connect after retries.")

    yield db
    try:
        db.clear_all()
    except Exception as e:
        print(f"Error while closing connection of {db.database()}: {e}")