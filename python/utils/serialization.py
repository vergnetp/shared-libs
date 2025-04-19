import ast

# Map Python types for safer deserialization
TYPE_MAP = {
    int: int,
    float: float,
    str: str,
    bool: bool,
    type(None): type(None),
    list: list,
    dict: dict,
    tuple: tuple,
}

def safe_deserialize(value: str, target_type: type):
    """
    Safely cast a string back to the given Python type.

    Args:
        value (str): The serialized value as a string.
        target_type (type): The desired Python type for the output.

    Returns:
        The deserialized value in its target_type, or the original string if conversion fails.

    Usage Examples:
        >>> safe_deserialize("123", int)
        123
        >>> safe_deserialize("3.14", float)
        3.14
        >>> safe_deserialize("True", bool)
        True
        >>> safe_deserialize("[1, 2, 3]", list)
        [1, 2, 3]
        >>> safe_deserialize("{'a': 1}", dict)
        {'a': 1}
        >>> safe_deserialize("invalid", int)
        'invalid'
    """
    try:
        # Lookup actual constructor
        actual = TYPE_MAP.get(target_type)
        if actual is None:
            raise TypeError(f"Unsupported type: {target_type}")

        # None special case
        if actual is type(None):
            return None

        # Boolean special case
        if actual is bool:
            val = value.strip().lower()
            if val in ('true', '1'):
                return True
            if val in ('false', '0'):
                return False
            raise ValueError(f"Cannot convert {value!r} to bool")

        # Try AST literal eval for safety
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            parsed = value

        # Cast to target type
        return actual(parsed)

    except Exception:
        # Fallback: return raw value
        return value
