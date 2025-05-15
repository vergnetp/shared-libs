import importlib
import time
from pathlib import Path
from .. import logging as mylog
from ... import utils


def patch_utils(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_root", lambda: str(tmp_path))

def get_log_file(tmp_path):
    return mylog.get_log_file()

def read_log_content(log_file):
    log_file = Path(log_file)
    assert log_file.exists(), "Log file was not created"
    with open(log_file, "r") as f:
        return f.read()

def test_error_logs_message(tmp_path, monkeypatch):
    patch_utils(monkeypatch, tmp_path)
    importlib.reload(mylog)
    mylog.error("[UNIT TEST] Error occurred")
    # Shutdown now fully synchronous - no async issues
    mylog.AsyncLogger.get_instance().shutdown()
    content = read_log_content(get_log_file(tmp_path))
    assert "[ERROR]" in content
    assert "[UNIT TEST] Error occurred" in content

def test_info_logs_message(tmp_path, monkeypatch):
    patch_utils(monkeypatch, tmp_path)
    importlib.reload(mylog)
    mylog.info("[UNIT TEST] Info message")
    mylog.AsyncLogger.get_instance().shutdown()
    content = read_log_content(get_log_file(tmp_path))
    assert "[INFO]" in content
    assert "[UNIT TEST] Info message" in content

def test_queue_accepts_multiple_messages(tmp_path, monkeypatch):
    patch_utils(monkeypatch, tmp_path)
    importlib.reload(mylog)

    for i in range(20):
        mylog.info(f"[UNIT TEST] log {i}")

    # All logs should be written immediately now, no sleep needed
    # But keeping a small sleep for stability
    time.sleep(0.1)

    log_file = get_log_file(tmp_path)
    content = read_log_content(log_file)

    for i in range(20):
        assert f"log {i}" in content, f"Log message {i} was not found in log file."