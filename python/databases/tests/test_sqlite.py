import os
import pytest
import pytest_asyncio
import asyncio
import time
from pathlib import Path

# Mark all tests as SQLite tests
pytestmark = pytest.mark.sqlite

def test_sqlite_save_and_fetch(sqlite_db):
    """Test basic save and fetch functionality"""
    entity = {"id": "1", "name": "Alice"}
    sqlite_db.save_entity("users", entity)
    result = sqlite_db.get_entity("users", "1")
    assert result["id"] == "1"
    assert result["name"] == "Alice"

def test_sqlite_save_multiple_entities(sqlite_db):
    """Test saving multiple entities at once"""
    entities = [
        {"id": "2", "name": "Bob", "age": 30},
        {"id": "3", "name": "Charlie", "age": 25},
        {"id": "4", "name": "David", "age": 35}
    ]
    
    sqlite_db.save_entities("users", entities)
    
    # Verify all entities were saved
    results = sqlite_db.get_entities("users")
    assert len(results) == 3
    
    # Check specific entity
    result = sqlite_db.get_entity("users", "3")
    assert result["name"] == "Charlie"
    assert result["age"] == "25"  # Stored as string

def test_sqlite_transactions(sqlite_db):
    """Test transaction functionality"""
    # Start a transaction
    sqlite_db.begin_transaction()
    
    try:
        # Save entity in transaction - explicitly set auto_commit=False
        sqlite_db.save_entity("products", {"id": "p1", "name": "Product 1"}, auto_commit=False)
        
        # Verify entity exists within transaction
        result = sqlite_db.get_entity("products", "p1")
        assert result is not None
        assert result["name"] == "Product 1"
        
        # Rollback changes
        sqlite_db.rollback_transaction()
        
        # Verify entity no longer exists
        result = sqlite_db.get_entity("products", "p1")
        assert result is None
    except Exception as e:
        sqlite_db.rollback_transaction()
        raise

def test_sqlite_transaction_context_manager(sqlite_db):
    """Test transaction context manager"""
    # Use context manager for transaction
    with sqlite_db.transaction():
        sqlite_db.save_entity("products", {"id": "p2", "name": "Product 2"}, auto_commit=False)
        
        # Verify entity exists within transaction
        result = sqlite_db.get_entity("products", "p2")
        assert result is not None
    
    # Verify entity still exists after transaction commits
    result = sqlite_db.get_entity("products", "p2")
    assert result is not None
    assert result["name"] == "Product 2"

def test_sqlite_transaction_context_manager_rollback(sqlite_db):
    """Test transaction context manager with rollback on exception"""
    # First ensure the products table exists with proper metadata
    sqlite_db.save_entity("products", {"id": "px", "name": "Test"})
    sqlite_db.delete_entity("products", "px")
    
    # Use context manager with exception to trigger rollback
    try:
        with sqlite_db.transaction():
            sqlite_db.save_entity("products", {"id": "p3", "name": "Product 3"}, auto_commit=False)
            
            # Verify entity exists within transaction
            result = sqlite_db.get_entity("products", "p3")
            assert result is not None
            
            # Raise exception to trigger rollback
            raise ValueError("Test exception to trigger rollback")
    except ValueError:
        pass
    
    # Verify entity doesn't exist after rollback
    result = sqlite_db.get_entity("products", "p3")
    assert result is None

def test_sqlite_execute_sql(sqlite_db):
    """Test direct SQL execution"""
    # Create a table
    sqlite_db.execute_sql("CREATE TABLE IF NOT EXISTS test_table (id TEXT PRIMARY KEY, value TEXT)")
    
    # Insert data
    sqlite_db.execute_sql("INSERT INTO test_table VALUES (?, ?)", ("key1", "value1"))
    
    # Query data
    result = sqlite_db.execute_sql("SELECT * FROM test_table WHERE id = ?", ("key1",))
    assert len(result) == 1
    assert result[0][0] == "key1"
    assert result[0][1] == "value1"

