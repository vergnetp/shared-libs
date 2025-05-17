import threading
import math
import redis
from typing import Optional, Dict, Any, Callable, List
from ..resilience import circuit_breaker, retry_with_backoff

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
            'redis_errors': 0,
            'validation_errors': 0,
            'general_errors': 0,
            'avg_enqueue_time': 0.0,
            'avg_process_time': 0.0,
            'last_timeout_timestamp': None,
            'queue_depths': {},  # Track queue depths by queue name
            
            # Thread pool metrics
            'thread_pool_exhaustion': 0,
            'thread_pool_usage': 0,
            'thread_pool_max_usage': 0,
            'thread_pool_utilization': 0,
            'avg_thread_processing_time': 0.0,
            'total_thread_time': 0,
            'thread_tasks_completed': 0,
        }
        self._metrics_lock = threading.RLock()

        # Track total enqueues for calculating averages
        self._total_enqueues = 0
        self._total_processes = 0
       
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
    
    @circuit_breaker(name="redis_connection", failure_threshold=3, recovery_timeout=10.0)
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(redis.RedisError, ConnectionError))
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
                # Use synchronous Redis client with timeout
                self.redis_client = redis.Redis.from_url(
                    self.redis_url, 
                    socket_timeout=self.connection_timeout
                )
                # Test the connection
                self.redis_client.ping()
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
        
    def update_metric(self, metric_name: str, value: Any = 1, force_log: bool = False):
        """
        Update a metric counter or value and log significant changes.
        
        Args:
            metric_name: Name of the metric to update
            value: Value to add or set for the metric (default: 1)
            force_log: If True, always log regardless of significance
        """
        with self._metrics_lock:
            # Record old value for change detection
            old_value = self._metrics.get(metric_name, 0)
            should_log = force_log  # Initialize with force_log
            
            # Update the metric based on type
            if metric_name not in self._metrics:
                # Initialize new metric
                self._metrics[metric_name] = value
                should_log = True  # Always log new metrics
            
            elif metric_name.endswith('_timestamp'):
                # Timestamp updates - don't log these normally
                self._metrics[metric_name] = value
                should_log = force_log  # Only log if forced
            
            elif metric_name.startswith('avg_'):
                # Average calculations
                total_key = f"_total_{metric_name[4:]}"
                count_key = f"_count_{metric_name[4:]}"
                
                if total_key not in self._metrics:
                    self._metrics[total_key] = 0
                if count_key not in self._metrics:
                    self._metrics[count_key] = 0
                
                self._metrics[total_key] += value
                self._metrics[count_key] += 1
                
                new_value = self._metrics[total_key] / self._metrics[count_key]
                self._metrics[metric_name] = new_value
                
                # For averages, log on significant changes (>10%)
                if old_value != 0:
                    relative_change = abs(new_value - old_value) / abs(old_value)
                    should_log = should_log or relative_change > 0.1
                else:
                    should_log = True  # First real value
            
            else:
                # Counter updates
                self._metrics[metric_name] += value
                new_value = self._metrics[metric_name]
                
                # Smart logging rules for counters
                if metric_name in ('failed', 'errors', 'timeouts', 'redis_errors', 'thread_pool_exhaustion'):
                    # Important error metrics - log every increment
                    should_log = should_log or new_value > old_value
                elif old_value < 5:
                    # First few occurrences of any metric
                    should_log = True
                elif new_value >= 10 and old_value < 10:
                    # Crossing 10
                    should_log = True
                elif new_value >= 100 and old_value < 100:
                    # Crossing 100
                    should_log = True
                elif new_value >= 1000 and old_value < 1000:
                    # Crossing 1000
                    should_log = True
                elif new_value >= 10000 and old_value < 10000:
                    # Crossing 10000
                    should_log = True
                elif old_value >= 10000:
                    # For large counters, log every 10% increase
                    should_log = should_log or new_value >= old_value * 1.1
                elif old_value >= 1000:
                    # For medium-large counters, log every 20% increase
                    should_log = should_log or new_value >= old_value * 1.2
                elif old_value >= 100:
                    # For medium counters, log every 50% increase
                    should_log = should_log or new_value >= old_value * 1.5
            
            # Store updated metric value and if we should log
            updated_value = self._metrics[metric_name]
            
        # End of metrics_lock block - we've released the lock
        
        # Now handle logging if needed - outside the metrics lock to prevent deadlocks
        if should_log and hasattr(self, 'logger'):
            # Create a separate lock for logging to prevent recursive issues
            if not hasattr(self, '_logging_lock'):
                self._logging_lock = threading.RLock()
                
            # Try to acquire the logging lock - with timeout to prevent deadlocks
            if self._logging_lock.acquire(timeout=1.0):
                try:
                    # Check if we're already in a recursive logging call
                    if hasattr(self, '_in_logging') and self._in_logging:
                        return
                    
                    self._in_logging = True
                    try:
                        # Get additional context for the log if available
                        queue_status = None
                        if hasattr(self, 'queue_manager'):
                            try:
                                queue_status = self.queue_manager.get_queue_status()
                            except Exception:
                                pass
                        
                        # Get current metrics to include in log - copy to avoid lock contention
                        with self._metrics_lock:
                            metrics_copy = self._metrics.copy()
                        
                        # Select log level based on metric type
                        if metric_name in ('failed', 'errors', 'timeouts', 'redis_errors', 'thread_pool_exhaustion') and updated_value > old_value:
                            log_method = self.logger.warning
                        else:
                            log_method = self.logger.info
                        
                        # Create the log message
                        log_method(
                            f"Queue metric update: {metric_name}",
                            metric_name=metric_name,
                            old_value=old_value,
                            new_value=updated_value,
                            change=updated_value - old_value if isinstance(old_value, (int, float)) else None,
                            metrics=metrics_copy,
                            queue_status=queue_status
                        )
                    finally:
                        self._in_logging = False
                except Exception as e:
                    # Ensure logging never breaks the metrics update
                    try:
                        self.logger.error(f"Error while logging metrics: {e}")
                    except:
                        pass
                finally:
                    self._logging_lock.release()

    def get_metrics(self) -> Dict[str, Any]:
        with self._metrics_lock:
            # Create a copy of the metrics
            metrics = self._metrics.copy()
            
            # Add some computed metrics
            if 'enqueued' in metrics and metrics['enqueued'] > 0:
                processed = metrics.get('processed', 0)
                failed = metrics.get('failed', 0)
                metrics['success_rate'] = (processed - failed) / metrics['enqueued'] * 100
            else:
                metrics['success_rate'] = 0
                
            # Add error breakdown percentage
            total_errors = metrics.get('errors', 0)
            if total_errors > 0:
                metrics['error_breakdown'] = {
                    'timeouts': (metrics.get('timeouts', 0) / total_errors) * 100,
                    'redis': (metrics.get('redis_errors', 0) / total_errors) * 100,
                    'validation': (metrics.get('validation_errors', 0) / total_errors) * 100,
                    'general': (metrics.get('general_errors', 0) / total_errors) * 100
                }
            
            # Add thread pool specific metrics if data exists
            if 'thread_pool_usage' in metrics and metrics['thread_pool_usage'] > 0:
                if 'thread_pool_max_usage' not in metrics:
                    metrics['thread_pool_max_usage'] = metrics['thread_pool_usage']
                    
                # Include thread pool exhaustion rate if available
                if 'thread_tasks_completed' in metrics and metrics['thread_tasks_completed'] > 0:
                    exhaustion_count = metrics.get('thread_pool_exhaustion', 0)
                    metrics['thread_pool_exhaustion_rate'] = (
                        (exhaustion_count / metrics['thread_tasks_completed']) * 100
                    )
            
            return metrics