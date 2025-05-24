import os

from ..path import (
    ensure_dir,
    get_file_parent_folder,
    get_current_directory,
    build_path,
    build_relative_path,
    get_parent_folder,
    get_levels_up,
    get_root,
    get_file_extension,
)


def test_ensure_dir(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    ensure_dir(str(target))
    assert target.is_dir()


def test_build_and_relative(tmp_path, monkeypatch):
    assert build_path("x", "y", "z") == os.path.join("x", "y", "z")

    monkeypatch.chdir(tmp_path)
    rel = build_relative_path("foo", "bar.txt")
    assert rel == os.path.join(str(tmp_path), "foo", "bar.txt")


def test_parent_and_levels():
    path = os.path.join("root", "sub", "file.txt")
    assert get_file_parent_folder(path).endswith(os.path.join("root", "sub"))
    assert get_parent_folder(path).endswith(os.path.join("root", "sub"))
    assert get_levels_up("a/b/c/d", 2) == os.path.join("a", "b")


def test_get_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert get_current_directory() == str(tmp_path)


def test_get_file_extension():
    assert get_file_extension("foo.txt") == "txt"
    assert get_file_extension("foo") == ""
    assert get_file_extension("archive.tar.gz") == "gz"


def test_get_root_override(monkeypatch):
    monkeypatch.setenv("LIB_ROOT", "/my/custom/root")
    assert get_root() == "/my/custom/root"
