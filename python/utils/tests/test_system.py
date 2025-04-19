import psutil

from ..system import can_file_fit_in_memory


def test_can_file_fit_zero():
    assert can_file_fit_in_memory(0) is True


def test_can_file_fit_too_large():
    # ask for more MB than available
    available_mb = psutil.virtual_memory().available / (1024 * 1024)
    assert can_file_fit_in_memory(available_mb + 1000) is False
