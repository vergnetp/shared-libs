from typing import Any, Dict

from ...config.base_config import BaseConfig


class QueueWorkerConfig(BaseConfig):
    """
    Configuration for worker execution and thread pool.
    
    Controls worker count, thread pool size, timeout settings,
    and execution behavior for queue processors.
    """
    def __init__(
        self,
        worker_count: int = 5,
        thread_pool_size: int = 20,
        work_timeout: float = 30.0
    ):
        """
        Initialize worker configuration.
        
        Args:
            worker_count: Number of concurrent worker tasks to run (default: 5)
            thread_pool_size: Size of the thread pool for executing sync processors (default: 20)
            work_timeout: Default timeout in seconds for processing operations (default: 30.0)
            grace_shutdown_period: Time in seconds to wait for clean shutdown (default: 5.0)  
        """
        self._worker_count = worker_count
        self._thread_pool_size = thread_pool_size
        self._work_timeout = work_timeout
        
        super().__init__()
        self._validate_config()
    
    @property
    def worker_count(self) -> int:
        return self._worker_count
    
    @property
    def thread_pool_size(self) -> int:
        return self._thread_pool_size
    
    @property
    def work_timeout(self) -> float:
        return self._work_timeout
    
    def _validate_config(self):
        """Validate worker configuration parameters."""
        errors = []
        
        if self._worker_count <= 0:
            errors.append(f"worker_count must be positive, got {self._worker_count}")
        
        if self._thread_pool_size <= 0:
            errors.append(f"thread_pool_size must be positive, got {self._thread_pool_size}")
        
        if self._work_timeout <= 0:
            errors.append(f"work_timeout must be positive, got {self._work_timeout}")
        
        if errors:
            raise ValueError(f"Worker configuration validation failed: {'; '.join(errors)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "worker_count": self._worker_count,
            "thread_pool_size": self._thread_pool_size,
            "work_timeout": self._work_timeout
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueWorkerConfig':
        """Create instance from dictionary."""
        return cls(
            worker_count=data.get('worker_count', 5),
            thread_pool_size=data.get('thread_pool_size', 20),
            work_timeout=data.get('work_timeout', 30.0)
        )

