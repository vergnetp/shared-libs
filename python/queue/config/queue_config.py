import threading
import time
import asyncio
from typing import Any, Dict, Optional, Callable

from .redis_config import QueueRedisConfig
from .log_config import QueueLoggingConfig
from .metrics_config import QueueMetricsConfig
from .retry_config import QueueRetryConfig
from .worker_config import QueueWorkerConfig
from .callable_config import QueueCallableConfig

class QueueConfig:
    """
    Central configuration for the entire queue system.
    
    Composes specialized configuration components for Redis,
    workers, retries, metrics, and logging to provide a
    single configuration source for all queue system components.
    """
    def __init__(
        self,
        redis: Optional[QueueRedisConfig] = None,
        worker: Optional[QueueWorkerConfig] = None,
        retry: Optional[QueueRetryConfig] = None,
        metrics: Optional[QueueMetricsConfig] = None,
        logging: Optional[QueueLoggingConfig] = None
    ):
        """
        Initialize queue system configuration.
        
        Args:
            redis: Redis connection configuration
            worker: Worker pool configuration
            retry: Retry behavior configuration
            metrics: Metrics collection configuration
            logging: Logging configuration
        """
        # Initialize each component with defaults if not provided
        self.redis = redis or QueueRedisConfig()
        self.worker = worker or QueueWorkerConfig()
        self.retry = retry or QueueRetryConfig()
        self.metrics = metrics or QueueMetricsConfig()
        self.logging = logging or QueueLoggingConfig()
        
        # Initialize unified callables registry with logger
        self.callables = QueueCallableConfig(logger=self.logging.logger)
        
        # Initialize metrics storage if enabled
        self._metrics = {} if self.metrics.enabled else None
        self._metrics_lock = threading.RLock()
        
        # Log initialization
        self.logger.info(
            f"Queue system configuration initialized",
            redis_url=self.redis._mask_connection_url(self.redis.url) if self.redis.url else None,
            worker_count=self.worker.worker_count,
            thread_pool_size=self.worker.thread_pool_size
        )
    
    @property
    def logger(self):
        """Get the configured logger."""
        return self.logging.logger
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the complete configuration to a dictionary.
        
        Returns:
            Dict with all configuration components
        """
        return {
            "redis": self.redis.to_dict(),
            "worker": self.worker.to_dict(),
            "retry": self.retry.to_dict(),
            "metrics": self.metrics.to_dict(),
            "logging": self.logging.to_dict(),
            "callables": self.callables.to_dict()
        }
    
