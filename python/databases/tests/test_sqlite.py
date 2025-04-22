def test_sqlite_save_and_fetch(sqlite_db):
    entity = {"id": "1", "name": "Alice"}
    sqlite_db.save_entity("users", entity)
    result = sqlite_db.get_entity("users", "1")
    assert result["id"] == "1"
    assert result["name"] == "Alice"