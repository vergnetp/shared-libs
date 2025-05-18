import threading
from typing import Any, Dict, List, Optional, Union, Callable, Type
from enum import Enum
import redis

from ...errors import Error, try_catch
from ...resilience import circuit_breaker, retry_with_backoff

# Define priorities as an enum for type safety
class QueuePriority(Enum):
    """Priority levels for queue operations."""
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

class QueueRedisConfig:
    """
    Configuration for Redis connection and behavior.
    
    Manages all Redis-specific settings including connection details,
    timeouts, retries, and circuit breaker behavior.
    """
    def __init__(
        self,
        url: Optional[str] = None,
        client: Optional[Any] = None,
        connection_timeout: float = 5.0,
        circuit_breaker_threshold: int = 5,
        circuit_recovery_timeout: float = 30.0,
        key_prefix: str = "queue:"
    ):
        """
        Initialize Redis configuration.
        
        Args:
            url: Redis connection URL (e.g. "redis://localhost:6379/0")
            client: Optional existing Redis client instance to use instead of creating new one
            connection_timeout: Timeout in seconds for Redis connection (default: 5.0)           
            circuit_breaker_threshold: Number of failures before opening circuit breaker (default: 5)
            circuit_recovery_timeout: Seconds to wait before attempting recovery (default: 30.0)
            key_prefix: Prefix for all Redis keys used by the queue system (default: "queue:")
        """
        self.url = url
        self.client = client
        self.connection_timeout = connection_timeout
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_recovery_timeout = circuit_recovery_timeout
        self.key_prefix = key_prefix   
        
        # Define queue priority prefixes
        self.queue_prefixes = {
            'high': 'high:',
            'normal': 'normal:',
            'low': 'low:'
        }
        
        # Internal state
        self._client_lock = threading.RLock()
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate Redis configuration parameters."""
        errors = []
        
        if not self.url and not self.client:
            errors.append("Either url or client must be provided")
            
        if self.connection_timeout <= 0:
            errors.append(f"connection_timeout must be positive, got {self.connection_timeout}") 
            
        if errors:
            raise ValueError(f"Redis configuration validation failed: {'; '.join(errors)}")
    
    @circuit_breaker(name="redis_connection", failure_threshold=5, recovery_timeout=30.0)
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(redis.RedisError, ConnectionError))
    def get_client(self):
        """
        Get or create Redis client with retries and circuit breaker.
        
        Returns:
            Redis client instance ready for use
            
        Raises:
            redis.RedisError: If connection fails after retries
            CircuitOpenError: If circuit breaker is open due to previous failures
        """
        with self._client_lock:
            if self.client is None:
                # Use synchronous Redis client with timeout
                self.client = redis.Redis.from_url(
                    self.url, 
                    socket_timeout=self.connection_timeout
                )
            # Test the connection
            self.client.ping()
            return self.client
    
    def get_queue_key(self, name: str, priority: Union[str, QueuePriority]) -> str:
        """
        Get full Redis key for a queue with the given name and priority.
        
        Args:
            name: Base name of the queue or operation
            priority: Priority level (QueuePriority enum or string: 'high', 'normal', 'low')
            
        Returns:
            Fully qualified Redis key string
            
        Raises:
            ValueError: If priority is invalid
        """
        # Convert string priority to enum if needed
        if isinstance(priority, str):
            try:
                priority = QueuePriority(priority).value
            except ValueError:
                raise ValueError(f"Invalid priority: {priority}. Must be 'high', 'normal', or 'low'.")
        elif isinstance(priority, QueuePriority):
            priority = priority.value
        
        # Use the queue prefixes dict
        if not hasattr(self, 'queue_prefixes'):
            self.queue_prefixes = {
                'high': 'high:',
                'normal': 'normal:',
                'low': 'low:'
            }
        
        priority_prefix = self.queue_prefixes.get(priority, 'normal:')
        return f"{self.key_prefix}{priority_prefix}{name}"
    
    def get_special_queue_key(self, name: str) -> str:
        """
        Get full Redis key for a special queue like failures or errors.
        
        Args:
            name: Name of the special queue (e.g., 'failures', 'system_errors')
            
        Returns:
            Fully qualified Redis key string
        """
        return f"{self.key_prefix}{name}"
    
    def get_registry_key(self) -> str:
        """
        Get the Redis key for the queue registry.
        
        Returns:
            Redis key string for the queue registry
        """
        return f"{self.key_prefix}registered"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary with sensitive data masked.
        
        Returns:
            Dictionary representation of the configuration
        """
        return {
            "url": self._mask_connection_url(self.url) if self.url else None,
            "connection_timeout": self.connection_timeout,           
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
            "circuit_recovery_timeout": self.circuit_recovery_timeout,
            "key_prefix": self.key_prefix        
        }
    
    def _mask_connection_url(self, url: str) -> str:
        """
        Mask password in connection URL for logging safety.
        
        Args:
            url: Redis connection URL potentially containing credentials
            
        Returns:
            URL with password masked for safe logging
        """
        if not url or "://" not in url:
            return url
        
        try:
            # Basic parsing - don't use urllib to avoid dependencies
            parts = url.split("://", 1)
            protocol = parts[0]
            rest = parts[1]
            
            if "@" in rest:
                auth_host_parts = rest.split("@", 1)
                auth_part = auth_host_parts[0]
                host_part = auth_host_parts[1]
                
                if ":" in auth_part:
                    user_pass = auth_part.split(":", 1)
                    user = user_pass[0]
                    return f"{protocol}://{user}:****@{host_part}"
                else:
                    return f"{protocol}://{auth_part}@{host_part}"
            
            return url
        except Exception:
            # If parsing fails, just mask the entire URL
            return f"{protocol}://****"
