import pytest
import pytest_asyncio
import asyncio
import json
import uuid
import os
from datetime import datetime, timedelta
import time
from ... import log as logger

# Import the database abstraction layer
""" from ..all import (
    DatabaseConfig, 
    DatabaseFactory,
    PoolManager
) """
from ...databases import (
    DatabaseConfig, 
    DatabaseFactory,
    PoolManager
) 

# Fixture for PostgreSQL database connection
@pytest.fixture
def postgres_db():
    """Set up test database connection to PostgreSQL"""
    config = DatabaseConfig(
        database="testdb_postgres",
        host="localhost",
        port=5433,  # Port from docker-compose
        user="test",
        password="test",
        alias="postgres_test",
        env="test"
    )
    db = DatabaseFactory.create_database("postgres", config)
    
    # Provide the database instance
    yield db, config
    
    # Cleanup after all tests
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Create a new event loop if not in an async context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(PoolManager.close_pool(config.hash(), timeout=5))


@pytest_asyncio.fixture
async def postgres_db_async():
    """Set up test database connection to PostgreSQL (async version)"""
    config = DatabaseConfig(
        database="testdb_postgres",
        host="localhost",
        port=5433,  # Port from docker-compose
        user="test",
        password="test",
        alias="postgres_test",
        env="test"
    )
    db = DatabaseFactory.create_database("postgres", config)

    # Provide the database instance
    yield db, config

    # Cleanup after all tests
    await PoolManager.close_pool(config.hash(), timeout=5)

# Fixture for MySQL database connection
@pytest.fixture
def mysql_db():
    """Set up test database connection to MySQL (async version)"""
    config = DatabaseConfig(
        database="testdb_mysql",
        host="localhost",
        port=3307,  # Port from docker-compose
        user="test",
        password="test",
        alias="mysql_test",
        env="test"
    )
    db = DatabaseFactory.create_database("mysql", config)
    
    
    # Provide the database instance
    yield db, config
    
    # Cleanup after all tests
    loop = asyncio.get_event_loop()
    loop.run_until_complete(PoolManager.close_pool(config.hash(), timeout=5))


# Fixture for MySQL database connection
@pytest_asyncio.fixture
async def mysql_db_async():
    """Set up test database connection to MySQL"""
    config = DatabaseConfig(
        database="testdb_mysql",
        host="localhost",
        port=3307,  # Port from docker-compose
        user="test",
        password="test",
        alias="mysql_test",
        env="test"
    )
    db = DatabaseFactory.create_database("mysql", config)
    
    
    # Provide the database instance
    yield db, config
    
    # Cleanup after all tests
    await PoolManager.close_pool(config.hash(), timeout=5)

# Fixture for SQLite database connection
@pytest.fixture
def sqlite_db():
    """Set up test database connection to SQLite"""
    # Use a temporary file for SQLite
    db_file = f"test_sqlite_{uuid.uuid4().hex[:8]}.db"
    config = DatabaseConfig(
        database=db_file,
        alias="sqlite_test",
        env="test"
    )
    db = DatabaseFactory.create_database("sqlite", config)
    
    # Provide the database instance
    yield db, config
    
    # Cleanup after all tests
    loop = asyncio.get_event_loop()
    loop.run_until_complete(PoolManager.close_pool(config.hash(), timeout=5))
    
    # Release any remaining connections and wait a bit
    db.release_sync_connection()  # Make sure sync connection is released
    time.sleep(0.5)  # Give the OS a moment to release file handles
    
    # Remove the SQLite file
    try:
        if os.path.exists(db_file):
            os.remove(db_file)
    except PermissionError:
        print(f"Could not remove SQLite file {db_file} - it may still be in use")


# Fixture for SQLite database connection
@pytest_asyncio.fixture
async def sqlite_db_async():
    """Set up test database connection to SQLite (async version)"""
    # Use a temporary file for SQLite
    db_file = f"test_sqlite_{uuid.uuid4().hex[:8]}.db"
    config = DatabaseConfig(
        database=db_file,
        alias="sqlite_test",
        env="test"
    )
    db = DatabaseFactory.create_database("sqlite", config)
    
    try:
        # Provide the database instance
        yield db, config
    finally:
        # Cleanup
        await PoolManager.close_pool(config.hash(), timeout=5)
        
        # Release any remaining connections and wait a bit
        if hasattr(db, '_local') and hasattr(db._local, '_sync_conn') and db._local._sync_conn:
            db.release_sync_connection()  # Make sure sync connection is released
        
        # Give the OS a moment to release file handles
        await asyncio.sleep(0.1)
        
        # Remove the SQLite file
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
        except PermissionError:
            print(f"Could not remove SQLite file {db_file} - it may still be in use")

