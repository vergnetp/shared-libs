import json
import time
import uuid
import hashlib
import threading
from typing import Any, Dict, List, Optional, Union, Callable, Tuple

from .queue_config import QueueConfig
from .queue_retry_config import QueueRetryConfig
from ..errors.try_catch import try_catch

class QueueManager:
    """
    Manager for queueing operations - used in API endpoints.
    
    This class provides a synchronous interface for adding jobs to the queue system.
    It handles operation creation, serialization, and enqueueing with appropriate
    retry configurations and callback registrations.
    
    Args:
        config: QueueConfig instance
    """
    def __init__(self, config: QueueConfig):
        """
        Initialize the queue manager.
        
        Args:
            config: QueueConfig instance
        """
        self.config = config
        # Lock for thread safety in critical sections
        self._enqueue_lock = threading.RLock()

    def _generate_operation_id(self) -> str:
        """
        Generate a unique operation ID.
        
        Returns:
            Unique ID string for the operation
        """
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
    
    def _serialize_entity(self, entity, default_serializer=None):
        """
        Serialize entity to JSON with custom handling for complex types.
        
        Args:
            entity: The entity to serialize
            default_serializer: Optional custom serializer function
            
        Returns:
            JSON string representation
        """
        try:
            if default_serializer:
                return json.dumps(entity, default=default_serializer)
            
            # Default serialization with enhanced type handling
            return json.dumps(entity, default=lambda obj: 
                obj.isoformat() if hasattr(obj, 'isoformat') else str(obj))
        except Exception as e:
            self.config.logger.error(f"Serialization error: {e}")
            # Fallback to basic string representation
            return json.dumps({"__error__": "Serialization error", 
                              "string_repr": str(entity)})
    
    @try_catch(
    description='Failed to enqueue operation',
    action='Check queue connectivity and entity format')
    def enqueue(self, 
                entity: Dict[str, Any], 
                processor: Union[Callable, str],
                # Basic queue parameters
                queue_name: Optional[str] = None,
                priority: str = "normal",
                operation_id: Optional[str] = None,
                
                # Retry configuration
                retry_config: Optional[QueueRetryConfig] = None,
                
                # Callback parameters
                on_success: Optional[Union[Callable, str]] = None,
                on_failure: Optional[Union[Callable, str]] = None,
                
                # Additional options
                timeout: Optional[float] = None,
                deduplication_key: Optional[str] = None,
                custom_serializer: Optional[Callable] = None
                ) -> Dict[str, Any]:
        """
        Enqueue an operation for asynchronous processing with optional retry and callback behavior.
        
        Args:
            entity: The data entity to process
            processor: Function that processes the entity or string name of processor
            
            # Basic queue parameters
            queue_name: Name of the queue (defaults to function name)
            priority: Priority ("high", "normal", "low")
            operation_id: Optional ID for the operation (auto-generated if not provided)
            
            # Retry configuration
            retry_config: Configuration for retry behavior (QueueRetryConfig instance)
            
            # Callback parameters
            on_success: Callback function or name to call on successful completion
            on_failure: Callback function or name to call when max retries are exhausted
            
            # Additional options
            timeout: Optional timeout for the operation in seconds
            deduplication_key: Optional key for deduplication (defaults to entity hash)
            custom_serializer: Optional function for custom serialization
            
        Returns:
            Dict with operation status and metadata
        """
        with self._enqueue_lock:
            try:
                # Generate or use operation ID
                op_id = operation_id or self._generate_operation_id()
                
                # Use provided deduplication key or generate from entity
                entity_hash = deduplication_key or self._hash_entity(entity)
                
                # Determine queue name if not provided
                if queue_name is None:
                    if callable(processor):
                        queue_name = f"{processor.__module__}.{processor.__name__}"
                    else:
                        # Assume processor is a string like "module.function" if not callable
                        queue_name = processor
                
                self.config.logger.debug(f"Enqueueing operation {op_id} on {queue_name}", 
                operation_id=op_id,
                processor=processor.__name__ if callable(processor) else processor,
                queue_name=queue_name,
                priority=priority,
                has_callbacks=bool(on_success or on_failure))
                        
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
                
                # Add timeout if provided
                if timeout is not None:
                    queue_data["timeout"] = float(timeout)
                
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
                self._queue_operation(queue_data, queue_name, priority, custom_serializer)
                
                # Update metrics
                self.config.update_metric('enqueued')
                
                self.config.logger.debug("Operation queued successfully", 
                      operation_id=op_id, 
                      queue_name=queue_name, 
                      priority=priority,
                      entity_id=getattr(entity, 'id', None),
                      has_callbacks=has_callbacks)
                
                # Return the operation details
                return {
                    "operation_id": op_id,
                    "status": "queued",
                    "has_callbacks": has_callbacks
                }
            except Exception as e:
                self.config.logger.error("Failed to enqueue operation", 
                            operation_id=op_id if 'op_id' in locals() else None, 
                            entity_id=getattr(entity, 'id', None), 
                            processor=queue_name if 'queue_name' in locals() else None,
                            error_type=type(e).__name__,
                            error_message=e.to_string() if hasattr(e, 'to_string') else str(e))
                raise
    
    @try_catch
    def enqueue_batch(self, 
                     entities: List[Dict[str, Any]], 
                     processor: Callable,
                     **kwargs) -> List[Dict[str, Any]]:
        """
        Enqueue multiple operations at once for batch processing.
        
        Args:
            entities: List of data entities to process
            processor: Function that processes the entities
            **kwargs: Same parameters as enqueue() method
            
        Returns:
            List of operation results with IDs and status
        """
        results = []
        
        # Pre-generate operation IDs
        operation_ids = [self._generate_operation_id() for _ in range(len(entities))]
        
        # Create a pipeline for batching Redis operations
        redis = self.config._ensure_redis_sync()
        pipeline = redis.pipeline()
        
        # Get common parameters
        queue_name = kwargs.get('queue_name')
        if queue_name is None and callable(processor):
            queue_name = f"{processor.__module__}.{processor.__name__}"
        
        priority = kwargs.get('priority', 'normal')
        retry_config = kwargs.get('retry_config')
        on_success = kwargs.get('on_success')
        on_failure = kwargs.get('on_failure')
        timeout = kwargs.get('timeout')
        custom_serializer = kwargs.get('custom_serializer')
        
        # Register processor if not already registered
        if callable(processor) and queue_name not in self.config.operations_registry:
            self.config.operations_registry[queue_name] = processor
        
        # Register callbacks if they are callables
        if callable(on_success):
            self.config.register_callback(on_success)
        if callable(on_failure):
            self.config.register_callback(on_failure)
        
        # Process each entity
        for i, entity in enumerate(entities):
            # Reuse enqueue logic but with pipeline
            op_id = operation_ids[i]
            entity_hash = self._hash_entity(entity)
            
            # Prepare queue data 
            queue_data = {
                "entity": entity,
                "operation_id": op_id,
                "entity_hash": entity_hash,
                "timestamp": time.time(),
                "attempts": 0,
                "processor": processor.__name__ if callable(processor) else processor,
                "processor_module": processor.__module__ if callable(processor) else None,
            }
            
            # Add timeout if provided
            if timeout is not None:
                queue_data["timeout"] = float(timeout)
            
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
            
            # Determine queue key
            queue_key = self.config.get_queue_key(queue_name, priority)
            
            # Serialize the queue data
            serialized_data = self._serialize_entity(queue_data, custom_serializer)
            
            # Add to pipeline instead of immediate execution
            pipeline.lpush(queue_key, serialized_data)
            pipeline.sadd(self.config.registry_key, queue_key)
            
            # Track the result
            results.append({
                "operation_id": op_id,
                "status": "queued"
            })
        
        # Execute all commands in a single network round-trip
        try:
            pipeline.execute()
            
            # Update metrics
            self.config.update_metric('enqueued', len(entities))
            
            self.config.logger.info(f"Batch enqueued {len(entities)} operations successfully",
                queue_name=queue_name, priority=priority)
        except Exception as e:
            self.config.logger.error(f"Failed to enqueue batch operations: {e}")
            raise
            
        return results
    
    @try_catch
    def _queue_operation(self,
                       queue_data: Dict[str, Any],
                       queue_name: str,
                       priority: str = "normal",
                       custom_serializer: Optional[Callable] = None) -> None:
        """
        Queue an operation for later processing.
        
        Args:
            queue_data: The data to add to the queue
            queue_name: Name of the queue
            priority: Queue priority
            custom_serializer: Optional function for custom serialization
        """
        # Get the full queue key
        queue_key = self.config.get_queue_key(queue_name, priority)
        
        # Initialize Redis client synchronously
        redis = self.config._ensure_redis_sync()
        
        # Serialize queue data
        serialized_data = self._serialize_entity(queue_data, custom_serializer)
            
        # Add to the queue
        redis.lpush(queue_key, serialized_data)
        
        # Register the queue
        redis.sadd(self.config.registry_key, queue_key)
    
    @try_catch
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
            
        # Add failure queues
        for queue_type, queue_key in self.config.queue_keys.items():
            queue_key_str = queue_key.decode() if isinstance(queue_key, bytes) else queue_key
            status[queue_key_str] = redis.llen(queue_key)
            
        # Add metrics
        status['metrics'] = self.config.get_metrics()
            
        return status
        
    @try_catch
    def purge_queue(self, queue_name: str, priority: str = "normal") -> int:
        """
        Remove all items from a specific queue.
        
        Args:
            queue_name: Name of the queue to purge
            priority: Queue priority
            
        Returns:
            Number of items purged
        """
        redis = self.config._ensure_redis_sync()
        queue_key = self.config.get_queue_key(queue_name, priority)
        
        # Get the current length
        count = redis.llen(queue_key)
        
        # Delete the queue
        redis.delete(queue_key)
        
        # Report the purge
        self.config.logger.info(f"Purged {count} items from queue {queue_name} with priority {priority}")
        
        return count