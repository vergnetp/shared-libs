import threading
import redis
from typing import Optional, Dict, Any, Callable, List

class SimpleLogger:
    @staticmethod
    def error(msg, **kwargs): print(f"ERROR: {msg}")
    @staticmethod
    def warning(msg, **kwargs): print(f"WARNING: {msg}")
    @staticmethod
    def debug(msg, **kwargs): print(f"DEBUG: {msg}")
    @staticmethod
    def info(msg, **kwargs): print(f"INFO: {msg}")
    @staticmethod
    def critical(msg, **kwargs): print(f"CRITICAL: {msg}")

class QueueConfig:
    """
    Configuration for queue operations.
    
    This class manages Redis connection configuration, queue naming schemes,
    and operation/callback registries. It provides the foundation for both
    the QueueManager and QueueWorker components.
    
    Args:
        redis_client: Optional Redis client instance to use
        redis_url: Redis URL to connect to if no client is provided
        queue_prefix: Prefix for queue keys
        backup_ttl: TTL for backups in seconds (default 7 days)
        logger: Logger instance for logging (defaults to SimpleLogger)
    """
    def __init__(self, 
                redis_client=None, 
                redis_url=None, 
                queue_prefix="queue:", 
                backup_ttl=86400*7,
                logger=None,
                connection_timeout=5.0,
                max_connection_retries=3):
        """
        Initialize the queue configuration.
        
        Args:
            redis_client: Optional Redis client instance to use
            redis_url: Redis URL to connect to if no client is provided
            queue_prefix: Prefix for queue keys
            backup_ttl: TTL for backups in seconds (default 7 days)
            logger: Logger instance for logging (defaults to SimpleLogger)
            connection_timeout: Timeout for Redis operations in seconds
            max_connection_retries: Maximum number of connection attempts
        """
        self.redis_client = redis_client
        self.redis_url = redis_url
        self.queue_prefix = queue_prefix
        self.backup_ttl = backup_ttl
        self.logger = logger or SimpleLogger()
        self.connection_timeout = connection_timeout
        self.max_connection_retries = max_connection_retries
        
        # Registries for operation functions and callbacks
        self.operations_registry = {}
        self.callbacks_registry = {}
        
        # Define registry key directly in init
        self.registry_key = f"{self.queue_prefix}registered"
        
        # Define all queue keys centrally
        self._define_queue_keys()
        
        # Lock for Redis initialization
        self._redis_lock = threading.RLock()
        
        # Metrics tracking
        self._metrics = {
            'enqueued': 0,
            'processed': 0,
            'failed': 0,
            'retried': 0,
            'timeouts': 0,
        }
        self._metrics_lock = threading.RLock()
       
    def _define_queue_keys(self):
        """Define keys for actual processing queues."""
        # Priority prefixes for operation queues
        self.queue_prefixes = {
            'high': f"{self.queue_prefix}high:",
            'normal': f"{self.queue_prefix}normal:",
            'low': f"{self.queue_prefix}low:",
        }
        
        # Failed operation queues
        self.queue_keys = {
            'system_errors': f"{self.queue_prefix}system_errors",  # Queue for ops with system-level issues
            'failures': f"{self.queue_prefix}failures",  # Queue for ops that consistently failed to execute
        }
    
    def _ensure_redis_sync(self, retry_count=None):
        """
        Ensure Redis client is initialized with retry logic.
        
        Args:
            retry_count: Number of connection attempts before failing (defaults to config value)
            
        Returns:
            Redis client instance
            
        Raises:
            ConnectionError: If Redis cannot be connected after retries
        """
        if retry_count is None:
            retry_count = self.max_connection_retries
            
        with self._redis_lock:
            if self.redis_client is None:
                last_error = None
                for attempt in range(retry_count):
                    try:
                        # Use synchronous Redis client with timeout
                        self.redis_client = redis.Redis.from_url(
                            self.redis_url, 
                            socket_timeout=self.connection_timeout
                        )
                        # Test the connection
                        self.redis_client.ping()
                        return self.redis_client
                    except (redis.RedisError, ConnectionError) as e:
                        last_error = e
                        if attempt < retry_count - 1:
                            # Exponential backoff: 0.5s, 1s, 2s, ...
                            import time
                            time.sleep(0.5 * (2 ** attempt))
                
                # If we get here, all retries failed
                error_msg = f"Could not connect to Redis after {retry_count} attempts: {last_error}"
                self.logger.error(error_msg)
                raise ConnectionError(error_msg)
            return self.redis_client
    
    def get_queue_key(self, queue_name: str, priority: str = "normal") -> str:
        """
        Get the full queue key for a specific queue and priority.
        
        Args:
            queue_name: Name of the queue/operation
            priority: Priority level ('high', 'normal', or 'low')
            
        Returns:
            Full queue key to use with Redis
            
        Raises:
            ValueError: If priority is invalid
        """
        priority_prefix = self.queue_prefixes.get(priority)
        if not priority_prefix:
            raise ValueError(f"Invalid priority: {priority}. Must be 'high', 'normal', or 'low'.")
        return f"{priority_prefix}{queue_name}"
    
    def get_registry_key(self) -> str:
        """
        Get the key for the queue registry SET.
        
        Returns:
            Redis key for the queue registry
        """
        return self.registry_key
        
    def get_callback_key(self, callback_name: str, callback_module: Optional[str] = None) -> str:
        """
        Get the registry key for a callback function.
        
        Args:
            callback_name: Name of the callback function
            callback_module: Module containing the callback
            
        Returns:
            Key for the callbacks registry
        """
        return f"{callback_module}.{callback_name}" if callback_module else callback_name
    
    def register_callback(self, callback: Callable, name: Optional[str] = None, module: Optional[str] = None):
        """
        Register a callback function for later use.
        
        Args:
            callback: The callback function to register
            name: Optional name to use (defaults to function.__name__)
            module: Optional module name (defaults to function.__module__)
        """
        callback_name = name or callback.__name__
        callback_module = module or callback.__module__
        callback_key = self.get_callback_key(callback_name, callback_module)
        
        self.callbacks_registry[callback_key] = callback
        
    def update_metric(self, metric_name: str, value: int = 1):
        """
        Update a metric counter.
        
        Args:
            metric_name: Name of the metric to update
            value: Value to add to the metric (default: 1)
        """
        with self._metrics_lock:
            if metric_name in self._metrics:
                self._metrics[metric_name] += value
    
    def get_metrics(self) -> Dict[str, int]:
        """
        Get current metrics.
        
        Returns:
            Dict of metric names and values
        """
        with self._metrics_lock:
            return self._metrics.copy()