def test_sqlite_executemany_sql(sqlite_db):
    """Test batch SQL execution"""
    # Create a table
    sqlite_db.execute_sql("CREATE TABLE IF NOT EXISTS test_batch (id TEXT PRIMARY KEY, value TEXT)")
    
    # Insert multiple rows
    data = [
        ("batch1", "value1"),
        ("batch2", "value2"),
        ("batch3", "value3")
    ]
    sqlite_db.executemany_sql("INSERT INTO test_batch VALUES (?, ?)", data)
    
    # Query data
    result = sqlite_db.execute_sql("SELECT * FROM test_batch ORDER BY id")
    assert len(result) == 3
    assert result[0][0] == "batch1"
    assert result[2][1] == "value3"

def test_sqlite_schema_evolution(sqlite_db):
    """Test schema evolution with new fields"""
    # Save entity with initial schema
    sqlite_db.save_entity("evolving", {"id": "e1", "field1": "value1"})
    
    # Save entity with new field
    sqlite_db.save_entity("evolving", {"id": "e2", "field1": "value2", "field2": "new_field"})
    
    # Update first entity with new schema
    sqlite_db.save_entity("evolving", {"id": "e1", "field1": "updated", "field2": "added_later"})
    
    # Verify both entities have the new field
    all_entities = sqlite_db.get_entities("evolving")
    assert len(all_entities) == 2
    
    e1 = sqlite_db.get_entity("evolving", "e1")
    assert e1["field1"] == "updated"
    assert e1["field2"] == "added_later"
    
    e2 = sqlite_db.get_entity("evolving", "e2")
    assert e2["field1"] == "value2"
    assert e2["field2"] == "new_field"

def test_sqlite_clear_all(sqlite_db):
    """Test clearing all data"""
    # Save some entities
    sqlite_db.save_entity("test_clear", {"id": "c1", "name": "Clear Test"})
    
    # Verify entity exists
    result = sqlite_db.get_entity("test_clear", "c1")
    assert result is not None
    
    # Clear all data
    sqlite_db.clear_all()
    
    # Save a new entity to verify tables are recreated
    sqlite_db.save_entity("test_clear", {"id": "c2", "name": "After Clear"})
    
    # Verify new entity exists but old one doesn't
    result = sqlite_db.get_entity("test_clear", "c2")
    assert result is not None
    result = sqlite_db.get_entity("test_clear", "c1")
    assert result is None

def test_sqlite_delete_entity(sqlite_db):
    """Test deleting a single entity"""
    # Save an entity
    sqlite_db.save_entity("test_delete", {"id": "d1", "name": "Delete Test"})
    
    # Verify entity exists
    result = sqlite_db.get_entity("test_delete", "d1")
    assert result is not None
    
    # Delete the entity
    deleted = sqlite_db.delete_entity("test_delete", "d1")
    assert deleted is True
    
    # Verify entity no longer exists
    result = sqlite_db.get_entity("test_delete", "d1")
    assert result is None

def test_sqlite_count_entities(sqlite_db):
    """Test counting entities"""
    # Create some test data
    entities = [
        {"id": "c1", "type": "A", "value": 10},
        {"id": "c2", "type": "B", "value": 20},
        {"id": "c3", "type": "A", "value": 30},
    ]
    sqlite_db.save_entities("test_count", entities)
    
    # Count all entities
    count = sqlite_db.count_entities("test_count")
    assert count == 3
    
    # Count with filter
    count_a = sqlite_db.count_entities("test_count", "type = ?", ("A",))
    assert count_a == 2
    
    # Count with value filter
    count_high = sqlite_db.count_entities("test_count", "CAST(value AS INTEGER) > ?", (15,))
    assert count_high == 2

# Async tests

@pytest.mark.asyncio
async def test_sqlite_async_save_and_fetch(sqlite_db):
    """Test basic async save and fetch functionality"""
    entity = {"id": "async1", "name": "Async Alice"}
    await sqlite_db.save_entity_async("async_users", entity)
    result = await sqlite_db.get_entity_async("async_users", "async1")
    assert result["id"] == "async1"
    assert result["name"] == "Async Alice"

