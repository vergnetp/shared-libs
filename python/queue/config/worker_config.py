from typing import Any, Dict, List, Optional, Union, Callable, Type


class QueueWorkerConfig:
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
        self.worker_count = worker_count
        self.thread_pool_size = thread_pool_size
        self.work_timeout = work_timeout    
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate worker configuration parameters."""
        errors = []
        
        if self.worker_count <= 0:
            errors.append(f"worker_count must be positive, got {self.worker_count}")
            
        if self.thread_pool_size <= 0:
            errors.append(f"thread_pool_size must be positive, got {self.thread_pool_size}")
            
        if self.work_timeout <= 0:
            errors.append(f"work_timeout must be positive, got {self.work_timeout}")
            
        if errors:
            raise ValueError(f"Worker configuration validation failed: {'; '.join(errors)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration
        """
        return {
            "worker_count": self.worker_count,
            "thread_pool_size": self.thread_pool_size,
            "work_timeout": self.work_timeout 
        }

