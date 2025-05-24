import os
import time
import tempfile

from ..files import (
    get_mime_type,
    safe_remove_directory,
    save_temp_file,
    get_temp_file,
    get_temp_file_by_id,
    delete_temp_files_by_id,
    launch_files_cleaning,
)
from ..path import get_temp_folder
from .. import files as files_mod

def test_get_mime_type_office():
    # create a dummy .docx file
    with tempfile.NamedTemporaryFile(suffix=".docx") as tf:
        mime = get_mime_type(tf.name)
    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_save_and_get_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(files_mod, "get_temp_folder", lambda: str(tmp_path))

    content = b"hello world"
    path = save_temp_file(content, "foo.bin")
    assert os.path.exists(path)

    f = get_temp_file("foo.bin")
    assert f.read() == content
    f.close()


def test_get_temp_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(files_mod, "get_temp_folder", lambda: str(tmp_path))
    assert get_temp_file("does_not_exist.txt") is None


def test_get_and_delete_temp_by_id(tmp_path, monkeypatch):
    monkeypatch.setattr(files_mod, "get_temp_folder", lambda: str(tmp_path))

    # create two files with doc_id "123"
    f1 = tmp_path / "123.txt"; f1.write_text("x")
    f2 = tmp_path / "123.pdf"; f2.write_text("y")

    found = get_temp_file_by_id("123")
    assert found is not None
    assert any(found.endswith(ext) for ext in (".txt", ".pdf"))

    delete_temp_files_by_id("123")
    assert not any(tmp_path.iterdir())


def test_safe_remove_directory(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    (d / "x.txt").write_text("1")
    safe_remove_directory(str(d))
    assert not d.exists()


def test_launch_files_cleaning(tmp_path, monkeypatch):
    monkeypatch.setattr(files_mod, "get_temp_folder", lambda: str(tmp_path))

    # create a file that matches doc_id "to_remove"
    f = tmp_path / "to_remove.log"; f.write_text("data")
    launch_files_cleaning("to_remove")
    # give thread a moment
    time.sleep(0.1)
    assert not any(tmp_path.iterdir())
