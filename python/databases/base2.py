import sys
import os
import json
import random
import time
import hashlib
import uuid
import asyncio
import contextlib
import traceback
from typing import Set, Awaitable, Callable, Optional, Tuple, List, Any, Dict, final, Union, ClassVar, Final, AsyncIterator, Iterator
import itertools
import threading
import enum
import functools
from abc import ABC, abstractmethod
from ..errors import TrackError
from .. import log as logger
from .. import utils

import sqlite3
import aiosqlite
import psycopg2
import asyncpg
import pymysql
import aiomysql


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


class CircuitOpenError(Exception):
    """Exception raised when a circuit breaker prevents an operation"""
    pass


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


class StatementCache:
    """Thread-safe cache for prepared SQL statements with dynamic sizing"""
    
    def __init__(self, initial_size=100, min_size=50, max_size=500, auto_resize=True):
        self._cache = {}
        self._max_size = initial_size
        self._min_size = min_size
        self._hard_max = max_size
        self._auto_resize = auto_resize
        self._lru = []  # Track usage for LRU eviction
        self._lock = threading.Lock()  # Add a lock for thread safety
        self._hits = 0
        self._misses = 0
        self._last_resize_check = time.time()
        self._resize_interval = 300  # Check resize every 5 minutes
  
    @staticmethod
    def hash(sql: str) -> str:
        return hashlib.md5(sql.encode('utf-8')).hexdigest()

    @property
    def hit_ratio(self) -> float:
        """Calculate the cache hit ratio"""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0
    
    def _check_resize(self):
        """Dynamically resize the cache based on hit ratio and usage"""
        if not self._auto_resize:
            return
            
        now = time.time()
        if now - self._last_resize_check < self._resize_interval:
            return
            
        self._last_resize_check = now
        total_ops = self._hits + self._misses
        
        # Only resize if we have enough operations to make a decision
        if total_ops < 1000:
            return
        
        hit_ratio = self.hit_ratio
        current_usage = len(self._cache)
        current_max = self._max_size
        
        # If hit ratio is high and we're close to capacity, increase size
        if hit_ratio > 0.8 and current_usage > 0.9 * current_max:
            new_size = min(current_max * 2, self._hard_max)
            if new_size > current_max:
                logger.info(f"Increasing statement cache size from {current_max} to {new_size} (hit ratio: {hit_ratio:.2f})")
                self._max_size = new_size
        
        # If hit ratio is low and we're using much less than capacity, decrease size
        elif hit_ratio < 0.4 and current_usage < 0.5 * current_max:
            new_size = max(int(current_max / 2), self._min_size)
            if new_size < current_max:
                logger.info(f"Decreasing statement cache size from {current_max} to {new_size} (hit ratio: {hit_ratio:.2f})")
                self._max_size = new_size
                
                # Trim the cache if needed
                excess = len(self._cache) - self._max_size
                if excess > 0:
                    for _ in range(excess):
                        if self._lru:
                            lru_hash = self._lru.pop(0)
                            self._cache.pop(lru_hash, None)
        
        # Reset stats periodically
        if total_ops > 10000:
            self._hits = int(self._hits * 0.5)
            self._misses = int(self._misses * 0.5)
    
    def get(self, sql_hash) -> Optional[Tuple[Any, str]]:
        """Get a prepared statement from the cache in a thread-safe manner"""
        with self._lock:
            if sql_hash in self._cache:
                # Update LRU tracking
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
                lru_hash = self._lru.pop(0)
                self._cache.pop(lru_hash, None)
            
            # Add to cache and update LRU
            self._cache[sql_hash] = (statement, sql)
            if sql_hash in self._lru:
                self._lru.remove(sql_hash)
            self._lru.append(sql_hash)

