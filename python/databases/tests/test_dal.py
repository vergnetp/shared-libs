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
    loop = asyncio.get_event_loop()
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

def test_quick(postgres_db):
    db, _ = postgres_db
    assert(True)


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
async def test_sqlite_transaction_commit(sqlite_db):
    """Test transaction commit"""
    db, _ = sqlite_db
    
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
async def test_sqlite_transaction_rollback(sqlite_db):
    """Test transaction rollback"""
    db, _ = sqlite_db
    
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
async def test_sqlite_save_and_get_entity(sqlite_db):
    """Test creating an entity and retrieving it"""
    db, _ = sqlite_db
    
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
async def test_sqlite_custom_serialization(sqlite_db):
    """Test custom type serialization"""
    db, _ = sqlite_db
    
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


# Add a simple command to run the tests
if __name__ == "__main__":
    pytest.main(["-v"])