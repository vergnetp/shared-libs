import functools
import asyncio
import time
import random
import sqlite3, psycopg2, asyncpg, pymysql, aiomysql, aiosqlite

def retry_with_backoff(max_retries=3, base_delay=0.1, max_delay=10.0, 
                      exceptions=None, total_timeout=30.0):
    """
    Decorator for retrying functions with exponential backoff on specified exceptions.
    
    Args:
        max_retries (int): Maximum number of retry attempts
        base_delay (float): Initial delay in seconds
        max_delay (float): Maximum delay between retries in seconds
        exceptions (tuple, optional): Exception types to catch and retry. If None,
                                     defaults to common database exceptions.
        total_timeout (float, optional): Maximum total time for all retries in seconds.
                                        Default is 30.0 seconds. Set to None to disable.
    """
    # Default common database exceptions to catch
    if exceptions is None:
        exceptions = (
            # Generic exception types that work across drivers
            ConnectionError,
            TimeoutError,
            # Combined list of common errors from various DB drivers
            # These are string names to avoid import errors if a driver isn't installed
            'OperationalError',
            'InterfaceError',
            'InternalError',
            'PoolError',
            'DatabaseError'
        )
    
    # Convert string exception names to actual exception classes if available
    exception_classes = []
    for exc in exceptions:
        if isinstance(exc, str):
            # Look for exception in common database modules
            for module in [sqlite3, psycopg2, asyncpg, pymysql, aiomysql, aiosqlite]:
                if hasattr(module, exc):
                    exception_classes.append(getattr(module, exc))
        else:
            exception_classes.append(exc)
    
    if exception_classes:
        exceptions = tuple(exception_classes)
    
    def decorator(func):

        # Add retry information to docstring
        msg = ''
        msg += f"\n\n        Note: Automatically retries on failure up to {max_retries} times"
        msg += f"\n        Retry delay: {base_delay}s initial, {max_delay}s maximum"
        if total_timeout:
            msg += f"\n        Total retry timeout: {total_timeout}s"
        func.__doc__ = '' if not func.__doc__ else func.__doc__
        func.__doc__ += msg
        
        from .. import log as logger
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            retries = 0
            delay = base_delay
            start_time = time.time()
            last_exception = None
            
            while True:
                # Check total timeout if set
                if total_timeout is not None and time.time() - start_time > total_timeout:
                    method_name = getattr(args[0].__class__ if args else None, '__name__', 'unknown') + '.' + func.__name__
                    logger.warning(f"Total timeout of {total_timeout}s exceeded for {method_name}")
                    if last_exception:
                        raise last_exception
                    raise TimeoutError(f"Operation timed out after {total_timeout}s for {method_name}")
                
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    retries += 1
                    if retries > max_retries:
                        logger.warning(f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}")
                        raise last_exception
                    
                    # Calculate delay with jitter to avoid thundering herd
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = min(delay * jitter, max_delay)
                    
                    # Check if next sleep would exceed total timeout
                    if total_timeout is not None:
                        elapsed = time.time() - start_time
                        remaining = total_timeout - elapsed
                        if remaining <= sleep_time:
                            # If we can't do a full sleep, either do a shorter one or just timeout now
                            if remaining > 0.1:  # Only sleep if we have a meaningful amount of time left
                                sleep_time = remaining * 0.9  # Leave a little margin
                                logger.debug(f"Adjusting sleep time to {sleep_time:.2f}s to respect total timeout")
                            else:
                                logger.warning(f"Total timeout of {total_timeout}s about to exceed for {func.__name__}")
                                raise last_exception
                    
                    logger.debug(f"Retry {retries}/{max_retries} for {func.__name__} after {sleep_time:.2f}s: {str(e)[:100]}")
                    try:
                        await asyncio.sleep(sleep_time)
                    except asyncio.CancelledError:
                        logger.warning("Retry sleep interrupted due to task cancellation")
                        raise
                    
                    # Exponential backoff
                    delay = min(delay * 2, max_delay)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            retries = 0
            delay = base_delay
            start_time = time.time()
            last_exception = None
            
            while True:
                # Check total timeout if set
                if total_timeout is not None and time.time() - start_time > total_timeout:
                    method_name = getattr(args[0].__class__ if args else None, '__name__', 'unknown') + '.' + func.__name__
                    logger.warning(f"Total timeout of {total_timeout}s exceeded for {method_name}")
                    if last_exception:
                        raise last_exception
                    raise TimeoutError(f"Operation timed out after {total_timeout}s for {method_name}")
                
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    retries += 1
                    if retries > max_retries:
                        logger.warning(f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}")
                        raise last_exception
                    
                    # Calculate delay with jitter to avoid thundering herd
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = min(delay * jitter, max_delay)
                    
                    # Check if next sleep would exceed total timeout
                    if total_timeout is not None:
                        elapsed = time.time() - start_time
                        remaining = total_timeout - elapsed
                        if remaining <= sleep_time:
                            # If we can't do a full sleep, either do a shorter one or just timeout now
                            if remaining > 0.1:  # Only sleep if we have a meaningful amount of time left
                                sleep_time = remaining * 0.9  # Leave a little margin
                                logger.debug(f"Adjusting sleep time to {sleep_time:.2f}s to respect total timeout")
                            else:
                                logger.warning(f"Total timeout of {total_timeout}s about to exceed for {func.__name__}")
                                raise last_exception
                    
                    logger.debug(f"Retry {retries}/{max_retries} for {func.__name__} after {sleep_time:.2f}s: {str(e)[:100]}")
                    time.sleep(sleep_time)
                    
                    # Exponential backoff
                    delay = min(delay * 2, max_delay)
        
        # Return appropriate wrapper based on whether the function is async or not
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator