import pytest
from errors.error import Error, TrackError, ApiKeyError

def test_basic_error_str_contains_description_and_location():
    err = Error(description="Something went wrong", action="Retry", critical=True)
    output = str(err)
    assert "Something went wrong" in output
    assert "Retry" in output
    assert "line" in output  # should include line number in location

def test_error_chain_bubbles_critical_flag():
    try:
        raise ValueError("Base error")
    except ValueError as e:
        wrapped = Error(error=e, critical=True)
    assert wrapped.critical is True

def test_track_error_sets_location():
    try:
        raise ValueError("Inner")
    except Exception as e:
        err = TrackError(e)
    assert "line" in err.location
    assert "test_track_error_sets_location" in err.location

def test_api_key_error_has_expected_fields():
    err = ApiKeyError(description="Invalid key", action="Check your key")
    assert isinstance(err, Error)
    assert err.description == "Invalid key"
    assert err.action == "Check your key"
    assert "line" in err.location

def test_trace_includes_all_locations():
    try:
        try:
            raise ValueError("low-level")
        except Exception as e:
            raise TrackError(e)
    except Exception as e:
        err = Error(e)
    trace = err.trace()
    assert isinstance(trace, list)
    assert any("line" in entry for entry in trace)

def test_error_encoding_with_nested_errors():
    try:
        raise ValueError("base")
    except Exception as e:
        err = Error(error=TrackError(e), description="top level")
    encoded = str(err)
    assert "top level" in encoded
    assert "base" in encoded
    assert "line" in encoded
