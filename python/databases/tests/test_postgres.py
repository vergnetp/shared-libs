def test_postgres_save_and_fetch(postgres_db):
    entity = {"id": "3", "name": "Charlie"}
    postgres_db.save_entity("clients", entity)
    result = postgres_db.get_entity("clients", "3")
    assert result["id"] == "3"
    assert result["name"] == "Charlie"