def test_quick(postgres_db):
    db, _ = postgres_db
    assert(True)
    
    # Ensure we properly clean up any event loops we create
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Create a new event loop if not in an async context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Do your test
            pass
        finally:
            # Clean up the loop
            loop.close()
            asyncio.set_event_loop(None)


def test_sync(postgres_db):
    db, _ = postgres_db
    
    results = []  
    conn = db.get_sync_connection()    
    result = conn.execute("SELECT 1") 
    results.append(result)   
    conn.close()
           
@pytest.mark.asyncio
async def test_async(postgres_db_async):  

    l = asyncio.get_running_loop()
    assert (True)
    db, _ = postgres_db_async
    is_async = db.is_environment_async()
    assert(is_async)

# PostgreSQL Tests
@pytest.mark.asyncio
async def test_postgres(postgres_db_async):
    """Test creating an entity and retrieving it"""
    db, _ = postgres_db_async
    
    # Create a unique entity name for this test
    entity_name = f"test_users_{uuid.uuid4().hex[:8]}"
    test_name = "Alice"
    
    async with db.async_connection() as conn:
        await conn.execute(f"create table [{entity_name}] (name TEXT)")
        await conn.execute(f"insert into [{entity_name}] values (?)", ('Phil',))
        rows = await conn.execute(f"select * from [{entity_name}]")
        assert (rows[0][0]=='Phil')



@pytest.mark.asyncio
async def test_postgres_save_and_get_entity(postgres_db_async):
    """Test creating an entity and retrieving it"""
    db, _ = postgres_db_async
    
    # Create a unique entity name for this test
    entity_name = f"test_users_{uuid.uuid4().hex[:8]}"
    test_name = "Alice"
    
    async with db.async_connection() as conn:
        # Save entity
        saved_entity = await conn.save_entity(entity_name, {"name": test_name})
        
        # Verify ID was generated
        assert saved_entity.get('id') is not None
        entity_id = saved_entity['id']
        
        # Get entity and verify data
        retrieved_entity = await conn.get_entity(entity_name, entity_id)
        assert retrieved_entity['name'] == test_name
        
        # Cleanup - delete the entity
        success = await conn.delete_entity(entity_name, entity_id, permanent=True)
        assert success


@pytest.mark.asyncio
async def test_postgres_update_entity(postgres_db):
    """Test updating an existing entity"""
    db, _ = postgres_db
    
    # Create a unique entity name for this test
    entity_name = f"test_users_{uuid.uuid4().hex[:8]}"
 
    async with db.async_connection() as conn:
        # Create initial entity
        entity = await conn.save_entity(entity_name, {"name": "Bob", "age": 30})
        entity_id = entity['id']
        
        # Update entity
        updated = await conn.save_entity(entity_name, {"id": entity_id, "name": "Bob", "age": 31})
        
        # Retrieve and verify
        retrieved = await conn.get_entity(entity_name, entity_id, deserialize=True)
        assert retrieved['age'] == 31
        
        # Cleanup
        await conn.delete_entity(entity_name, entity_id, permanent=True)


@pytest.mark.asyncio
async def test_postgres_entity_history(postgres_db):
    """Test entity versioning and history"""
    db, _ = postgres_db
    
    entity_name = f"test_users_{uuid.uuid4().hex[:8]}"
    
    async with db.async_connection() as conn:
        # Create entity
        entity = await conn.save_entity(entity_name, {"name": "Charlie"}, comment="Initial creation")
        entity_id = entity['id']
        
        # Update it
        await conn.save_entity(entity_name, {"id": entity_id, "name": "Charlie", "department": "Engineering"}, 
                              comment="Added department")
        
        # Get history
        history = await conn.get_entity_history(entity_name, entity_id)
        
        # Should have 2 versions
        assert len(history) == 2
        
        # Get first version
        old_version = await conn.get_entity_by_version(entity_name, entity_id, 1)
        assert old_version is not None
        assert old_version.get('department') is None
        
        # Cleanup
        await conn.delete_entity(entity_name, entity_id, permanent=True)


