import functools
import asyncio
import time
import threading
import enum

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
    
    @classmethod
    def reset(cls, name=None):
        """
        Reset the circuit breaker state. Used primarily for testing.
        
        Args:
            name: Name of the breaker to reset. If None, resets all breakers.
        """
        with cls._lock:
            if name is None:
                cls._breakers.clear()
            elif name in cls._breakers:
                del cls._breakers[name]
    
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
        from .. import log as logger
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
        from .. import log as logger
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

        # Add information to docstring
        msg = ''
        msg += f"\n\n        Note: Protected by circuit breaker '{breaker_name}'"
        msg += f"\n        Opens after {failure_threshold} failures, recovers after {recovery_timeout}s"

        func.__doc__ = '' if not func.__doc__ else func.__doc__
        func.__doc__ += msg

        
        breaker = CircuitBreaker.get_or_create(
            breaker_name, failure_threshold, recovery_timeout, 
            half_open_max_calls, window_size
        )
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Check if circuit is open before executing the function
            with breaker._lock:
                breaker._check_state_transitions()
                if not breaker.allow_request():
                    raise CircuitOpenError(f"Circuit breaker '{breaker_name}' is OPEN - request rejected")
            
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise e
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Check if circuit is open before executing the function
            with breaker._lock:
                breaker._check_state_transitions()
                if not breaker.allow_request():
                    # Use a descriptive message and make sure to include the word "circuit" and "open"
                    raise CircuitOpenError(f"Circuit breaker '{breaker_name}' is OPEN - request rejected")
            
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise e
        
        # Choose the appropriate wrapper based on whether the function is async or not
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

