"""
Time utilities: current date and time formatting and parsing.
"""

from datetime import datetime, timezone
from typing import Tuple, Union
from ..errors import TrackError


def get_current_date() -> Tuple[int, int, int]:
    """
    Return the current date as a tuple: (day, month, year).

    Example:
        >>> day, month, year = get_current_date()
        >>> isinstance(day, int) and 1 <= day <= 31
        True
    """
    now = datetime.now()
    return now.day, now.month, now.year


def get_now(fmt: str = "%d/%m/%Y %H:%M:%S:%f") -> str:
    """
    Return the current date and time formatted according to fmt.

    Args:
        fmt (str): A strftime-compatible format string.

    Example:
        >>> ts = get_now()
        >>> isinstance(ts, str)
        True
        >>> get_now("%Y-%m-%d")  # returns like '2025-04-18'
        '2025-04-18'
    """
    try:
        return datetime.now().strftime(fmt)
    except (ValueError, TypeError) as e:
        raise TrackError(e)


def timestamp_to_string(timestamp: Union[int, float], fmt: str = "%d/%m/%Y %H:%M:%S:%f") -> str:
    """
    Convert a Unix timestamp to a formatted date-time string.

    Args:
        timestamp (int | float): Seconds since the Unix epoch.
        fmt (str): A strftime-compatible format string.

    Example:
        >>> timestamp_to_string(0, "%Y-%m-%d %H:%M:%S")
        '1970-01-01 00:00:00'
    """
    try:
        ts = float(timestamp)
        return datetime.fromtimestamp(ts).strftime(fmt)
    except (ValueError, TypeError, OSError) as e:
        raise TrackError(e)


def string_to_timestamp(formatted: str, fmt: str = "%d/%m/%Y %H:%M:%S:%f") -> float:
    """
    Parse a formatted date-time string into a Unix timestamp.

    Args:
        formatted (str): The date-time string to parse.
        fmt (str): The format string that matches the input.

    Example:
        >>> string_to_timestamp("1970-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
        0.0
    """
    try:
        dt = datetime.strptime(formatted, fmt)
        dt = dt.replace(tzinfo=timezone.utc)  # This avoids OSError on Windows
        return dt.timestamp()
    except (ValueError, TypeError) as e:
        raise TrackError(e)