class SqlGenerator(ABC):
    """
    Abstract base class for SQL generation.
    
    Different databases use different parameter placeholder syntax. This class
    provides a way to convert between a standard format (? placeholders)
    and database-specific formats for positional parameters.

    It also provide database specific sql for usual operations.
    """
    
    @abstractmethod
    def convert_query_to_native(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        """
        Converts a standard SQL query with ? placeholders to a database-specific format.
        
        Args:
            sql: SQL query with ? placeholders
            params: Positional parameters for the query
            
        Returns:
            Tuple containing the converted SQL and the converted parameters
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
        
class PostgresSqlGenerator(SqlGenerator):
    def __init__(self, is_async: bool=True):
        super().__init__()
        self._is_async=is_async
        
    """Converter for PostgreSQL numeric placeholders ($1, $2, etc.) if async or positional '%s' if sync"""    
    def convert_query_to_native(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        if not params:
            return sql, []
        if self._is_async:
            new_sql = sql
            for i in range(1, len(params) + 1):
                new_sql = new_sql.replace('?', f"${i}", 1)
        else:
            new_sql = sql.replace('?', '%s')
        return new_sql, params

    def get_timeout_sql(self, timeout: Optional[float]) -> Optional[str]:
        if timeout:
            return f"SET LOCAL statement_timeout = {int(timeout * 1000)}"
        return None      


class MySqlGenerator(SqlGenerator):
    """Converter for MySQL placeholders (%s)"""    
    def convert_query_to_native(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        if not params:
            return sql, []
        new_sql = sql.replace('?', '%s')
        return new_sql, params

class SqliteSqlGenerator(SqlGenerator):
    """Converter for SQLite placeholders (?)"""    
    def convert_query_to_native(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        return sql, params

class BaseConnection:
    """
    Base class for database connections.
    """
    def __init__(self):
         self._statement_cache = StatementCache() 

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
            comment_sql = self.parameter_converter.make_comment_sql(tags)
            if comment_sql:
                combined_parts.append(comment_sql)

        if timeout:
            timeout_sql = self.parameter_converter.make_timeout_sql(timeout)
            if timeout_sql:
                combined_parts.append(timeout_sql)

        combined_parts.append(sql)

        return "\n".join(combined_parts)

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
            
        converted_sql, _ = self.parameter_converter.convert_query(final_sql)
        stmt = await self._prepare_statement_async(converted_sql)
        self._statement_cache.put(sql_hash, stmt, final_sql)
        return stmt
        
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
            
        converted_sql, _ = self.parameter_converter.convert_query(final_sql)
        stmt = self._prepare_statement_sync(converted_sql)
        self._statement_cache.put(sql_hash, stmt, sql)
        return stmt
    
    @contextlib.contextmanager
    def _auto_transaction(self):
        if self.in_transaction():
            yield
        else:
            self.begin_transaction()
            try:
                yield
                self.commit_transaction()
            except:
                self.rollback_transaction()
                raise

    @contextlib.asynccontextmanager
    async def _auto_transaction_async(self):
        if await self.in_transaction():
            yield
        else:
            await self.begin_transaction()
            try:
                yield
                await self.commit_transaction()
            except:
                await self.rollback_transaction()
                raise

    # region -- PRIVATE ABSTRACT METHODS ----------

    @abstractmethod
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """
        Prepares a statement using database-specific API
        
        Args:
            native_sql: SQL with database-specific placeholders
            
        Returns:
            A database-specific prepared statement object
        """
        pass

    @abstractmethod
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """
        Executes a prepared statement with given parameters
        
        Args:
            statement: A database-specific prepared statement
            params: Parameters to bind
            
        Returns:
            Raw execution result
        """
        pass

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

    # endregion --------------------------------



class AsyncConnection(BaseConnection, ABC):
    """
    Abstract base class defining the interface for asynchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends asynchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """ 
    def __init__(self, conn: Any):
        super().__init__(self)
        self.__conn = conn
        self._acquired_time = None
        self._acquired_stack = None
        self._last_active_time = None
        self._is_leaked = False
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
        self._is_leaked = True
    
    @property
    def _is_leaked(self):
        """Check if this connection has been marked as leaked"""
        return self._is_leaked

    @track_slow_method
    async def _execute_with_timeout(self, sql, params, stmt, timeout):           
            if timeout:
                raw_result = await asyncio.wait_for(self._execute_statement_async(stmt, params), timeout=timeout)
            else:
                raw_result = await self._execute_statement_async(stmt, params)    
            _ = sql # we need the sql as argument to log if the query is slow (@track_slow_method)    
            return raw_result
    
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
        raw_result = await self._execute_with_timeout(sql, params, stmt, timeout)
        return self._normalize_result(raw_result)

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

        async def _run_batch():
            results = []
            for params in param_list:
                raw_result = await self._execute_with_timeout(sql, params, stmt, individual_timeout)
                normalized = self._normalize_result(raw_result)
                if normalized:
                    results.extend(normalized)
            return results

        if timeout:
            async with self._auto_transaction_async():
                return await asyncio.wait_for(_run_batch(), timeout=timeout)
        else:
            async with self._auto_transaction_async():
                return await _run_batch()

    def _get_raw_connection(self) -> Any:
        """ Return the underlying database connection (as defined by the driver) """
        return self.__conn
    
    # region -- PUBLIC ABSTRACT METHODS ----------

    @property
    @abstractmethod
    def parameter_converter(self) -> SqlGenerator:
        """Returns the parameter converter for this connection."""
        pass

    @abstractmethod
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""
        pass

    @abstractmethod
    async def begin_transaction(self) -> None:
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        pass

    @abstractmethod
    async def commit_transaction(self) -> None:
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        pass

    @abstractmethod
    async def rollback_transaction(self) -> None:
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        pass

    @abstractmethod
    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        pass
 
    # endregion --------------------------------



class SyncConnection(ABC, BaseConnection):
    """
    Abstract base class defining the interface for synchronous database connections.
    
    This class provides a standardized API for interacting with various database
    backends synchronously. Concrete implementations should be provided for 
    specific database systems (PostgreSQL, MySQL, SQLite, etc.).
    
    All methods are abstract and must be implemented by derived classes.
    """
    def __init__(self):
        super().__init__()
        self.__conn = conn

    @track_slow_method
    def _execute_with_soft_timeout(self, sql, params, stmt, timeout):
        soft_timeout = (timeout - 0.5) if timeout and timeout > 1 else None
        start = time.time()
        raw_result = self._execute_statement_sync(stmt, params)
        elapsed = time.time() - start
        if soft_timeout and elapsed > soft_timeout:
            raise TimeoutError(f"Query exceeded soft timeout of {soft_timeout}s (took {elapsed:.2f}s)")
        _ = sql # need sql in the arg for logging details of slow queries
        return raw_result

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
        raw_result = self._execute_with_soft_timeout(sql, params, stmt, timeout)
        return self._normalize_result(raw_result)


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
        start_total = time.time()

        with self._auto_transaction():
            for params in param_list:
                raw_result = self._execute_with_soft_timeout(sql, params, stmt, individual_timeout)
                normalized = self._normalize_result(raw_result)
                if normalized:
                    results.extend(normalized)

                # Total soft timeout check
                if timeout:
                    elapsed_total = time.time() - start_total
                    soft_total_timeout = timeout - 0.5 if timeout > 1 else None
                    if soft_total_timeout and elapsed_total > soft_total_timeout:
                        raise TimeoutError(f"executemany exceeded total timeout of {soft_total_timeout}s (took {elapsed_total:.2f}s)")

        return results

    def _get_raw_connection(self) -> Any:
        """ Return the underlying database connection (as defined by the driver) """
        return self._conn
    
    # region -- PUBLIC ABSTRACT METHODS ----------

    @property
    @abstractmethod
    def parameter_converter(self) -> SqlGenerator:
        """Returns the parameter converter for this connection."""
        pass

    @abstractmethod
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""
        pass

    @abstractmethod
    def begin_transaction(self) -> None:
        """
        Begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction() or rollback_transaction() is called.
        """
        pass

    @abstractmethod
    def commit_transaction(self) -> None:
        """
        Commits the current transaction.
        
        This permanently applies all changes made since begin_transaction() was called.
        """
        pass

    @abstractmethod
    def rollback_transaction(self) -> None:
        """
        Rolls back the current transaction.
        
        This discards all changes made since begin_transaction() was called.
        """
        pass

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

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, List

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
    
    @abstractmethod
    async def _test_connection(self, connection: Any) -> None:
        """Run a database-specific test query on the connection"""
        pass

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
        
    @abstractmethod
    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:
            force (bool): If True, forcibly close connections, potentially 
                          interrupting operations in progress.
            timeout (Optional[float]): Maximum time in seconds to wait for graceful shutdown
                                      when force=False. If None, wait indefinitely.
                          
        Notes:
            - When force=False, wait for all connections to be released naturally
            - When force=True, terminate any executing operations (may cause data loss)
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
    
    def host(self) -> str:
        """
        Returns the database host.
        
        Returns:
            str: The configured database host.
        """
        return self.__host
    
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
                    f"(cpus={cpus}, mem={available_memory_gb:.1f}GB, env={self.env()})")
        
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
        
        # Define a timeout for connection acquisition (in seconds)
        acquisition_timeout = getattr(self, 'connection_acquisition_timeout', 10.0)
        
        try:
            start_time = time.time()
            try:
                # Acquire connection
                raw_conn = await self._pool.acquire(timeout=acquisition_timeout)
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
        self._connections.discard(async_conn)

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
                    self._pool = await self._create_pool(self)
                    logger.info(f"{self.alias()} - {self.hash()} async pool initialized in {(time.time() - start_time):.2f}s")
                except Exception as e:
                    logger.error(f"{self.alias()} - {self.hash()} async pool creation failed: {e}")
                    self._pool = None
                    raise

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
                        await pool.close(force=True)
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
    async def _create_pool(self, config: Dict) -> ConnectionPool:
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

class ConnectionManager(PoolManager, DatabaseConfig):
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
        database (str): Database name.
        host (str, optional): Server hostname. Defaults to "localhost".
        port (int, optional): Server port. Defaults to 5432.
        user (str, optional): Username for authentication. Defaults to None.
        password (str, optional): Password for authentication. Defaults to None.
        alias (str, optional): Friendly name for the connection. Defaults to database name.
        env (str, optional): Environment label (e.g. prod, dev, test). Defaults to "prod".
    """
    def __init__(self, database: str, host: str="localhost", port: int=5432, user: str=None, 
                 password: str=None, alias: str=None, env: str='prod', 
                 connection_acquisition_timeout: float=10.0, *args, **kwargs):
        # Store the timeout value
        self.connection_acquisition_timeout = connection_acquisition_timeout
        
        # Forward all named parameters
        super().__init__(
            database=database, 
            host=host, 
            port=port, 
            user=user, 
            password=password, 
            alias=alias, 
            env=env, 
            *args, 
            **kwargs
        )
        # Use thread-local storage for sync connections
        self._local = threading.local()
        self._local._sync_conn = None     

        if self.is_environment_async():
            try:
                asyncio.get_running_loop().create_task(self._initialize_pool_if_needed())
                asyncio.get_running_loop().create_task(self._leak_detection_task())
            except RuntimeError:
                self._local._sync_conn = self.get_sync_connection()
        else:
            self._local._sync_conn = self.get_sync_connection()

    async def _leak_detection_task(self):
        """Background task that periodically checks for and recovers from connection leaks"""
        IDLE_TIMEOUT = 1800  # 30 minutes idle time before considering a connection dead
        
        while True:
            try:
                # Wait to avoid excessive CPU usage
                try:
                    await asyncio.sleep(300)  # Check every 5 minutes
                except asyncio.CancelledError:
                    logger.info("Leak detection task cancelled")
                    break
                
                # Check for leaked connections
                leaked_conns = await self.check_for_leaked_connections(threshold_seconds=300)
                
                # Additionally check for idle connections
                now = time.time()
                idle_conns = []
                
                for conn in self._connections:
                    if conn._is_idle(IDLE_TIMEOUT) and not conn._is_leaked:
                        idle_conns.append(conn)
                
                # Log idle connections
                if idle_conns:
                    logger.warning(f"Found {len(idle_conns)} idle connections in {self.alias()} pool that haven't been active for 30+ minutes")
                
                # Attempt recovery for leaked connections
                for conn, duration, stack in leaked_conns:
                    try:
                        # Mark as leaked to avoid duplicate recovery attempts
                        conn._mark_leaked()
                        
                        # Try to gracefully return to the pool
                        logger.warning(f"Attempting to recover leaked connection in {self.alias()} pool (leaked for {duration:.2f}s)")
                        await self._release_connection_to_pool(conn)
                        logger.info(f"Successfully recovered leaked connection in {self.alias()} pool")
                    except Exception as e:
                        logger.error(f"Failed to recover leaked connection: {e}")
                        
                        # Try to close directly as a last resort
                        try:
                            await conn.close()
                        except Exception:
                            pass
                
                # Also recover idle connections
                for conn in idle_conns:
                    try:
                        logger.warning(f"Recovering idle connection in {self.alias()} pool")
                        await self._release_connection_to_pool(conn)
                    except Exception as e:
                        logger.error(f"Failed to recover idle connection: {e}")
            except Exception as e:
                logger.error(f"Error in connection leak detection task: {e}")

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
        if not hasattr(self._local, '_sync_conn') or self._local._sync_conn is None:
            try:
                start_time = time.time()
                raw_conn = self._create_sync_connection(self.config())
                logger.info(f"Sync connection created and cached for {self.alias()} in {(time.time() - start_time):.2f}s")
                self._local._sync_conn = self._wrap_sync_connection(raw_conn)
            except Exception as e:
                logger.error(f"Could not create a sync connection for {self.alias()}")            
        return self._local._sync_conn     

    def release_sync_connection(self) -> None:
        """
        Closes and releases the cached synchronous connection.
        
        This method should be called when the connection is no longer needed
        to properly release database resources. After calling this method,
        the next call to get_sync_connection() will create a new connection.
        """
        if hasattr(self._local, '_sync_conn') and self._local._sync_conn:
            try:
                self._local._sync_conn.close_sync()
                logger.debug(f"{self.alias()} sync connection closed")
            except Exception as e:
                logger.warning(f"{self.alias()} failed to close sync connection: {e}")
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
        await self._initialize_pool_if_needed()
        async_conn = await self._get_connection_from_pool(self._wrap_async_connection)
        return async_conn

    async def release_async_connection(self, async_conn: AsyncConnection):
        """
        Releases an asynchronous connection back to the pool.
        
        This method should be called when the connection is no longer needed
        to make it available for reuse by other operations.
        Connections are always properly tracked even if release fails, preventing connection leaks.
        
        Args:
            async_conn (AsyncConnection): The connection to release.
        """
        if not async_conn or not self._pool:
            return
            
        try:
            await self._release_connection_to_pool(async_conn)
        except Exception as e:
            logger.error(f"{self.alias()} failed to release async connection: {e}")
            # Even if release failed, remove from tracking to prevent memory leaks
            self._connections.discard(async_conn)
            
            # Try to close the connection directly to prevent resource leaks
            try:
                await async_conn.close()
            except Exception as close_error:
                logger.error(f"Failed to close leaked connection: {close_error}")
            
            # Try to maintain pool health by creating a replacement connection
            try:
                asyncio.create_task(self._initialize_pool_if_needed())
            except Exception:
                pass

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




class PostgresSyncConnection(SyncConnection):
    """
    PostgreSQL implementation of the SyncConnection interface.
    
    This class wraps a raw psycopg2 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw psycopg2 connection object.
    """
    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()
        self._param_converter = PostgresSqlGenerator(False)
        self._prepared_counter = self.ThreadSafeCounter()

    class ThreadSafeCounter:
        def __init__(self, start=0, step=1):
            self.counter = itertools.count(start, step)
            self.lock = threading.Lock()
            
        def next(self):
            with self.lock:
                return next(self.counter)
        
    @property
    def parameter_converter(self) -> SqlGenerator:
        """Returns the PostgreSQL parameter converter."""
        return self._param_converter
    
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """Prepare a statement using psycopg2"""
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
        # statement is a string name of the prepared statement
        placeholders = ','.join(['%s'] * len(params or []))
        self._cursor.execute(f"EXECUTE {statement} ({placeholders})", params or ())
        return self._cursor.fetchall()  # Return raw results
  
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
        cursor = self._connection.cursor()
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
        raw_conn: Raw asyncpg connection object.
    """
    def __init__(self, raw_conn):
        self._conn = raw_conn
        self._tx = None
        self._param_converter = PostgresSqlGenerator(True)

    @property
    def parameter_converter(self) -> SqlGenerator:
        """Returns the PostgreSQL parameter converter."""
        return self._param_converter


    @retry_with_backoff(
        exceptions=(
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            asyncpg.exceptions.ConnectionFailureError
        )
    )
    async def _prepare_statement_async(self, native_sql: str) -> Any:
        """Prepare a statement using asyncpg"""
        return await self._conn.prepare(native_sql)
    
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
    
    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction."""       
        return await self._conn.is_in_transaction()

    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        if self._tx is None:
            self._tx = self._conn.transaction()
            await self._tx.start()

    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.commit()
            self._tx = None

    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        If no transaction is active, this method does nothing.
        """
        if self._tx:
            await self._tx.rollback()
            self._tx = None

    async def close(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        version_tuple = self._connection.get_server_version()
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
        _last_health_check: Timestamp of the last health check
        _health_check_interval: Minimum time between health checks in seconds
        _healthy: Current known health state
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
        self._last_health_check = 0
        self._health_check_interval = 5.0  # Check at most every 5 seconds
        self._healthy = True
    
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
    
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The asyncpg connection to release
        """
        await self._pool.release(connection)
    
    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:
            force: If True, forcibly terminate connections
            timeout: Maximum time to wait for graceful shutdown when force=False
        """
        # asyncpg.Pool.close() has a cancel_tasks parameter that maps to our force parameter
        await self._pool.close(cancel_tasks=force)
    

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

    # region -- Implementation of Abstract methods ---------
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw psycopg2 connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new psycopg2 connection.
        """
        return psycopg2.connect(**config)
       
    async def _create_pool(self, config: Dict) -> ConnectionPool:
        """
        Creates a PostgreSQL connection pool wrapped in our interface.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            ConnectionPool: A PostgreSQL-specific pool implementation.
        """
        min_size, max_size = self._calculate_pool_size()
        raw_pool = await asyncpg.create_pool(
            min_size=min_size, 
            max_size=max_size, 
            command_timeout=60.0, 
            **config
        )
        return PostgresConnectionPool(
            raw_pool, 
            timeout=self.connection_acquisition_timeout
        )
    
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

class MysqlSyncConnection(SyncConnection):
    """
    MySQL implementation of the SyncConnection interface.
    
    This class wraps a raw pymysql connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw pymysql connection object.
    """
    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()
        self._param_converter = MySqlGenerator()

    @property
    def parameter_converter(self) -> SqlGenerator:
        """Returns the MySql parameter converter."""
        return self._param_converter
    
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
        cursor = self._connection.cursor()
        cursor.execute("SELECT VERSION();")
        server_version = cursor.fetchone()[0]

        module = type(self._connection).__module__.split(".")[0]
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
        self._conn = conn
        self._param_converter = MySqlGenerator()

    @property
    def parameter_converter(self) -> SqlGenerator:
        """Returns the SQL parameter converter."""
        return self._param_converter

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
 

    async def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return not self._conn.get_autocommit()
    
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed,
        regardless of whether you've explicitly started a transaction.
        """
        await self._conn.begin()

    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        await self._conn.commit()

    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
    
        Note: MySQL automatically commits the current transaction when 
        a DDL statement (CREATE/ALTER/DROP TABLE, etc.) is executed, and any previous insert/update would not be rolled back.
        """
        await self._conn.rollback()

    async def close(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        self._conn.close()

    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        async with self._connection.cursor() as cursor:
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
        _last_health_check: Timestamp of the last health check
        _health_check_interval: Minimum time between health checks in seconds
        _healthy: Current known health state
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
        self._last_health_check = 0
        self._health_check_interval = 5.0  # Check at most every 5 seconds
        self._healthy = True
    
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
    
    async def release(self, connection: Any) -> None:
        """
        Releases a connection back to the pool.
        
        Args:
            connection: The aiomysql connection to release
        """
        self._pool.release(connection)
    
    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
        """
        Closes the pool and all connections.
        
        Args:
            force: If True, forcibly terminate connections
            timeout: Maximum time to wait for graceful shutdown when force=False
        """
        if force:
            # aiomysql doesn't have a direct force close option
            # This is a workaround to mark the pool as closing and wake up waiters
            self._pool._closing = True
            if hasattr(self._pool, '_cond') and hasattr(self._pool._cond, 'notify_all'):
                self._pool._cond._loop.call_soon(self._pool._cond.notify_all)
        await self._pool.close()
    
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

    # region -- Implementation of Abstract methods ---------
    def _create_sync_connection(self, config: Dict):
        """
        Creates a raw pymysql connection.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            A new pymysql connection.
        """        
        return pymysql.connect(**config)        

    async def _create_pool(self, config: Dict) -> ConnectionPool:
        """
        Creates a MySQL connection pool wrapped in our interface.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            ConnectionPool: A MySQL-specific pool implementation.
        """
        min_size, max_size = self._calculate_pool_size()
        cfg = config.copy()
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

class SqliteSyncConnection(SyncConnection):
    """
    SQLite implementation of the SyncConnection interface.
    
    This class wraps a raw sqlite3 connection and cursor to provide
    the standardized SyncConnection interface.
    
    Args:
        conn: Raw sqlite3 connection object.
    """
    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()
        self._param_converter = SqliteSqlGenerator()

    @property
    def parameter_converter(self) -> SqlGenerator:
        """Returns the SQL parameter converter."""
        return self._param_converter

    @retry_with_backoff()
    def _prepare_statement_sync(self, native_sql: str) -> Any:
        """Prepare a statement using sqlite3"""
        return self._conn.prepare(native_sql)
    
    @retry_with_backoff()
    def _execute_statement_sync(self, statement: Any, params=None) -> Any:
        """Execute a prepared statement using sqlite3"""
        return statement.execute(params or ())

        
    def in_transaction(self) -> bool:
        """Return True if connection is in an active transaction.""" 
        return not self._conn.in_transaction

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
        cursor = self._connection.cursor()
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
        self._conn = conn
        self._param_converter = SqliteSqlGenerator()

    @property
    def parameter_converter(self) -> SqlGenerator:
        """Returns the SQL parameter converter."""
        return self._param_converter

  
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
    
    async def begin_transaction(self):
        """
        Asynchronously begins a database transaction.
        
        After calling this method, subsequent queries will be part of the transaction
        until either commit_transaction_async() or rollback_transaction_async() is called.
        """
        await self._conn.execute("BEGIN")

    async def commit_transaction(self):
        """
        Asynchronously commits the current transaction.
        
        This permanently applies all changes made since begin_transaction_async() was called.
        """
        await self._conn.commit()

    async def rollback_transaction(self):
        """
        Asynchronously rolls back the current transaction.
        
        This discards all changes made since begin_transaction_async() was called.
        """
        await self._conn.rollback()

    async def close(self):
        """
        Asynchronously closes the database connection.
        
        This releases any resources used by the connection. The connection
        should not be used after calling this method.
        """
        await self._conn.close()

    async def get_version_details(self) -> Dict[str, str]:
        """ Returns {'db_server_version', 'db_driver'} """
        async with self._connection.execute("SELECT sqlite_version();") as cursor:
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
        self._last_health_check = 0
        self._health_check_interval = 5.0
        self._healthy = True
    
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
    
    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
        """
        Closes the SQLite connection.
        
        Args:
            force: If True, close immediately regardless of active use
            timeout: Maximum time to wait for the connection to be released when force=False
        """
        if force:
            # Force close immediately
            await self._conn.close()
        else:
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

    # region -- Implementation of Abstract methods ---------
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

    async def _create_pool(self, config: Dict) -> ConnectionPool:
        """
        Creates a SQLite connection wrapped in our pool interface.
        
        Args:
            config (Dict): Database configuration dictionary.
            
        Returns:
            ConnectionPool: A SQLite-specific pool implementation.
        """
        db_path = config["database"]
        conn = await aiosqlite.connect(db_path)
        return SqliteConnectionPool(
            conn,
            timeout=self.connection_acquisition_timeout
        )
    
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


""" 
Example usage:
# Create a PostgreSQL database connection
db = PostgresDatabase(
    database="my_database",
    host="localhost",
    port=5432,
    user="postgres",
    password="secret",
    alias="main_db",
    env="dev"
)

# Synchronous usage
with db.sync_connection() as conn:
    result = conn.execute("SELECT * FROM users WHERE id = %s", (1,))
    # Process result...

# Asynchronous usage
async def async_example():
    async with db.async_connection() as conn:
        result = await conn.execute("SELECT * FROM users WHERE id = %s", (1,))
        # Process result...

# Cleanup at application shutdown
async def shutdown():
    await PostgresDatabase.close_pool() 
"""


class EntityRepository:
    def __init__(self, db: ConnectionManager):
        self._db = db
    
    def get_entity(self, entity_id):
        raise NotImplementedError()

class PostgresEntityRepository(EntityRepository):
    def get_entity(self, entity_id):
        with self._db.sync_connection() as conn:
            result = conn.execute("SELECT * FROM entities WHERE id = %s", (entity_id,))
            # Process result...
            return result


class MetadataCacheMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self._load_all_metadata()
        except Exception as e:
            logger.warning(f"Metadata load failed: {e}")

    def _load_all_metadata(self):
        # Assumes a working sync connection
        rows = self.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_meta'"
        )
        for (table,) in rows:
            if not table.endswith("_meta"):
                continue
            entity = table[:-5]
            meta_rows = self.execute_sql(f"SELECT name, type FROM {table}")
            meta = {name: typ for name, typ in meta_rows}
            self._meta_cache[entity] = meta
            self._keys_cache[entity] = list(meta.keys())
            self._types_cache[entity] = list(meta.values())


class DatabaseFactory:
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
