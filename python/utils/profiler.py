import time
import inspect
import threading
import logging
from functools import wraps

logger = logging.getLogger(__name__)

class Profiler:
    """
    Simple timer for code blocks.

    Usage Example:
        from utils.profiler import Profiler
        profiler = Profiler()
        # Code block to measure
        do_something()
        print(profiler.report("do_something execution time"))
        
        # Alternatively, manual start/elapsed
        profiler.start()
        another_task()
        elapsed_ms = profiler.elapsed()
        print(f"another_task took {elapsed_ms:.2f} ms")
    """
    def __init__(self):
        self._start = time.time()

    def start(self) -> None:
        """Reset the start time to current time."""
        self._start = time.time()

    def elapsed(self) -> float:
        """
        Return elapsed time in milliseconds since last start (or __init__),
        and reset the timer.
        """
        now = time.time()
        diff = (now - self._start) * 1000
        self.start()
        return diff

    def report(self, msg: str = 'Elapsed time') -> str:
        """
        Return a formatted string with the elapsed time, e.g. "Elapsed time: 12.34 ms".
        """
        return f"{msg}: {self.elapsed():.2f} ms"

_profile_lock = threading.RLock()
_profile_cache: dict = {}

def profiled_function(is_entry: bool = False):
    """
    Decorator that profiles a function and logs timing stats at entry points.

    This decorator can be applied to functions to accumulate run-time statistics
    across calls, organized by entry-point key.

    Args:
        is_entry (bool): Mark this function as an entry point for profiling.
                         When True, the internal cache is reset for this function's key.

    Usage Example:
        from utils.profiler import profiled_function
        
        @profiled_function(is_entry=True)
        def main():
            work()

        @profiled_function()
        def work():
            # perform some tasks
            pass

        # Calling main() will log the profiling info for work()
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            entry_key = f"{func.__module__}.{func.__name__}"

            if is_entry:
                with _profile_lock:
                    _profile_cache[entry_key] = {}

            # Attempt to find an active entry in the call stack
            key = entry_key
            if not is_entry:
                for frame in inspect.stack():
                    module_name = frame.frame.f_globals.get("__name__")
                    func_name = frame.function
                    candidate = f"{module_name}.{func_name}"
                    if candidate in _profile_cache:
                        key = candidate
                        break

            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = (time.time() - start) * 1000
                with _profile_lock:
                    entry_stats = _profile_cache.setdefault(key, {})
                    stats = entry_stats.setdefault(func.__name__, {'run_time': 0.0, 'nb_calls': 0})
                    stats['run_time'] += duration
                    stats['nb_calls'] += 1
                    if is_entry:
                        logger.info("Profiler %s stats: %s", key, entry_stats)
        return wrapper
    return decorator
