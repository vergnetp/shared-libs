import shutil
import os
import glob
import threading
import mimetypes
import inspect
from pathlib import Path
from .path import get_temp_folder
from ..errors import TrackError
import logging

# Register Office MIME types once
mimetypes.add_type(
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx')
mimetypes.add_type(
    'application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx')
mimetypes.add_type(
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx')

logger = logging.getLogger(__name__)

# Determine whether to use the new `onexc` parameter (Python ≥ 3.12)
_HAS_ONEXC = 'onexc' in inspect.signature(shutil.rmtree).parameters

def get_mime_type(file_path: str) -> str:
    """
    Determine the MIME type of a file based on its extension.
    """
    try:
        media_type, _ = mimetypes.guess_type(file_path)
        return media_type
    except Exception as e:
        raise TrackError(e)


def safe_remove_directory(dir_path: str) -> None:
    """
    Recursively delete a directory and its contents, handling permission errors.

    Uses the `onexc` parameter on Python ≥ 3.12, and falls back to `onerror` otherwise.
    """
    def _handler(func, path, exc_info):
        # Try resetting permissions and retry
        os.chmod(path, 0o666)
        func(path)

    def _onexc(func, path, *exc_info):
        _handler(func, path, exc_info)

    try:
        if _HAS_ONEXC:
            shutil.rmtree(dir_path, onexc=_onexc)
        else:
            shutil.rmtree(dir_path, onerror=_handler)
    except Exception as e:
        logger.error("Error removing directory %s: %s", dir_path, e)
        raise TrackError(e)


def save_temp_file(binary_content: bytes, file_name: str) -> str:
    """
    Save binary content to the resources/temp folder and return the file path.
    """
    try:
        temp_folder = get_temp_folder()
        path = Path(temp_folder) / file_name
        path.write_bytes(binary_content)
        return str(path)
    except Exception as e:
        raise TrackError(e)


def get_temp_file(file_name: str):
    """
    Open and return a binary file from the resources/temp folder, or None if missing.
    """
    try:
        temp_folder = get_temp_folder()
        path = Path(temp_folder) / file_name
        if not path.exists():
            return None
        return path.open('rb')
    except Exception as e:
        raise TrackError(e)


def get_temp_file_by_id(doc_id: str) -> str:
    """
    Return the first temp file path matching {doc_id}.* or None.
    """
    try:
        temp_folder = get_temp_folder()
        pattern = str(Path(temp_folder) / f"{doc_id}.*")
        matches = glob.glob(pattern)
        return matches[0] if matches else None
    except Exception as e:
        raise TrackError(e)


def delete_temp_files_by_id(doc_id: str) -> None:
    """
    Delete all temp files matching {doc_id}*.* in the temp folder.
    """
    try:
        temp_folder = get_temp_folder()
        pattern = str(Path(temp_folder) / f"{doc_id}*.*")
        for filepath in glob.glob(pattern):
            try:
                os.remove(filepath)
            except OSError as oe:
                logger.warning("Failed to delete %s: %s", filepath, oe)
    except Exception as e:
        raise TrackError(e)


def launch_files_cleaning(doc_id: str) -> None:
    """
    Spawn a daemon thread to delete temp files by document ID.
    """
    thread = threading.Thread(
        target=delete_temp_files_by_id,
        args=(doc_id,),
        daemon=True
    )
    thread.start()
