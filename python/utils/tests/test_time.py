import re
import time
import pytest

from datetime import datetime
from ..time import (
    get_current_date,
    get_now,
    timestamp_to_string,
    string_to_timestamp,
)


def test_get_current_date():
    day, month, year = get_current_date()
    assert isinstance(day, int) and 1 <= day <= 31
    assert isinstance(month, int) and 1 <= month <= 12
    assert isinstance(year, int) and year >= 1970


def test_get_now_default_and_custom():
    now_str = get_now()
    # dd/mm/YYYY HH:MM:SS:ffffff
    assert re.match(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}:\d{6}", now_str)

    iso = get_now("%Y-%m-%d")
    assert re.match(r"\d{4}-\d{2}-\d{2}", iso)


def test_timestamp_to_and_from_string_roundtrip():
    fmt = "%Y-%m-%d %H:%M:%S"
    ts0 = 0.0
    s = timestamp_to_string(ts0, fmt)
    assert s == "1970-01-01 00:00:00"
    # roundtrip
    ts1 = string_to_timestamp(s, fmt)
    assert ts1 == pytest.approx(ts0, abs=1e-6)

    # current time roundtrip
    now = time.time()
    s2 = timestamp_to_string(now, fmt)
    ts2 = string_to_timestamp(s2, fmt)
    assert ts2 == pytest.approx(now, rel=1e-3)
