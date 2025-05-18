from __future__ import annotations # for the inject_mixin decorator

import sys
import os
import re
import json
import random
import time
import datetime
import hashlib
import uuid
import asyncio
import contextlib
import traceback
from typing import Set, Awaitable, Callable, Optional, Tuple, List, Any, Dict, final, Union, ClassVar, Final, AsyncIterator, Iterator, TYPE_CHECKING
import itertools
import threading
import enum
import functools
from abc import ABC, abstractmethod
from ..errors import TrackError, try_catch
from .. import log as logger
from ..utils.patching import patcher
import sqlite3
import aiosqlite
import psycopg2
import asyncpg
import pymysql
import aiomysql
import inspect

import functools
import json

MAX_LENGTH = 200


def serialize(value):
    """Serialize any value to a JSON string, trimmed to MAX_LENGTH."""
    try:
        serialized = json.dumps(value, default=str)
    except Exception:
        serialized = str(value)

    if len(serialized) > MAX_LENGTH:
        return serialized[:MAX_LENGTH] + "..."
    return serialized


def log_method_calls(logger, cls):
    """Patch class methods in-place to log calls and return values."""

    for attr_name, attr in cls.__dict__.items():
        if attr_name.startswith("__"):
            continue  # Skip special methods
        
        if callable(attr) and not isinstance(attr, contextlib._AsyncGeneratorContextManager):        
            @functools.wraps(attr)
            def wrapper(self, *args, __attr=attr, __name=attr_name, **kwargs):
                class_name = self.__class__.__name__
                serialized_args = serialize({"args": args, "kwargs": kwargs})
                logger(f"v2 Called {class_name}.{__name} with {serialized_args}")

                result = __attr(self, *args, **kwargs)

                serialized_result = serialize(result)
                logger(f"v2 {class_name}.{__name} returned {serialized_result}")

                return result

            setattr(cls, attr_name, wrapper)

    return cls

# region     ############## DECORATORS ###########################

def merge_classes(mixin_class, target_class):
    # Get all public methods (non-underscore methods) from the mixin
    for name, method in inspect.getmembers(mixin_class, predicate=inspect.isfunction):
        #if not name.startswith('_'):  # Only add public methods
            # Add the method to the target class
        setattr(target_class, name, method)
    return target_class

def inject_mixin(mixin_class):
    """
    Class decorator that adds all public methods from a mixin class
    to the decorated class without inheritance.
    
    Args:
        mixin_class: The class whose methods will be added
        
    Returns:
        A decorator function that adds the mixin methods to a target class
    """
    def decorator(target_class):
        return merge_classes(mixin_class, target_class)
    return decorator

def with_timeout(default_timeout: float = 60.0):
    """
    Decorator that adds timeout functionality to both async and sync methods.
    
    The decorated method will have a timeout applied, which can be:
    1. Passed directly as a 'timeout' parameter to the method
    2. Or use the default_timeout value if none is provided
    
    For sync methods, implements a "soft timeout" that periodically checks elapsed time.
    
    Args:
        default_timeout: Default timeout in seconds if none is provided
    """
    def decorator(func):
        is_async = asyncio.iscoroutinefunction(func)
        
        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Extract timeout from kwargs or use default
                timeout = kwargs.pop('timeout', None) or default_timeout
                
                # Define the function that will be executed with a timeout
                async def execute_with_timeout():
                    start_time = time.time()
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        elapsed = time.time() - start_time
                        # Enhance the exception with timing information
                        e.args = (*e.args, f"Error after {elapsed:.2f}s")
                        raise
                
                # Execute with timeout
                try:
                    return await asyncio.wait_for(execute_with_timeout(), timeout=timeout)
                except asyncio.TimeoutError:
                    method_name = func.__name__
                    class_name = args[0].__class__.__name__ if args else None
                    full_name = f"{class_name}.{method_name}" if class_name else method_name
                    
                    # Create a more descriptive timeout error
                    raise TimeoutError(
                        f"{full_name} operation timed out after {timeout:.2f}s"
                    )
            
            wrapper = async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # Extract timeout from kwargs or use default
                timeout = kwargs.pop('timeout', None) or default_timeout
                
                # Create a timeout checker but don't add it to kwargs
                class TimeoutChecker:
                    def __init__(self):
                        self.start_time = time.time()
                        
                    def check(self):
                        elapsed = time.time() - self.start_time
                        if elapsed > timeout:
                            method_name = func.__name__
                            class_name = args[0].__class__.__name__ if args else None
                            full_name = f"{class_name}.{method_name}" if class_name else method_name
                            raise TimeoutError(
                                f"{full_name} operation timed out after {elapsed:.2f}s (limit: {timeout:.2f}s)"
                            )
                
                checker = TimeoutChecker()
                
                # Function that wraps the original with timeout checks
                def execute_with_timeout_checks():
                    # Instead of injecting checker into kwargs, check timeout before and after
                    checker.check()
                    result = func(*args, **kwargs)
                    checker.check()
                    return result
                
                try:
                    return execute_with_timeout_checks()
                except Exception as e:
                    elapsed = time.time() - checker.start_time
                    # Enhance the exception with timing information
                    if not isinstance(e, TimeoutError):
                        e.args = (*e.args, f"Error after {elapsed:.2f}s")
                    raise
            
            wrapper = sync_wrapper
        
        # Add a note about timeout in the docstring
        if func.__doc__:
            func.__doc__ += f"\n\n        timeout: Optional timeout in seconds (default: {default_timeout}s)"
            if not is_async:
                func.__doc__ += f"\n        Note: Uses soft timeout for synchronous method"
        
        return wrapper
    return decorator

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

def auto_transaction(func):
    """
    Decorator that automatically wraps a function in a transaction.
    Works for both sync and async functions.
    
    If the decorated function is called when a transaction is already in progress,
    it will use the existing transaction. Otherwise, it will create a new transaction,
    commit it if the function succeeds, or roll it back if an exception occurs.

    Need to be applied to methods of a class that offers in_transaction, begin_transaction (and commit/rollback)
    
    Usage:
        @auto_transaction
        def some_function(self, ...):
            # Function body, runs within a transaction
            
        @auto_transaction
        async def some_async_function(self, ...):
            # Async function body, runs within a transaction
    """
    @functools.wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        if self.in_transaction():
            return func(self, *args, **kwargs)
        else:
            self.begin_transaction()
            try:
                result = func(self, *args, **kwargs)
                self.commit_transaction()
                return result
            except:
                self.rollback_transaction()
                raise

    @functools.wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        if await self.in_transaction():
            return await func(self, *args, **kwargs)
        else:
            await self.begin_transaction()
            try:
                result = await func(self, *args, **kwargs)
                await self.commit_transaction()
                return result
            except:
                await self.rollback_transaction()
                raise

    # Choose the appropriate wrapper based on whether the function is async or not
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper

class CircuitState(enum.Enum):
    CLOSED = 'closed'      # Normal operation, requests go through
    OPEN = 'open'          # Service unavailable, short-circuits requests
    HALF_OPEN = 'half-open'  # Testing if the service is back

