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
    time.sleep(0.5)
    content = read_log_content(get_log_file(tmp_path))
    assert "[ERROR]" in content
    assert "[UNIT TEST] Error occurred" in content

def test_info_logs_message(tmp_path, monkeypatch):
    patch_utils(monkeypatch, tmp_path)
    importlib.reload(mylog)
    mylog.info("[UNIT TEST] Info message")
    time.sleep(0.5)
    content = read_log_content(get_log_file(tmp_path))
    assert "[INFO]" in content
    assert "[UNIT TEST] Info message" in content

def test_debug_logs_to_stdout_only(tmp_path, monkeypatch, capsys):
    patch_utils(monkeypatch, tmp_path)
    importlib.reload(mylog)
    mylog.debug("[UNIT TEST] Debug info")
    time.sleep(0.5)
    out = capsys.readouterr().out
    assert "[UNIT TEST] Debug info" in out
    log_file = Path(get_log_file(tmp_path))
    assert not log_file.exists() or "[UNIT TEST] Debug info" not in read_log_content(log_file)

def test_profile_logs_to_stdout_only(tmp_path, monkeypatch, capsys):
    patch_utils(monkeypatch, tmp_path)
    importlib.reload(mylog)
    mylog.profile("[UNIT TEST] Profile start")
    time.sleep(0.5)
    out = capsys.readouterr().out
    assert "[UNIT TEST] Profile start" in out
    log_file = Path(get_log_file(tmp_path))
    assert not log_file.exists() or "[UNIT TEST] Profile start" not in read_log_content(log_file)

def test_critical_logs_and_flushes(tmp_path, monkeypatch, capsys):
    patch_utils(monkeypatch, tmp_path)
    importlib.reload(mylog)
    mylog.critical("[UNIT TEST] Fatal error")
    out = capsys.readouterr().out
    assert "[CRITICAL]" in out
    log_file = get_log_file(tmp_path)
    content = read_log_content(log_file)
    assert "[CRITICAL]" in content
    assert "[UNIT TEST] Fatal error" in content

def test_queue_accepts_multiple_messages(tmp_path, monkeypatch):
    patch_utils(monkeypatch, tmp_path)
    importlib.reload(mylog)

    for i in range(20):
        mylog.info(f"[UNIT TEST] log {i}")

    time.sleep(1)

    log_file = get_log_file(tmp_path)
    content = read_log_content(log_file)

    for i in range(20):
        assert f"log {i}" in content, f"Log message {i} was not found in log file."
