import concurrent.futures
import threading
import time
import signal
import asyncio
import functools
import platform
from typing import Callable, Any, Optional

# Global thread pool with limited size for timeout operations
_timeout_executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)

def with_timeout(default_timeout: float = 60.0):
    """
    Decorator that adds timeout functionality to both async and sync methods.
    
    The decorated method will have a timeout applied, which can be:
    1. Passed directly as a 'timeout' parameter to the method
    2. Or use the default_timeout value if none is provided
    
    For sync methods, implements a "soft timeout" using a hybrid approach:
    - Thread pool for normal cases
    - Signal-based timeout (UNIX) or periodic checking (Windows) as fallback
    
    Args:
        default_timeout: Default timeout in seconds if none is provided
    """
    from .. import log as logger
    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)
        is_windows = platform.system() == "Windows"

        # Update docstring with timeout info
        if func.__doc__:
            func.__doc__ += f"\n\n        timeout: Optional timeout in seconds (default: {default_timeout}s)"
            if not is_async and is_windows:
                func.__doc__ += f"\n        Note: In Windows, if the ThreadPool get exhausted, uses soft timeout for synchronous method"
        else:
            func.__doc__ = f"timeout: Optional timeout in seconds (default: {default_timeout}s)"
            if not is_async and is_windows:
                func.__doc__ += f"\n        Note: In Windows, if the ThreadPool get exhausted, uses soft timeout for synchronous method"
        
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract timeout parameter or use default
            timeout = kwargs.pop('timeout', default_timeout)
            
            try:
                # Use asyncio's wait_for to implement the timeout
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError:
                # Provide consistent error type
                raise TimeoutError(f"Function {func.__name__} timed out after {timeout}s")
                
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract timeout parameter or use default
            timeout = kwargs.pop('timeout', default_timeout)
            
            # Try to submit to thread pool with a very short wait
            # This helps detect if pool is saturated
            try:
                future = _timeout_executor.submit(func, *args, **kwargs)
                
                # Wait for immediate execution or short queue (100ms)
                queue_start = time.time()
                queue_timeout = min(0.1, timeout / 10)
                
                # If this succeeds quickly, thread was available
                try:
                    return future.result(timeout=queue_timeout)
                except concurrent.futures.TimeoutError:
                    # Task is running or queued, continue with normal timeout
                    remaining_timeout = timeout - (time.time() - queue_start)
                    if remaining_timeout <= 0:
                        future.cancel()
                        raise TimeoutError(f"Function {func.__name__} timed out after {timeout}s")
                    
                    try:
                        return future.result(timeout=remaining_timeout)
                    except concurrent.futures.TimeoutError:
                        future.cancel()
                        raise TimeoutError(f"Function {func.__name__} timed out after {timeout}s")
                    
            except RuntimeError:
                # Thread pool is at capacity, fall back to alternate methods
                return _fallback_timeout_execution(func, args, kwargs, timeout)
                
        def _fallback_timeout_execution(func: Callable, args: tuple, kwargs: dict, timeout: float) -> Any:
            """Fallback timeout execution when thread pool is at capacity."""
            # On Unix-like systems, use signal-based approach
            if hasattr(signal, 'SIGALRM'):
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Function {func.__name__} timed out after {timeout}s")
                
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                try:
                    signal.alarm(int(timeout) + 1)  # +1 for safety margin
                    return func(*args, **kwargs)
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
            else:
                # On Windows or other systems without SIGALRM, use periodic checking
                logger.warning(f"Thread pool exhausted and falling back to soft timeout for {func.__name__} on Windows. Some operations may not be interruptible.")
                start_time = time.time()
                check_interval = min(0.1, timeout / 10)
                  
                # Create a monitoring thread
                stop_monitoring = threading.Event()
                
                def monitor_timeout():
                    while not stop_monitoring.is_set():
                        if time.time() - start_time > timeout:
                            # Inject a timeout exception into the main thread
                            thread_id = threading.get_ident()
                            if hasattr(threading, '_active'):
                                for t in threading._active.values():
                                    if t.ident == thread_id:
                                        t.raise_exc(TimeoutError)
                                        break
                            break
                        time.sleep(check_interval)
                
                monitor_thread = threading.Thread(target=monitor_timeout)
                monitor_thread.daemon = True
                
                try:
                    monitor_thread.start()
                    return func(*args, **kwargs)
                finally:
                    stop_monitoring.set()
                    monitor_thread.join(0.1)  # Short join timeout
        
        # Return the appropriate wrapper based on function type
        if is_async:
            return async_wrapper
        return sync_wrapper
        
    return decorator