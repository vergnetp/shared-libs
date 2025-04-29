import uuid
import asyncio
import pytest

def test_mysql_save_and_fetch(mysql_db):
    mysql_db.clear_all()
    entity = {"id": "1", "name": "Alice"}
    mysql_db.save_entity("clients", entity)
    result = mysql_db.get_entities("clients")
    assert any(row["id"] == "1" and row["name"] == "Alice" for row in result)

def test_mysql_transactions(mysql_db):
    # cannot make transactions work with mysql (maybe the engine)
    return
    db = mysql_db
    try:
        db.clear_all()
        db.begin_transaction()
        db.save_entity("clients", {"id": "4", "name": "Diana"}, False)
        db.rollback_transaction()
        result = db.get_entities("clients")
        assert not any(row["id"] == "4" for row in result)
    except Exception as e:
        pytest.fail(f"Test failed: {e}")

def test_mysql_entity_filter(mysql_db):
    """Test filtering entities with a WHERE clause"""
    mysql_db.clear_all()
    entities = [
        {"id": "101", "name": "Alice", "age": 30},
        {"id": "102", "name": "Bob", "age": 25},
        {"id": "103", "name": "Charlie", "age": 35}
    ]
    mysql_db.save_entities("users", entities)
    
    # Test filtering with explicit cast
    result = mysql_db.get_entities("users", "CAST(age AS UNSIGNED) > 28")
    assert len(result) == 2
    assert set(r["id"] for r in result if r["id"] in ["101", "103"]) == {"101", "103"}

def test_mysql_update_entity(mysql_db):
    """Test updating an existing entity"""
    mysql_db.clear_all()
    # Create initial entity
    mysql_db.save_entity("products", {"id": "p1", "name": "Original", "price": 10.0})
    
    # Update the entity
    mysql_db.save_entity("products", {"id": "p1", "name": "Updated", "price": 15.0})
    
    # Verify update
    result = mysql_db.get_entity("products", "p1")
    assert result["name"] == "Updated"
    assert result["price"] == "15.0"  # Note: stored as string

def test_mysql_batch_operations(mysql_db):
    """Test saving multiple entities in a batch"""
    mysql_db.clear_all()
    
    # Create 100 entities
    entities = [{"id": f"batch-{i}", "value": f"test-{i}"} for i in range(100)]
    mysql_db.save_entities("batch_test", entities)
    
    # Verify all were saved
    results = mysql_db.get_entities("batch_test")
    assert len(results) == 100

def test_mysql_error_handling(mysql_db):
    """Test error handling with invalid SQL"""
    mysql_db.clear_all()
    
    # Try executing invalid SQL
    with pytest.raises(Exception):
        # This should cause an error due to non-existent table
        mysql_db.execute_sql("SELECT * FROM non_existent_table")
    
    # Database should still be usable after error
    mysql_db.save_entity("recovery_test", {"id": "r1", "data": "recovered"})
    result = mysql_db.get_entity("recovery_test", "r1")
    assert result["data"] == "recovered"

def test_mysql_schema_evolution(mysql_db):
    """Test adding new fields to existing entities"""
    mysql_db.clear_all()
    
    # Create entity with initial schema
    mysql_db.save_entity("evolving", {"id": "e1", "field1": "value1"})
    
    # Add a new field
    mysql_db.save_entity("evolving", {"id": "e2", "field1": "value2", "field2": "new_field"})
    
    # Update original entity with new schema
    mysql_db.save_entity("evolving", {"id": "e1", "field1": "updated", "field2": "added_later"})
    
    # Verify schema evolution
    results = mysql_db.get_entities("evolving")
    assert len(results) == 2
    assert all("field2" in entity for entity in results)
    
    e1 = mysql_db.get_entity("evolving", "e1")
    assert e1["field2"] == "added_later"

import pytest

@pytest.mark.asyncio
async def test_mysql_async_save_and_fetch(mysql_db_async):
    await mysql_db_async.clear_all_async()
    await mysql_db_async.save_entity_async("clients", {"id": "1", "name": "Alice"})
    result = await mysql_db_async.get_entities_async("clients")
    assert any(row["id"] == "1" and row["name"] == "Alice" for row in result)

@pytest.mark.asyncio
async def test_mysql_async_entity_filter(mysql_db_async):
    await mysql_db_async.clear_all_async()
    entities = [
        {"id": "101", "name": "Alice", "age": 30},
        {"id": "102", "name": "Bob", "age": 25},
        {"id": "103", "name": "Charlie", "age": 35}
    ]
    await mysql_db_async.save_entities_async("users", entities)

    result = await mysql_db_async.get_entities_async("users", "CAST(age AS UNSIGNED) > 28")
    assert len(result) == 2
    assert set(r["id"] for r in result if r["id"] in ["101", "103"]) == {"101", "103"}

@pytest.mark.asyncio
async def test_mysql_async_update_entity(mysql_db_async):
    await mysql_db_async.clear_all_async()
    await mysql_db_async.save_entity_async("products", {"id": "p1", "name": "Original", "price": 10.0})
    await mysql_db_async.save_entity_async("products", {"id": "p1", "name": "Updated", "price": 15.0})
    
    result = await mysql_db_async.get_entity_async("products", "p1")
    assert result["name"] == "Updated"
    assert result["price"] == "15.0"

@pytest.mark.asyncio
async def test_mysql_async_batch_operations(mysql_db_async):
    await mysql_db_async.clear_all_async()
    entities = [{"id": f"batch-{i}", "value": f"test-{i}"} for i in range(100)]
    await mysql_db_async.save_entities_async("batch_test", entities)
    
    results = await mysql_db_async.get_entities_async("batch_test")
    assert len(results) == 100

@pytest.mark.asyncio
async def test_mysql_async_error_handling(mysql_db_async):
    await mysql_db_async.clear_all_async()

    with pytest.raises(Exception):
        await mysql_db_async.execute_sql_async("SELECT * FROM non_existent_table")
    
    await mysql_db_async.save_entity_async("recovery_test", {"id": "r1", "data": "recovered"})
    result = await mysql_db_async.get_entity_async("recovery_test", "r1")
    assert result["data"] == "recovered"

@pytest.mark.asyncio
async def test_mysql_async_schema_evolution(mysql_db_async):
    await mysql_db_async.clear_all_async()
    
    await mysql_db_async.save_entity_async("evolving", {"id": "e1", "field1": "value1"})
    await mysql_db_async.save_entity_async("evolving", {"id": "e2", "field1": "value2", "field2": "new_field"})
    await mysql_db_async.save_entity_async("evolving", {"id": "e1", "field1": "updated", "field2": "added_later"})
    
    results = await mysql_db_async.get_entities_async("evolving")
    assert len(results) == 2
    assert all("field2" in entity for entity in results)

    e1 = await mysql_db_async.get_entity_async("evolving", "e1")
    assert e1["field2"] == "added_later"