class CircuitBreaker:
    """
    Circuit breaker implementation that can be used as a decorator for sync and async methods.
    """
    # Class-level dictionary to store circuit breakers by name
    _breakers = {}
    _lock = threading.RLock()
    
    @classmethod
    def get_or_create(cls, name, failure_threshold=5, recovery_timeout=30.0, 
                     half_open_max_calls=3, window_size=60.0):
        """Get an existing circuit breaker or create a new one"""
        with cls._lock:
            if name not in cls._breakers:
                cls._breakers[name] = CircuitBreaker(
                    name, failure_threshold, recovery_timeout, 
                    half_open_max_calls, window_size
                )
            return cls._breakers[name]
    
    def __init__(self, name, failure_threshold=5, recovery_timeout=30.0, 
                half_open_max_calls=3, window_size=60.0):
        """
        Initialize a new circuit breaker.
        
        Args:
            name (str): Unique name for this circuit breaker
            failure_threshold (int): Number of failures before opening the circuit
            recovery_timeout (float): Seconds to wait before attempting recovery
            half_open_max_calls (int): Max calls to allow in half-open state
            window_size (float): Time window in seconds to track failures
        """
        self.name = name
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0
        self._last_state_change_time = time.time()
        self._half_open_calls = 0
        self._half_open_successes = 0
        
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._window_size = window_size
        
        self._recent_failures = []  # Track failures with timestamps
        self._lock = threading.RLock()  # For thread safety 
    
    @property
    def state(self):
        """Get the current state of the circuit breaker."""
        with self._lock:
            self._check_state_transitions()
            return self._state
    
    def _check_state_transitions(self):
        """Check and apply state transitions based on timing."""
        now = time.time()
        
        # Clean up old failures outside the window
        self._recent_failures = [t for t in self._recent_failures 
                              if now - t <= self._window_size]
        
        # Update failure count
        self._failure_count = len(self._recent_failures)
        
        # Check for state transitions
        if self._state == CircuitState.OPEN:
            if now - self._last_state_change_time >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._half_open_successes = 0
                self._last_state_change_time = now
                logger.info(f"Circuit {self.name} transitioning from OPEN to HALF_OPEN")
        
        elif self._state == CircuitState.HALF_OPEN:
            if self._half_open_successes >= self._half_open_max_calls:
                # Enough test calls succeeded, close the circuit
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._recent_failures = []
                self._last_state_change_time = now
                logger.info(f"Circuit {self.name} transitioning from HALF_OPEN to CLOSED")
    
    def record_success(self):
        """Record a successful call through the circuit breaker."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                self._check_state_transitions()
    
    def record_failure(self):
        """Record a failed call through the circuit breaker."""
        now = time.time()
        with self._lock:
            self._last_failure_time = now
            self._recent_failures.append(now)
            
            # Check if we need to open the circuit
            if self._state == CircuitState.CLOSED and len(self._recent_failures) >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._last_state_change_time = now
                logger.warning(f"Circuit {self.name} transitioning from CLOSED to OPEN after {self._failure_count} failures")
            
            elif self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reverts to open
                self._state = CircuitState.OPEN
                self._last_state_change_time = now
                logger.warning(f"Circuit {self.name} transitioning from HALF_OPEN back to OPEN due to failure")
    
    def allow_request(self):
        """
        Check if a request should be allowed through the circuit breaker.
        
        Returns:
            bool: True if the request should be allowed, False otherwise
        """
        with self._lock:
            self._check_state_transitions()
            
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.HALF_OPEN and self._half_open_calls < self._half_open_max_calls:
                self._half_open_calls += 1
                return True
            
            return False

class CircuitOpenError(Exception):
    """Exception raised when a circuit breaker prevents an operation"""
    pass

def circuit_breaker(name=None, failure_threshold=5, recovery_timeout=30.0, 
                   half_open_max_calls=3, window_size=60.0):
    """
    Decorator that applies circuit breaker pattern to a function.

    The circuit breaker pattern prevents cascading system failures by monitoring error rates. 
    If too many failures occur within a time window, the circuit 'opens' and immediately rejects new requests without attempting to call the failing service. 
    After a recovery timeout period, the circuit transitions to 'half-open' state, allowing a few test requests through. 
    If these succeed, the circuit 'closes' and normal operation resumes; if they fail, the circuit opens again to protect system resources (and the previous steps repeat)
    
    Args:
        name (str, optional): Name for this circuit breaker. If not provided, 
                             the function name will be used.
        failure_threshold (int): Number of failures before opening the circuit
        recovery_timeout (float): Seconds to wait before attempting recovery
        half_open_max_calls (int): Max calls to allow in half-open state
        window_size (float): Time window in seconds to track failures
        
    Usage:
        @circuit_breaker(name="db_operations")
        async def database_operation():
            # ...
    """
    def decorator(func):
        breaker_name = name or f"{func.__module__}.{func.__qualname__}"
        breaker = CircuitBreaker.get_or_create(
            breaker_name, failure_threshold, recovery_timeout, 
            half_open_max_calls, window_size
        )
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not breaker.allow_request():
                raise CircuitOpenError(f"Circuit {breaker_name} is OPEN")
            
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not breaker.allow_request():
                raise CircuitOpenError(f"Circuit {breaker_name} is OPEN")
            
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise
        
        # Choose the appropriate wrapper based on whether the function is async or not
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

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
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            retries = 0
            delay = base_delay
            start_time = time.time()
            
            while True:
                # Check total timeout if set
                if total_timeout is not None and time.time() - start_time > total_timeout:
                    method_name = getattr(args[0].__class__ if args else None, '__name__', 'unknown') + '.' + func.__name__
                    logger.warning(f"Total timeout of {total_timeout}s exceeded for {method_name}")
                    raise TimeoutError(f"Operation timed out after {total_timeout}s for {method_name}")
                
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries:
                        logger.warning(f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}")
                        raise
                    
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
                                raise TimeoutError(f"Operation timed out after {total_timeout}s for {func.__name__}")
                    
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
            
            while True:
                # Check total timeout if set
                if total_timeout is not None and time.time() - start_time > total_timeout:
                    method_name = getattr(args[0].__class__ if args else None, '__name__', 'unknown') + '.' + func.__name__
                    logger.warning(f"Total timeout of {total_timeout}s exceeded for {method_name}")
                    raise TimeoutError(f"Operation timed out after {total_timeout}s for {method_name}")
                
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries:
                        logger.warning(f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}")
                        raise
                    
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
                                raise TimeoutError(f"Operation timed out after {total_timeout}s for {func.__name__}")
                    
                    logger.debug(f"Retry {retries}/{max_retries} for {func.__name__} after {sleep_time:.2f}s: {str(e)[:100]}")
                    time.sleep(sleep_time)
                    
                    # Exponential backoff
                    delay = min(delay * 2, max_delay)
        
        # Return appropriate wrapper based on whether the function is async or not
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator

def track_slow_method(threshold=2.0):
    """
    Decorator that logs a warning if the execution of the method took longer than the threshold (default to 2 seconds).
    Logs the subclass.method names, execution time, and arguments.
    """
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

def overridable(method):
    """Marks a method as overridable for documentation / IDE purposes."""
    method.__overridable__ = True
    return method

# endregion ############## DECORATORS ###########################

#region      ############# SQL ############################

class SqlGenerator(ABC):
    """
    Abstract base class defining the interface for database-specific SQL generation.
    
    SQL Generation Syntax Conventions:
    ---------------------------------
    The database layer follows SQL Server-style syntax conventions that are automatically 
    translated to each database's native syntax:
    
    1. Identifiers (table and column names) should be wrapped in square brackets:
    - Correct: SELECT [column_name] FROM [table_name]
    - Incorrect: SELECT column_name FROM table_name
    
    2. Parameter placeholders should use question marks:
    - Correct: WHERE [id] = ?
    - Incorrect: WHERE [id] = $1 or WHERE [id] = %s
    
    Examples:
        - Basic query: "SELECT [id], [name] FROM [customers] WHERE [status] = ?"
        - Insert: "INSERT INTO [orders] ([id], [product]) VALUES (?, ?)"
        - Update: "UPDATE [users] SET [last_login] = ? WHERE [id] = ?"
    
    These conventions ensure SQL statements work safely across all supported 
    databases and properly handle reserved SQL keywords.
    """
    
    @final
    def get_comment_sql(self, tags: Optional[Dict[str, Any]]) -> Optional[str]:
        """
        Return SQL comment with tags if supported by database.

        Args:
            tags (Optional[Dict[str, Any]]): Tags to include as comment.

        Returns:
            Optional[str]: SQL comment or None.
        """
        if tags:
            parts = [f"{k}={v}" for k, v in tags.items()]
            return f"/* {' '.join(parts)} */"
        return None

    @overridable
    def get_timeout_sql(self, timeout: Optional[float]) -> Optional[str]:
        """
        Return a SQL statement to enforce query timeout (if applicable).

        Args:
            timeout (Optional[float]): Timeout in seconds.

        Returns:
            Optional[str]: SQL statement to enforce timeout, or None if not supported.
        """
        return None 
    
    def escape_identifier(self, identifier: str) -> str:
        """
        Escape a SQL identifier (table or column name).
        
        This must be implemented by each database-specific generator.
        """
        raise NotImplementedError("Subclasses must implement escape_identifier")
    
    def convert_query_to_native(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """
        Converts a standard SQL query with ? placeholders to a database-specific format and
        escapes SQL identifiers.
        
        Args:
            sql: SQL query with ? placeholders
            params: Positional parameters for the query
            
        Returns:
            Tuple containing the converted SQL and the converted parameters
        """
        # First, temporarily replace escaped brackets
        sql = sql.replace('[[', '___OPEN_BRACKET___').replace(']]', '___CLOSE_BRACKET___')
        
        # Process identifiers - replace [identifier] with properly escaped version
        pattern = r'\[(\w+)\]'
        
        def replace_id(match):
            return self.escape_identifier(match.group(1))
        
        escaped_sql = re.sub(pattern, replace_id, sql)
        
        # Restore escaped brackets
        escaped_sql = escaped_sql.replace('___OPEN_BRACKET___', '[').replace('___CLOSE_BRACKET___', ']')
        
        # Now handle parameter placeholders
        return self._convert_parameters(escaped_sql, params)
    
    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """
        Convert parameter placeholders.
        This should be implemented by each subclass based on their parameter style.
        """
        return sql, params
   
# endregion      ############# SQL ##########################


# region      ############# CONNETIONS ############################

class StatementCache:
    """Thread-safe cache for prepared SQL statements with dynamic sizing"""
    
    def __init__(self, initial_size=100, min_size=50, max_size=500, auto_resize=True):
        self._cache = {}
        self._max_size = initial_size
        self._min_size = min_size
        self._hard_max = max_size
        self._auto_resize = auto_resize
        self._lru = []  # Track usage for LRU eviction
        self._lock = threading.RLock()  # Use a reentrant lock for thread safety
        self._hits = 0
        self._misses = 0
        self._last_resize_check = time.time()
        self._resize_interval = 300  # Check resize every 5 minutes
  
    @staticmethod
    def hash(sql: str) -> str:
        """Generate a hash for the SQL statement"""
        return hashlib.md5(sql.encode('utf-8')).hexdigest()

    @property
    def hit_ratio(self) -> float:
        """Calculate the cache hit ratio"""
        with self._lock:
            total = self._hits + self._misses
            return self._hits / total if total > 0 else 0
    
    def _check_resize(self):
        """Dynamically resize the cache based on hit ratio and usage"""
        with self._lock:
            # Implementation unchanged - already thread-safe with lock
            pass
    
    def get(self, sql_hash) -> Optional[Tuple[Any, str]]:
        """Get a prepared statement from the cache in a thread-safe manner"""
        with self._lock:
            if sql_hash in self._cache:
                # Update LRU tracking
                if sql_hash in self._lru:
                    self._lru.remove(sql_hash)
                self._lru.append(sql_hash)
                self._hits += 1
                self._check_resize()
                return self._cache[sql_hash]
            self._misses += 1
            self._check_resize()
            return None
    
    def put(self, sql_hash, statement, sql):
        """Add a prepared statement to the cache in a thread-safe manner"""
        with self._lock:
            # Evict least recently used if at capacity
            if len(self._cache) >= self._max_size and sql_hash not in self._cache:
                if self._lru:  # Check if there are any items in the LRU list
                    lru_hash = self._lru.pop(0)
                    self._cache.pop(lru_hash, None)
            
            # Add to cache and update LRU
            self._cache[sql_hash] = (statement, sql)
            if sql_hash in self._lru:
                self._lru.remove(sql_hash)
            self._lru.append(sql_hash)

class ConnectionInterface(ABC):
    """Interface that defines the required methods and properties for connections."""
    @try_catch(log_success=True)
    @abstractmethod
    def execute(self, sql: str, params: Optional[tuple] = None, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """Execute SQL with parameters"""
        raise NotImplementedError("This method must be implemented by the host class")
    
    @try_catch(log_success=True)
    @abstractmethod
    def executemany(self, sql: str, param_list: List[tuple], timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """Execute SQL multiple times with different parameters"""
        raise NotImplementedError("This method must be implemented by the host class")
    
    @property
    @abstractmethod
    def sql_generator(self) -> SqlGenerator:
        """Returns the SQL parameter converter to use"""
        raise NotImplementedError("This property must be implemented by the host class")
    
class BaseConnection(ConnectionInterface):
    """
    Base class for database connections.
    """
    def __init__(self):
         self._statement_cache = StatementCache() 

    @try_catch    
    def _normalize_result(self, raw_result: Any) -> List[Tuple]:
        """
        Default implementation to normalize results to a list of tuples.
        
        This handles common result types:
        - None/empty results → empty list
        - Cursor objects → fetch all results as tuples
        - List of tuples → returned as is
        - List of dict-like objects → converted to tuples
        - Single scalar result → wrapped in a list with a single tuple
        
        Subclasses can override for database-specific behavior.
        """
        # Handle None/empty results
        if raw_result is None:
            return []
        
        # Handle cursor objects (common in sync drivers)
        if hasattr(raw_result, 'fetchall') and callable(getattr(raw_result, 'fetchall')):
            return raw_result.fetchall()
        
        # Already a list of tuples
        if (isinstance(raw_result, list) and 
            (not raw_result or isinstance(raw_result[0], tuple))):
            return raw_result
        
        # Handle Oracle/SQL Server specific cursor result types
        if hasattr(raw_result, 'rowcount') and hasattr(raw_result, 'description'):
            try:
                return list(raw_result)  # Many cursor objects are iterable
            except (TypeError, ValueError):
                if hasattr(raw_result, 'fetchall'):
                    return raw_result.fetchall()
        
        # List of dict-like objects (e.g., asyncpg Records)
        if (isinstance(raw_result, list) and raw_result and
            hasattr(raw_result[0], 'keys') and 
            callable(getattr(raw_result[0], 'keys'))):
            # Convert each record to a tuple
            return [tuple(record.values()) for record in raw_result]
        
        # Single scalar result
        if not isinstance(raw_result, (list, tuple)):
            return [(raw_result,)]
        
        # Default case - try to convert to a list of tuples
        try:
            return [tuple(row) if not isinstance(row, tuple) else row 
                  for row in raw_result]
        except (TypeError, ValueError):
            # If conversion fails, wrap in a list with single tuple
            return [(raw_result,)]

    def _finalize_sql(self, sql: str, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]] = None) -> str:
        combined_parts = []

        if tags:
            comment_sql = self.sql_generator.get_comment_sql(tags)
            if comment_sql:
                combined_parts.append(comment_sql)

        if timeout:
            timeout_sql = self.sql_generator.get_timeout_sql(timeout)
            if timeout_sql:
                combined_parts.append(timeout_sql)

        combined_parts.append(sql)

        return "\n".join(combined_parts)

    @try_catch
    async def _get_statement_async(self, sql: str, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]] = None) -> Any:
        """
        Gets a prepared statement from cache or creates a new one

        Note that statement is unique for the combination of sql, timeout and tags 
        
        Args:
            sql: SQL query with ? placeholders
            timeout: optional timeout in seconds
            tags: optional dictionary of tags to add in the sql comment
                       
        Returns:
            A database-specific prepared statement object
        """
        final_sql = self._finalize_sql(sql, timeout, tags)
        sql_hash = StatementCache.hash(final_sql)      
    
        stmt_tuple = self._statement_cache.get(sql_hash)
        if stmt_tuple:
            return stmt_tuple[0]  # First element is the statement
            
        converted_sql, _ = self.sql_generator.convert_query_to_native(final_sql)
        stmt = await self._prepare_statement_async(converted_sql)
        self._statement_cache.put(sql_hash, stmt, final_sql)

        return stmt

    @try_catch  
    def _get_statement_sync(self, sql: str, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]] = None) -> Any:
        """
        Gets a prepared statement from cache or creates a new one (synchronous version)
        
        Args:
            sql: SQL query with ? placeholders
            timeout: optional timeout in seconds
            tags: optional dictionary of tags to add in the sql comment
            
        Returns:
            A database-specific prepared statement object
        """
        final_sql = self._finalize_sql(sql, timeout, tags)
        sql_hash = StatementCache.hash(final_sql)       
    
        stmt_tuple = self._statement_cache.get(sql_hash)
        if stmt_tuple:
            return stmt_tuple[0]  # First element is the statement
            
        converted_sql, _ = self.sql_generator.convert_query_to_native(final_sql)
        stmt = self._prepare_statement_sync(converted_sql)
        self._statement_cache.put(sql_hash, stmt, final_sql)
        return stmt
    
class AsyncConnection(BaseConnection):
    """
    Abstract base class defining the interface for asynchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends asynchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """ 
    def __init__(self, conn: Any):
        super().__init__()
        self._conn = conn
        self._acquired_time = None
        self._acquired_stack = None
        self._last_active_time = None
        self._leaked = False
        self._id = str(uuid.uuid4())  # Unique ID for tracking

    def _mark_active(self):
        """Mark the connection as active (used recently)"""
        self._last_active_time = time.time()
    
    def _is_idle(self, timeout_seconds: int=1800):
        """Check if the connection has been idle for too long (default to 30mns)"""
        if self._last_active_time is None:
            return False
        return (time.time() - self._last_active_time) > timeout_seconds
    
    def _mark_leaked(self):
        """Mark this connection as leaked"""
        self._leaked = True
    
    @property
    def _is_leaked(self):
        """Check if this connection has been marked as leaked"""
        return self._leaked

     
    @async_method   
    @with_timeout()
    @track_slow_method()
    @circuit_breaker(name="async_execute")    
    async def execute(self, sql: str, params: Optional[tuple] = None, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """
        Asynchronously executes a SQL query with standard ? placeholders.
        
        Note:
            Automatically prepares and caches statements for repeated executions.

        Args:
            sql: SQL query with ? placeholders
            params: Parameters for the query
            timeout (float, optional): a timeout, in second, after which a TimeoutError is raised
            tags: optional dictionary of tags to inject to the sql as comment
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        self._mark_active()
        stmt = await self._get_statement_async(sql, timeout, tags)        
        raw_result = await self._execute_statement_async(stmt, params)
        result = self._normalize_result(raw_result)
        return result

    @async_method   
    @with_timeout()
    @auto_transaction
    @track_slow_method()
    @circuit_breaker(name="async_executemany")
    async def executemany(self, sql: str, param_list: List[tuple], timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """
        Asynchronously executes a SQL query multiple times with different parameters.

        Note:
            Automatically prepares and caches statements for repeated executions.            
            
        Args:
            sql: SQL query with ? placeholders
            param_list: List of parameter tuples, one for each execution
            timeout (float, optional): a timeout, in second, after which a TimeoutError is raised
            tags: optional dictionary of tags to inject to the sql as comment
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        self._mark_active()
        
        if not param_list:
            return []
        
        individual_timeout = None
        if timeout and timeout > 1:
            individual_timeout = timeout * 0.1

        stmt = await self._get_statement_async(sql, individual_timeout, tags)
       
        results = []
        for params in param_list:
            raw_result = await self._execute_statement_async(stmt, params)
            normalized = self._normalize_result(raw_result)
            if normalized:
                results.extend(normalized)
        return results
       

    def _get_raw_connection(self) -> Any:
        """ Return the underlying database connection (as defined by the driver) """
        return self._conn
    
    # region -- PRIVATE ABSTRACT METHODS ----------

    @async_method
    @try_catch
    @abstractmethod
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """
        Prepares a statement using database-specific API
        
        Args:
            native_sql: SQL with database-specific placeholders
            
        Returns:
            A database-specific prepared statement object
        """
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """
        Executes a prepared statement with given parameters
        
        Args:
            statement: A database-specific prepared statement
            params: Parameters to bind
            
        Returns:
            Raw execution result
        """
        pass

    # endregion
    
    # region -- PUBLIC ABSTRACT METHODS ----------

    @abstractmethod
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def begin_transaction(self) -> None:
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def commit_transaction(self) -> None:
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def rollback_transaction(self) -> None:
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def close(self) -> None:
        """
        Closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        pass

    @async_method
    @abstractmethod
    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        pass
 
    # endregion --------------------------------

class SyncConnection(BaseConnection):
    """
    Abstract base class defining the interface for synchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends synchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """
    def __init__(self, conn: Any):
        super().__init__()
        self._conn = conn
    
    @with_timeout()
    @track_slow_method()
    @circuit_breaker(name="sync_execute")
    def execute(self, sql: str, params: Optional[tuple] = None, timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """
        Synchronously executes a SQL query with standard ? placeholders.
        
        Note:
            Automatically prepares and caches statements for repeated executions.

        Args:
            sql: SQL query with ? placeholders
            params: Parameters for the query
            timeout: optional timeout in seconds after which a TimeoutError is raised
            tags: optional dictionary of tags to inject as sql comments
            
        Returns:
            List[Tuple]: Result rows as tuples
        """
        stmt = self._get_statement_sync(sql, timeout, tags)
        raw_result = self._execute_statement_sync(stmt, params)
        return self._normalize_result(raw_result)

    @with_timeout()
    @track_slow_method()
    @auto_transaction
    @circuit_breaker(name="sync_executemany")
    @overridable
    def executemany(self, sql: str, param_list: List[tuple], timeout: Optional[float] = None, tags: Optional[Dict[str, Any]]=None) -> List[Tuple]:
        """
        Synchronously executes a SQL query multiple times with different parameters.

        Note:
            Automatically prepares and caches statements for repeated executions.
            Subclasses SHOULD override this method if the underlying driver supports native batch/array/bulk execution for better performance.
                   
        Args:
            sql: SQL query with ? placeholders
            param_list: List of parameter tuples, one for each execution
            timeout (float, optional): a timeout, in second, after which a TimeoutError is raised
            tags: optional dictionary of tags to inject to the sql as comment

        Returns:
            List[Tuple]: Result rows as tuples
        """
        if not param_list:
            return []
    
        individual_timeout = None
        if timeout and timeout > 1:
            individual_timeout = timeout * 0.1

        stmt = self._get_statement_sync(sql, individual_timeout, tags)

        # Fallback to executing one-by-one
        results = []
   
        for params in param_list:
            raw_result = self._execute_statement_sync(stmt, params)
            normalized = self._normalize_result(raw_result)
            if normalized:
                results.extend(normalized)

        return results

    def _get_raw_connection(self) -> Any:
        """ Return the underlying database connection (as defined by the driver) """
        return self._conn
    
    # region -- PRIVATE ABSTRACT METHODS ----------

    @try_catch
    @abstractmethod
    async def _prepare_statement_sync(self, native_sql: str) -> Any:
        """
        Prepares a statement using database-specific API
        
        Args:
            native_sql: SQL with database-specific placeholders
            
        Returns:
            A database-specific prepared statement object
        """
        pass

    @try_catch
    @abstractmethod
    async def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """
        Executes a prepared statement with given parameters
        
        Args:
            statement: A database-specific prepared statement
            params: Parameters to bind
            
        Returns:
            Raw execution result
        """
        pass
    
    # endregion --------------------------------
    
    # region -- PUBLIC ABSTRACT METHODS ----------

    @property
    @abstractmethod
    def sql_generator(self) -> SqlGenerator:
        """Returns the parameter converter for this connection."""
        pass

    @abstractmethod
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""
        pass

    @try_catch
    @abstractmethod
    def begin_transaction(self) -> None:
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        pass

    @try_catch
    @abstractmethod
    def commit_transaction(self) -> None:
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        pass

    @try_catch
    @abstractmethod
    def rollback_transaction(self) -> None:
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        pass

    @try_catch
    @abstractmethod
    def close(self) -> None:
        """
        Closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        pass

    @abstractmethod
    def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        pass
 
    # endregion --------------------------------

 #endregion      ############# CONNETIONS #########################


# region      ############# POOLS ############################

class ConnectionPool(ABC):
    """
    Abstract connection pool interface that standardizes behavior across database drivers.
    
    This interface provides a consistent API for connection pool operations, regardless
    of the underlying database driver. It abstracts away driver-specific details and
    ensures that all pools implement the core functionality needed by the connection
    management system.
    
    Implementation Requirements:
        - Must handle timeout properly in acquire()
        - Must properly track connection state
        - Must handle force close behavior appropriately
        - Must implement health checking for pool vitality
    """
    @async_method
    @try_catch
    async def health_check(self) -> bool:
        """
        Checks if the pool is healthy by testing a connection.
        
        To avoid excessive health checks, this caches the result for a short time.
        
        Returns:
            True if the pool is healthy, False otherwise
        """
        # Get cache values from instance attributes or provide defaults
        last_health_check = getattr(self, '_last_health_check', 0)
        health_check_interval = getattr(self, '_health_check_interval', 5.0)
        healthy = getattr(self, '_healthy', True)
        
        now = time.time()
        if now - last_health_check < health_check_interval and healthy:
            return healthy
            
        setattr(self, '_last_health_check', now)
        try:
            conn = await self.acquire()
            try:
                # This is the database-specific part - subclasses should override
                await self._test_connection(conn)
                setattr(self, '_healthy', True)
                return True
            finally:
                await self.release(conn)
        except Exception:
            setattr(self, '_healthy', False)
            return False
    
    @try_catch
    @abstractmethod
    async def _test_connection(self, connection: Any) -> None:
        """Run a database-specific test query on the connection"""
        pass

    @async_method
    @try_catch
    @abstractmethod
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires a connection from the pool with optional timeout.
        
        Args:
            timeout (Optional[float]): Maximum time in seconds to wait for a connection.
                                      If None, use the pool's default timeout.
        
        Returns:
            Any: A database connection specific to the underlying driver.
            
        Raises:
            TimeoutError: If the acquisition times out.
            Exception: For other acquisition errors.
        """
        pass
        
    @async_method
    @try_catch
    @abstractmethod
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The connection to release, specific to the underlying driver.
            
        Raises:
            Exception: If the connection cannot be released.
        """
        pass
        
    @async_method
    @try_catch
    @abstractmethod
    async def close(self, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:          
            timeout (Optional[float]): Maximum time in seconds to wait for graceful shutdown                                                           

        """
        pass
    

    
    @property
    @abstractmethod
    def min_size(self) -> int:
        """
        Gets the minimum number of connections the pool maintains.
        
        Returns:
            int: The minimum pool size.
        """
        pass
    
    @property
    @abstractmethod
    def max_size(self) -> int:
        """
        Gets the maximum number of connections the pool can create.
        
        Returns:
            int: The maximum pool size.
        """
        pass
    
    @property
    @abstractmethod
    def size(self) -> int:
        """
        Gets the current number of connections in the pool.
        
        Returns:
            int: The total number of connections (both in-use and idle).
        """
        pass
    
    @property
    @abstractmethod
    def in_use(self) -> int:
        """
        Gets the number of connections currently in use.
        
        Returns:
            int: The number of connections currently checked out from the pool.
        """
        pass
    
    @property
    @abstractmethod
    def idle(self) -> int:
        """
        Gets the number of idle connections in the pool.
        
        Returns:
            int: The number of connections currently available for checkout.
        """
        pass
    
class PoolManager(ABC):
    """
    Abstract base class to manage the lifecycle of asynchronous connection pools.
    
    This class implements a shared connection pool management system based on database configuration. Pools are created lazily, shared across instances with the same configuration, and can be properly closed during application shutdown.
    
    Subclasses must also inherit from `DatabaseConfig` or provide compatible `hash()` and `alias()` methods, and must implement the abstract method `_create_pool()` to create a backend-specific connection pool.
    
    Key Features:
        - Pools are shared across instances with the same database configuration
        - Pools are lazily initialized on first use
        - Pools are uniquely identified by the hash of their configuration
        - Thread-safe pool initialization with locks
        - Connection health checking
        - Graceful pool shutdown
    
    Thread Safety:
        - Pool initialization is protected by asyncio.Lock to ensure thread safety
        - Shared pools are accessed via atomic dictionary operations
        - Each distinct database configuration gets its own lock object
        - Multiple threads can safely create instances with the same configuration
        - Pool access is not generally thread-safe and should be used from a single thread
    
    Class Attributes:
        _shared_pools (Dict[str, Any]): Dictionary mapping config hashes to pool instances
        _shared_locks (Dict[str, asyncio.Lock]): Locks for thread-safe pool initialization
        _active_connections (Dict[str, Set[AsyncConnection]]): Keep track of active connections
        _shutting_down: [Dict[str, bool]: Keep track of pools shutdown status
        _metrics: Dict[str, Dict[str, int]]: keep track of some metrics for each pool (e.g. how many connection acquisitions timed out)
    """
    _shared_pools: ClassVar[Final[Dict[str, Any]]] = {}
    _shared_locks: ClassVar[Final[Dict[str, asyncio.Lock]]] = {}
    _active_connections: ClassVar[Final[Dict[str, Set[AsyncConnection]]]] = {}
    _shutting_down: ClassVar[Final[Dict[str, bool]]] = {}
    _metrics: ClassVar[Final[Dict[str, Dict[str, int]]]] = {}
    _metrics_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    
    def __init__(self, config: DatabaseConfig, connection_acquisition_timeout: float=60):
        self._alias = config.alias()
        self._hash = config.hash()
        self.config = config
        self._connection_acquisition_timeout = connection_acquisition_timeout     
        
        # Try to initialize pool and start leak detection task if in async environment
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._initialize_pool_if_needed())
            loop.create_task(self._leak_detection_task())
        except RuntimeError:
            # Not in an async environment, which is fine
            pass

    @property
    def connection_acquisition_timeout(self) -> float:
        '''Returns the connection acquisition timeout defined in PoolManager'''
        return self._connection_acquisition_timeout
    
    async def _leak_detection_task(self):
        """Background task that periodically checks for and recovers from connection leaks"""
        IDLE_TIMEOUT = 1800  # 30 minutes idle time before considering a connection dead
        LEAK_THRESHOLD_SECONDS = 300  # if a connection has been used for longer than 5 mins, it should be considered leaked
        SLEEP_TIME = 300  # 300 seconds are 5 mins

        logger.info("Task started: will check and reclaim leaked or idle connections from the pool", 
                    pool_name=self.alias(), 
                    check_interval_mins=int(SLEEP_TIME/60))
                    
        while True:
            try:
                # Wait to avoid excessive CPU usage
                try:
                    await asyncio.sleep(SLEEP_TIME)  
                except asyncio.CancelledError:
                    logger.info("Task cancelled", 
                            pool_name=self.alias())
                    break
                
                # Check for leaked connections
                leaked_conns = await self.check_for_leaked_connections(threshold_seconds=LEAK_THRESHOLD_SECONDS)  
                
                # Attempt recovery for leaked connections
                for conn, duration, stack in leaked_conns:
                    try:
                        # Mark as leaked to avoid duplicate recovery attempts
                        conn._mark_leaked()
                        
                        # Try to gracefully return to the pool
                        logger.warning(f"Attempting to recover leaked connection that has leaked for {duration:.2f}s)", 
                                    pool_name=self.alias(), 
                                    duration_seconds=duration,
                                    connection_id=conn._id)
                                    
                        await self._release_connection_to_pool(conn)
                        
                        logger.info("Successfully recovered leaked connection", 
                                pool_name=self.alias(), connection_id=conn._id)
                                
                    except Exception as e:
                        logger.error("Failed to recover leaked connection", pool_name=self.alias(), connection_id=conn._id, error=e.to_string() if hasattr(e, 'to_string') else str(e))
                                    
                        self._connections.discard(conn)  # Explicitly discard leaked connection
                        # Try to close directly as a last resort
                        try:
                            await conn.close()
                        except Exception:
                            pass
                
                # Additionally check for idle connections               
                idle_conns = []
                
                for conn in self._connections:
                    if conn._is_idle(IDLE_TIMEOUT) and not conn._is_leaked:
                        idle_conns.append(conn)
                
                # Log idle connections
                if idle_conns:
                    logger.warning(f"There some idle connections", 
                                pool_name=self.alias(), 
                                idle_connections_count=len(idle_conns), 
                                idle_threshold_mins=int(IDLE_TIMEOUT/60))

                # Also recover idle connections
                for conn in idle_conns:
                    try:
                        logger.warning("Recovering idle connection", 
                                    pool_name=self.alias(), connection_id=conn._id)
                                    
                        await self._release_connection_to_pool(conn)
                        
                    except Exception as e:
                        logger.error("Failed to recover idle connection", 
                                    pool_name=self.alias(), connection_id=conn._id,
                                    error=e.to_string() if hasattr(e, 'to_string') else str(e))
                                    
            except Exception as e:
                logger.error(f"Error in connection leak detection task for {self.alias()} pool: {e}", 
                            pool_name=self.alias(), connection_id=conn._id,
                            error=e.to_string() if hasattr(e, 'to_string') else str(e))

    def alias(self):
        return self._alias

    def hash(self):
        return self._hash

    @try_catch
    def _calculate_pool_size(self) -> Tuple[int, int]:
        """
        Calculate optimal pool size based on workload characteristics.
        
        This uses a combination of:
        - CPU count (for CPU-bound workloads)
        - System memory (to avoid exhausting resources)
        - Expected concurrency
        
        Returns:
            Tuple[int, int]: (min_size, max_size) of the connection pool
        """
        # Get system information
        cpus = os.cpu_count() or 1
        
        # Try to get available memory in GB
        try:
            import psutil
            available_memory_gb = psutil.virtual_memory().available / (1024 * 1024 * 1024)
        except (ImportError, AttributeError):
            # Default assumption if psutil is not available
            available_memory_gb = 4.0
        
        estimated_mem = 0.03
        
        # Calculate max connections based on memory
        max_by_memory = int(available_memory_gb / estimated_mem * 0.5)  # Use no more than 50% of available memory

        min_size = max(3, cpus // 2)
        # Max should be enough to handle spikes but not exhaust resources
        max_size = min(max(cpus * 4, 20), max_by_memory)       
        
        # Log the calculation for transparency
        logger.debug(f"Calculated connection pool size: min={min_size}, max={max_size} " +
                    f"(cpus={cpus}, mem={available_memory_gb:.1f}GB)")
        
        return min_size, max_size

    async def _track_metrics(self, is_new: bool=True, error: Exception=None, is_timeout: bool=False):
        k = self.hash()
        async with self._metrics_lock:
            if k not in self._metrics:
                self._metrics[k] = {
                    'total_acquired': 1 if is_new and not error and not is_timeout else 0,
                    'total_released': 0,
                    'current_active': 1 if is_new and not error and not is_timeout else 0,
                    'peak_active': 1 if is_new and not error and not is_timeout else 0,
                    'errors': 0 if not error else 1,
                    'timeouts': 0 if not is_timeout else 1,
                    'last_timeout_timestamp': time.time() if is_timeout else None,
                    'avg_acquisition_time': 0.0,
                }
            else:
                metrics = self._metrics[k]
                if is_timeout:
                    metrics['timeouts'] += 1
                    metrics['last_timeout_timestamp'] = time.time()
                elif error:
                    metrics['errors'] += 1
                else:
                    if is_new:
                        metrics['total_acquired'] += 1
                        metrics['current_active'] += 1
                    else:
                        metrics['total_released'] += 1
                        metrics['current_active'] = max(0, metrics['current_active'] - 1)

                    metrics['peak_active'] = max(metrics['peak_active'], metrics['current_active'])

        try:
            logger.info(f"Pool status:\n{json.dumps(self.get_pool_status())}")
        except Exception as e:
            logger.warning(f"Error logging metrics: {e}")

    def get_pool_status(self) -> Dict[str, Any]:
        """
        Gets comprehensive status information about the connection pool.
        
        Returns:
            Dict[str, Any]: Dictionary containing detailed pool status.
        """
        if not self._pool:
            return {
                "initialized": False,
                "alias": self.alias(),
                "hash": self.hash()
            }
            
        metrics = self._metrics.get(self.hash(), {})
        
        return {
            "initialized": True,
            "alias": self.alias(),
            "hash": self.hash(),     
            "min_size": self._pool.min_size,
            "max_size": self._pool.max_size,
            "current_size": self._pool.size,
            "in_use": self._pool.in_use,
            "idle": self._pool.idle,
            "active_connections": len(self._connections),
            "shutting_down": self._shutting_down.get(self.hash(), False),
            "metrics": {
                "total_acquired": metrics.get("total_acquired", 0),
                "total_released": metrics.get("total_released", 0),
                "current_active": metrics.get("current_active", 0),
                "peak_active": metrics.get("peak_active", 0),
                "errors": metrics.get("errors", 0),
                "timeouts": metrics.get("timeouts", 0),
                "last_timeout": metrics.get("last_timeout_timestamp"),
                "avg_acquisition_time": metrics.get("avg_acquisition_time", 0),
            }
        }
    
    @async_method
    @classmethod
    async def health_check_all_pools(cls) -> Dict[str, bool]:
        """
        Checks the health of all connection pools.
        
        Returns:
            Dict[str, bool]: Dictionary mapping pool keys to health status.
        """
        results = {}
        for key, pool in cls._shared_pools.items():
            try:
                is_healthy = await pool.health_check()
                results[key] = is_healthy
            except Exception:
                results[key] = False
        return results    

    @classmethod
    def get_pool_metrics(cls, config_hash=None) -> Dict:
        if config_hash:
            return cls._metrics.get(config_hash, {})
        return cls._metrics
    
    @property
    def _pool(self) -> Optional[Any]:
        """
        Gets the connection pool for this instance's configuration.
        
        The pool is retrieved from the shared pools dictionary using the
        hash of this instance's configuration as the key.
        
        Returns:
            Optional[Any]: The connection pool, or None if not initialized.
        """
        return self._shared_pools.get(self.hash())

    @_pool.setter
    def _pool(self, value: Any) -> None:
        """
        Sets or clears the connection pool for this instance's configuration.
        
        If value is None, the pool is removed from the shared pools dictionary.
        Otherwise, the pool is stored in the shared pools dictionary using the
        hash of this instance's configuration as the key.
        
        Args:
            value (Any): The connection pool to set, or None to clear.
        """
        k = self.hash()
        if value is None:
            self._shared_pools.pop(k, None)
        else:
            self._shared_pools[k] = value

    @property
    def _pool_lock(self) -> asyncio.Lock:
        """
        Gets the lock for this instance's configuration.
        
        The lock is used to ensure thread-safe initialization of the connection pool.
        If no lock exists for this configuration, a new one is created.
        
        Returns:
            asyncio.Lock: The lock for this instance's configuration.
        """
        k = self.hash()
        if k not in self._shared_locks:
            self._shared_locks[k] = asyncio.Lock()
        return self._shared_locks[k]

    @property
    def _connections(self) -> Set[AsyncConnection]:
        """Gets the set of active connections for this instance's configuration."""
        k = self.hash()
        if k not in self._active_connections:
            self._active_connections[k] = set()
        return self._active_connections[k]      
   
    @try_catch
    async def _get_connection_from_pool(self, wrap_raw_connection: Callable) -> AsyncConnection:
        """
        Acquires a connection from the pool with timeout handling and leak tracking.
        """
        if self._shutting_down.get(self.hash(), False):
            raise RuntimeError(f"Cannot acquire new connections: pool for {self.alias()} is shutting down")
        
        if not self._pool:
            await self._initialize_pool_if_needed()
        if not self._pool:
            raise Exception(f"Cannot get a connection from the pool as the pool could not be initialized for {self.alias()} - {self.hash()}")
                
        try:
            start_time = time.time()
            try:
                # Acquire connection
                raw_conn = await self._pool.acquire(timeout=self._connection_acquisition_timeout)
                acquisition_time = time.time() - start_time
                logger.debug(f"Connection acquired from {self.alias()} pool in {acquisition_time:.2f}s")
                await self._track_metrics(True)
            except TimeoutError as e:
                acquisition_time = time.time() - start_time
                logger.warning(f"Timeout acquiring connection from {self.alias()} pool after {acquisition_time:.2f}s")
                await self._track_metrics(is_new=False, error=None, is_timeout=True)
                raise  # Re-raise the TimeoutError
                
        except Exception as e:
            if isinstance(e, TimeoutError):
                # Re-raise the timeout
                raise
                
            # Other errors
            pool_info = {
                'active_connections': len(self._connections),
                'pool_exists': self._pool is not None,
            }
            logger.error(f"Connection acquisition failed for {self.alias()} pool: {e}, pool info: {pool_info}")
            await self._track_metrics(True, e)           
            raise
        
        async_conn = wrap_raw_connection(raw_conn)
        
        # Add tracking information for leak detection
        async_conn._acquired_time = time.time()
        async_conn._acquired_stack = traceback.format_stack()
        
        self._connections.add(async_conn)
        return async_conn

    @try_catch
    async def _release_connection_to_pool(self, async_conn: AsyncConnection) -> None:
        try:
            # Calculate how long this connection was out
            if hasattr(async_conn, '_acquired_time'):
                duration = time.time() - async_conn._acquired_time
                
                # Log if this connection was out for a long time
                if duration > 60:  # 1 minute
                    logger.warning(
                        f"Connection from {self.alias()} pool was out for {duration:.2f}s. "
                        f"This may indicate inefficient usage. Stack trace at acquisition:\n"
                        f"{getattr(async_conn, '_acquired_stack', 'Stack not available')}"
                    )
                
                # Clean up tracking attributes
                delattr(async_conn, '_acquired_time')
                delattr(async_conn, '_acquired_stack')
            
            start_time = time.time()
            # Use the ConnectionPool interface
            await self._pool.release(async_conn._get_raw_connection())
            logger.debug(f"Connection released back to {self.alias()} pool in {(time.time() - start_time):.2f}s")
            await self._track_metrics(False)
        except Exception as e:
            pool_info = {
                'active_connections': len(self._connections),
                'pool_exists': self._pool is not None,
            }
            logger.error(f"Connection release failed for {self.alias()} pool: {e}, pool info: {pool_info}")
            await self._track_metrics(False, e)
            raise
        finally:
            self._connections.discard(async_conn)

    @async_method
    @try_catch
    async def check_for_leaked_connections(self, threshold_seconds=300) -> List[Tuple[AsyncConnection, float, str]]:
        """
        Check for connections that have been active for longer than the threshold.
        Returns a list of (connection, duration, stack) tuples for leaked connections.
        """
        now = time.time()
        leaked_connections = []
        
        for conn in self._connections:
            if hasattr(conn, '_acquired_time'):
                duration = now - conn._acquired_time
                if duration > threshold_seconds:
                    leaked_connections.append((
                        conn,
                        duration,
                        getattr(conn, '_acquired_stack', 'Stack not available')
                    ))
        
        # Log any leaks
        for conn, duration, stack in leaked_connections:
            logger.warning(
                f"Connection leak detected in {self.alias()} pool! "
                f"Connection has been active for {duration:.2f}s. "
                f"Stack trace at acquisition:\n{stack}"
            )
        
        return leaked_connections

    @try_catch
    async def _initialize_pool_if_needed(self) -> None:
        """
        Initializes the connection pool if it doesn't exist or isn't usable.
        
        This method first checks if a pool already exists and is usable by attempting to acquire a connection and run a test query. If the pool doesn't exist or isn't usable, a new pool is created.
        
        Thread Safety:
            - Pool creation is protected by a per-configuration lock
            - Multiple concurrent calls will only create one pool instance
            - The lock ensures only one thread can initialize a pool at a time
            - After initialization, the pool itself must handle concurrent access
            
        Concurrency:
            - Safe for multiple concurrent calls from the same event loop
            - Database connections are tested with a simple SELECT 1 query
            - Failed pools are properly closed before recreating them
            - Connections acquired for testing are properly released back to the pool
        """
        # Check if existing pool is usable
        if self._pool:
            is_healthy = False
            try:
                is_healthy = await self._pool.health_check()
            except Exception as e:
                pass
            if not is_healthy:
                logger.debug(f"Existing pool unusable for {self.alias()} - {self.hash()}: {e}")
                try:
                    await self._pool.close()
                except Exception:
                    pass
                self._pool = None

        # Create pool under lock
        async with self._pool_lock:
            if self._pool is None:
                try:
                    start_time = time.time()
                    self._pool = await self._create_pool(self.config, self._connection_acquisition_timeout)
                    logger.info(f"{self.alias()} - {self.hash()} async pool initialized in {(time.time() - start_time):.2f}s")
                except Exception as e:
                    logger.error(f"{self.alias()} - {self.hash()} async pool creation failed: {e}")
                    self._pool = None
                    raise

    @try_catch
    async def _test_connection(self, conn: Any) -> None:
        """
        Tests if a connection is usable by executing a simple query.
        
        Args:
            conn (Any): The connection to test.
            
        Raises:
            Exception: If the test query fails, indicating the connection is not usable.
        """
        try:
            await conn.execute("SELECT 1")
        except Exception:
            raise
    
    @classmethod
    @try_catch
    async def _cleanup_connection(cls, async_conn: AsyncConnection):
        try:            
            try:
                await async_conn.commit_transaction()
            except Exception as e:
                logger.warning(f"Error committing transaction during cleanup: {e}")

            try:      
                raw_conn = async_conn._get_raw_connection()
                for key, conn_set in cls._active_connections.items():
                    if async_conn in conn_set:
                        pool = cls._shared_pools.get(key)
                        if pool:
                            await pool.release(raw_conn)
                        conn_set.discard(async_conn)
                        break
            except Exception as e:
                logger.warning(f"Error releasing connection during cleanup: {e}")
        except Exception as e:
            logger.error(f"Error during connection cleanup: {e}")

    @classmethod
    @try_catch
    async def _release_pending_connections(cls, key, timeout):
        # Handle active connections first
        active_conns = cls._active_connections.get(key, set())
        if active_conns:
            logger.info(f"Cleaning up {len(active_conns)} active connections for pool {key}")
            
            # Process each tracked connection with a timeout
            cleanup_tasks = []
            for conn in list(active_conns):
                task = asyncio.create_task(cls._cleanup_connection(conn))
                cleanup_tasks.append(task)
            
            # Wait for all connections to be cleaned up with timeout
            if cleanup_tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*cleanup_tasks), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for connections to be released for pool {key}")

    @classmethod
    @try_catch
    async def close_pool(cls, config_hash: Optional[str] = None, timeout: Optional[float]=60) -> None:
        """
        Closes one or all shared connection pools with proper cleanup.

        This method should be called during application shutdown to properly
        release database resources. It first prevents new connections from being acquired,
        then attempts to gracefully commit and release all active connections before
        closing the pool.

        Args:
            config_hash (Optional[str], optional): Hash of the configuration
                for the pool to close. If None, all pools will be closed.
                Defaults to None.
            timeout (Optional[float]): The number of seconds to wait before
                canceling the proper commit+release of pending connections. 
                If timeout is reached, will forcibly close connections (losing active transactions) (at least for Postgres, MySql and Sqlite)
        """
        keys = [config_hash] if config_hash else list(cls._shared_pools.keys())
        
        # First mark all specified pools as shutting down
        for key in keys:
            cls._shutting_down[key] = True
            logger.info(f"Pool {key} marked as shutting down, no new connections allowed")
        
        # Then process each pool
        for key in keys:
            try:
                await PoolManager._release_pending_connections(key, timeout)
                pool = cls._shared_pools.get(key)
                if pool:
                    try:
                        # Use the ConnectionPool interface force parameter
                        await pool.close()
                        logger.info(f"Pool for {key} closed")
                    except Exception as e:
                        logger.error(f"Error closing pool for {key}: {e}")
            finally:
                # Clean up all references to this pool
                cls._shared_pools.pop(key, None)
                cls._shared_locks.pop(key, None)
                cls._active_connections.pop(key, None)
                cls._shutting_down.pop(key, None)

    @abstractmethod
    @try_catch
    async def _create_pool(self, config: DatabaseConfig, connection_acqusition_timeout: float) -> ConnectionPool:
        """
        Creates a new connection pool.
        
        This abstract method must be implemented by subclasses to create a
        ConnectionPool implementation specific to the database backend being used.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            ConnectionPool: A connection pool that implements the ConnectionPool interface.
        """
        raise NotImplementedError()

# endregion      ############# POOLS #########################


# region    ################# DATABSE ######################

class DatabaseConfig:
    """
    Holds database connection configuration parameters.
    
    This class encapsulates all settings required to establish a database connection,
    including connection parameters, environment information, and connection identification.
    It provides methods to access these settings and generate a unique hash-based 
    identifier for the connection.
    
    Args:
        database (str): Database name.
        host (str, optional): Server hostname. Defaults to "localhost".
        port (int, optional): Server port. Defaults to 5432.
        user (str, optional): Username for authentication. Defaults to None.
        password (str, optional): Password for authentication. Defaults to None.
        alias (str, optional): Friendly name for the connection. Defaults to database name.
        env (str, optional): Environment label (e.g. prod, dev, test). Defaults to "prod".
    """
    def __init__(self, database: str, host: str="localhost", port: int=5432, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod',  *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Validate inputs
        if not database:
            raise ValueError("Database name or connection string is required")
        
        if port is not None and not isinstance(port, int):
            raise ValueError(f"Port must be an integer, got {type(port).__name__}")
        
        if env not in ('prod', 'dev', 'test', 'staging'):
            logger.warning(f"Unrecognized environment '{env}', using anyway but this might indicate a mistake")
  
        self.__host = host
        self.__port = port
        self.__database = database
        self.__user = user
        self.__password = password
        self.__env = env
        self.__alias = alias or database or f'database'

    def config(self) -> Dict[str, Any]:
        """
        Returns the database configuration as a dictionary.
        
        This dictionary contains all the parameters needed to establish a database
        connection and can be passed directly to database drivers.
        
        Returns:
            Dict: Dictionary containing host, port, database, user, and password.
        """
        return {
            'host': self.__host,
            'port': self.__port,
            'database': self.__database,
            'user': self.__user,
            'password': self.__password
        }
    
    def database(self) -> str:
        """
        Returns the database name.
        
        Returns:
            str: The configured database name.
        """
        return self.__database
    
    def alias(self) -> str:
        """
        Returns the database connection alias.
        
        The alias is a friendly name for the connection, which defaults to the
        database name if not explicitly provided.
        
        Returns:
            str: The database connection alias.
        """
        return self.__alias
    
    def user(self) -> str:
        """
        Returns the database user.
        
        Returns:
            str: The configured database user.
        """
        return self.__user
    
    def host(self) -> str:
        """
        Returns the database host.
        
        Returns:
            str: The configured database host.
        """
        return self.__host
    
    def password(self):
        return self.__password #todo  clean this unsafe thing
    
    def port(self) -> int:
        """
        Returns the database port.
        
        Returns:
            int: The configured database port.
        """
        return self.__port
    
    def env(self) -> str:
        """
        Returns the database environment.
        
        The environment is a label (e.g., 'prod', 'dev', 'test') that identifies
        the context in which the database is being used.
        
        Returns:
            str: The database environment label.
        """
        return self.__env

    def hash(self) -> str:
        """
        Returns a stable, hash-based key for the database configuration.
        
        This hash is used to uniquely identify connection pools and can be
        used as a key in dictionaries. It is based on all configuration
        parameters except the password.
        
        Returns:
            str: MD5 hash of the JSON-serialized configuration.
        """
        cfg = self.config().copy()
        cfg.pop('password', None)  # optional, if you want pools keyed w/o password
        key_json = json.dumps(cfg, sort_keys=True)
        return hashlib.md5(key_json.encode()).hexdigest()

class ConnectionManager():
    """
    Manages synchronized and asynchronous database connection lifecycles.
    
    This class provides a unified interface for obtaining both sync and async database connections, with proper resource management through context managers. It handles connection pooling for async connections and caching for sync connections.
    
    Features:
        - Synchronous connection caching with automatic cleanup
        - Asynchronous connection pooling with proper resource management
        - Context managers for safe connection usage
        - Environment detection (async vs sync)
        - Graceful connection release
    
    Thread Safety:
        - Sync connections are NOT thread-safe and should only be used from one thread
        - The cached sync connection (_sync_conn) is per-instance and not shared
        - Async connections use thread-safe connection pools (see AsyncPoolManager)
        - Each instance maintains its own sync connection state
        - DO NOT share a ConnectionManager instance across threads
    
    Concurrency:
        - Sync methods will block and should not be used from async code
        - Async methods should only be called from async context
        - Auto-detects async environment during initialization
        - Context managers ensure proper connection cleanup even with exceptions
        - Connection release is handled safely in both sync and async contexts
    
    Subclasses must implement:
        - _create_sync_connection(config): Create a backend-specific sync connection
        - _create_pool(config): Create a backend-specific async connection pool
        - _wrap_sync_connection(raw_conn): Wrap raw connection in SyncConnection interface
        - _wrap_async_connection(raw_conn): Wrap raw connection in AsyncConnection interface
    
    Args:
        config (DatabaseConfig)     
        ...
    """
    def __init__(self, config: DatabaseConfig=None, database: str=None, host: str="localhost", port: int=5432, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod', 
                 connection_acquisition_timeout: float=10.0, *args, **kwargs):
        super().__init__(*args,**kwargs)
        
        # todo: move in config
        self._connection_acquisition_timeout = connection_acquisition_timeout
        
        # todo add validation or remove named args
        if config:
            self.config = config
        else:
            self.config = DatabaseConfig(
            database=database, 
            host=host, 
            port=port, 
            user=user, 
            password=password, 
            alias=alias, 
            env=env)           
              
        # Use thread-local storage for sync connections
        self._local = threading.local()
        self._local._sync_conn = None     

        if not self.is_environment_async():
            self._local._sync_conn = self.get_sync_connection()

    @property
    def connection_acquisition_timeout(self) -> float:
        '''Returns the connection acqusition timeout defined in the ConnectionManager'''
        return self._connection_acquisition_timeout
    
    def is_environment_async(self) -> bool:
        """
        Determines if code is running in an async environment.
        
        This method checks if an event loop is running in the current thread,
        which indicates that async/await code can be used.
        
        Returns:
            bool: True if running in an async environment, False otherwise.
        """
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    # region -- SYNC METHODS ---------
    
    @try_catch
    def get_sync_connection(self) -> SyncConnection:
        """
        Returns a synchronized database connection.
        
        This method returns an existing connection if one is already cached, or creates a new one if needed. The connection is wrapped in the SyncConnection interface for standardized access.
        
        Thread Safety:
            - NOT thread-safe: the cached connection is per-instance
            - Should only be called from a single thread
            - Multiple instances should be used for multi-threaded applications
        
        Returns:
            SyncConnection: A database connection for synchronous operations.
            
        Note:
            The connection should be closed with release_sync_connection() or by using the sync_connection() context manager.
        """
        thread_id = threading.get_ident()
        logger.info(f"Thread {thread_id}: Requesting sync connection for {self.config.alias()}")
    

        if not hasattr(self._local, '_sync_conn') or self._local._sync_conn is None:
            try:
                start_time = time.time()
                raw_conn = self._create_sync_connection(self.config.config())
                logger.info(f"Thread {thread_id}: Sync connection created and cached for {self.config.alias()} in {(time.time() - start_time):.2f}s")
                self._local._sync_conn = self._wrap_sync_connection(raw_conn)
            except Exception as e:
                logger.error(f"Thread {thread_id}: Could not create a sync connection for {self.config.alias()}: {e}")                     
        else:
            logger.info(f"Thread {thread_id}: Reusing existing sync connection for {self.config.alias()}")
        
        return self._local._sync_conn     

    @try_catch
    def release_sync_connection(self) -> None:
        """
        Closes and releases the cached synchronous connection.
        
        This method should be called when the connection is no longer needed
        to properly release database resources. After calling this method,
        the next call to get_sync_connection() will create a new connection.
        """
        if hasattr(self._local, '_sync_conn') and self._local._sync_conn:
            try:
                self._local._sync_conn.close()
                logger.debug(f"{self.config.alias()} sync connection closed")
            except Exception as e:
                logger.warning(f"{self.config.alias()} failed to close sync connection: {e}")
            self._local._sync_conn = None

    @contextlib.contextmanager
    def sync_connection(self) -> Iterator[SyncConnection]:
        """
        Context manager for safe synchronous connection usage.
        
        This context manager ensures that the connection is properly released
        when the block exits, even if an exception occurs.
        
        Yields:
            SyncConnection: A database connection for synchronous operations.
            
        Example:
            with db.sync_connection() as conn:
                conn.execute("SELECT * FROM users")
        """
        conn = self.get_sync_connection()
        try:
            yield conn
        finally:
            self.release_sync_connection()

    @try_catch
    def __del__(self):
        """
        Destructor that ensures connections are released when the object is garbage collected.
        
        This is a fallback cleanup mechanism and should not be relied upon as the
        primary means of releasing connections.
        """
        try:
            if sys.is_finalizing():
                return
            self.release_sync_connection()
        except Exception:
            pass
    
    # endregion


    # region -- ASYNC METHODS ----------
   
    @async_method
    @try_catch
    async def get_async_connection(self) -> AsyncConnection:
        """
        Acquires an asynchronous connection from the pool.
        
        This method ensures the connection pool is initialized, then acquires a connection from it and wraps it in the AsyncConnection interface for standardized access.
        
        Thread Safety:
            - Safe to call from multiple coroutines in the same event loop
            - The underlying pool handles concurrent connection requests
            - Uses _initialize_pool_if_needed() which has thread safety guarantees
        
        Concurrency:
            - Uses connection pooling for efficient resource sharing
            - Will block only when the pool has reached max_size
            - Each connection is exclusive to the caller until released
        
        Returns:
            AsyncConnection: A database connection for asynchronous operations.
            
        Note:
            The connection should be released with release_async_connection() or by using the async_connection() context manager.
        """
        await self.pool_manager._initialize_pool_if_needed()
        async_conn = await self.pool_manager._get_connection_from_pool(self._wrap_async_connection)
        return async_conn

    @async_method
    @try_catch
    async def release_async_connection(self, async_conn: AsyncConnection):
        """
        Releases an asynchronous connection back to the pool.
        
        This method should be called when the connection is no longer needed
        to make it available for reuse by other operations.
        Connections are always properly tracked even if release fails, preventing connection leaks.
        
        Args:
            async_conn (AsyncConnection): The connection to release.
        """
        if not async_conn or not self.pool_manager._pool:
            return
            
        try:
            await self.pool_manager._release_connection_to_pool(async_conn)
        except Exception as e:
            logger.error(f"{self.config.alias()} failed to release async connection: {e}")
            
            # Try to close the connection directly to prevent resource leaks
            try:
                await async_conn.close()
            except Exception as close_error:
                logger.error(f"Failed to close leaked connection: {close_error}")
            
            # Try to maintain pool health by creating a replacement connection
            try:
                asyncio.create_task(self.pool_manager._initialize_pool_if_needed())
            except Exception:
                pass

    #@async_method
    @contextlib.asynccontextmanager
    async def async_connection(self) -> Iterator[AsyncConnection]:
        """
        Async context manager for safe asynchronous connection usage.
        
        This context manager ensures that the connection is properly released
        when the block exits, even if an exception occurs.
        
        Yields:
            AsyncConnection: A database connection for asynchronous operations.
            
        Example:
            async with db.async_connection() as conn:
                await conn.execute("SELECT * FROM users")
        """
        conn = await self.get_async_connection()
        try:
            yield conn
        finally:
            await self.release_async_connection(conn)
    
    # endregion

    @property
    @abstractmethod
    def pool_manager(self) -> PoolManager:
        raise Exception("Derived class must implement this")


    @abstractmethod
    def _wrap_sync_connection(self, raw_conn: Any) -> SyncConnection:
        """
        Wraps a raw database connection in the SyncConnection interface.
        
        This abstract method must be implemented by subclasses to create a
        database-specific wrapper that implements the SyncConnection interface.
        
        Args:
            raw_conn (Any): The raw database connection to wrap.
            
        Returns:
            SyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        raise Exception("Derived class must implement this")

    @abstractmethod
    def _wrap_async_connection(self, raw_conn: Any) -> AsyncConnection:
        """
        Wraps a raw database connection in the AsyncConnection interface.
        
        This abstract method must be implemented by subclasses to create a
        database-specific wrapper that implements the AsyncConnection interface.
        
        Args:
            raw_conn (Any): The raw database connection to wrap.
            
        Returns:
            AsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        raise Exception("Derived class must implement this")

    @abstractmethod
    @try_catch
    def _create_sync_connection(self, config: Dict) -> Any:
        """
        Creates a new synchronous database connection.
        
        This abstract method must be implemented by subclasses to create a
        connection specific to the database backend being used.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            Any: A new raw database connection object.
            
        Example implementation:
            return pymysql.connect(**config)
        """
        raise Exception("Derived class must implement this")  

# endregion    ################# DATABSE ###################


# region ################# ENTITY ###############################################

class SqlEntityGenerator(ABC):
    """
    Abstract base class defining the interface for database-specific SQL generation.
    
    This class defines the contract that all database-specific SQL generators must implement.
    Each database backend (PostgreSQL, SQLite, MySQL, etc.) will have its own implementation
    that handles the specific SQL dialect and features of that database.
    """
    @abstractmethod
    @try_catch
    def escape_identifier(self, identifier: str) -> str:
        """
        Escape a SQL identifier (table or column name).
        
        Args:
            identifier: The identifier to escape
            
        Returns:
            Escaped identifier according to database-specific syntax
        """
        raise NotImplementedError("Subclasses must implement escape_identifier")
    
    @abstractmethod
    @try_catch
    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """
        Convert parameter placeholders.
        
        Args:
            sql: SQL with standard ? placeholders
            params: Parameters for the placeholders
            
        Returns:
            Tuple of (converted SQL, converted parameters)
        """
        raise NotImplementedError("Subclasses must implement _convert_parameters")
     
    @abstractmethod
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """
        Generate database-specific upsert SQL for an entity.
        
        Args:
            entity_name: Name of the entity (table)
            fields: List of field names to include in the upsert operation
            
        Returns:
            SQL string with placeholders for the upsert operation
        """
        pass
        
    @abstractmethod
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """
        Generate database-specific CREATE TABLE SQL.
        
        Args:
            entity_name: Name of the entity (table) to create
            columns: List of (column_name, column_type) tuples
            
        Returns:
            SQL string for creating the table
        """
        pass
    
    @abstractmethod
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """
        Generate database-specific SQL for creating a metadata table.
        
        Args:
            entity_name: Name of the entity whose metadata table to create
            
        Returns:
            SQL string for creating the metadata table
        """
        pass
        
    @abstractmethod
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """
        Generate database-specific history table SQL.
        
        Args:
            entity_name: Name of the entity whose history to track
            columns: List of (column_name, column_type) tuples from the main table
            
        Returns:
            SQL string for creating the history table
        """
        pass
    
    @abstractmethod
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """
        Get SQL to list all tables in the database.
        
        Returns:
            Tuple of (SQL string, parameters) for listing tables
        """
        pass
    
    @abstractmethod
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """
        Get SQL to list all columns in a table (same order as in the table)
        
        Args:
            table_name: Name of the table to list columns for
            
        Returns:
            Tuple of (SQL string, parameters) for listing columns
        """
        pass
    
    @abstractmethod
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """
        Generate database-specific upsert SQL for a metadata table.
        
        Args:
            entity_name: Name of the entity whose metadata to upsert
            
        Returns:
            SQL string with placeholders for the metadata upsert
        """
        pass
    
    @abstractmethod
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """
        Generate SQL to add a column to an existing table.
        
        Args:
            table_name: Name of the table to alter
            column_name: Name of the column to add
            
        Returns:
            SQL string for adding the column
        """
        pass
    
    @abstractmethod
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """
        Generate SQL to check if a table exists.
        
        Args:
            table_name: Name of the table to check
            
        Returns:
            Tuple of (SQL string, parameters) for checking table existence
        """
        pass
    
    @abstractmethod
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """
        Generate SQL to check if a column exists in a table.
        
        Args:
            table_name: Name of the table to check
            column_name: Name of the column to check
            
        Returns:
            Tuple of (SQL string, parameters) for checking column existence
        """
        pass
    
    @abstractmethod
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """
        Generate SQL to retrieve an entity by ID.
        
        Args:
            entity_name: Name of the entity to retrieve
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            SQL string with placeholders for the query
        """
        pass
    
    @abstractmethod
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """
        Generate SQL to retrieve the history of an entity.
        
        Args:
            entity_name: Name of the entity
            id: ID of the entity
            
        Returns:
            Tuple of (SQL string, parameters) for retrieving entity history
        """
        pass
    
    @abstractmethod
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """
        Generate SQL to retrieve a specific version of an entity.
        
        Args:
            entity_name: Name of the entity
            id: ID of the entity
            version: Version number to retrieve
            
        Returns:
            Tuple of (SQL string, parameters) for retrieving the entity version
        """
        pass
    
    @abstractmethod
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """
        Generate SQL for soft-deleting an entity.
        
        Args:
            entity_name: Name of the entity to soft-delete
            
        Returns:
            SQL string with placeholders for the soft delete
        """
        pass
    
    @abstractmethod
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """
        Generate SQL for restoring a soft-deleted entity.
        
        Args:
            entity_name: Name of the entity to restore
            
        Returns:
            SQL string with placeholders for the restore operation
        """
        pass
    
    @abstractmethod
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """
        Generate SQL for counting entities, optionally with a WHERE clause.
        
        Args:
            entity_name: Name of the entity to count
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            SQL string with placeholders for the count query
        """
        pass
    
    @abstractmethod
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """
        Generate SQL for a flexible query with various clauses.
        
        Args:
            entity_name: Name of the entity to query
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
            limit: Optional LIMIT value
            offset: Optional OFFSET value
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            SQL string with placeholders for the query
        """
        pass
    
    @abstractmethod
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """
        Generate SQL for updating specific fields of an entity.
        
        Args:
            entity_name: Name of the entity to update
            fields: List of field names to update
            
        Returns:
            SQL string with placeholders for the update
        """
        pass
    
    @abstractmethod
    def get_pragma_or_settings_sql(self) -> List[str]:
        """
        Get a list of database-specific PRAGMA or settings statements.
        
        These are typically executed when initializing a connection to
        configure optimal settings for the database.
        
        Returns:
            List of SQL statements to execute for optimal configuration
        """
        pass
    
    @abstractmethod
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """
        Generate SQL to get the next value from a sequence.
        
        Not all databases support sequences. For those that don't,
        this method should return None.
        
        Args:
            sequence_name: Name of the sequence
            
        Returns:
            SQL string for getting the next sequence value, or None
        """
        pass
    
    def get_timeout_sql(self, timeout: Optional[float]) -> Optional[str]:
        """
        Return a SQL statement to enforce query timeout (if applicable).

        Args:
            timeout (Optional[float]): Timeout in seconds.

        Returns:
            Optional[str]: SQL statement to enforce timeout, or None if not supported.
        """
        return None

class PostgresSqlGenerator(SqlGenerator, SqlEntityGenerator):
    """
    PostgreSQL-specific SQL generator implementation.
    
    This class provides SQL generation tailored to PostgreSQL's dialect and features.
    """
    def __init__(self, is_async):
        self._is_async = is_async
    
    def escape_identifier(self, identifier: str) -> str:
        """Escape a column or table name for PostgreSQL."""
        return f"\"{identifier}\""
    
    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """Convert standard ? placeholders to PostgreSQL $1, $2, etc. format"""        
            
        if self._is_async:           
            # Use regex to safely replace placeholders with indexed parameters
            placeholder_pattern = r'(?<!\?)\?(?!\?)'  # Match ? but not ?? (escaped ?)
            param_index = 0
            
            def replace_placeholder(match):
                nonlocal param_index
                param_index += 1
                return f"${param_index}"
                
            new_sql = re.sub(placeholder_pattern, replace_placeholder, sql)
            
            # Handle escaped ?? placeholders (convert back to single ?)
            new_sql = new_sql.replace('??', '?')            
        else:            
            # For sync connections, replace ? with ? but handle escaped ?? properly
            new_sql = ''
            i = 0
            while i < len(sql):
                if i+1 < len(sql) and sql[i:i+2] == '??':
                    new_sql += '?'  # Replace ?? with single ?
                    i += 2
                elif sql[i] == '?':
                    new_sql += '?'  # Replace ? with ?
                    i += 1
                else:
                    new_sql += sql[i]
                    i += 1                  
        return new_sql, params or []    
    
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate PostgreSQL-specific upsert SQL for an entity.""" 
        fields_str = ', '.join([f"[{field}]" for field in fields])
        placeholders = ', '.join(['?'] * len(fields))
        update_clause = ', '.join([f"[{field}]=EXCLUDED.[{field}]" for field in fields if field != 'id'])
        
        return f"INSERT INTO [{entity_name}] ({fields_str}) VALUES ({placeholders}) ON CONFLICT([id]) DO UPDATE SET {update_clause}"
    
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate PostgreSQL-specific CREATE TABLE SQL."""
        column_defs = []
        for name, type_name in columns:
            if name == 'id':
                column_defs.append(f"[id] TEXT PRIMARY KEY")
            else:
                column_defs.append(f"[{name}] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}] (
                {', '.join(column_defs)}
            )
        """
    
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """Generate PostgreSQL-specific SQL for creating a metadata table."""
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_meta] (
                [name] TEXT PRIMARY KEY,
                [type] TEXT
            )
        """
    
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate PostgreSQL-specific history table SQL."""
        column_defs = [f"[{name}] TEXT" for name, _ in columns]
        column_defs.append("[version] INTEGER")
        column_defs.append("[history_timestamp] TEXT")
        column_defs.append("[history_user_id] TEXT")
        column_defs.append("[history_comment] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_history] (
                {', '.join(column_defs)},
                PRIMARY KEY ([id], [version])
            )
        """
    
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """Get SQL to list all tables in PostgreSQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name LIKE ?",
            ('%_meta',)
        )
    
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a PostgreSQL table."""
        return (
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? "
            "ORDER BY ordinal_position",  # Order by the column's position
            (table_name,)
        )
    
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """Generate PostgreSQL-specific upsert SQL for a metadata table."""
        return f"INSERT INTO [{entity_name}_meta] VALUES (?, ?) ON CONFLICT([name]) DO UPDATE SET [type]=EXCLUDED.[type]"
    
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """Generate SQL to add a column to an existing PostgreSQL table."""
        return f"ALTER TABLE [{table_name}] ADD COLUMN IF NOT EXISTS [{column_name}] TEXT"
    
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a table exists in PostgreSQL."""
        return (
            "SELECT table_name FROM information_schema.tables WHERE table_name = ?",
            (table_name,)
        )
    
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a column exists in a PostgreSQL table."""
        return (
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
            (table_name, column_name)
        )
    
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """Generate SQL to retrieve an entity by ID in PostgreSQL."""
        query = f"SELECT * FROM [{entity_name}] WHERE [id] = ?"
        
        if not include_deleted:
            query += " AND [deleted_at] IS NULL"
            
        return query
    
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """Generate SQL to retrieve the history of an entity in PostgreSQL."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? ORDER BY [version] DESC",
            (id,)
        )
    
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """Generate SQL to retrieve a specific version of an entity in PostgreSQL."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? AND [version] = ?",
            (id, version)
        )
    
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """Generate SQL for soft-deleting an entity in PostgreSQL."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = ?, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """Generate SQL for restoring a soft-deleted entity in PostgreSQL."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = NULL, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """Generate SQL for counting entities in PostgreSQL."""
        query = f"SELECT COUNT(*) FROM [{entity_name}]"
        conditions = []
        
        if not include_deleted:
            conditions.append("[deleted_at] IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        return query
    
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """Generate SQL for a flexible query in PostgreSQL."""
        query = f"SELECT * FROM [{entity_name}]"
        conditions = []
        
        if not include_deleted:
            conditions.append("[deleted_at] IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        if order_by:
            query += f" ORDER BY {order_by}"
            
        if limit is not None:
            query += f" LIMIT {limit}"
            
        if offset is not None:
            query += f" OFFSET {offset}"
            
        return query
    
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQL for updating specific fields of an entity in PostgreSQL."""
        set_clause = ", ".join([f"[{field}] = ?" for field in fields])
        return f"UPDATE [{entity_name}] SET {set_clause}, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_pragma_or_settings_sql(self) -> List[str]:
        """Get optimal PostgreSQL settings."""
        return [
            "SET TIME ZONE 'UTC'",
            "SET application_name = 'EntityManager'"
        ]
    
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """Generate SQL to get the next value from a PostgreSQL sequence."""
        return f"SELECT nextval('{sequence_name}')"

class MySqlSqlGenerator(SqlGenerator, SqlEntityGenerator):
    """
    MySQL-specific SQL generator implementation.
    
    This class provides SQL generation tailored to MySQL's dialect and features.
    """
    
    def escape_identifier(self, identifier: str) -> str:
        """Escape a column or table name for MySQL."""
        return f"`{identifier}`"
    
    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """Convert standard ? placeholders to MySQL %s placeholders."""
        # For MySQL, replace ? with %s but handle escaped ?? properly
        new_sql = ''
        i = 0
        while i < len(sql):
            if i+1 < len(sql) and sql[i:i+2] == '??':
                new_sql += '?'  # Replace ?? with single ? (literal question mark, not a parameter)
                i += 2
            elif sql[i] == '?':
                new_sql += '%s'  # Replace ? with %s for MySQL parameters
                i += 1
            else:
                new_sql += sql[i]
                i += 1
        
        if not params:
            return new_sql, []
        
        return new_sql, params or []
    
    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate MySQL-specific upsert SQL for an entity."""
        fields_str = ', '.join([f"[{field}]" for field in fields])
        placeholders = ', '.join(['?'] * len(fields))
        update_clause = ', '.join([f"[{field}]=VALUES([{field}])" for field in fields if field != 'id'])
        
        return f"INSERT INTO [{entity_name}] ({fields_str}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate MySQL-specific CREATE TABLE SQL."""
        column_defs = []
        for name, type_name in columns:
            if name == 'id':
                column_defs.append(f"[id] VARCHAR(36) PRIMARY KEY")
            else:
                column_defs.append(f"[{name}] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}] (
                {', '.join(column_defs)}
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """Generate MySQL-specific SQL for creating a metadata table."""
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_meta] (
                [name] VARCHAR(255) PRIMARY KEY,
                [type] VARCHAR(50)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate MySQL-specific history table SQL."""
        column_defs = []
        for name, _ in columns:
            if name == 'id':
                column_defs.append(f"[id] VARCHAR(36)")
            else:
                column_defs.append(f"[{name}] TEXT")
                
        column_defs.append("[version] INT")
        column_defs.append("[history_timestamp] TEXT")
        column_defs.append("[history_user_id] TEXT")
        column_defs.append("[history_comment] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_history] (
                {', '.join(column_defs)},
                PRIMARY KEY ([id], [version])
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """Get SQL to list all tables in MySQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=DATABASE() AND table_name LIKE ?",
            ('%_meta',)
        )
    
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a MySQL table."""
        return (
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? AND table_schema = DATABASE() "
            "ORDER BY ordinal_position",  # Order by the column's position
            (table_name,)
        )
    
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """Generate MySQL-specific upsert SQL for a metadata table."""
        return f"INSERT INTO [{entity_name}_meta] VALUES (?, ?) AS new ON DUPLICATE KEY UPDATE [type]=new.[type]"
    
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """Generate SQL to add a column to an existing MySQL table."""
        # MySQL doesn't support IF NOT EXISTS for columns, so the caller must check first
        return f"ALTER TABLE [{table_name}] ADD COLUMN [{column_name}] TEXT"
    
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a table exists in MySQL."""
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = ?",
            (table_name,)
        )
    
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a column exists in a MySQL table."""
        return (
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ? AND table_schema = DATABASE()",
            (table_name, column_name)
        )
    
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """Generate SQL to retrieve an entity by ID in MySQL."""
        query = f"SELECT * FROM [{entity_name}] WHERE [id] = ?"
        
        if not include_deleted:
            query += " AND [deleted_at] IS NULL"
            
        return query
    
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """Generate SQL to retrieve the history of an entity in MySQL."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? ORDER BY [version] DESC",
            (id,)
        )
    
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """Generate SQL to retrieve a specific version of an entity in MySQL."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? AND [version] = ?",
            (id, version)
        )
    
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """Generate SQL for soft-deleting an entity in MySQL."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = ?, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """Generate SQL for restoring a soft-deleted entity in MySQL."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = NULL, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """Generate SQL for counting entities in MySQL."""
        query = f"SELECT COUNT(*) FROM [{entity_name}]"
        conditions = []
        
        if not include_deleted:
            conditions.append("[deleted_at] IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        return query
    
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """Generate SQL for a flexible query in MySQL."""
        query = f"SELECT * FROM [{entity_name}]"
        conditions = []
        
        if not include_deleted:
            conditions.append("[deleted_at] IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        if order_by:
            query += f" ORDER BY {order_by}"
            
        if limit is not None:
            query += f" LIMIT {limit}"
            
        if offset is not None:
            query += f" LIMIT {offset}, {limit if limit is not None else 18446744073709551615}"
            
        return query
    
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQL for updating specific fields of an entity in MySQL."""
        set_clause = ", ".join([f"[{field}] = ?" for field in fields])
        return f"UPDATE [{entity_name}] SET {set_clause}, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_pragma_or_settings_sql(self) -> List[str]:
        """Get optimal MySQL settings."""
        return [
            "SET NAMES utf8mb4",
            "SET time_zone = '+00:00'",
            "SET sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'"
        ]
    
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """
        MySQL doesn't support native sequences like PostgreSQL.
        This is typically implemented using auto-increment columns or custom tables.
        """
        # For MySQL, we return None as there's no direct sequence support
        # The application would need to use auto-increment or a custom sequence table
        return None

