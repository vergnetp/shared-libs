import pytest
import pytest_asyncio
import time
import asyncio
import pymysql

from ..sqlite import SqliteDatabase
from ..mysql import MySqlDatabase
from ..postgres import PostgresDatabase

@pytest.fixture(scope="session")
def mysql_config():
    return {
        "database": "testdb_mysql",  # Match exact database name
        "host": "localhost",
        "port": 3307,                # Use port 3307 as mapped in docker-compose
        "user": "test",              # Match existing user
        "password": "test",          # Match existing password
        "charset": "utf8mb4",
        "autocommit": True           # For session control
    }

@pytest.fixture(scope="session")
def postgres_config():
    return dict(host="localhost", port=5433, user="test", password="test", database="testdb_postgres")



@pytest.fixture
def sqlite_db(tmp_path):
    db = SqliteDatabase(database=str(tmp_path / "test.db"), env="test")
    yield db
    db.clear_all()





def _init_mysql_db(config, retries=15, delay=3):
    """Initialize MySQL connection with improved retry logic"""
    last_error = None
    db_name = config.get('database')
    
    # Try different approaches in sequence for resiliency
    for i in range(retries):
        try:
            # First connect as root to ensure database exists
            root_config = {
                'host': config.get('host'),
                'port': config.get('port'),
                'user': 'root',
                'password': 'root',
                'connect_timeout': 10,
                'charset': 'utf8mb4'
            }
            
            print(f"Attempt {i+1}/{retries}: Connecting as root to setup database...")
            conn = pymysql.connect(**root_config)
            cursor = conn.cursor()
            
            # Create the database and ensure user has permissions
            print(f"Creating database if needed: {db_name}")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
            
            # Create user and grant permissions
            user = config.get('user')
            password = config.get('password')
            print(f"Setting up user permissions for {user}")
            
            # Try to create user if it doesn't exist
            try:
                cursor.execute(f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY '{password}'")
            except:
                print("User may already exist, continuing...")
                
            # Grant permissions to the user
            cursor.execute(f"GRANT ALL PRIVILEGES ON {db_name}.* TO '{user}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
            
            # Close root connection
            cursor.close()
            conn.close()
            
            # Now connect with the regular user
            print(f"Connecting as {user} to verify access...")
            db = MySqlDatabase(**config, env="test", alias="unit_test_mysql_db")
            
            # Test executing a simple query to verify connection
            try:
                db.execute_sql("SELECT 1")
                print(f"Successfully connected to MySQL database {db_name}")
                return db
            except Exception as e:
                print(f"Error verifying connection: {e}")
                raise
                
        except Exception as e:
            last_error = e
            error_msg = str(e)
            print(f"MySQL connection error (attempt {i+1}): {error_msg}")
            time.sleep(delay)
    
    raise RuntimeError(f"MySQL failed to connect after {retries} retries. Last error: {last_error}")

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

@pytest_asyncio.fixture
async def mysql_db_async(mysql_config):
    # Close any existing pool - start fresh for each test
    if MySqlDatabase._pool:
        try:
            MySqlDatabase._pool.close()
            await MySqlDatabase._pool.wait_closed()
        except:
            pass
        MySqlDatabase._pool = None
        
    # Create a new db instance
    db = _init_mysql_db(mysql_config)
    
    # Create a new pool for this test
    try:
        await MySqlDatabase.initialize_pool_if_needed(mysql_config)
    except Exception as e:
        pytest.skip(f"Failed to initialize MySQL database pool: {e}")
    
    try:
        # Initialize and clear before test runs
        await db._init_async()
        await db.clear_all_async()
        yield db
    finally:
        # Clean up after test
        try:
            await db.close_async()
        except:
            pass
        
        # Close the pool after each test to prevent test interference
        if MySqlDatabase._pool:
            try:
                MySqlDatabase._pool.close()
                await MySqlDatabase._pool.wait_closed()
                MySqlDatabase._pool = None
            except:
                pass

# Fixture to close pool at the end of all tests
@pytest_asyncio.fixture(scope="session")
async def close_mysql_pools():
    yield
    if MySqlDatabase._pool:
        try:
            MySqlDatabase._pool.close()
            await MySqlDatabase._pool.wait_closed()
        except:
            pass