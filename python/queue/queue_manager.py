import json
import time
import uuid
import hashlib
from typing import Any, Dict, List, Optional, Union, Callable

from .queue_config import QueueConfig
from .queue_retry_config import QueueRetryConfig

class QueueManager:
    """Manager for queueing operations - used in API endpoints."""
    def __init__(self, config: QueueConfig):
        """
        Initialize the queue manager.
        
        Args:
            config: QueueConfig instance
        """
        self.config = config
        
    def _generate_operation_id(self) -> str:
        """Generate a unique operation ID"""
        return str(uuid.uuid4())
    
    def _hash_entity(self, entity: Dict[str, Any]) -> str:
        """
        Generate a hash for an entity for deduplication.
        
        Args:
            entity: The data entity to hash
            
        Returns:
            Hash string
        """
        # Sort keys to ensure consistent hashing
        normalized = json.dumps(entity, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def enqueue(self, 
                entity: Dict[str, Any], 
                processor: Callable,
                # Basic queue parameters
                queue_name: Optional[str] = None,
                priority: str = "normal",
                operation_id: Optional[str] = None,
                
                # Retry configuration
                retry_config: Optional[QueueRetryConfig] = None,
                
                # Callback parameters
                on_success: Optional[Union[Callable, str]] = None,
                on_failure: Optional[Union[Callable, str]] = None
                ) -> Dict[str, Any]:
        """
        Enqueue an operation for asynchronous processing with optional retry and callback behavior.
        
        Args:
            entity: The data entity to process
            processor: Function that processes the entity
            
            # Basic queue parameters
            queue_name: Name of the queue (defaults to function name)
            priority: Priority ("high", "normal", "low")
            operation_id: Optional ID for the operation (auto-generated if not provided)
            
            # Retry configuration
            retry_config: Configuration for retry behavior (QueueRetryConfig instance)
            
            # Callback parameters
            on_success: Callback function or name to call on successful completion
            on_failure: Callback function or name to call when max retries are exhausted
            
        Returns:
            Dict with operation status and metadata
        """
        # Generate or use operation ID
        op_id = operation_id or self._generate_operation_id()
        entity_hash = self._hash_entity(entity)
        
        # Determine queue name if not provided
        if queue_name is None:
            if callable(processor):
                queue_name = f"{processor.__module__}.{processor.__name__}"
            else:
                # Assume processor is a string like "module.function" if not callable
                queue_name = processor
        
        # Register processor if not already registered
        if callable(processor) and queue_name not in self.config.operations_registry:
            self.config.operations_registry[queue_name] = processor

        # Register callbacks if they are callables
        has_callbacks = bool(on_success or on_failure)
        if callable(on_success):
            self.config.register_callback(on_success)
        if callable(on_failure):
            self.config.register_callback(on_failure)
        
        # Validate callbacks if provided
        if on_success and not callable(on_success) and not isinstance(on_success, str):
            raise ValueError("on_success must be a callable or string function name")
        if on_failure and not callable(on_failure) and not isinstance(on_failure, str):
            raise ValueError("on_failure must be a callable or string function name")
        
        # Prepare the queue data
        queue_data = {
            "entity": entity,
            "operation_id": op_id,
            "entity_hash": entity_hash,
            "timestamp": time.time(),
            "attempts": 0,
            "processor": processor.__name__ if callable(processor) else processor,
            "processor_module": processor.__module__ if callable(processor) else None,
        }
        
        # Add callback info if provided
        if on_success:
            queue_data["on_success"] = on_success.__name__ if callable(on_success) else on_success
            queue_data["on_success_module"] = on_success.__module__ if callable(on_success) else None
        
        if on_failure:
            queue_data["on_failure"] = on_failure.__name__ if callable(on_failure) else on_failure
            queue_data["on_failure_module"] = on_failure.__module__ if callable(on_failure) else None
        
        # Add retry configuration if provided
        if retry_config:
            queue_data.update({
                "max_attempts": retry_config.max_attempts,
                "delays": retry_config.delays,
                "timeout": retry_config.timeout,
                "next_retry_time": time.time()
            })
        else:
            # Default max attempts
            queue_data["max_attempts"] = 5
        
        # Queue the operation
        self._queue_operation(queue_data, queue_name, priority)
        
        # Return the operation details
        return {
            "operation_id": op_id,
            "status": "queued",
            "has_callbacks": has_callbacks
        }
    
    def _queue_operation(self,
                       queue_data: Dict[str, Any],
                       queue_name: str,
                       priority: str = "normal") -> None:
        """
        Queue an operation for later processing.
        
        Args:
            queue_data: The data to add to the queue
            queue_name: Name of the queue
            priority: Queue priority
        """
        # Get the full queue key
        queue_key = self.config.get_queue_key(queue_name, priority)
        
        # Initialize Redis client synchronously
        redis = self.config._ensure_redis_sync()
            
        # Add to the queue
        redis.lpush(queue_key, json.dumps(queue_data, default=str))
        
        # Register the queue
        redis.sadd(self.config.registry_key, queue_key)
    
    def get_queue_status(self) -> Dict[str, int]:
        """
        Get the status of all processing queues.
        
        Returns:
            Dict with queue names and item counts
        """
        redis = self.config._ensure_redis_sync()
        
        # Get all registered queues
        queues = redis.smembers(self.config.registry_key)
        
        status = {}
        for queue in queues:
            # Decode queue name if it's bytes
            queue_name = queue.decode() if isinstance(queue, bytes) else queue
            queue_len = redis.llen(queue)
            status[queue_name] = queue_len
            
        return status