import threading
import time
import asyncio
from typing import Any, Dict, Optional, Callable

from ...config.base_config import BaseConfig
from .redis_config import QueueRedisConfig
from .log_config import QueueLoggingConfig
from .metrics_config import QueueMetricsConfig
from .retry_config import QueueRetryConfig
from .worker_config import QueueWorkerConfig
from .callable_config import QueueCallableConfig

class QueueConfig(BaseConfig):
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
        self._redis = redis or QueueRedisConfig()
        self._worker = worker or QueueWorkerConfig()
        self._retry = retry or QueueRetryConfig()
        self._metrics = metrics or QueueMetricsConfig()
        self._logging = logging or QueueLoggingConfig()
        
        # Initialize unified callables registry with logger
        self._callables = QueueCallableConfig(logger=self._logging.logger)
        
        super().__init__()
        
        # Log initialization
        self.logger.info(
            f"Queue system configuration initialized",
            redis_url=self._mask_url(self._redis.url) if self._redis.url else None,
            worker_count=self._worker.worker_count,
            thread_pool_size=self._worker.thread_pool_size
        )
    
    @property
    def redis(self) -> QueueRedisConfig:
        return self._redis
    
    @property
    def worker(self) -> QueueWorkerConfig:
        return self._worker
    
    @property
    def retry(self) -> QueueRetryConfig:
        return self._retry
    
    @property
    def metrics(self) -> QueueMetricsConfig:
        return self._metrics
    
    @property
    def logging(self) -> QueueLoggingConfig:
        return self._logging
    
    @property
    def callables(self) -> QueueCallableConfig:
        return self._callables
    
    @property
    def logger(self):
        """Get the configured logger."""
        return self._logging.logger
    
    def _validate_config(self):
        """No additional validation needed - components validate themselves."""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the complete configuration to a dictionary."""
        return {
            "redis": self._redis.to_dict(),
            "worker": self._worker.to_dict(),
            "retry": self._retry.to_dict(),
            "metrics": self._metrics.to_dict(),
            "logging": self._logging.to_dict(),
            "callables": self._callables.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueConfig':
        """Create instance from dictionary."""
        redis_config = None
        if 'redis' in data:
            redis_config = QueueRedisConfig.from_dict(data['redis'])
        
        worker_config = None
        if 'worker' in data:
            worker_config = QueueWorkerConfig.from_dict(data['worker'])
        
        retry_config = None
        if 'retry' in data:
            retry_config = QueueRetryConfig.from_dict(data['retry'])
        
        metrics_config = None
        if 'metrics' in data:
            metrics_config = QueueMetricsConfig.from_dict(data['metrics'])
        
        logging_config = None
        if 'logging' in data:
            logging_config = QueueLoggingConfig.from_dict(data['logging'])
        
        return cls(
            redis=redis_config,
            worker=worker_config,
            retry=retry_config,
            metrics=metrics_config,
            logging=logging_config
        )