@pytest.mark.asyncio
async def test_sqlite_async_transaction(sqlite_db):
    """Test async transaction functionality"""
    # Start a transaction
    await sqlite_db.begin_transaction_async()
    
    try:
        # Save entity in transaction
        await sqlite_db.save_entity_async("async_products", {"id": "ap1", "name": "Async Product 1"}, auto_commit=False)
        
        # Verify entity exists within transaction
        result = await sqlite_db.get_entity_async("async_products", "ap1")
        assert result is not None
        assert result["name"] == "Async Product 1"
        
        # Rollback changes
        await sqlite_db.rollback_transaction_async()
        
        # Verify entity no longer exists
        result = await sqlite_db.get_entity_async("async_products", "ap1")
        assert result is None
    except Exception:
        await sqlite_db.rollback_transaction_async()
        raise

@pytest.mark.asyncio
async def test_sqlite_async_transaction_decorator(sqlite_db):
    """Test async transaction decorator"""
    # Create a function with transaction decorator
    @sqlite_db.async_transaction
    async def create_entity():
        await sqlite_db.save_entity_async("async_products", {"id": "ap2", "name": "Async Product 2"}, auto_commit=False)
        return "Success"
    
    # Call the function
    result = await create_entity()
    assert result == "Success"
    
    # Verify entity exists after transaction commits
    entity = await sqlite_db.get_entity_async("async_products", "ap2")
    assert entity is not None
    assert entity["name"] == "Async Product 2"

@pytest.mark.asyncio
async def test_sqlite_async_execute_sql(sqlite_db):
    """Test direct async SQL execution"""
    # Create a table
    await sqlite_db.execute_sql_async("CREATE TABLE IF NOT EXISTS async_test (id TEXT PRIMARY KEY, value TEXT)")
    
    # Insert data
    await sqlite_db.execute_sql_async("INSERT INTO async_test VALUES (?, ?)", ("async_key1", "async_value1"))
    
    # Query data
    result = await sqlite_db.execute_sql_async("SELECT * FROM async_test WHERE id = ?", ("async_key1",))
    assert len(result) == 1
    assert result[0][0] == "async_key1"
    assert result[0][1] == "async_value1"

@pytest.mark.asyncio
async def test_sqlite_async_delete_entity(sqlite_db):
    """Test deleting a single entity asynchronously"""
    # Save an entity
    await sqlite_db.save_entity_async("async_delete", {"id": "ad1", "name": "Async Delete Test"})
    
    # Verify entity exists
    result = await sqlite_db.get_entity_async("async_delete", "ad1")
    assert result is not None
    
    # Delete the entity
    deleted = await sqlite_db.delete_entity_async("async_delete", "ad1")
    assert deleted is True
    
    # Verify entity no longer exists
    result = await sqlite_db.get_entity_async("async_delete", "ad1")
    assert result is None

@pytest.mark.asyncio
async def test_sqlite_async_count_entities(sqlite_db):
    """Test counting entities asynchronously"""
    # Create some test data
    entities = [
        {"id": "ac1", "type": "A", "value": 10},
        {"id": "ac2", "type": "B", "value": 20},
        {"id": "ac3", "type": "A", "value": 30},
    ]
    await sqlite_db.save_entities_async("async_count", entities)
    
    # Count all entities
    count = await sqlite_db.count_entities_async("async_count")
    assert count == 3
    
    # Count with filter
    count_a = await sqlite_db.count_entities_async("async_count", "type = ?", ("A",))
    assert count_a == 2
    
    # Count with value filter
    count_high = await sqlite_db.count_entities_async("async_count", "CAST(value AS INTEGER) > ?", (15,))
    assert count_high == 2

@pytest.mark.asyncio
async def test_sqlite_async_close(sqlite_db):
    """Test async close functionality"""
    # Save an entity
    await sqlite_db.save_entity_async("async_close", {"id": "ac1", "data": "Close Test"})
    
    # Close async connection
    await sqlite_db.close_async()
    
    # Connection should reopen automatically on next use
    result = await sqlite_db.get_entity_async("async_close", "ac1")
    assert result is not None
    assert result["data"] == "Close Test"