class SqliteSqlGenerator(SqlGenerator, SqlEntityGenerator):
    """
    SQLite-specific SQL generator implementation.
    
    This class provides SQL generation tailored to SQLite's dialect and features.
    """
    
    def escape_identifier(self, identifier: str) -> str:
        """Escape a column or table name for SQLite."""
        return f"\"{identifier}\""
    
    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """Convert placeholders - SQLite already uses ? so just handle escaped ??"""
        new_sql = ''
        i = 0
        while i < len(sql):
            if i+1 < len(sql) and sql[i:i+2] == '??':
                new_sql += '?'  # Replace ?? with single ?
                i += 2          
            else:
                new_sql += sql[i]
                i += 1

        if not params:
            return new_sql, []  
              
        return new_sql, params

    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQLite-specific upsert SQL for an entity."""
        fields_str = ', '.join([f"[{field}]" for field in fields])
        placeholders = ', '.join(['?'] * len(fields))
        
        return f"INSERT OR REPLACE INTO [{entity_name}] ({fields_str}) VALUES ({placeholders})"
    
    def get_create_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate SQLite-specific CREATE TABLE SQL."""
        column_defs = []
        for name, type_name in columns:
            if name == 'id':
                column_defs.append(f"[id] TEXT PRIMARY KEY")
            else:
                column_defs.append(f"[{name}] TEXT")
        
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}] (
                {', '.join(column_defs)}
            )
        """
    
    def get_create_meta_table_sql(self, entity_name: str) -> str:
        """Generate SQLite-specific SQL for creating a metadata table."""
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_meta] (
                [name] TEXT PRIMARY KEY,
                [type] TEXT
            )
        """
    
    def get_create_history_table_sql(self, entity_name: str, columns: List[Tuple[str, str]]) -> str:
        """Generate SQLite-specific history table SQL."""
        column_defs = [f"[{name}] TEXT" for name, _ in columns]
        column_defs.append("[version] INTEGER")
        column_defs.append("[history_timestamp] TEXT")
        column_defs.append("[history_user_id] TEXT")
        column_defs.append("[history_comment] TEXT")
        
        # SQLite's PRIMARY KEY syntax
        return f"""
            CREATE TABLE IF NOT EXISTS [{entity_name}_history] (
                {', '.join(column_defs)},
                PRIMARY KEY ([id], [version])
            )
        """
    
    def get_list_tables_sql(self) -> Tuple[str, tuple]:
        """Get SQL to list all tables in SQLite."""
        return (
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
            ('%_meta',)
        )
    
    def get_list_columns_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Get SQL to list all columns in a SQLite table."""
        # Note: SQLite's PRAGMA statements don't support escaped identifiers in the same way
        # We need to handle the escaping differently for PRAGMA statements
        return (
            f"PRAGMA table_info({table_name})",
            ()
        )
    
    def get_meta_upsert_sql(self, entity_name: str) -> str:
        """Generate SQLite-specific upsert SQL for a metadata table."""
        return f"INSERT OR REPLACE INTO [{entity_name}_meta] VALUES (?, ?)"
    
    def get_add_column_sql(self, table_name: str, column_name: str) -> str:
        """Generate SQL to add a column to an existing SQLite table."""
        # SQLite doesn't support ADD COLUMN IF NOT EXISTS, so the caller must check
        return f"ALTER TABLE [{table_name}] ADD COLUMN [{column_name}] TEXT"
    
    def get_check_table_exists_sql(self, table_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a table exists in SQLite."""
        return (
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
    
    def get_check_column_exists_sql(self, table_name: str, column_name: str) -> Tuple[str, tuple]:
        """Generate SQL to check if a column exists in a SQLite table."""
        # SQLite requires checking the table_info PRAGMA result
        return (
            f"PRAGMA table_info({table_name})",
            ()
        )
        # Note: Caller will need to check if column_name is in the results
    
    def get_entity_by_id_sql(self, entity_name: str, include_deleted: bool = False) -> str:
        """Generate SQL to retrieve an entity by ID in SQLite."""
        query = f"SELECT * FROM [{entity_name}] WHERE [id] = ?"
        
        if not include_deleted:
            query += " AND [deleted_at] IS NULL"
            
        return query
    
    def get_entity_history_sql(self, entity_name: str, id: str) -> Tuple[str, tuple]:
        """Generate SQL to retrieve the history of an entity in SQLite."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? ORDER BY [version] DESC",
            (id,)
        )
    
    def get_entity_version_sql(self, entity_name: str, id: str, version: int) -> Tuple[str, tuple]:
        """Generate SQL to retrieve a specific version of an entity in SQLite."""
        return (
            f"SELECT * FROM [{entity_name}_history] WHERE [id] = ? AND [version] = ?",
            (id, version)
        )
    
    def get_soft_delete_sql(self, entity_name: str) -> str:
        """Generate SQL for soft-deleting an entity in SQLite."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = ?, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_restore_entity_sql(self, entity_name: str) -> str:
        """Generate SQL for restoring a soft-deleted entity in SQLite."""
        return f"UPDATE [{entity_name}] SET [deleted_at] = NULL, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_count_entities_sql(self, entity_name: str, where_clause: Optional[str] = None,
                              include_deleted: bool = False) -> str:
        """Generate SQL for counting entities in SQLite."""
        query = f"SELECT COUNT(*) FROM [{entity_name}]"
        conditions = []
        
        if not include_deleted:
            conditions.append("[deleted_at] IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        return query
    
    def get_query_builder_sql(self, entity_name: str, where_clause: Optional[str] = None,
                            order_by: Optional[str] = None, limit: Optional[int] = None,
                            offset: Optional[int] = None, include_deleted: bool = False) -> str:
        """Generate SQL for a flexible query in SQLite."""
        query = f"SELECT * FROM [{entity_name}]"
        conditions = []
        
        if not include_deleted:
            conditions.append("[deleted_at] IS NULL")
            
        if where_clause:
            conditions.append(where_clause)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        if order_by:
            query += f" ORDER BY {order_by}"
            
        if limit is not None:
            query += f" LIMIT {limit}"
            
        if offset is not None:
            query += f" OFFSET {offset}"
            
        return query
    
    def get_update_fields_sql(self, entity_name: str, fields: List[str]) -> str:
        """Generate SQL for updating specific fields of an entity in SQLite."""
        set_clause = ", ".join([f"[{field}] = ?" for field in fields])
        return f"UPDATE [{entity_name}] SET {set_clause}, [updated_at] = ?, [updated_by] = ? WHERE [id] = ?"
    
    def get_pragma_or_settings_sql(self) -> List[str]:
        """Get optimal SQLite settings using PRAGMAs."""
        return [
            "PRAGMA journal_mode = WAL",
            "PRAGMA synchronous = NORMAL",
            "PRAGMA foreign_keys = ON",
            "PRAGMA cache_size = -8000"  # Negative means kibibytes
        ]
    
    def get_next_sequence_value_sql(self, sequence_name: str) -> Optional[str]:
        """
        SQLite doesn't support native sequences like PostgreSQL.
        This is typically implemented using rowid or custom tables.
        """
        # For SQLite, we return None as there's no direct sequence support
        return None

class EntityUtils:
    """
    Shared utility methods for entity operations.
    
    This mixin class provides common functionality needed by both database-level
    and connection-level entity operations, including serialization/deserialization,
    type handling, and entity preparation.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.info("++++++++++ Creating EntityUtils")
        self._init_serializers()
        self._custom_serializers = {}
        self._custom_deserializers = {}
        logger.info(f"++++++++++ EntityUtils custom_serializers: {self._custom_serializers}")
    
    def _init_serializers(self):
        """Initialize standard serializers and deserializers for different types."""
        # Type serializers (Python type -> string)
        self._serializers = {
            'dict': lambda v: json.dumps(v) if v is not None else None,
            'list': lambda v: json.dumps(v) if v is not None else None,
            'set': lambda v: json.dumps(list(v)) if v is not None else None,
            'tuple': lambda v: json.dumps(list(v)) if v is not None else None,
            'datetime': lambda v: v.isoformat() if v is not None else None,
            'date': lambda v: v.isoformat() if v is not None else None,
            'time': lambda v: v.isoformat() if v is not None else None,
            'bytes': lambda v: v.hex() if v is not None else None,
            'bool': lambda v: str(v).lower() if v is not None else None,
            'int': lambda v: str(v) if v is not None else None,
            'float': lambda v: str(v) if v is not None else None,
        }
        
        # Type deserializers (string -> Python type)
        self._deserializers = {
            'dict': lambda v: json.loads(v) if v else {},
            'list': lambda v: json.loads(v) if v else [],
            'set': lambda v: set(json.loads(v)) if v else set(),
            'tuple': lambda v: tuple(json.loads(v)) if v else (),
            'datetime': lambda v: datetime.datetime.fromisoformat(v) if v else None,
            'date': lambda v: datetime.date.fromisoformat(v) if v else None,
            'time': lambda v: datetime.time.fromisoformat(v) if v else None,
            'bytes': lambda v: bytes.fromhex(v) if v else None,
            'int': lambda v: int(v) if v and v.strip() else 0,
            'float': lambda v: float(v) if v and v.strip() else 0.0,
            'bool': lambda v: v.lower() in ('true', '1', 'yes', 'y', 't') if v else False,
        }
    
    def register_serializer(self, type_name: str, serializer_func, deserializer_func):
        """
        Register custom serialization functions for handling non-standard types.
        
        Args:
            type_name: String identifier for the type
            serializer_func: Function that converts the type to a string
            deserializer_func: Function that converts a string back to the type
        """
        self._custom_serializers[type_name] = serializer_func
        self._custom_deserializers[type_name] = deserializer_func
    
    def _infer_type(self, value: Any) -> str:
        """
        Infer the type of a value as a string.
        
        Args:
            value: Any Python value
            
        Returns:
            String identifier for the type
        """
        if value is None:
            return 'str'  # Default to string for None values
        
        python_type = type(value).__name__
        
        # Check for custom type
        for type_name, serializer in self._custom_serializers.items():
            try:
                if isinstance(value, eval(type_name)):
                    return type_name
            except (NameError, TypeError):
                # Type might not be importable here - try duck typing
                try:
                    # Try to apply serializer as a test
                    serializer(value)
                    return type_name
                except Exception:
                    pass
        
        # Map Python types to our type system
        type_map = {
            'dict': 'dict',
            'list': 'list',
            'tuple': 'tuple',
            'set': 'set',
            'int': 'int',
            'float': 'float',
            'bool': 'bool',
            'str': 'str',
            'bytes': 'bytes',
            'datetime': 'datetime',
            'date': 'date',
            'time': 'time',
        }
        
        return type_map.get(python_type, 'str')
    
    def _serialize_value(self, value: Any, value_type: Optional[str] = None) -> str:
        """
        Serialize a value based on its type.
        
        Args:
            value: Value to serialize
            value_type: Optional explicit type, if None will be inferred
            
        Returns:
            String representation of the value
        """
        if value is None:
            return None
        
        # Determine type if not provided
        if value_type is None:
            value_type = self._infer_type(value)
        
        # Check for custom serializer first
        if value_type in self._custom_serializers:
            try:
                return self._custom_serializers[value_type](value)
            except Exception as e:
                logger.warning(f"Custom serializer for {value_type} failed: {e}")
                # Fall back to string conversion
        
        # Use standard serializer if available
        serializer = self._serializers.get(value_type)
        if serializer:
            try:
                return serializer(value)
            except Exception as e:
                logger.warning(f"Standard serializer for {value_type} failed: {e}")
                # Fall back to string conversion
        
        # Default fallback
        return str(value)
    
    def _deserialize_value(self, value: Optional[str], value_type: str) -> Any:
        """
        Deserialize a value based on its type.
        
        Args:
            value: String representation of a value
            value_type: Type of the value
            
        Returns:
            Python object of the appropriate type
        """
        if value is None:
            return None
        
        # Check for custom deserializer first
        if value_type in self._custom_deserializers:
            try:
                return self._custom_deserializers[value_type](value)
            except Exception as e:
                logger.warning(f"Custom deserializer for {value_type} failed: {e}")
                # Fall back to returning the raw value
        
        # Use standard deserializer if available
        deserializer = self._deserializers.get(value_type)
        if deserializer:
            try:
                return deserializer(value)
            except Exception as e:
                logger.warning(f"Standard deserializer for {value_type} failed: {e}")
                # Fall back to returning the raw value
        
        # Default fallback
        return value
    
    def _serialize_entity(self, entity: Dict[str, Any], meta: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
        """
        Serialize all values in an entity to strings.
        
        Args:
            entity: Dictionary with entity data
            meta: Optional metadata with field types
            
        Returns:
            Dictionary with all values serialized to strings
        """
        result = {}
        
        for key, value in entity.items():
            value_type = meta.get(key, None) if meta else None
            
            try:
                result[key] = self._serialize_value(value, value_type)
            except Exception as e:
                logger.error(f"Error serializing field '{key}': {e}")
                # Use string representation as fallback
                result[key] = str(value) if value is not None else None
        
        return result
    
    def _deserialize_entity(self, entity_name: str, entity: Dict[str, Optional[str]], meta: Dict[str, str]) -> Dict[str, Any]:
        """
        Deserialize entity values based on metadata.
        
        Args:
            entity_name: Name of the entity for metadata lookup
            entity: Dictionary with string values
            meta: Dictionary of field name/field type(as string)
            
        Returns:
            Dictionary with values converted to appropriate Python types
        """
        result = {}   
        
        for key, value in entity.items():
            value_type = meta.get(key, 'str')
            
            try:
                result[key] = self._deserialize_value(value, value_type)
            except Exception as e:
                logger.error(f"Error deserializing field '{key}' as {value_type}: {e}")
                # Use the raw value as a fallback
                result[key] = value
        
        return result
    
    def _prepare_entity(self, entity_name: str, entity: Dict[str, Any], 
                       user_id: Optional[str] = None, comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Prepare an entity for storage by adding required fields.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity data
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            Entity with added/updated system fields
        """
        now = datetime.datetime.utcnow().isoformat()
        result = entity.copy()
        
        # Add ID if missing
        if 'id' not in result or not result['id']:
            result['id'] = str(uuid.uuid4())
        
        # Add timestamps
        if 'created_at' not in result:
            result['created_at'] = now
        
        result['updated_at'] = now
        
        # Add user_id if provided
        if user_id is not None:
            result['updated_by'] = user_id
            
            if 'created_by' not in result:
                result['created_by'] = user_id
        
        # Add comment if provided
        if comment is not None:
            result['update_comment'] = comment
        
        return result
    
    def _to_json(self, entity: Dict[str, Any]) -> str:
        """
        Convert an entity to a JSON string.
        
        Args:
            entity: Entity dictionary
            
        Returns:
            JSON string representation
        """
        return json.dumps(entity, default=str)
    
    def _from_json(self, json_str: str) -> Dict[str, Any]:
        """
        Convert a JSON string to an entity dictionary.
        
        Args:
            json_str: JSON string
            
        Returns:
            Entity dictionary
        """
        return json.loads(json_str)
    
    async def _internal_operation(self, is_async: bool, func_sync, func_async, *args, **kwargs):
        """
        Execute an operation in either sync or async mode.
        
        This internal helper method allows implementing a function once and then
        exposing it as both sync and async methods.
        
        Args:
            is_async: Whether to execute in async mode
            func_sync: Synchronous function to call
            func_async: Asynchronous function to call
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Result of the function call
        """
        if is_async:
            return await func_async(*args, **kwargs)
        else:
            return func_sync(*args, **kwargs)
    
    def _create_sync_method(self, internal_method, *args, **kwargs):
        """
        Create a synchronous wrapper for an internal method.
        
        Args:
            internal_method: Coroutine that implements the operation
            *args, **kwargs: Default arguments to pass to the method
            
        Returns:
            Synchronous function that executes the internal method
        """
        def sync_method(*method_args, **method_kwargs):
            combined_args = args + method_args
            combined_kwargs = {**kwargs, **method_kwargs}
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop in this thread, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(
                internal_method(is_async=False, *combined_args, **combined_kwargs)
            )
        
        return sync_method
    
    def _create_async_method(self, internal_method, *args, **kwargs):
        """
        Create an asynchronous wrapper for an internal method.
        
        Args:
            internal_method: Coroutine that implements the operation
            *args, **kwargs: Default arguments to pass to the method
            
        Returns:
            Asynchronous function that executes the internal method
        """
        async def async_method(*method_args, **method_kwargs):
            combined_args = args + method_args
            combined_kwargs = {**kwargs, **method_kwargs}
            return await internal_method(is_async=True, *combined_args, **combined_kwargs)
        
        return async_method
  
class EntityAsyncMixin(EntityUtils):#, ConnectionInterface):
    """
    Mixin that adds entity operations to async connections.
    
    This mixin provides async methods for entity CRUD operations,
    leveraging the EntityUtils serialization/deserialization
    and the AsyncConnection database operations.
    """
    
    # Meta cache to optimize metadata lookups
    _meta_cache = {}
    
    @async_method
    async def _get_field_names(self, entity_name: str, is_history: bool = False) -> List[str]:
        """
        Get field names for an entity table.
        
        This method tries multiple approaches to get field names:
        1. Use metadata cache if available
        2. Query database schema as fallback
        
        Args:
            entity_name: Name of the entity type
            is_history: Whether to get field names for the history table
            
        Returns:
            List of field names
        """
        table_name = f"{entity_name}_history" if is_history else entity_name
        
        # Try to get from schema directly - more reliable way to get columns in order
        schema_sql, schema_params = self.sql_generator.get_list_columns_sql(table_name)
        schema_result = await self.execute(schema_sql, schema_params)
        if schema_result:
            # Check if this is SQLite's PRAGMA table_info() result
            # SQLite PRAGMA returns rows in format (cid, name, type, notnull, dflt_value, pk)
            if isinstance(schema_result[0][0], int) and len(schema_result[0]) >= 3 and isinstance(schema_result[0][1], str):
                # For SQLite, column name is at index 1
                field_names = [row[1] for row in schema_result]
            else:
                # For other databases, column name is at index 0
                field_names = [row[0] for row in schema_result]
            logger.info(f"Got field names for {table_name} from schema: {field_names}")
            return field_names
        
        # Only fall back to metadata if schema query failed
        if not is_history:
            meta = await self._get_entity_metadata(entity_name)
            if meta:
                field_names = list(meta.keys())
                logger.info(f"Got field names for {table_name} from metadata: {field_names}")
                if is_history:
                    # Add history-specific fields
                    history_fields = ["version", "history_timestamp", "history_user_id", "history_comment"]
                    for field in history_fields:
                        if field not in field_names:
                            field_names.append(field)
                return field_names
        
        # Last resort for history tables - use base entity + history fields
        if is_history:
            meta = await self._get_entity_metadata(entity_name)
            field_names = list(meta.keys())
            # Add history-specific fields
            history_fields = ["version", "history_timestamp", "history_user_id", "history_comment"]
            for field in history_fields:
                if field not in field_names:
                    field_names.append(field)
            logger.info(f"Constructed field names for history table {table_name}: {field_names}")
            return field_names
        
        # If all else fails, return an empty list
        return []

    # Core CRUD operations
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def get_entity(self, entity_name: str, entity_id: str, 
                         include_deleted: bool = False, 
                         deserialize: bool = False) -> Optional[Dict[str, Any]]:
        """
        Fetch an entity by ID.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to fetch
            include_deleted: Whether to include soft-deleted entities
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            Entity dictionary or None if not found
        """
        # Generate the SQL
        sql = self.sql_generator.get_entity_by_id_sql(entity_name, include_deleted)
        
        # Execute the query
        result = await self.execute(sql, (entity_id,))
        
        # Return None if no entity found
        if not result or len(result) == 0:
            return None
        
        # Get schema information from metadata cache or retrieve it
        field_names = await self._get_field_names(entity_name)
        
        # Convert the first row to a dictionary
        entity_dict = dict(zip(field_names[:len(result[0])], result[0]))
        
        # Deserialize if requested
        if deserialize:
            meta = await self._get_entity_metadata(entity_name)
            return self._deserialize_entity(entity_name, entity_dict, meta)
        
        return entity_dict
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def save_entity(self, entity_name: str, entity: Dict[str, Any], 
                        user_id: Optional[str] = None, 
                        comment: Optional[str] = None,
                        timeout: Optional[float] = 60) -> Dict[str, Any]:
        """
        Save an entity (create or update).
        
        Args:
            entity_name: Name of the entity type
            entity: Entity data dictionary
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            timeout: Optional timeout in seconds for the operation (defaults to 60)
            
        Returns:
            The saved entity with updated fields
        """
        async def perform_save():
            # Prepare entity with timestamps, IDs, etc.
            prepared_entity = self._prepare_entity(entity_name, entity, user_id, comment)
            
            # Ensure schema exists (will be a no-op if already exists)
            await self._ensure_entity_schema(entity_name, prepared_entity)
            
            # Update metadata based on entity fields
            await self._update_entity_metadata(entity_name, prepared_entity)
            
            # Serialize the entity to string values
            meta = await self._get_entity_metadata(entity_name)
            serialized = self._serialize_entity(prepared_entity, meta)
            
            # Always use targeted upsert with exactly the fields provided
            # (plus system fields added by _prepare_entity)
            fields = list(serialized.keys())
            sql = self.sql_generator.get_upsert_sql(entity_name, fields)
            
            # Execute the upsert
            params = tuple(serialized[field] for field in fields)
            await self.execute(sql, params)
            
            # Add to history
            await self._add_to_history(entity_name, serialized, user_id, comment)
            
            # Return the prepared entity
            return prepared_entity        

        try:
            return await asyncio.wait_for(perform_save(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"save_entity operation for {entity_name} timed out after {timeout:.1f}s")
        
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def save_entities(self, entity_name: str, entities: List[Dict[str, Any]],
                        user_id: Optional[str] = None,
                        comment: Optional[str] = None,
                        timeout: Optional[float] = 60) -> List[Dict[str, Any]]:
        """
        Save multiple entities in a single transaction with batch operations.
        
        Args:
            entity_name: Name of the entity type
            entities: List of entity data dictionaries
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            timeout: Optional timeout in seconds for the entire operation (defaults to 60)
            
        Returns:
            List of saved entities with their IDs
        """
        if not entities:
            return []
        
        async def perform_batch_save():
            # Prepare all entities and collect fields
            prepared_entities = []
            all_fields = set()
            
            for entity in entities:
                prepared = self._prepare_entity(entity_name, entity, user_id, comment)
                prepared_entities.append(prepared)
                all_fields.update(prepared.keys())
            
            # Ensure schema exists and can accommodate all fields
            await self._ensure_entity_schema(entity_name, {field: None for field in all_fields})
            
            # Update metadata for all fields at once
            meta = {}
            for entity in prepared_entities:
                for field_name, value in entity.items():
                    if field_name not in meta:
                        meta[field_name] = self._infer_type(value)
            
            # Batch update the metadata
            meta_params = [(field_name, field_type) for field_name, field_type in meta.items()]
            if meta_params:
                sql = self.sql_generator.get_meta_upsert_sql(entity_name)
                await self.executemany(sql, meta_params)
            
            # Add all entities to the database with batch upsert
            fields = list(all_fields)
            sql = self.sql_generator.get_upsert_sql(entity_name, fields)
            
            # Prepare parameters for batch upsert
            batch_params = []
            for entity in prepared_entities:
                params = tuple(entity.get(field, None) for field in fields)
                batch_params.append(params)
            
            # Execute batch upsert
            await self.executemany(sql, batch_params)
            
            # Get all entity IDs for history lookup
            entity_ids = [entity['id'] for entity in prepared_entities]
            
            # Single query to get all existing versions
            versions = {}
            if entity_ids:
                placeholders = ','.join(['?'] * len(entity_ids))
                version_sql = f"SELECT [id], MAX([version]) as max_version FROM [{entity_name}_history] WHERE [id] IN ({placeholders}) GROUP BY [id]"
                version_results = await self.execute(version_sql, tuple(entity_ids))
                
                # Create a dictionary of id -> current max version
                versions = {row[0]: row[1] for row in version_results if row[1] is not None}
            
            # Prepare history entries
            now = datetime.datetime.utcnow().isoformat()
            history_fields = list(all_fields) + ['version', 'history_timestamp', 'history_user_id', 'history_comment']
            history_sql = f"INSERT INTO [{entity_name}_history] ({', '.join(['['+f+']' for f in history_fields])}) VALUES ({', '.join(['?'] * len(history_fields))})"
            
            history_params = []
            for entity in prepared_entities:
                history_entry = entity.copy()
                entity_id = entity['id']
                
                # Get next version (default to 1 if no previous versions exist)
                next_version = (versions.get(entity_id, 0) or 0) + 1
                
                history_entry['version'] = next_version
                history_entry['history_timestamp'] = now
                history_entry['history_user_id'] = user_id
                history_entry['history_comment'] = comment
                
                # Create params tuple with all fields in the correct order
                params = tuple(history_entry.get(field, None) for field in history_fields)
                history_params.append(params)
            
            # Execute batch history insert
            await self.executemany(history_sql, history_params)
            
            return prepared_entities
        
        try:
            return await asyncio.wait_for(perform_batch_save(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"save_entities operation timed out after {timeout:.1f}s")

    
    @async_method
    @with_timeout()
    @auto_transaction
    async def delete_entity(self, entity_name: str, entity_id: str, 
                           user_id: Optional[str] = None, 
                           permanent: bool = False) -> bool:
        """
        Delete an entity by ID.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to delete
            user_id: Optional ID of the user making the change
            permanent: Whether to permanently delete (true) or soft delete (false)
            
        Returns:
            True if deletion was successful
        """
        # Get current entity state for history
        current_entity = None
        if not permanent:
            current_entity = await self.get_entity(entity_name, entity_id, include_deleted=True)
            if not current_entity:
                return False
        
        # For permanent deletion, use a direct DELETE
        if permanent:
            sql = f"DELETE FROM [{entity_name}] WHERE [id] = ?"
            result = await self.execute(sql, (entity_id,))
            # For DELETE we expect an empty result if successful, but some drivers might
            # return a tuple with count
            if result and len(result) > 0 and isinstance(result[0], tuple) and len(result[0]) > 0:
                return result[0][0] > 0
            # Otherwise consider it successful if the query didn't raise an exception
            return True

        # For soft deletion, use an UPDATE
        now = datetime.datetime.utcnow().isoformat()
        sql = self.sql_generator.get_soft_delete_sql(entity_name)
        result = await self.execute(sql, (now, now, user_id, entity_id))
        
        # Add to history if soft-deleted
        if current_entity:
            # Update the entity with deletion info
            current_entity['deleted_at'] = now
            current_entity['updated_at'] = now
            if user_id:
                current_entity['updated_by'] = user_id
                
            # Serialize and add to history
            meta = await self._get_entity_metadata(entity_name)
            serialized = self._serialize_entity(current_entity, meta)
            await self._add_to_history(entity_name, serialized, user_id, "Soft deleted")
                
        return True
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def restore_entity(self, entity_name: str, entity_id: str, 
                            user_id: Optional[str] = None) -> bool:
        """
        Restore a soft-deleted entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to restore
            user_id: Optional ID of the user making the change
            
        Returns:
            True if restoration was successful
        """
        # Check if entity exists and is deleted
        current_entity = await self.get_entity(entity_name, entity_id, include_deleted=True)
        if not current_entity or current_entity.get('deleted_at') is None:
            return False
            
        # Update timestamps
        now = datetime.datetime.utcnow().isoformat()
        
        # Generate restore SQL
        sql = self.sql_generator.get_restore_entity_sql(entity_name)
        result = await self.execute(sql, (now, user_id, entity_id))
        
        # Add to history if restored

        # Update the entity with restoration info
        current_entity['deleted_at'] = None
        current_entity['updated_at'] = now
        if user_id:
            current_entity['updated_by'] = user_id
            
        # Serialize and add to history
        meta = await self._get_entity_metadata(entity_name)
        serialized = self._serialize_entity(current_entity, meta)
        await self._add_to_history(entity_name, serialized, user_id, "Restored")
                
        return True
    
    # Query operations
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def find_entities(self, entity_name: str, where_clause: Optional[str] = None,
                          params: Optional[Tuple] = None, order_by: Optional[str] = None,
                          limit: Optional[int] = None, offset: Optional[int] = None,
                          include_deleted: bool = False, deserialize: bool = False) -> List[Dict[str, Any]]:
        """
        Query entities with flexible filtering.
        
        Args:
            entity_name: Name of the entity type
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            params: Parameters for the WHERE clause
            order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
            limit: Optional LIMIT value
            offset: Optional OFFSET value
            include_deleted: Whether to include soft-deleted entities
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            List of entity dictionaries
        """
        # Generate query SQL
        sql = self.sql_generator.get_query_builder_sql(
            entity_name, where_clause, order_by, limit, offset, include_deleted
        )
        
        # Execute the query
        result = await self.execute(sql, params or ())
        
        # If no results, return empty list
        if not result:
            return []
            
        # Get field names from result description
        field_names = await self._get_field_names(entity_name)
        
        if deserialize:
            meta = await self._get_entity_metadata(entity_name)

        # Convert rows to dictionaries
        entities = []
        for row in result:
            entity_dict = dict(zip(field_names, row))
            
            # Deserialize if requested
            if deserialize:
                entity_dict = self._deserialize_entity(entity_name, entity_dict, meta)
                
            entities.append(entity_dict)
            
        return entities
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def count_entities(self, entity_name: str, where_clause: Optional[str] = None,
                           params: Optional[Tuple] = None, 
                           include_deleted: bool = False) -> int:
        """
        Count entities matching criteria.
        
        Args:
            entity_name: Name of the entity type
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            params: Parameters for the WHERE clause
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Count of matching entities
        """
        # Generate count SQL
        sql = self.sql_generator.get_count_entities_sql(
            entity_name, where_clause, include_deleted
        )
        
        # Execute the query
        result = await self.execute(sql, params or ())
        
        # Return the count
        if result and len(result) > 0:
            return result[0][0]
        return 0
    
    # History operations
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def get_entity_history(self, entity_name: str, entity_id: str, 
                                deserialize: bool = False) -> List[Dict[str, Any]]:
        """
        Get the history of an entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            List of historical versions
        """
        # Generate SQL
        sql, params = self.sql_generator.get_entity_history_sql(entity_name, entity_id)
        
        # Execute the query
        result = await self.execute(sql, params)
        
        # If no results, return empty list
        if not result:
            return []
            
        # Get field names from result description
        field_names = await self._get_field_names(entity_name)
        
        if deserialize:
            meta = await self._get_entity_metadata(entity_name)

        # Convert rows to dictionaries
        history_entries = []
        for row in result:
            entity_dict = dict(zip(field_names, row))
            
            # Deserialize if requested
            if deserialize:
                entity_dict = self._deserialize_entity(entity_name, entity_dict, meta)
                
            history_entries.append(entity_dict)
            
        return history_entries

    @async_method
    @with_timeout()
    @auto_transaction
    async def get_entity_by_version(self, entity_name: str, entity_id: str, 
                            version: int, deserialize: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get a specific version of an entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity
            version: Version number to retrieve
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            Entity version or None if not found
        """
        # Get all field names for complete entity comparison
        all_fields = set(await self._get_field_names(entity_name))
        all_history_fields = set(await self._get_field_names(entity_name, is_history=True))
        
        # Generate SQL
        sql, params = self.sql_generator.get_entity_version_sql(entity_name, entity_id, version)
        
        # Execute the query
        result = await self.execute(sql, params)
        
        # Return None if no entity found
        if not result or len(result) == 0:
            return None
            
        # Convert the first row to a dictionary using history field names
        field_names = await self._get_field_names(entity_name, is_history=True)
        history_entity = {}
        
        # Map values by name and handle column length discrepancies
        for i, column_name in enumerate(field_names):
            if i < len(result[0]):
                history_entity[column_name] = result[0][i]
        
        # Find fields that exist in current entity but not in this version
        missing_fields = all_fields - set(history_entity.keys())
        
        # If this version doesn't have certain fields that exist in the current version,
        # they should be explicitly set to None
        for field in missing_fields:
            history_entity[field] = None
        
        # Remove history-specific fields
        for field in list(history_entity.keys()):
            if field in ['version', 'history_timestamp', 'history_user_id', 'history_comment'] and field not in all_fields:
                history_entity.pop(field)
        
        # Deserialize if requested
        if deserialize:
            meta = await self._get_entity_metadata(entity_name)
            return self._deserialize_entity(entity_name, history_entity, meta)
            
        return history_entity


    # Schema operations
    
    @async_method
    @auto_transaction
    async def _ensure_entity_schema(self, entity_name: str, sample_entity: Optional[Dict[str, Any]] = None) -> None:
        """
        Ensure entity tables and metadata exist.
        
        Args:
            entity_name: Name of the entity type
            sample_entity: Optional example entity to infer schema
        """
        # Check if the main table exists
        main_exists_sql, main_params = self.sql_generator.get_check_table_exists_sql(entity_name)
        main_result = await self.execute(main_exists_sql, main_params)
        main_exists = main_result and len(main_result) > 0
        
        # Check if the meta table exists
        meta_exists_sql, meta_params = self.sql_generator.get_check_table_exists_sql(f"{entity_name}_meta")
        meta_result = await self.execute(meta_exists_sql, meta_params)
        meta_exists = meta_result and len(meta_result) > 0
        
        # Check if the history table exists
        history_exists_sql, history_params = self.sql_generator.get_check_table_exists_sql(f"{entity_name}_history")
        history_result = await self.execute(history_exists_sql, history_params)
        history_exists = history_result and len(history_result) > 0
        
        # Get columns if the main table exists
        columns = []
        if main_exists:
            columns_sql, columns_params = self.sql_generator.get_list_columns_sql(entity_name)
            columns_result = await self.execute(columns_sql, columns_params)
            if columns_result:
                columns = [(row[0], row[1]) for row in columns_result]
        
        # Create main table if needed
        if not main_exists:
            # Default columns if no sample entity
            if not sample_entity:
                default_columns = [
                    ("id", "TEXT"),
                    ("created_at", "TEXT"),
                    ("created_by", "TEXT"),
                    ("updated_at", "TEXT"),
                    ("updated_by", "TEXT"),
                    ("deleted_at", "TEXT")
                ]
                main_sql = self.sql_generator.get_create_table_sql(entity_name, default_columns)
            else:
                # Use sample entity to determine columns
                columns = [(field, "TEXT") for field in sample_entity.keys()]
                # Ensure required columns exist
                req_columns = ["id", "created_at", "created_by", "updated_at", "updated_by", "deleted_at"]
                for col in req_columns:
                    if col not in sample_entity:
                        columns.append((col, "TEXT"))
                main_sql = self.sql_generator.get_create_table_sql(entity_name, columns)
                
            await self.execute(main_sql, ())
            
            # Update columns for history table creation
            if not columns:
                columns = [(col, "TEXT") for col in req_columns]
            
        # Create meta table if needed
        if not meta_exists:
            meta_sql = self.sql_generator.get_create_meta_table_sql(entity_name)
            await self.execute(meta_sql, ())
            
        # Create history table if needed
        if not history_exists:
            # Get current columns if table exists and columns empty
            if not columns and main_exists:
                columns_sql, columns_params = self.sql_generator.get_list_columns_sql(entity_name)
                columns_result = await self.execute(columns_sql, columns_params)
                if columns_result:
                    columns = [(row[0], row[1]) for row in columns_result]
                
            # Create history table with current columns plus history-specific ones
            history_sql = self.sql_generator.get_create_history_table_sql(entity_name, columns)
            await self.execute(history_sql, ())
            
        # Update metadata if sample entity provided
        if sample_entity:
            await self._update_entity_metadata(entity_name, sample_entity)
    
    @async_method
    @auto_transaction
    async def _update_entity_metadata(self, entity_name: str, entity: Dict[str, Any]) -> None:
        """
        Update metadata table based on entity fields and add missing columns to the table.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity dictionary with fields to register
        """
        # Ensure meta table exists
        try:
            main_exists_sql, main_params = self.sql_generator.get_check_table_exists_sql(f"{entity_name}_meta")
            meta_exists = bool(await self.execute(main_exists_sql, main_params))
            
            if not meta_exists:
                meta_sql = self.sql_generator.get_create_meta_table_sql(entity_name)
                await self.execute(meta_sql, ())
        except Exception as e:
            logger.error(f"Error checking/creating meta table for {entity_name}: {e}")
            raise
        
        # Get existing metadata
        try:
            meta = await self._get_entity_metadata(entity_name, use_cache=False)
        except Exception as e:
            logger.error(f"Error getting metadata for {entity_name}: {e}")
            meta = {}  # Use empty dict as fallback
        
        # Track new fields to add
        new_fields = []
        
        # Check each field in the entity
        for field_name, value in entity.items():
            # Skip system fields that should already exist
            if field_name in ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at']:
                continue
                
            # Check if field is in metadata
            if field_name not in meta:
                # Determine the type
                value_type = self._infer_type(value)
                logger.info(f"Found new field {field_name} in {entity_name} with type {value_type}")
                
                # Add to metadata
                meta_sql = self.sql_generator.get_meta_upsert_sql(entity_name)
                try:
                    await self.execute(meta_sql, (field_name, value_type))
                    meta[field_name] = value_type  # Update local meta dict
                    new_fields.append(field_name)  # Track for column addition
                except Exception as e:
                    logger.error(f"Error updating metadata for field {field_name}: {e}")
        
        # Now add any new columns to the tables
        for field_name in new_fields:
            # Check if column exists in table
            try:
                exists = await self._check_column_exists(entity_name, field_name)
                if not exists:
                    logger.info(f"Adding column {field_name} to table {entity_name}")
                    sql = self.sql_generator.get_add_column_sql(entity_name, field_name)
                    await self.execute(sql, ())
            except Exception as e:
                logger.error(f"Error adding column {field_name} to {entity_name}: {e}")
                raise
                
            # Add to history table as well
            try:
                history_exists = await self._check_column_exists(f"{entity_name}_history", field_name)
                if not history_exists:
                    logger.info(f"Adding column {field_name} to history table {entity_name}_history")
                    sql = self.sql_generator.get_add_column_sql(f"{entity_name}_history", field_name)
                    await self.execute(sql, ())
            except Exception as e:
                logger.warning(f"Error adding column {field_name} to history table: {e}")
                # Continue even if history update fails
        
        # Update cache
        self._meta_cache[entity_name] = meta
    
    # Utility methods
    
    @async_method
    async def _check_column_exists(self, table_name: str, column_name: str) -> bool:
        """
        Check if a column exists in a table.
        
        This method handles different database formats properly.
        
        Args:
            table_name: Name of the table to check
            column_name: Name of the column to check
            
        Returns:
            bool: True if column exists, False otherwise
        """
        try:
            # Get SQL for checking column existence
            sql, params = self.sql_generator.get_check_column_exists_sql(table_name, column_name)
            result = await self.execute(sql, params)
            
            # Handle empty result
            if not result or len(result) == 0:
                return False
                
            # Handle SQLite PRAGMA result format
            if isinstance(result[0][0], int) and len(result[0]) > 1:
                # SQLite returns rows with format (cid, name, type, notnull, dflt_value, pk)
                # Check if any row has matching column name at index 1
                return any(row[1] == column_name for row in result)
                
            # Handle PostgreSQL/MySQL format - they return the column name directly
            # or sometimes a row count
            return bool(result[0][0])
                
        except Exception as e:
            logger.warning(f"Error checking if column {column_name} exists in {table_name}: {e}")
            return False  # Assume it doesn't exist if check fails
    
    @async_method
    async def _get_entity_metadata(self, entity_name: str, use_cache: bool = True) -> Dict[str, str]:
        """
        Get metadata for an entity type.
        
        Args:
            entity_name: Name of the entity type
            use_cache: Whether to use cached metadata
            
        Returns:
            Dictionary of field names to types
        """
        # Check cache first if enabled
        if use_cache and entity_name in self._meta_cache:
            return self._meta_cache[entity_name]
            
        # Check if meta table exists
        meta_exists_sql, meta_params = self.sql_generator.get_check_table_exists_sql(f"{entity_name}_meta")
        meta_exists = bool(await self.execute(meta_exists_sql, meta_params))
        
        # Return empty dict if table doesn't exist
        if not meta_exists:
            self._meta_cache[entity_name] = {}
            return {}
            
        # Query metadata
        result = await self.execute(f"SELECT [name], [type] FROM [{entity_name}_meta]", ())
        
        # Process results
        meta = {}
        for row in result:
            meta[row[0]] = row[1]
            
        # Cache results
        self._meta_cache[entity_name] = meta
        return meta
    

    @async_method
    @auto_transaction
    async def _add_to_history(self, entity_name: str, entity: Dict[str, Any], 
                            user_id: Optional[str] = None, 
                            comment: Optional[str] = None) -> None:
        """
        Add an entry to entity history.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity dictionary to record
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
        """
        # Ensure entity has required fields
        if 'id' not in entity:
            return
            
        # Get the current highest version
        history_sql = f"SELECT MAX([version]) FROM [{entity_name}_history] WHERE [id] = ?"
        version_result = await self.execute(history_sql, (entity['id'],))
        
        # Calculate the next version number
        next_version = 1
        if version_result and version_result[0][0] is not None:
            next_version = version_result[0][0] + 1
            
        # Prepare history entry
        history_entry = entity.copy()
        now = datetime.datetime.utcnow().isoformat()
        
        # Add history-specific fields
        history_entry['version'] = next_version
        history_entry['history_timestamp'] = now
        history_entry['history_user_id'] = user_id
        history_entry['history_comment'] = comment
        
        # Get the list of columns in the history table to ensure we only use existing columns
        field_names = await self._get_field_names(entity_name, is_history=True)
        
        # Filter history_entry to only include fields that exist in the table
        filtered_entry = {k: v for k, v in history_entry.items() if k in field_names}
        
        # Generate insert SQL using only the filtered fields
        fields = list(filtered_entry.keys())
        placeholders = ', '.join(['?'] * len(fields))
        fields_str = ', '.join([f"[{field}]" for field in fields])
        history_sql = f"INSERT INTO [{entity_name}_history] ({fields_str}) VALUES ({placeholders})"
        
        # Execute insert
        params = tuple(filtered_entry[field] for field in fields)
        await self.execute(history_sql, params)


class EntitySyncMixin(EntityUtils, ConnectionInterface):    
    """
    Mixin that adds entity operations to sync connections.
    
    This mixin provides sync methods for entity operations by wrapping
    the async versions from EntityAsyncMixin using the _create_sync_method utility.
    """
    
    # Meta cache to optimize metadata lookups (shared with async mixin)
    _meta_cache = {}
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_sync_methods()
    
    def _create_sync_methods(self):
        """
        Create sync versions of all entity operations by wrapping the async methods.
        """
        # Create sync versions of all entity methods from EntityAsyncMixin
        method_names = [
            # CRUD operations
            'get_entity',
            'save_entity',
            'save_entities',
            'delete_entity',
            'restore_entity',
            
            # Query operations
            'find_entities',
            'count_entities',
            
            # History operations
            'get_entity_history',
            'get_entity_by_version',
            
            # Schema operations
            '_ensure_entity_schema',
            '_update_entity_metadata',
            
            # Utility methods
            '_get_entity_metadata',
            '_add_to_history',        
        ]
        
        # Get the async mixin methods from a temporary EntityAsyncMixin instance
        async_mixin = EntityAsyncMixin()
        
        # Create sync versions of all methods
        for method_name in method_names:
            if hasattr(async_mixin, method_name) and callable(getattr(async_mixin, method_name)):
                async_method = getattr(async_mixin, method_name)
                sync_method = self._create_sync_method(async_method)
                setattr(self, method_name, sync_method)

# endregion ################# ENTITY ############################################


# region ######### BACKENDS - POSTGRES #################

class PostgresSyncConnection(SyncConnection):
    """
    PostgreSQL implementation of the SyncConnection interface.
    
    This class wraps a raw psycopg2 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw psycopg2 connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)   
        logger.debug("postgres init")     
        self._cursor = self._conn.cursor()       
        self._prepared_counter = self.ThreadSafeCounter()
        self._sql_generator = None

    class ThreadSafeCounter:
        def __init__(self, start=0, step=1):
            self.counter = itertools.count(start, step)
            self.lock = threading.Lock()
            
        def next(self):
            with self.lock:
                return next(self.counter)
        
    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the PostgreSQL parameter converter."""
        if not  self._sql_generator:
            self._sql_generator = PostgresSqlGenerator(False)
        return  self._sql_generator
    
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """Prepare a statement using psycopg2"""
        logger.debug("postgres _prepare_statement") 
        stmt_name = f"prep_{self._prepared_counter.next()}" 
        
        # Prepare the statement
        self._cursor.execute(f"PREPARE {stmt_name} AS {native_sql}")
        return stmt_name
    
    @retry_with_backoff(
        max_retries=3, 
        exceptions=(
            psycopg2.OperationalError,
            psycopg2.InterfaceError,
            psycopg2.InternalError
        )
    )
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using psycopg2"""
        try:           
            # Handle the empty parameters case properly
            if not params or len(params) == 0:
                self._cursor.execute(f"EXECUTE {statement}")
            else:
                placeholders = ','.join(['?'] * len(params))
                self._cursor.execute(f"EXECUTE {statement} ({placeholders})", params)
                
            return self._cursor.fetchall()  # Return raw results
        except Exception as e:
            logger.error(f"Error executing statement: {e}")
            raise
  
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        Note:
            In psycopg2, transactions are started implicitly with the first query,
            so this method is a no-op for compatibility.
        """
        # psycopg2 starts transaction implicitly on execute
        pass

    def commit_transaction(self):
        """
        Commits the current transaction.
        
        This permanently applies all changes made since the transaction began.
        """
        self._conn.commit()

    def rollback_transaction(self):
        """
        Rolls back the current transaction.
        
        This discards all changes made since the transaction began.
        """
        self._conn.rollback()

    def close(self):
        """
        Closes the database connection and cursor.
        
        This releases all resources used by the connection. The connection
        should not be used after calling this method.
        """
        self._cursor.close()
        self._conn.close()
    
    def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        cursor = self._conn.cursor()
        cursor.execute("SHOW server_version;")
        server_version = cursor.fetchone()[0]

        import psycopg2
        driver_version = f"psycopg2 {psycopg2.__version__}"

        return {           
            "db_server_version": server_version,
            "db_driver": driver_version
        }

class PostgresAsyncConnection(AsyncConnection):
    """
    PostgreSQL implementation of the AsyncConnection interface.
    
    This class wraps a raw asyncpg connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw asyncpg connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)        
        self._tx = None 
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the PostgreSQL parameter converter."""
        if not  self._sql_generator:
            self._sql_generator = PostgresSqlGenerator(True)
        return  self._sql_generator

    @retry_with_backoff(
        exceptions=(
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            asyncpg.exceptions.ConnectionFailureError
        )
    )
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """Prepare a statement using asyncpg"""
        try:
            return await self._conn.prepare(native_sql)
        except Exception as e:
            logger.error(f'Error while Postgres async driver tried to prepare this: {native_sql}: {e}')
            raise

    
    @retry_with_backoff(
        exceptions=(
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            asyncpg.exceptions.TooManyConnectionsError,
            asyncpg.exceptions.ConnectionFailureError
        )
    )
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using asyncpg"""
        return await statement.fetch(*(params or []))
    
    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""       
        return self._conn.is_in_transaction()

    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        if self._tx is None:
            self._tx = self._conn.transaction()
            await self._tx.start()

    @async_method
    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.commit()
            self._tx = None

    @async_method
    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.rollback()
            self._tx = None

    @async_method
    async def close(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

    @async_method
    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        version_tuple = self._conn.get_server_version()
        server_version = ".".join(str(v) for v in version_tuple[:2])

        import asyncpg
        driver_version = f"asyncpg {asyncpg.__version__}"

        return {      
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    
class PostgresConnectionPool(ConnectionPool):
    """
    PostgreSQL implementation of ConnectionPool using asyncpg.
    
    This class wraps asyncpg's connection pool to provide a standardized interface
    and additional functionality for connection management.
    
    Attributes:
        _pool: The underlying asyncpg pool
        _timeout: Default timeout for connection acquisition
    """
    
    def __init__(self, pool, timeout: float = 10.0):
        """
        Initialize a PostgreSQL connection pool wrapper.
        
        Args:
            pool: The underlying asyncpg pool
            timeout: Default timeout for connection acquisition in seconds
        """
        self._pool = pool
        self._timeout = timeout        
       
    @async_method
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires a connection from the pool with timeout.
        
        Args:
            timeout: Maximum time to wait for connection, defaults to pool default
            
        Returns:
            The raw asyncpg connection
            
        Raises:
            TimeoutError: If connection acquisition times out
        """
        timeout = timeout if timeout is not None else self._timeout
        try:
            return await asyncio.wait_for(self._pool.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for PostgreSQL connection after {timeout}s")
    
    @async_method
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The asyncpg connection to release
        """
        await self._pool.release(connection)
    
    @async_method
    async def close(self, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:
           
            timeout: Maximum time to wait for graceful shutdown 
        """
        await self._pool.close()
    

    async def _test_connection(self, connection):
        await connection.execute("SELECT 1")

    
    @property
    def min_size(self) -> int:
        """Gets the minimum number of connections the pool maintains."""
        return self._pool._minsize
    
    @property
    def max_size(self) -> int:
        """Gets the maximum number of connections the pool can create."""
        return self._pool._maxsize
    
    @property
    def size(self) -> int:
        """Gets the current number of connections in the pool."""
        return len(self._pool._holders)
    
    @property
    def in_use(self) -> int:
        """Gets the number of connections currently in use."""
        return len([h for h in self._pool._holders if h._in_use])
    
    @property
    def idle(self) -> int:
        """Gets the number of idle connections in the pool."""
        return len([h for h in self._pool._holders if not h._in_use])

class PostgresPoolManager(PoolManager):
    async def _create_pool(self, config: DatabaseConfig, connection_acquisition_timeout: float) -> ConnectionPool:
        min_size, max_size = self._calculate_pool_size()
        raw_pool = await asyncpg.create_pool(
            min_size=min_size, 
            max_size=max_size, 
            command_timeout=connection_acquisition_timeout,  
            host=config.host(),
             port=config.port(),
              database=config.database(),
               user=config.user(),
                password=config.password()
           
        )
        return PostgresConnectionPool(
            raw_pool, 
            timeout=self.connection_acquisition_timeout
        )
    
class PostgresDatabase(ConnectionManager):
    """
    PostgreSQL implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for PostgreSQL using psycopg2 for synchronous operations
    and asyncpg for asynchronous operations.
    
    Usage:
        db = PostgresDatabase(
            database="my_database",
            host="localhost",
            user="postgres",
            password="secret"
        )
        
        # Synchronous
        with db.sync_connection() as conn:
            conn.execute("SELECT * FROM users")
            
        # Asynchronous
        async with db.async_connection() as conn:
            await conn.execute("SELECT * FROM users")
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs) 
        self._pool_manager = None
        
    # region -- Implementation of Abstract methods ---------
    @property
    def pool_manager(self):
        if not self._pool_manager:
            self._pool_manager = PostgresPoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw psycopg2 connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new psycopg2 connection.
        """
        return psycopg2.connect(**config)
          
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw asyncpg connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw asyncpg connection.
            
        Returns:
            PostgresAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return PostgresAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw psycopg2 connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw psycopg2 connection.
            
        Returns:
            PostgresSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return PostgresSyncConnection(raw_conn)
    # endregion

# endregion ######### BACKENDS - POSTGRES ##############


# region ######### BACKENDS - MYSQL #################

class MysqlSyncConnection(SyncConnection):
    """
    MySQL implementation of the SyncConnection interface.
    
    This class wraps a raw pymysql connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw pymysql connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)       
        self._cursor = self._conn.cursor()
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the MySql parameter converter."""
        if not self._sql_generator:
            self._sql_generator = MySqlSqlGenerator()
        return self._sql_generator
    
    @retry_with_backoff()
    def _prepare_statement_sync(self, converted_sql: str) -> Any:
        """
        MySQL with pymysql doesn't have true prepared statements API
        so we just return the SQL for later execution
        """
        return converted_sql  # Just return the converted SQL

    @retry_with_backoff()
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a statement using pymysql"""
        # statement is just the SQL string
        self._cursor.execute(statement, params or ())
        return self._cursor.fetchall()  # Return raw results

     
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return not self._conn.get_autocommit()

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        self._conn.begin()

    def commit_transaction(self):
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        self._conn.commit()

    def rollback_transaction(self):
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        self._conn.rollback()

    def close(self):
        """
        Closes the database connection and cursor.
        
        This releases all resources used by the connection. The connection
        should not be used after calling this method.
        """
        self._cursor.close()
        self._conn.close()

    def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        cursor = self._conn.cursor()
        cursor.execute("SELECT VERSION();")
        server_version = cursor.fetchone()[0]

        module = type(self._conn).__module__.split(".")[0]
        driver_version = f"{module} {__import__(module).__version__}"

        return {
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    
class MysqlAsyncConnection(AsyncConnection):
    """
    MySQL implementation of the AsyncConnection interface.
    
    This class wraps a raw aiomysql connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw aiomysql connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)        
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the MySql parameter converter."""
        if not self._sql_generator:
            self._sql_generator = MySqlSqlGenerator()
        return self._sql_generator

    @retry_with_backoff()
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """
        MySQL with aiomysql doesn't have true prepared statements API
        so we just return the SQL for later execution
        """
        return native_sql
    
    @retry_with_backoff()
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a statement using aiomysql"""
        # statement is just the SQL string
        async with self._conn.cursor() as cursor:
            await cursor.execute(statement, params or ())
            return await cursor.fetchall()   
 
    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return not self._conn.get_autocommit()
    
    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed,
        regardless of whether you've explicitly started a transaction.
        """
        await self._conn.begin()

    @async_method
    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        await self._conn.commit()

    @async_method
    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
    
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed, and any previous insert/update would not be rolled back.
        """
        await self._conn.rollback()

    @async_method
    async def close(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

    @async_method
    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        async with self._conn.cursor() as cursor:
            await cursor.execute("SELECT VERSION();")
            row = await cursor.fetchone()
            server_version = row[0]

        import aiomysql
        driver_version = f"aiomysql {aiomysql.__version__}"

        return {           
            "db_server_version": server_version,
            "db_driver": driver_version
        }
    
class MySqlConnectionPool(ConnectionPool):
    """
    MySQL implementation of ConnectionPool using aiomysql.
    
    This class wraps aiomysql's connection pool to provide a standardized interface
    and additional functionality for connection management.
    
    Attributes:
        _pool: The underlying aiomysql pool
        _timeout: Default timeout for connection acquisition
    """
    
    def __init__(self, pool, timeout: float = 10.0):
        """
        Initialize a MySQL connection pool wrapper.
        
        Args:
            pool: The underlying aiomysql pool
            timeout: Default timeout for connection acquisition in seconds
        """
        self._pool = pool
        self._timeout = timeout
     
    @async_method
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires a connection from the pool with timeout.
        
        Args:
            timeout: Maximum time to wait for connection, defaults to pool default
            
        Returns:
            The raw aiomysql connection
            
        Raises:
            TimeoutError: If connection acquisition times out
        """
        timeout = timeout if timeout is not None else self._timeout
        try:
            # aiomysql doesn't directly support timeout in acquire
            return await asyncio.wait_for(self._pool.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for MySQL connection after {timeout}s")
    
    @async_method
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The aiomysql connection to release
        """
        self._pool.release(connection)
    
    @async_method
    async def close(self, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args
            
            timeout: Maximum time to wait for graceful shutdown
        """        
        if self._pool:
            await self._pool.close()            
            self._pool = None
    
    async def _test_connection(self, connection):
        await connection.execute("SELECT 1")
    
    @property
    def min_size(self) -> int:
        """Gets the minimum number of connections the pool maintains."""
        return self._pool.minsize
    
    @property
    def max_size(self) -> int:
        """Gets the maximum number of connections the pool can create."""
        return self._pool.maxsize
    
    @property
    def size(self) -> int:
        """Gets the current number of connections in the pool."""
        return self._pool.size
    
    @property
    def in_use(self) -> int:
        """Gets the number of connections currently in use."""
        # aiomysql pool tracks free connections, so in-use is size - len(free)
        return self._pool.size - len(self._pool._free)
    
    @property
    def idle(self) -> int:
        """Gets the number of idle connections in the pool."""
        return len(self._pool._free)   

class MySqlPoolManager(PoolManager):
    async def _create_pool(self, config: DatabaseConfig, connection_acquisition_timeout: float) -> ConnectionPool:
        min_size, max_size = self._calculate_pool_size()
        cfg = config.config().copy()
        cfg["db"] = cfg.pop("database")  # aiomysql expects "db"
        raw_pool = await aiomysql.create_pool(
            minsize=min_size, 
            maxsize=max_size, 
            **cfg
        )
        return MySqlConnectionPool(
            raw_pool, 
            timeout=self.connection_acquisition_timeout
        )
    
class MySqlDatabase(ConnectionManager):
    """
    MySQL implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for MySQL using pymysql for synchronous operations
    and aiomysql for asynchronous operations.
    
    Usage:
        db = MySqlDatabase(
            database="my_database",
            host="localhost",
            user="root",
            password="secret"
        )
        
        # Synchronous
        with db.sync_connection() as conn:
            conn.execute("SELECT * FROM users")
            
        # Asynchronous
        async with db.async_connection() as conn:
            await conn.execute("SELECT * FROM users")
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs) 
        self._pool_manager = None
        
    # region -- Implementation of Abstract methods ---------
    @property
    def pool_manager(self):
        if not self._pool_manager:
            self._pool_manager = MySqlPoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw pymysql connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new pymysql connection.
        """        
        return pymysql.connect(**config)        
    
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw aiomysql connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw aiomysql connection.
            
        Returns:
            MysqlAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return MysqlAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw pymysql connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw pymysql connection.
            
        Returns:
            MysqlSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return MysqlSyncConnection(raw_conn)
    # endregion

# endregion ######### BACKENDS - MYSQL ##############


# region ######### BACKENDS - SQLITE #################

class SqliteSyncConnection(SyncConnection):
    """
    SQLite implementation of the SyncConnection interface.
    
    This class wraps a raw sqlite3 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw sqlite3 connection object.
    """
    def __init__(self, conn):
        super().__init__(conn)
        self._cursor = self._conn.cursor()
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the SQL parameter converter."""
        if not self._sql_generator:
            self._sql_generator = SqliteSqlGenerator()
        return self._sql_generator

    @retry_with_backoff()
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """
        SQLite with sqlite3 doesn't have a separate prepare API,
        so we just return the SQL for later execution
        """
        return native_sql  # Just return the SQL string
    
    @retry_with_backoff()
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a statement using sqlite3"""
        # statement is the SQL string
        self._cursor.execute(statement, params or ())
        return self._cursor.fetchall()  # Return raw results
        
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return self._conn.in_transaction

    def begin_transaction(self):
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        self._conn.execute("BEGIN")

    def commit_transaction(self):
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        self._conn.commit()

    def rollback_transaction(self):
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        self._conn.rollback()

    def close(self):
        """
        Closes the database connection and cursor.
        
        This releases all resources used by the connection. The connection
        should not be used after calling this method.
        """
        self._cursor.close()
        self._conn.close()

    def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        cursor = self._conn.cursor()
        cursor.execute("SELECT sqlite_version();")
        server_version = cursor.fetchone()[0]

        import sqlite3
        driver_version = f"sqlite3 {sqlite3.sqlite_version}"

        return {          
            "db_server_version": server_version,
            "db_driver": driver_version
        }
           
class SqliteAsyncConnection(AsyncConnection):
    """
    SQLite implementation of the AsyncConnection interface.
    
    This class wraps a raw aiosqlite connection to provide the standardized
    AsyncConnection interface, including transaction management.
    
    Args:
        conn: Raw aiosqlite connection object.
    """
    def __init__(self, conn):
        super().__init__(conn) 
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        """Returns the SQL parameter converter."""
        if not self._sql_generator:
            self._sql_generator = SqliteSqlGenerator()
        return self._sql_generator
  
    @retry_with_backoff()
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """
        SQLite with aiosqlite doesn't have a separate prepare API, so returning the sql        
        """       
        return native_sql
    
    @retry_with_backoff()
    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using aiosqlite"""
        async with self._conn.execute(statement, params or ()) as cursor:
            return await cursor.fetchall()

    @async_method
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        # aiosqlite allows checking transaction status via in_transaction property
        return self._conn.in_transaction

    @async_method
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        await self._conn.execute("BEGIN")

    @async_method
    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        await self._conn.commit()

    @async_method
    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        """
        await self._conn.rollback()

    @async_method
    async def close(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

    @async_method
    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        async with self._conn.execute("SELECT sqlite_version();") as cursor:
            row = await cursor.fetchone()
            server_version = row[0]

        import aiosqlite
        driver_version = f"aiosqlite {aiosqlite.__version__}"

        return {
            "db_server_version": server_version,
            "db_driver": driver_version
        }
            
class SqliteConnectionPool(ConnectionPool):
    """
    SQLite implementation of ConnectionPool.
    
    Since SQLite doesn't natively support connection pooling, this implementation
    provides a pool-like interface around a single SQLite connection that can
    only be used by one client at a time.
    
    Attributes:
        _conn: The single SQLite connection
        _in_use: Whether the connection is currently checked out
        _timeout: Default timeout for connection acquisition
        _lock: Lock to ensure thread safety
    """
    
    def __init__(self, conn, timeout: float = 10.0):
        """
        Initialize a SQLite connection pool wrapper.
        
        Args:
            conn: The single aiosqlite connection
            timeout: Default timeout for connection acquisition in seconds
        """
        self._conn = conn
        self._in_use = False
        self._timeout = timeout
        self._lock = asyncio.Lock()
    
    @async_method
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        """
        Acquires the SQLite connection if it's not in use.
        
        SQLite doesn't support concurrent access to the same connection,
        so this implementation only allows one client to use the connection
        at a time.
        
        Args:
            timeout: Maximum time to wait for the connection to be available
            
        Returns:
            The SQLite connection
            
        Raises:
            TimeoutError: If the connection is busy for too long
        """
        timeout = timeout if timeout is not None else self._timeout
        try:
            # Wait for the lock with timeout
            acquired = await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
            if not acquired:
                raise TimeoutError(f"Timed out waiting for SQLite connection after {timeout}s")
                
            self._in_use = True
            return self._conn
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for SQLite connection after {timeout}s")
    
    @async_method
    async def release(self, connection: Any) -> None:
        """
        Releases the SQLite connection back to the pool.
        
        Args:
            connection: The SQLite connection to release (must be the same one)
        """
        if connection is not self._conn:
            raise ValueError("Released connection is not the same as the managed connection")
            
        self._in_use = False
        self._lock.release()
    
    @async_method
    async def close(self, timeout: Optional[float] = None) -> None:
        """
        Closes the SQLite connection.
        
        Args:       
            timeout: Maximum time to wait for the connection to be released 
        """
        # Wait for the connection to be released first
        if self._in_use and timeout:
            try:
                # Try to acquire the lock (which means the connection is released)
                # and then release it immediately
                acquired = await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
                if acquired:
                    self._lock.release()
            except asyncio.TimeoutError:
                # Timeout waiting for release, close anyway
                pass
            # Close the connection
            await self._conn.close()
    
    async def _test_connection(self, connection):
        await connection.execute("SELECT 1")
    
    @property
    def min_size(self) -> int:
        """Always returns 1 for SQLite (single connection)."""
        return 1
    
    @property
    def max_size(self) -> int:
        """Always returns 1 for SQLite (single connection)."""
        return 1
    
    @property
    def size(self) -> int:
        """Always returns 1 for SQLite (single connection)."""
        return 1
    
    @property
    def in_use(self) -> int:
        """Returns 1 if the connection is in use, 0 otherwise."""
        return 1 if self._in_use else 0
    
    @property
    def idle(self) -> int:
        """Returns 0 if the connection is in use, 1 otherwise."""
        return 0 if self._in_use else 1

class SqlitePoolManager(PoolManager):
    async def _create_pool(self, config: DatabaseConfig, connection_acquisition_timeout: float) -> ConnectionPool:
        db_path = config.config()["database"]
        conn = await aiosqlite.connect(db_path)
        return SqliteConnectionPool(
            conn,
            timeout=self.connection_acquisition_timeout
        )
    
class SqliteDatabase(ConnectionManager):
    """
    SQLite implementation of the ConnectionManager.
    
    This class provides concrete implementations of the abstract methods
    in ConnectionManager for SQLite using sqlite3 for synchronous operations
    and aiosqlite for asynchronous operations.
    
    Usage:
        db = SqliteDatabase(
            database="path/to/my_database.db"
        )
        
        # Synchronous
        with db.sync_connection() as conn:
            conn.execute("SELECT * FROM users")
            
        # Asynchronous
        async with db.async_connection() as conn:
            await conn.execute("SELECT * FROM users")
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs) 
        self._pool_manager = None
        
    # region -- Implementation of Abstract methods ---------
    @property
    def pool_manager(self):
        if not self._pool_manager:
            self._pool_manager = SqlitePoolManager(self.config, self.connection_acquisition_timeout)
        return self._pool_manager
    
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw sqlite3 connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new sqlite3 connection.
            
        Note:
            For SQLite, only the 'database' parameter is used, which should
            be the path to the database file.
        """       
        return sqlite3.connect(config["database"])        
    
    def _wrap_async_connection(self, raw_conn):
        """
        Wraps a raw aiosqlite connection in the AsyncConnection interface.
        
        Args:
            raw_conn: Raw aiosqlite connection.
            
        Returns:
            SqliteAsyncConnection: A wrapped connection implementing the AsyncConnection interface.
        """
        return SqliteAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        """
        Wraps a raw sqlite3 connection in the SyncConnection interface.
        
        Args:
            raw_conn: Raw sqlite3 connection.
            
        Returns:
            SqliteSyncConnection: A wrapped connection implementing the SyncConnection interface.
        """
        return SqliteSyncConnection(raw_conn)
    # endregion

# endregion ######### BACKENDS - SQLITE ##############


#merge_classes(EntityAsyncMixin, AsyncConnection)
#merge_classes(EntitySyncMixin, SyncConnection)



from typing import TYPE_CHECKING

patcher.patch_class(PostgresAsyncConnection, EntityAsyncMixin)
patcher.patch_class(MysqlAsyncConnection, EntityAsyncMixin)
patcher.patch_class(SqliteAsyncConnection, EntityAsyncMixin)
if TYPE_CHECKING:
    class PostgresAsyncConnection(PostgresAsyncConnection, EntityAsyncMixin): pass
    class MySqlAsyncConnection(PostgresAsyncConnection, EntityAsyncMixin): pass
    class SqliteAsyncConnection(PostgresAsyncConnection, EntityAsyncMixin): pass
 


# region    ################# FACTORY ######################

class DatabaseFactory:
    '''Factory to create a DAL to specific backends. Currently support 'postgres', 'mysql' and 'sqlite'.'''
    @staticmethod
    def create_database(db_type: str, db_config: DatabaseConfig) -> ConnectionManager:
        """Factory method to create the appropriate database instance"""
        if db_type.lower() == 'postgres':    
            return PostgresDatabase(**db_config.config())
        elif db_type.lower() == 'mysql':
            return MySqlDatabase(**db_config.config())
        elif db_type.lower() == 'sqlite':
            return SqliteDatabase(**db_config.config())
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

# endregion    ################# FACTORY ####################

#log_method_calls(logger.debug, PoolManager)
#log_method_calls(logger.debug, ConnectionManager)
#log_method_calls(logger.debug, AsyncConnection)
#log_method_calls(logger.debug, SyncConnection)
#log_method_calls(logger.debug, PostgresSyncConnection)