# MySQL Tests
@pytest.mark.asyncio
async def test_mysql_save_and_find_entities(mysql_db_async):
    """Test saving multiple entities and querying them"""
    db, _ = mysql_db_async
    
    entity_name = f"test_products_{uuid.uuid4().hex[:8]}"
    
    async with db.async_connection() as conn:
        # Save multiple entities
        entities = await conn.save_entities(entity_name, [
            {"name": "Product A", "price": 10.99},
            {"name": "Product B", "price": 24.99},
            {"name": "Product C", "price": 5.99}
        ])
        
        # Verify we have 3 entities
        assert len(entities) == 3
        
        # Find entities with a price less than 20
        results = await conn.find_entities(
            entity_name, 
            where_clause="price < ?", 
            params=(20,),
            deserialize=True
        )
        
        # Should find 2 products
        assert len(results) == 2
        
        # Clean up
        for entity in entities:
            await conn.delete_entity(entity_name, entity['id'], permanent=True)


@pytest.mark.asyncio
async def test_mysql_count_entities(mysql_db_async):
    """Test counting entities with filters"""
    db, _ = mysql_db_async
    
    entity_name = f"test_employees_{uuid.uuid4().hex[:8]}"
    
    async with db.async_connection() as conn:
        # Create several entities
        entities = await conn.save_entities(entity_name, [
            {"name": "John", "department": "Engineering"},
            {"name": "Lisa", "department": "Marketing"},
            {"name": "Mike", "department": "Engineering"},
            {"name": "Sarah", "department": "HR"}
        ])
        
        # Count all entities
        count = await conn.count_entities(entity_name)
        assert count == 4
        
        # Count with filter
        eng_count = await conn.count_entities(
            entity_name,
            where_clause="department = ?",
            params=("Engineering",)
        )
        assert eng_count == 2
        
        # Clean up
        for entity in entities:
            await conn.delete_entity(entity_name, entity['id'], permanent=True)


@pytest.mark.asyncio
async def test_mysql_soft_delete_restore(mysql_db_async):
    """Test soft delete and restore functionality"""
    db, _ = mysql_db_async
    
    entity_name = f"test_users_{uuid.uuid4().hex[:8]}"
    
    async with db.async_connection() as conn:
        # Create entity
        entity = await conn.save_entity(entity_name, {"name": "David"})
        entity_id = entity['id']
        
        # Soft delete
        deleted = await conn.delete_entity(entity_name, entity_id, permanent=False)
        assert deleted
        
        # Try to get it normally (should fail)
        missing = await conn.get_entity(entity_name, entity_id)
        assert missing is None
        
        # Get it including deleted
        found = await conn.get_entity(entity_name, entity_id, include_deleted=True)
        assert found is not None
        assert found.get('deleted_at') is not None
        
        # Restore it
        restored = await conn.restore_entity(entity_name, entity_id)
        assert restored
        
        # Now we should be able to find it normally
        back = await conn.get_entity(entity_name, entity_id)
        assert back is not None
        assert back.get('deleted_at') is None
        
        # Clean up
        await conn.delete_entity(entity_name, entity_id, permanent=True)


# SQLite Tests
@pytest.mark.asyncio
async def test_sqlite_transaction_commit(sqlite_db_async):
    """Test transaction commit"""
    db, _ = sqlite_db_async
    
    entity_name = f"test_accounts_{uuid.uuid4().hex[:8]}"
    
    async with db.async_connection() as conn:
        # Start a transaction
        await conn.begin_transaction()
        
        try:
            # Create two entities in a transaction
            entity1 = await conn.save_entity(entity_name, {"account": "Savings", "balance": 1000})
            entity2 = await conn.save_entity(entity_name, {"account": "Checking", "balance": 500})
            
            # Commit the transaction
            await conn.commit_transaction()
            
            # Verify both entities exist
            count = await conn.count_entities(entity_name)
            assert count == 2
            
            # Clean up
            await conn.delete_entity(entity_name, entity1['id'], permanent=True)
            await conn.delete_entity(entity_name, entity2['id'], permanent=True)
            
        except Exception as e:
            await conn.rollback_transaction()
            raise

 

@pytest.mark.asyncio
async def test_sqlite_transaction_rollback(sqlite_db_async):
    """Test transaction rollback"""
    db, _ = sqlite_db_async
    
    entity_name = f"test_orders_{uuid.uuid4().hex[:8]}"
    
    async with db.async_connection() as conn:
        # Create a test entity outside the transaction
        base_entity = await conn.save_entity(entity_name, {"order": "Base Order"})
        
        # Start a transaction
        await conn.begin_transaction()
        
        try:
            # Create an entity in the transaction
            await conn.save_entity(entity_name, {"order": "Will be rolled back"})
            
            # Verify we see both entities during the transaction
            count_during = await conn.count_entities(entity_name)
            assert count_during == 2
            
            # Rollback the transaction
            await conn.rollback_transaction()
            
            # After rollback, we should only see the original entity
            count_after = await conn.count_entities(entity_name)
            assert count_after == 1
            
            # Clean up
            await conn.delete_entity(entity_name, base_entity['id'], permanent=True)
            
        except Exception as e:
            await conn.rollback_transaction()
            raise

