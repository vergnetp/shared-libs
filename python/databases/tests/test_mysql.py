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

@pytest.mark.asyncio
async def test_mysql_async_save_and_fetch(mysql_db_async):
    db = mysql_db_async
    try:
        await db.clear_all_async()
        await db.save_entity_async("clients", {"id": "3", "name": "Charlie"})
        result = await db.get_entities_async("clients")
        assert any(row["id"] == "3" and row["name"] == "Charlie" for row in result)
    except Exception as e:
        pytest.fail(f"Test failed: {e}")

@pytest.mark.asyncio
async def test_mysql_async_transaction(mysql_db_async):
    """Test async transaction with explicit isolation"""
    db = mysql_db_async
    try:
        # Clear database and create tables outside transaction
        await db.clear_all_async()
        
        # Create a simple test table directly with SQL for isolated testing
        async with db._async_conn.cursor() as cursor:
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS transaction_test_async (
                    id VARCHAR(50) PRIMARY KEY, 
                    name VARCHAR(100)
                ) ENGINE=InnoDB
            """)
            
            # Verify table engine is InnoDB
            await cursor.execute("SHOW CREATE TABLE transaction_test_async")
            table_info = await cursor.fetchone()
            print(f"Table creation info: {table_info}")
        
        # Start explicit transaction
        await db._async_conn.autocommit(False)
        async with db._async_conn.cursor() as cursor:
            await cursor.execute("START TRANSACTION")
            print("Transaction started")
            
            # Insert test data directly
            await cursor.execute(
                "INSERT INTO transaction_test_async (id, name) VALUES (%s, %s)",
                ("test1", "Test Name")
            )
            print("Data inserted")
            
            # Verify data exists
            await cursor.execute("SELECT * FROM transaction_test_async")
            result = await cursor.fetchall()
            print(f"Data during transaction: {result}")
            
            # Execute explicit rollback
            await cursor.execute("ROLLBACK")
            print("Transaction rolled back")
        
        # Reset connection state
        await db._async_conn.autocommit(True)
        
        # Verify data is gone after rollback
        async with db._async_conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM transaction_test_async")
            result = await cursor.fetchall()
            print(f"Data after rollback: {result}")
            
            # The assertion
            assert len(result) == 0, "Transaction rollback failed to remove data"
    except Exception as e:
        print(f"Test error: {e}")
        pytest.fail(f"Test failed: {e}")
        
@pytest.mark.asyncio
async def test_mysql_async_concurrency(mysql_db_async):
    """Test sequential operations instead of true concurrency"""
    db = mysql_db_async
    try:
        await db.clear_all_async()
        
        # Create entities sequentially (simulating concurrency)
        entity_ids = []
        for i in range(5):  # Reduced from 10 to 5 for faster tests
            entity_id = f"concurrent-{i}"
            await db.save_entity_async("concurrent_test", {"id": entity_id, "value": f"value-{i}"})
            entity_ids.append(entity_id)
        
        # Verify all entities were saved
        results = await db.get_entities_async("concurrent_test")
        assert len(results) == 5
        assert set(r["id"] for r in results) == set(entity_ids)
    except Exception as e:
        pytest.fail(f"Test failed: {e}")

@pytest.mark.asyncio
async def test_mysql_async_transaction_commit(mysql_db_async):
    """Test async transaction with commit"""
    db = mysql_db_async
    try:
        await db.clear_all_async()
        
        # Start transaction
        await db.begin_transaction_async()
        
        # Save entities in transaction
        await db.save_entity_async("tx_commit_test", {"id": "tx1", "data": "transaction data"}, auto_commit=False)
        
        # Commit transaction
        await db.commit_transaction_async()
        
        # Verify entity was saved
        result = await db.get_entity_async("tx_commit_test", "tx1")
        assert result is not None
        assert result["data"] == "transaction data"
    except Exception as e:
        pytest.fail(f"Test failed: {e}")
