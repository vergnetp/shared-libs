import concurrent.futures
import asyncio
import functools
import inspect
import threading
from typing import Callable, Any, Optional, TypeVar, Awaitable, Union, cast

# Type variables for generic functions
T = TypeVar('T')
SyncFunc = Callable[..., T]
AsyncFunc = Callable[..., Awaitable[T]]
AnyFunc = Union[SyncFunc[T], AsyncFunc[T]]

# Global thread pool with limited size for timeout operations
_timeout_executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)

# Thread-local storage to track current timeout context
_timeout_context = threading.local()

def get_current_timeout_context() -> Optional[float]:
    """Get the current timeout context if one exists."""
    return getattr(_timeout_context, 'timeout', None)

def set_timeout_context(timeout: Optional[float]):
    """Set the current timeout context."""
    _timeout_context.timeout = timeout

def clear_timeout_context():
    """Clear the current timeout context."""
    if hasattr(_timeout_context, 'timeout'):
        delattr(_timeout_context, 'timeout')

async def _execute_async_with_timeout(func: AsyncFunc[T], 
                                     args: tuple, 
                                     kwargs: dict, 
                                     timeout: Optional[float],
                                     override_context: bool = False) -> T:
    """Internal async execution with timeout."""
    # Check if already in a timeout context and not overriding
    current_context = get_current_timeout_context()
    if current_context is not None and not override_context:
        # Already in a timeout context, use the current timeout
        return await func(*args, **kwargs)
    
    # No context or overriding, apply timeout
    if timeout is None:
        return await func(*args, **kwargs)
    
    # Set timeout context for nested calls
    old_context = get_current_timeout_context()
    set_timeout_context(timeout)
    
    try:
        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Function {func.__name__} timed out after {timeout}s")
    finally:
        # Restore previous context
        if old_context is not None:
            set_timeout_context(old_context)
        else:
            clear_timeout_context()

def _execute_sync_with_timeout(func: SyncFunc[T], 
                              args: tuple, 
                              kwargs: dict, 
                              timeout: Optional[float],
                              override_context: bool = False) -> T:
    """Internal sync execution with timeout."""
    # Check if already in a timeout context and not overriding
    current_context = get_current_timeout_context()
    if current_context is not None and not override_context:
        # Already in a timeout context, just execute without timeout
        return func(*args, **kwargs)
    
    # No context or overriding, apply timeout
    if timeout is None:
        return func(*args, **kwargs)
    
    # Set timeout context for nested calls
    old_context = get_current_timeout_context()
    set_timeout_context(timeout)
    
    try:
        future = _timeout_executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError(f"Function {func.__name__} timed out after {timeout}s")
    except RuntimeError:
        raise RuntimeError(f"Thread pool at capacity ({_timeout_executor._max_workers} workers): cannot execute {func.__name__} with timeout")
    finally:
        # Restore previous context
        if old_context is not None:
            set_timeout_context(old_context)
        else:
            clear_timeout_context()

def execute_with_timeout(func: AnyFunc[T], 
                        args: tuple = (), 
                        kwargs: dict = None, 
                        timeout: Optional[float] = None,
                        override_context: bool = False) -> Union[T, Awaitable[T]]:
    """
    Execute a function with timeout, handling both sync and async functions.
    
    This unified helper automatically detects if the function is async or sync
    and applies the appropriate timeout mechanism.
    
    Args:
        func: Function to execute (either sync or async)
        args: Positional arguments to pass to the function
        kwargs: Keyword arguments to pass to the function
        timeout: Timeout in seconds (None means no timeout)
        override_context: If True, apply the specified timeout even if already 
                         in a timeout context. If False, nested calls within a
                         timeout context won't add additional timeouts.
    
    Returns:
        For sync functions: The direct result 
        For async functions: An awaitable that will resolve to the result
        
    Raises:
        TimeoutError: If execution exceeds the timeout
        RuntimeError: If thread pool is at capacity (sync functions only)
    
    Example (sync):
        result = execute_with_timeout(my_func, (arg1, arg2), {'kwarg': value}, timeout=5.0)
    
    Example (async):
        result = await execute_with_timeout(my_async_func, (arg1, arg2), {'kwarg': value}, timeout=5.0)
    """
    kwargs = kwargs or {}
    
    # If timeout is None and in timeout context, use the context timeout
    # unless override_context is True
    if timeout is None and not override_context:
        context_timeout = get_current_timeout_context()
        if context_timeout is not None:
            timeout = context_timeout
    
    # Detect if the function is async
    is_async = asyncio.iscoroutinefunction(func) or inspect.isawaitable(func)
    
    if is_async:
        # For async functions, return an awaitable
        async_func = cast(AsyncFunc[T], func)
        return _execute_async_with_timeout(async_func, args, kwargs, timeout, override_context)
    else:
        # For sync functions, execute directly
        sync_func = cast(SyncFunc[T], func)
        return _execute_sync_with_timeout(sync_func, args, kwargs, timeout, override_context)

def with_timeout(default_timeout: Optional[float] = 60.0):
    """
    Decorator that adds timeout functionality to both async and sync methods.
    
    The decorated method will have a timeout applied, which can be:
    1. Passed directly as a 'timeout' parameter to the method
    2. Or use the default_timeout value if none is provided
    
    For sync methods, uses a thread pool with max_workers=20 to implement timeouts.
    If the thread pool is at capacity, a RuntimeError is raised.
    
    When a function decorated with this decorator calls another function using
    execute_with_timeout, the inner function will inherit the outer timeout context
    unless explicitly overridden.
    
    Args:
        default_timeout: Default timeout in seconds if none is provided (None means no timeout)
    """
    def decorator(func: AnyFunc[T]) -> AnyFunc[T]:
        is_async = asyncio.iscoroutinefunction(func)

        # Update docstring with timeout info
        if func.__doc__:
            func.__doc__ += f"\n\n        timeout: Optional timeout in seconds (default: {default_timeout}s)"
        else:
            func.__doc__ = f"timeout: Optional timeout in seconds (default: {default_timeout or 'None'}s)"
        
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract timeout parameter or use default
            timeout = kwargs.pop('timeout', default_timeout)
            # We already know func is async, so we can await the result directly
            return await _execute_async_with_timeout(cast(AsyncFunc, func), args, kwargs, timeout, True)
                
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract timeout parameter or use default
            timeout = kwargs.pop('timeout', default_timeout) 
            # We already know func is sync
            return _execute_sync_with_timeout(cast(SyncFunc, func), args, kwargs, timeout, True)
        
        # Return the appropriate wrapper based on function type
        if is_async:
            return cast(AnyFunc[T], async_wrapper)
        return cast(AnyFunc[T], sync_wrapper)
        
    return decorator