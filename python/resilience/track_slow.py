
import functools
import asyncio
import time
import json

def track_slow_method(threshold=2.0):
    """
    Decorator that logs a warning if the execution of the method took longer than the threshold (default to 2 seconds).
    Logs the subclass.method names, execution time, and arguments.
    """
    from .. import log as logger
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                start = time.time()
                result = await func(*args, **kwargs)
                elapsed = time.time() - start

                if elapsed > threshold:
                    instance = args[0]
                    class_name = instance.__class__.__name__
                    method_name = func.__name__

                    try:
                        arg_str = json.dumps(args[1:], default=str)
                        kwarg_str = json.dumps(kwargs, default=str)
                    except Exception:
                        arg_str = str(args[1:])
                        kwarg_str = str(kwargs)

                    logger.warning(
                        f"Slow method {class_name}.{method_name} took {elapsed:.2f}s. "
                        f"Args={arg_str} Kwargs={kwarg_str}"
                    )

                return result
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                result = func(*args, **kwargs)
                elapsed = time.time() - start

                if elapsed > threshold:
                    instance = args[0]
                    class_name = instance.__class__.__name__
                    method_name = func.__name__

                    try:
                        arg_str = json.dumps(args[1:], default=str)
                        kwarg_str = json.dumps(kwargs, default=str)
                    except Exception:
                        arg_str = str(args[1:])
                        kwarg_str = str(kwargs)

                    logger.warning(
                        f"Slow method {class_name}.{method_name} took {elapsed:.2f}s. "
                        f"Args={arg_str} Kwargs={kwarg_str}"
                    )

                return result
        return wrapper
    return decorator

