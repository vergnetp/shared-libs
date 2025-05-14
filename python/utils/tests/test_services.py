
from .. import services

def test_service_ready():
    is_ready = services.wait_for_service('mysql','localhost','3307', 'test', 'test', 'testdb_mysql',10)
    assert is_ready