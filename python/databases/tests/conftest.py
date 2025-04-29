import pytest
import pytest_asyncio
import time
import asyncio
import pymysql
from pathlib import Path
import os

from ..sqlite import SqliteDatabase
from ..mysql import MySqlDatabase
from ..postgres import PostgresDatabase


@pytest.fixture
def sqlite_db(tmp_path):
    """Create a SQLite database in a temporary directory for testing"""
    from ..sqlite import SqliteDatabase
    
    db_path = tmp_path / "test.db"
    db = SqliteDatabase(database=str(db_path), env="test", alias="test_sqlite")
    
    yield db
    
    # Close connections properly
    try:
        db.close()
        
        # Try to delete the file, but don't fail the test if it's in use
        try:
            if db_path.exists():
                os.chmod(str(db_path), 0o666)  # Ensure we have write permissions
                # Wait a moment for any file handles to be released
                for _ in range(3):
                    try:
                        os.remove(str(db_path))
                        break
                    except OSError:
                        time.sleep(0.1)
        except Exception as e:
            print(f"Note: Could not delete test database file: {e}")
    except Exception as e:
        print(f"Error cleaning up SQLite DB: {e}")

@pytest.fixture(scope="session")
def mysql_config():
    """Configuration for MySQL test database"""
    return {
        "database": "testdb_mysql",  # Match exact database name in docker-compose
        "host": "localhost",
        "port": 3307,                # Use port 3307 as mapped in docker-compose
        "user": "test",              # Match existing user
        "password": "test",          # Match existing password
        "charset": "utf8mb4",
        "autocommit": True           # For session control
    }

@pytest.fixture(scope="session")
def postgres_config():
    """Configuration for PostgreSQL test database"""
    return {
        "host": "localhost", 
        "port": 5433,               # Use port 5433 as mapped in docker-compose
        "user": "test", 
        "password": "test", 
        "database": "testdb_postgres"
    }


@pytest.fixture
def mysql_db(mysql_config):
    """Create a MySQL database connection for testing with retries"""
    retries = 10
    delay = 2
    db = None

    # Try to connect with retries for container startup delays
    for i in range(retries):
        try:
            db = MySqlDatabase(**mysql_config, env="test")
            # Test connection with a simple query
            db.execute_sql("SELECT 1")
            break
        except Exception as e:
            print(f"MySQL not ready yet (try {i+1}/{retries}): {e}")
            time.sleep(delay)
    
    if db is None:
        pytest.skip("MySQL connection failed after multiple retries")

    yield db
    
    try:
        db.clear_all()
        db.close()
    except Exception as e:
        print(f"Error cleaning up MySQL DB: {e}")

@pytest_asyncio.fixture
async def mysql_db_async(mysql_config):
    """Create an async MySQL database connection for testing"""
    # Close any existing pool - start fresh for each test
    if MySqlDatabase._pool:
        try:
            MySqlDatabase._pool.close()
            await MySqlDatabase._pool.wait_closed()
        except Exception:
            pass
        MySqlDatabase._pool = None
        
    # Create a new db instance
    db = None
    retries = 10
    delay = 2
    
    # Try to connect with retries
    for i in range(retries):
        try:
            db = MySqlDatabase(**mysql_config, env="test", alias="test_mysql_async")
            # Test connection
            db.execute_sql("SELECT 1")
            break
        except Exception as e:
            print(f"MySQL async not ready yet (try {i+1}/{retries}): {e}")
            time.sleep(delay)
    
    if db is None:
        pytest.skip("MySQL async connection failed after multiple retries")
        
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
        except Exception:
            pass
        
        # Close the pool after each test to prevent test interference
        if MySqlDatabase._pool:
            try:
                MySqlDatabase._pool.close()
                await MySqlDatabase._pool.wait_closed()
                MySqlDatabase._pool = None
            except Exception:
                pass

@pytest.fixture(scope="session")
def postgres_db(postgres_config):
    """Create a PostgreSQL database connection for testing"""
    retries = 10
    delay = 2
    db = None

    # Try to connect with retries
    for i in range(retries):
        try:
            db = PostgresDatabase(**postgres_config, env="test")
            # Test connection
            db.execute_sql("SELECT 1")
            break
        except Exception as e:
            print(f"PostgreSQL not ready yet (try {i+1}/{retries}): {e}")
            time.sleep(delay)
    
    if db is None:
        pytest.skip("PostgreSQL connection failed after multiple retries")

    yield db
    
    try:
        db.clear_all()
        db.close()
    except Exception as e:
        print(f"Error cleaning up PostgreSQL DB: {e}")

@pytest_asyncio.fixture
async def postgres_db_async(postgres_config):
    """Create an async PostgreSQL database connection for testing"""
    # Close any existing pool - start fresh for each test
    if PostgresDatabase._pool:
        try:
            await PostgresDatabase._pool.close()
        except Exception:
            pass
        PostgresDatabase._pool = None
        
    # Create a new db instance
    db = None
    retries = 10
    delay = 2
    
    # Try to connect with retries
    for i in range(retries):
        try:
            db = PostgresDatabase(**postgres_config, env="test", alias="test_postgres_async")
            # Test connection
            db.execute_sql("SELECT 1")
            break
        except Exception as e:
            print(f"PostgreSQL async not ready yet (try {i+1}/{retries}): {e}")
            time.sleep(delay)
    
    if db is None:
        pytest.skip("PostgreSQL async connection failed after multiple retries")
    
    try:
        # Initialize and clear before test runs
        await db._init_async()
        await db.clear_all_async()
        yield db
    finally:
        # Clean up after test
        try:
            await db.close_async()
        except Exception:
            pass
        
        # Close the pool after each test to prevent test interference
        if PostgresDatabase._pool:
            try:
                await PostgresDatabase._pool.close()
                PostgresDatabase._pool = None
            except Exception:
                pass

# Helper function to check if Docker containers are running
def are_docker_containers_running():
    """Check if required Docker containers are running"""
    try:
        import docker
        client = docker.from_env()
        containers = client.containers.list()
        
        # Check for required containers
        mysql_running = any("mysql" in container.name.lower() for container in containers)
        postgres_running = any("postgres" in container.name.lower() for container in containers)
        
        return mysql_running and postgres_running
    except Exception as e:
        print(f"Error checking Docker containers: {e}")
        return False
    
# Skip database tests if containers aren't running
def pytest_collection_modifyitems(config, items):
    """Skip database tests if Docker containers aren't running"""
    if not are_docker_containers_running():
        skip_db = pytest.mark.skip(reason="Docker containers not running")
        for item in items:
            if "mysql_db" in item.fixturenames or "postgres_db" in item.fixturenames:
                item.add_marker(skip_db)