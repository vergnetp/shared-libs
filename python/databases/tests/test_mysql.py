def test_mysql_save_and_fetch(mysql_db):
    entity = {"id": "2", "name": "Bob"}
    mysql_db.save_entity("customers", entity)
    result = mysql_db.get_entity("customers", "2")
    assert result["id"] == "2"
    assert result["name"] == "Bob"