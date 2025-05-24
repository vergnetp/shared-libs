from .. import log as logger

import time
import functools
import inspect
import json
from typing import Any, Callable, TypeVar, cast, Union, Optional

T = TypeVar('T')

def profile(func_or_max_length: Union[Callable, int] = 200) -> Union[Callable, Callable[[Callable], Callable]]:
    """
    Decorator that profiles and logs the execution time of a function.
    Always includes arguments and results in the log, with length limiting.
    
    Can be used as:
        @profile
        def my_function(): ...
    
    Or with parameters:
        @profile(max_length=500)
        def my_function(): ...
    
    Args:
        func_or_max_length: Either the function to decorate or max_length parameter
        
    Returns:
        Decorated function or a decorator function
    """
    # Check if this is a direct decoration (@profile) or with args (@profile())
    if callable(func_or_max_length):
        # It's being used directly as @profile without parentheses
        return _profile_decorator(func_or_max_length, max_length=200)
    else:
        # It's being used as @profile(...) with arguments
        max_length = func_or_max_length
        # Return a decorator function that will be applied to the function
        return lambda func: _profile_decorator(func, max_length=max_length)

def _profile_decorator(func: Callable[..., T], max_length: int = 200) -> Callable[..., T]:
    """The actual decorator implementation."""
    # Get function signature for argument names
    sig = inspect.signature(func)
    
    # Determine if the function is a coroutine
    is_async = inspect.iscoroutinefunction(func)

    # Extract component and subcomponent from function
    func_module = func.__module__.split('.')[-1]
    func_qualname = func.__qualname__
    
    # If function is a method, the qualname will be something like "ClassName.method_name"
    if '.' in func_qualname:
        class_name, method_name = func_qualname.rsplit('.', 1)
        component = class_name
        subcomponent = method_name
    else:
        # This is a regular function, not a method
        component = func_module
        subcomponent = func_qualname

    def _safe_serialize(obj: Any) -> str:
        """Safely convert an object to a string for logging."""
        if obj is None:
            return "None"
            
        try:
            return json.dumps(obj)
        except (TypeError, ValueError, OverflowError):
            result = str(obj)
            if len(result) > max_length:
                return result[:max_length] + "..."
            return result

    def _format_args(*args, **kwargs):
        """Format arguments for logging based on function signature."""
        # Get parameter names from signature
        params = list(sig.parameters.keys())
        
        # Build args dictionary
        args_dict = {}
        
        # Add positional arguments using param names when available
        for i, arg in enumerate(args):
            if i < len(params):
                arg_name = params[i]
            else:
                arg_name = f"arg{i}"
            args_dict[arg_name] = _safe_serialize(arg)
        
        # Add keyword arguments
        for key, value in kwargs.items():
            args_dict[key] = _safe_serialize(value)
            
        return args_dict

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        """Async wrapper for profiling async functions."""
        start_time = time.perf_counter()
        args_dict = _format_args(*args, **kwargs)
        
        try:
            result = await func(*args, **kwargs)
            execution_time = time.perf_counter() - start_time
            result_str = _safe_serialize(result)
            
            logger.profile(
                "Function profiled", 
                component=component,
                subcomponent=subcomponent,
                status="success",
                execution_time=round(execution_time, 6),
                result=result_str,
                **args_dict
            )
            return result
            
        except Exception as e:
            execution_time = time.perf_counter() - start_time
            logger.profile(
                "Function profiled", 
                component=component,
                subcomponent=subcomponent,
                status="error",
                execution_time=round(execution_time, 6),
                error=str(e),
                error_type=type(e).__name__,
                **args_dict
            )
            raise

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        """Sync wrapper for profiling regular functions."""
        start_time = time.perf_counter()
        args_dict = _format_args(*args, **kwargs)
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.perf_counter() - start_time
            result_str = _safe_serialize(result)
            
            logger.profile(
                "Function profiled", 
                component=component,
                subcomponent=subcomponent,
                status="success",
                execution_time=round(execution_time, 6),
                result=result_str,
                **args_dict
            )
            return result
            
        except Exception as e:
            execution_time = time.perf_counter() - start_time
            logger.profile(
                "Function profiled", 
                component=component,
                subcomponent=subcomponent,
                status="error",
                execution_time=round(execution_time, 6),
                error=str(e),
                error_type=type(e).__name__,
                **args_dict
            )
            raise

    # Return appropriate wrapper based on function type
    if is_async:
        return cast(Callable[..., T], async_wrapper)
    return cast(Callable[..., T], sync_wrapper)