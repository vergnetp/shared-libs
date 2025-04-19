
import pytest
import smtplib
from unittest import mock
from ... import emailing
from ...errors import TrackError

def test_compress_file_with_string(tmp_path):
    file_path = tmp_path / "test.txt"
    content = b"Hello, World!"
    file_path.write_bytes(content)
    compressed = emailing.compress_file(str(file_path))
    assert isinstance(compressed, bytes)
    assert len(compressed) > 0

def test_compress_file_with_bytes():
    content = b"Sample data"
    compressed = emailing.compress_file(content)
    assert isinstance(compressed, bytes)
    assert len(compressed) > 0

def test_send_email_minimal(monkeypatch):
    monkeypatch.setenv("APP_GMAIL_PWD", "dummy_password")

    class FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, sender, pwd): self.logged_in = True
        def sendmail(self, from_addr, to_addrs, msg): self.sent = (from_addr, to_addrs, msg)

    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: FakeSMTP())
    emailing.send_email(
        subject="Test",
        recipients=["bob@example.com"],
        text="testing"
    )

def test_send_email_with_compression(monkeypatch):
    monkeypatch.setenv("APP_GMAIL_PWD", "dummy_password")

    class FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, sender, pwd): pass
        def sendmail(self, *args): self.called = True

    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: FakeSMTP())
    emailing.send_email(
        subject="Test Compressed",
        recipients=["a@example.com"],
        attached_file=b"content",
        compress=True,
        attached_file_name="file.txt",
        text="Test"
    )

def test_send_email_missing_credentials(monkeypatch):
    monkeypatch.delenv("APP_GMAIL_PWD", raising=False)
    with pytest.raises(TrackError, match="SMTP credentials are missing"):
        emailing.send_email(
            subject="Test",
            recipients=["x@example.com"],
            text="Missing password"
        )

def test_send_email_oversized_file(monkeypatch):
    monkeypatch.setenv("APP_GMAIL_PWD", "dummy_password")

    class FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, sender, pwd): pass
        def sendmail(self, *args): self.called = True

    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: FakeSMTP())

    data = b"x" * ((emailing.MAX_FILE_SIZE_MB + 10) * 1024 * 1024)
    with pytest.raises(TrackError, match="File size exceeds"):
        emailing.send_email(
            subject="Too big",
            recipients=["a@example.com"],
            attached_file=data,
            compress=False,
            attached_file_name="oversized.txt",
            text="oversized"
        )
