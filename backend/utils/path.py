import os
from pathlib import Path
from typing import Optional

def ensure_dir(path: str) -> None:
    """Create the directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)

def get_file_parent_folder(file: str) -> str:
    """Return the directory of the given file path."""
    return str(Path(file).resolve().parent)

def get_current_directory() -> str:
    """Return the current working directory."""
    return os.getcwd()

def build_path(*args: str) -> str:
    """Join arguments into a file system path."""
    return str(Path(*args))

def build_relative_path(*args: str) -> str:
    """Join cwd with given arguments into a path."""
    return str(Path(os.getcwd(), *args))

def get_parent_folder(path: str) -> str:
    """Return the parent directory of the given path."""
    return str(Path(path).parent)

def get_levels_up(path: str, nb_levels: int = 1) -> str:
    """Return the path nb_levels above the given path."""
    p = Path(path)
    for _ in range(nb_levels):
        p = p.parent
    return str(p)

def get_root() -> str:
    """
    Return the repo root (3 levels up from this file),
    or override via the LIB_ROOT environment variable.
    """
    override = os.getenv('LIB_ROOT')
    if override:
        return override
    return get_levels_up(__file__, 3)

def get_resources_folder() -> str:
    """Return the path to the server/resources folder."""
    return build_path(get_root(), 'server', 'resources')

def get_temp_folder() -> str:
    """
    Return the path to server/resources/files/temp,
    creating it if necessary.
    """
    temp_folder = build_path(get_resources_folder(), 'files', 'temp')
    ensure_dir(temp_folder)
    return temp_folder

def get_config_folder() -> str:
    """Return the path to the config folder under the repo root."""
    config_folder = build_path(get_root(), 'config')
    ensure_dir(config_folder)
    return config_folder

def get_file_extension(file_name: str) -> str:
    """Return the extension (no dot) of the given file name."""
    return Path(file_name).suffix.lstrip('.')
