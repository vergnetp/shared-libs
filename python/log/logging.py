from datetime import datetime
import queue
import threading
import atexit
import sys
import os
from .. import utils

# Maximum verbosity level; any message with a level above this will be ignored
MAX_VERBOSE_LEVEL = 10

# Thread-safe queue for passing log messages from the main thread to the logging thread
log_queue = queue.Queue(maxsize=1000)

def log_worker():
    """
    Background thread worker that processes log messages from the queue.
    
    Runs continuously in a daemon thread. Waits for log records pushed by queue_msg(),
    and writes them via _write_log(). If it receives `None`, it shuts down.

    This function is meant to isolate file and stdout I/O from the main thread,
    to avoid blocking application execution due to logging overhead.
    """
    while True:
        try:
            record = log_queue.get()
            if record is None:  # Sentinel received — shutdown requested
                break
            _write_log(
                record.get('message', ''),
                record.get('level', 0),
                record.get('truncate', True),
                record.get('is_debug', False)
            )
        finally:
            log_queue.task_done()

# Start the logging thread as a background daemon
log_thread = threading.Thread(target=log_worker, daemon=True)
log_thread.start()

def close():
    """
    Signals the logging thread to stop and waits for it to finish.
    
    Sends a sentinel (None) to the queue, waits for all pending messages to be processed,
    and joins the thread. Should be called when the application is exiting to ensure
    all logs are flushed.

    Registered with atexit for automatic cleanup on normal interpreter shutdown.
    """
    if log_thread.is_alive():
        log_queue.put(None)
        log_queue.join()
        log_thread.join()
    print('logger properly closed.')

# Ensure logger is shut down on exit
atexit.register(close)

def _write_log(msg, level=0, truncate=True, is_debug=False):
    """
    Internal function that performs actual log writing to stdout and file.
    
    Runs inside the logging thread, called by log_worker().

    Args:
        msg (str): The log message.
        level (int): The verbosity/indentation level.
        truncate (bool): If True, truncates messages longer than 200 characters.
        is_debug (bool): If True, skips writing to file and logs only to stdout.

    Behavior:
        - If the verbosity level exceeds MAX_VERBOSE_LEVEL, the message is skipped.
        - Output is formatted with timestamp and indentation, and printed to stdout.
        - If not a debug message, it is appended to a daily log file and flushed immediately.
        - File I/O is protected with try/except to avoid any crash on failure.
    """
    msg = str(msg)
    if level > MAX_VERBOSE_LEVEL:
        return

    indent = '    ' * level
    timestamp = utils.get_now()
    truncated_msg = msg[:200] + '..' if len(msg) > 200 and truncate else msg
    formatted_msg = f"{timestamp}: {indent}{truncated_msg}"

    # Always print to console
    print(formatted_msg)

    if is_debug:
        return  # Debug messages are only shown on stdout

    try:
        try:
            log_file_path = get_log_path()
        except Exception as e:
            print(f'Failed to get log path: {e}')
            return

        with open(log_file_path, 'a') as log_file:
            log_file.write(f'{formatted_msg}\n')
            log_file.flush()  # Ensure it's immediately written to disk
    except IOError:
        print(f'Cannot write to the log file: {log_file_path}')
    except Exception as e:
        print(f'Logging error: {e}')

def get_log_path(date=None):
    """
    Returns the file path where logs should be saved.

    Args:
        date (str, optional): A date string in YYYY_MM_DD format. Defaults to today.

    Returns:
        str: Full path to the log file for the given date.

    The path is built using `utils.build_path()` and follows:
    ../../../logs/YYYY_MM_DD.log

    If the logs directory does not exist, it is created automatically.
    """
    if date is None:
        date = datetime.now().strftime("%Y_%m_%d")

    res = utils.build_path(utils.get_root(), 'logs', f'{date}.log')

    log_dir = os.path.dirname(res)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    return res

def queue_msg(msg, level=0, truncate=True, is_debug=False):
    """
    Called from application code to log a message without blocking.

    Args:
        msg (str): The message to log.
        level (int): Indentation/verbosity level.
        truncate (bool): If True, limit message to 200 characters.
        is_debug (bool): If True, skips file logging and shows only on stdout.

    Behavior:
        - Message is placed in the `log_queue`.
        - If the queue is full (e.g., under high load), the message is silently dropped.
        - The message will eventually be picked up by the background logger thread.
    """
    try:
        log_queue.put_nowait({
            'message': msg,
            'level': level,
            'truncate': truncate,
            'is_debug': is_debug
        })
    except queue.Full:
        pass  # Avoid blocking; just drop excess logs under load

def info(msg, level=0, truncate=True):
    """
    Logs an informational message via the background logger.

    Args:
        msg (str): The message to log.
        level (int): Optional indentation level.
        truncate (bool): If True, truncate the message if too long.

    Logs are written both to stdout and the log file.
    """
    queue_msg(f'INFO: {msg}', level, truncate=truncate)

def error(msg, level=0):
    """
    Logs an error message via the background logger.

    Args:
        msg (str): The error message.
        level (int): Optional indentation level.

    This message is never truncated and is always written to the file and stdout.
    """
    queue_msg(f'ERROR:\n{msg}', level, truncate=False)

def debug(msg, level=0):
    """
    Logs a debug-only message.

    Args:
        msg (str): The debug message.
        level (int): Optional indentation level.

    These messages are printed to stdout only and not written to the file.
    """
    queue_msg(f'DEBUG: {msg}', level, truncate=False, is_debug=True)

def profile(msg, level=0):
    """
    Logs a profiling message (e.g., timing info) to stdout only.

    Args:
        msg (str): The profiling detail.
        level (int): Optional indentation level.

    Like debug(), this avoids file I/O and is helpful for inline performance traces.
    """
    queue_msg(f'PROFILER: {msg}', level, truncate=False, is_debug=True)

def critical(msg, force_close=False):
    """
    Immediately logs a critical message to both stdout and the log file.

    This bypasses the logging queue and writes synchronously from the caller thread.
    It is intended for fatal errors or shutdown scenarios where logs must be flushed
    immediately and cannot wait for the background logger.

    Args:
        msg (str): The message to log.       
        force_close (bool): If True, calls `close()` after logging to flush remaining logs.

    Behavior:
        - Writes directly to stdout and log file.
        - Calls `sys.stdout.flush()` to ensure the message appears instantly.
        - If `force_close` is True, joins the background logger thread and flushes the queue.
    """
    _write_log(f'CRITICAL: {msg}', level=0, truncate=False, is_debug=False)
    sys.stdout.flush()
    if force_close:
        close()