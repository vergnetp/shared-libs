
import functools
import asyncio


def async_method(func):
    """
    Decorator that marks a function as asynchronous.
    
    This is a documentation-only decorator that doesn't change the behavior
    of the function. It helps clarify which methods are meant to be called
    with 'await' and makes async methods more visible in the codebase.
    
    Usage:
        @async_method
        async def some_async_function(self, ...):
            # Async function body
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    
    return wrapper

def overridable(method):
    """Marks a method as overridable for documentation / IDE purposes."""
    method.__overridable__ = True
    return method