

def test_postgres_save_and_fetch(postgres_db):
    postgres_db.clear_all()
    entity = {"id": "1", "name": "Alice"}
    postgres_db.save_entity("clients", entity)
    result = postgres_db.get_entities("clients")
    assert any(row["id"] == "1" and row["name"] == "Alice" for row in result)

def test_postgres_transactions(postgres_db):
    postgres_db.clear_all()
    postgres_db.begin_transaction()
    postgres_db.save_entity("clients", {"id": "2", "name": "Bob"}, False)
    postgres_db.rollback_transaction()
    result = postgres_db.get_entities("clients")
    print(result)
    assert not any(row["id"] == "2" for row in result)

import pytest

@pytest.mark.asyncio
async def test_postgres_async_save_and_fetch(postgres_db):
    db = postgres_db
    await db.clear_all_async()
    await db.save_entity_async("clients", {"id": "3", "name": "Charlie"})
    result = await db.get_entities_async("clients")
    assert any(row["id"] == "3" and row["name"] == "Charlie" for row in result)

@pytest.mark.asyncio
async def test_postgres_async_transaction(postgres_db):
    db = postgres_db
    await db.clear_all_async()
    await db.begin_transaction_async()
    await db.save_entity_async("clients", {"id": "4", "name": "Diana"})
    await db.rollback_transaction_async()
    result = await db.get_entities_async("clients")
    assert not any(row["id"] == "4" for row in result)
