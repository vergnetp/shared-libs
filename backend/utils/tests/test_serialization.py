from ..serialization import safe_deserialize


def test_safe_deserialize_int():
    assert safe_deserialize("123", int) == 123


def test_safe_deserialize_float():
    assert abs(safe_deserialize("3.14", float) - 3.14) < 1e-6


def test_safe_deserialize_bool():
    assert safe_deserialize("true", bool) is True
    assert safe_deserialize("0", bool) is False


def test_safe_deserialize_none():
    assert safe_deserialize("anything", type(None)) is None


def test_safe_deserialize_collection_types():
    assert safe_deserialize("[1, 2, 3]", list) == [1, 2, 3]
    assert safe_deserialize("{'a': 1}", dict) == {'a': 1}
    assert safe_deserialize("(4,5)", tuple) == (4, 5)


def test_safe_deserialize_invalid_fallback():
    # unsupported type: str is supported, but let's try an invalid literal for int
    assert safe_deserialize("not_an_int", int) == "not_an_int"
