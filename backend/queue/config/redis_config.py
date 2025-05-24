import threading
from typing import Any, Dict, List, Optional, Union, Callable, Type
from enum import Enum
import redis

from ...config.base_config import BaseConfig
from ...resilience import circuit_breaker, retry_with_backoff

# Define priorities as an enum for type safety
class QueuePriority(Enum):
    """Priority levels for queue operations."""
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

class QueueRedisConfig(BaseConfig):
    """
    Configuration for Redis connection and behavior.
    
    Manages all Redis-specific settings including connection details,
    timeouts, retries, and circuit breaker behavior.
    """

    def __init__(
        self,
        url: str,
        connection_timeout: float = 5.0,
        key_prefix: str = "queue:"
    ):
        """
        Initialize Redis configuration.
        
        Args:
            url: Redis connection URL (e.g. "redis://localhost:6379/0")
            connection_timeout: Timeout in seconds for Redis connection (default: 5.0)
            key_prefix: Prefix for all Redis keys used by the queue system (default: "queue:")
        """
        self._url = url
        self._connection_timeout = connection_timeout
        self._key_prefix = key_prefix
        self._client = None
        
        # Define queue priority prefixes
        self.queue_prefixes = {
            'high': 'high:',
            'normal': 'normal:',
            'low': 'low:'
        }
        
        # Internal state
        self._client_lock = threading.RLock()
        
        super().__init__()
        self._validate_config()
    
    @property
    def url(self) -> str:
        return self._url
    
    @property
    def connection_timeout(self) -> float:
        return self._connection_timeout
    
    @property
    def key_prefix(self) -> str:
        return self._key_prefix
    
    def _validate_config(self):
        """Validate Redis configuration parameters."""
        errors = []
        
        if self._connection_timeout <= 0:
            errors.append(f"connection_timeout must be positive, got {self._connection_timeout}")
        
        if errors:
            raise ValueError(f"Redis configuration validation failed: {'; '.join(errors)}")
   
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary with sensitive data masked."""
        return {
            "url": self._mask_url(self._url) if self._url else None,
            "connection_timeout": self._connection_timeout,
            "key_prefix": self._key_prefix
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueRedisConfig':
        """Create instance from dictionary."""
        return cls(
            url=data.get('url', ''),
            connection_timeout=data.get('connection_timeout', 5.0),
            key_prefix=data.get('key_prefix', 'queue:')
        )
    
    @circuit_breaker(name="redis_connection", failure_threshold=5, recovery_timeout=30)
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(redis.RedisError, ConnectionError))
    def get_client(self):
        """Get or create Redis client with retries and circuit breaker."""
        with self._client_lock:
            if self._client is None:  # ← Fix: use private attribute
                # Use synchronous Redis client with timeout
                self._client = redis.Redis.from_url(  # ← Fix: use private attribute
                    self._url,  # ← Fix: use private attribute
                    socket_timeout=self._connection_timeout  # ← Fix: use private attribute
                )
            # Test the connection
            self._client.ping()  # ← Fix: use private attribute
            return self._client  # ← Fix: use private attribute
    
    def get_queue_key(self, name: str, priority: Union[str, QueuePriority]) -> str:
        """Get full Redis key for a queue with the given name and priority."""
        # Convert string priority to enum if needed
        if isinstance(priority, str):
            try:
                priority = QueuePriority(priority).value
            except ValueError:
                raise ValueError(f"Invalid priority: {priority}. Must be 'high', 'normal', or 'low'.")
        elif isinstance(priority, QueuePriority):
            priority = priority.value
        
        priority_prefix = self.queue_prefixes.get(priority, 'normal:')
        return f"{self._key_prefix}{priority_prefix}{name}"  # ← Fix: use private attribute
    
    def get_special_queue_key(self, name: str) -> str:
        """Get full Redis key for a special queue like failures or errors."""
        return f"{self._key_prefix}{name}"  # ← Fix: use private attribute
    
    def get_registry_key(self) -> str:
        """Get the Redis key for the queue registry."""
        return f"{self._key_prefix}registered"
     