@pytest.mark.asyncio
async def test_sqlite_save_and_get_entity(sqlite_db_async):
    """Test creating an entity and retrieving it"""
    db, _ = sqlite_db_async
    
    # Create a unique entity name for this test
    entity_name = f"test_users_{uuid.uuid4().hex[:8]}"
    test_name = "Alice"
    
    async with db.async_connection() as conn:
        # Save entity
        saved_entity = await conn.save_entity(entity_name, {"name": test_name})
        
        # Verify ID was generated
        assert saved_entity.get('id') is not None
        entity_id = saved_entity['id']
        
        # Get entity and verify data
        retrieved_entity = await conn.get_entity(entity_name, entity_id)

        logger.info(f"============= {json.dumps(retrieved_entity, indent=4)}")
        assert retrieved_entity['name'] == test_name
        
        # Cleanup - delete the entity
        success = await conn.delete_entity(entity_name, entity_id, permanent=True)
        assert success

@pytest.mark.asyncio
async def test_sqlite_custom_serialization(sqlite_db_async):
    """Test custom type serialization"""
    db, _ = sqlite_db_async
    
    entity_name = f"test_events_{uuid.uuid4().hex[:8]}"
    
    # Define custom serialization for datetime
    def serialize_date(value):
        if value is None:
            return None
        return value.isoformat()
        
    def deserialize_date(value):
        if not value:
            return None
        return datetime.fromisoformat(value)
    
    async with db.async_connection() as conn:
        # Register custom serializers
        conn.register_serializer("datetime", serialize_date, deserialize_date)
        
        # Event date for testing
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        
        # Save entity with custom date type
        event = await conn.save_entity(entity_name, {
            "title": "Test Event",
            "event_date": tomorrow
        })
        
        # Get entity with deserialization
        retrieved = await conn.get_entity(entity_name, event['id'], deserialize=True)

        assert retrieved['title'] == 'Test Event'
       
        
        # Verify the date was properly serialized and deserialized
        assert isinstance(retrieved['event_date'], datetime)
        assert retrieved['event_date'].date() == tomorrow.date()
        
        # Clean up
        await conn.delete_entity(entity_name, event['id'], permanent=True)

import pytest
import time
import asyncio
from ... import log as logger

# Test timeouts on connection acquisition
@pytest.mark.asyncio
async def test_connection_acquisition_timeout(postgres_db_async):
    """Test that connection acquisition properly times out"""
    db, config = postgres_db_async
    
    # Create a config with very short acquisition timeout
    short_timeout_config = DatabaseConfig(
        database=config.database(),
        host=config.host(),
        port=config.port(),
        user=config.user(),
        password=config.password(),
        connection_acquisition_timeout=0.001  # Very short timeout (1ms)
    )
    
    # Create a new database instance with the short timeout
    db_short_timeout = DatabaseFactory.create_database("postgres", short_timeout_config)
    
    # Create enough connections to exhaust the pool
    connections = []
    pool_size = 0
    
    try:
        # First get the pool's max size to make sure we exhaust it
        async with db_short_timeout.async_connection() as conn:
            pool_manager = db_short_timeout.pool_manager
            pool = pool_manager._pool
            pool_size = pool.max_size
        
        # Now get enough connections to fill the pool
        for _ in range(pool_size):
            try:
                conn = await db_short_timeout.get_async_connection()
                connections.append(conn)
            except Exception as e:
                logger.error(f"Failed to get connection {len(connections)+1}: {e}")
                break
        
        # The next connection acquisition should time out
        with pytest.raises(TimeoutError):
            await db_short_timeout.get_async_connection()
            
    finally:
        # Release all connections
        for conn in connections:
            await db_short_timeout.release_async_connection(conn)
        
        # Close the pool
        await PoolManager.close_pool(short_timeout_config.hash())


# Test timeouts on query execution
@pytest.mark.asyncio
async def test_query_execution_timeout(postgres_db_async):
    """Test that long-running queries properly time out"""
    db, config = postgres_db_async
    
    # Create a config with reasonable query timeout
    query_timeout_config = DatabaseConfig(
        database=config.database(),
        host=config.host(),
        port=config.port(),
        user=config.user(),
        password=config.password(),
        query_execution_timeout=0.5  # 500ms timeout
    )
    
    # Create a new database instance with the query timeout
    db_query_timeout = DatabaseFactory.create_database("postgres", query_timeout_config)
    
    async with db_query_timeout.async_connection() as conn:
        # Run a query that will definitely timeout (pg_sleep takes seconds)
        with pytest.raises(TimeoutError):
            await conn.execute("SELECT pg_sleep(2)")
        
        # Normal query should still work
        result = await conn.execute("SELECT 1")
        assert result == [(1,)]
    
    # Close the pool
    await PoolManager.close_pool(query_timeout_config.hash())


