import threading
import redis
from typing import Optional

class QueueConfig:
    """Configuration for queue operations."""
    def __init__(self, 
                redis_client=None, 
                redis_url=None, 
                queue_prefix="queue:", 
                backup_ttl=86400*7,
                logger=None):
        """
        Initialize the queue configuration.
        
        Args:
            redis_client: Optional Redis client instance to use
            redis_url: Redis URL to connect to if no client is provided
            queue_prefix: Prefix for queue keys
            backup_ttl: TTL for backups in seconds (default 7 days)
            logger: Logger instance for logging (defaults to SimpleLogger)
        """
        self.redis_client = redis_client
        self.redis_url = redis_url
        self.queue_prefix = queue_prefix
        self.backup_ttl = backup_ttl
        self.logger = logger or SimpleLogger()
        self.operations_registry = {}
        self.callbacks_registry = {}
        
        # Define registry key directly in init
        self.registry_key = f"{self.queue_prefix}registered"
        
        # Define all queue keys centrally
        self._define_queue_keys()
        
        # Lock for Redis initialization
        self._redis_lock = threading.RLock()
       
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
    
    def _ensure_redis_sync(self):
        """
        Ensure Redis client is initialized - synchronous version.
        
        Returns:
            Redis client instance
        """
        with self._redis_lock:
            if self.redis_client is None:
                # Use synchronous Redis client
                self.redis_client = redis.Redis.from_url(self.redis_url)
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
    
    def register_callback(self, callback, name: Optional[str] = None, module: Optional[str] = None):
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

class SimpleLogger:
    @staticmethod
    def error(msg): print(f"ERROR: {msg}")
    @staticmethod
    def warning(msg): print(f"WARNING: {msg}")
    @staticmethod
    def debug(msg): print(f"DEBUG: {msg}")
    @staticmethod
    def info(msg): print(f"INFO: {msg}")
    @staticmethod
    def critical(msg): print(f"CRITICAL: {msg}")