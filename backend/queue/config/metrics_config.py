import threading
import time
from typing import Any, Dict, List, Optional, Union, Callable, Type

from ...config.base_config import BaseConfig

class QueueMetricsConfig(BaseConfig):
    """
    Configuration for metrics collection and reporting.
    
    Controls what metrics are collected, logging thresholds,
    and related behavior for the queue system's metrics tracking.
    """
    def __init__(
        self,
        enabled: bool = True,
        log_threshold: float = 0.1
    ):
        """
        Initialize metrics configuration.
        
        Args:
            enabled: Whether metrics collection is enabled (default: True)
            log_threshold: Threshold for logging metric changes, as a fraction (default: 0.1 = 10%)
        """
        self._enabled = enabled
        self._log_threshold = log_threshold
        
        # Initialize metrics storage
        self._metrics = {} if self._enabled else None
        self._metrics_lock = threading.RLock()
        
        if self._enabled:
            self._metrics['enqueued'] = 0
            self._metrics['processed'] = 0
            self._metrics['failed'] = 0
            self._metrics['retried'] = 0
            self._metrics['timeouts'] = 0
            self._metrics['system_start_time'] = time.time()
        
        super().__init__()
        self._validate_config()
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @property
    def log_threshold(self) -> float:
        return self._log_threshold
    
    def _validate_config(self):
        """Validate configuration."""
        if self._log_threshold < 0 or self._log_threshold > 1:
            raise ValueError(f"log_threshold must be between 0 and 1, got {self._log_threshold}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "enabled": self._enabled,
            "log_threshold": self._log_threshold
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueMetricsConfig':
        """Create instance from dictionary."""
        return cls(
            enabled=data.get('enabled', True),
            log_threshold=data.get('log_threshold', 0.1)
        )

    def update_metric(self, metric_name: str, value: Any = 1, force_log: bool = False, logger=None):
        """
        Update a metric counter or value and log significant changes.
        
        Args:
            metric_name: Name of the metric to update
            value: Value to add or set for the metric (default: 1)
            force_log: If True, always log regardless of significance (default: False)
            logger: Logger instance to use for logging (default: None)
        """
        if not self.enabled:
            return            
            
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
                
                # For averages, log on significant changes
                if old_value != 0:
                    relative_change = abs(new_value - old_value) / abs(old_value)
                    should_log = should_log or relative_change > self.log_threshold
                else:
                    should_log = True  # First real value
            
            else:
                # Counter updates
                self._metrics[metric_name] = self._metrics.get(metric_name, 0) + value
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
            
            # Store updated metric value
            updated_value = self._metrics[metric_name]
            self._metrics['last_update_time'] = time.time()
            
            # If success_rate has not been calculated, do it now
            if 'enqueued' in self._metrics and self._metrics['enqueued'] > 0:
                processed = self._metrics.get('processed', 0)
                failed = self._metrics.get('failed', 0)
                self._metrics['success_rate'] = ((processed - failed) / self._metrics['enqueued']) * 100
        
        # End of metrics_lock block - we've released the lock
        
        # Handle logging if needed - outside the metrics lock to prevent deadlocks
        if should_log and logger:
            # Select log level based on metric type
            if metric_name in ('failed', 'errors', 'timeouts', 'redis_errors', 'thread_pool_exhaustion') and updated_value > old_value:
                log_method = logger.warning
            else:
                log_method = logger.info
            
            # Create the log message
            log_method(
                f"Queue metric update: {metric_name}",
                metric_name=metric_name,
                old_value=old_value,
                new_value=updated_value,
                change=updated_value - old_value if isinstance(old_value, (int, float)) else None
            )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics with computed fields.
        
        Returns:
            Dict with all metrics including computed fields
        """
        if not self.enabled or not self._metrics:
            return {}
            
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
            
            # Add uptime
            metrics['uptime_seconds'] = time.time() - metrics.get('system_start_time', time.time())
            
            return metrics
    