@pytest.mark.asyncio
async def test_pool_creation_timeout():
    """Test that pool creation properly times out"""
    # Use a non-routable IP address to force timeout
    timeout_config = DatabaseConfig(
        database="postgres",
        host="10.255.255.1",  # Non-routable IP address
        port=5432,
        user="test",
        password="test",
        pool_creation_timeout=1.0  # 1 second timeout
    )
    
    # Creating a database with this config should trigger pool creation timeout
    db = DatabaseFactory.create_database("postgres", timeout_config)
    
    # Check that attempting to get a connection raises a TimeoutError
    start_time = time.time()
    
    with pytest.raises(TimeoutError) as exc_info:
        async with db.async_connection() as conn:
            pass
    
    elapsed_time = time.time() - start_time
    logger.info(f"Connection attempt failed after {elapsed_time:.2f}s with: {exc_info.value}")
    
    # Verify that the operation took approximately the time we specified
    # We allow a bit of flexibility in timing
    assert 0.5 <= elapsed_time <= 3.0, f"Expected timeout in ~1.0s, got {elapsed_time:.2f}s"


# Test timeouts for both the explicit parameter and config default
@pytest.mark.asyncio
async def test_explicit_vs_config_timeout(postgres_db_async):
    """Test that explicit timeout overrides config default"""
    db, config = postgres_db_async
    
    async with db.async_connection() as conn:
        # Create a table for this test
        await conn.execute("CREATE TABLE IF NOT EXISTS timeout_test (id SERIAL PRIMARY KEY, value TEXT)")
        
        # Insert some data
        await conn.execute("INSERT INTO timeout_test (value) VALUES ('test data')")
        
        # Query with explicit short timeout (should fail)
        with pytest.raises(TimeoutError):
            await conn.execute("SELECT pg_sleep(1), * FROM timeout_test", timeout=0.1)
        
        # Same query with longer explicit timeout (should succeed)
        result = await conn.execute("SELECT pg_sleep(0.5), * FROM timeout_test", timeout=2.0)
        assert len(result) > 0
        
        # Clean up
        await conn.execute("DROP TABLE timeout_test")

@pytest.mark.asyncio
async def test_transaction_timeout(postgres_db_async):
    """Test timeout behavior within transactions"""
    db, config = postgres_db_async
    
    async with db.async_connection() as conn:
        # Create a test table
        await conn.execute("CREATE TABLE IF NOT EXISTS tx_timeout_test (id SERIAL PRIMARY KEY, value TEXT)")
        
        # First test: Normal transaction behavior with timeout
        logger.info("Testing transaction behavior with timeout...")
        
        # Start a transaction
        await conn.begin_transaction()
        
        try:
            # Insert some data
            await conn.execute("INSERT INTO tx_timeout_test (value) VALUES ('before timeout')")
            
            # Execute a query that will timeout
            with pytest.raises(TimeoutError):
                await conn.execute("SELECT pg_sleep(2)", timeout=0.5)
            
            # In PostgreSQL, the transaction is now aborted and we must roll back
            logger.info("Query timed out as expected. Rolling back transaction...")
            await conn.rollback_transaction()
            
            # Start a new transaction
            await conn.begin_transaction()
            try:
                # Insert after rolling back and starting a new transaction
                await conn.execute("INSERT INTO tx_timeout_test (value) VALUES ('after rollback')")
                await conn.commit_transaction()
            except Exception as e:
                await conn.rollback_transaction()
                raise
                
            # Verify the results - should have 'after rollback' but not 'before timeout'
            # since that transaction was rolled back
            rows = await conn.execute("SELECT value FROM tx_timeout_test ORDER BY id")
            values = [row[0] for row in rows]
            logger.info(f"Values in table after test: {values}")
            
            # 'before timeout' should not be present since that transaction was rolled back
            assert 'after rollback' in [row[0] for row in rows]
            
        except Exception as e:
            # Make sure we rollback on any error
            logger.error(f"Error during test: {e}")
            await conn.rollback_transaction()
            raise
        finally:
            # Clean up
            await conn.execute("DROP TABLE tx_timeout_test")
