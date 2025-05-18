import json
import time
import uuid
import hashlib
import datetime
import threading
from typing import Any, Dict, List, Optional, Union, Callable, Tuple

import redis
import asyncio

from .config import QueueConfig, QueueRetryConfig
from ..errors.try_catch import try_catch
from ..resilience import circuit_breaker

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

    @circuit_breaker(name="queue_enqueue", failure_threshold=5, recovery_timeout=10.0)
    @try_catch(
        description='Failed to enqueue operation',
        action='Check queue connectivity and entity format'
    )
    def enqueue(self, 
                entity: Dict[str, Any], 
                processor: Union[Callable, str],
                # Basic queue parameters
                queue_name: Optional[str] = None,
                priority: str = "normal",
                operation_id: Optional[str] = None,
                
                # Retry configuration
                retry_config: Optional[Union[Dict[str, Any], QueueRetryConfig]] = None,
                
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
            retry_config: Configuration for retry behavior (either QueueRetryConfig object or dict with retry options). Default to self.config.retry.
            
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
        start_time = time.time()
        success = False
        error_type = None
        
        try:
            # Generate or use operation ID
            op_id = operation_id or self._generate_operation_id()
            
            # Use provided deduplication key or generate from entity
            entity_hash = deduplication_key or self._hash_entity(entity)
            
            # Determine processor information based on type
            processor_name = None
            processor_module = None
            
            if callable(processor):
                # If processor is a callable, register it and get its name/module
                self.config.callables.register(processor)
                processor_name = processor.__name__
                processor_module = processor.__module__
                
                # Use processor module/name for queue name if not provided
                if queue_name is None:
                    queue_name = f"{processor_module}.{processor_name}"
                    
                # Log processor type for debugging
                is_async = asyncio.iscoroutinefunction(processor)
                self.config.logger.debug(
                    f"Using {'async' if is_async else 'sync'} processor: {queue_name}"
                )
            else:
                # If processor is a string, parse it to get module/name
                if "." in processor:
                    # String contains module path (e.g., "module.submodule.function")
                    parts = processor.split(".")
                    processor_name = parts[-1]
                    processor_module = ".".join(parts[:-1])
                    
                    # Use processor string for queue name if not provided
                    if queue_name is None:
                        queue_name = processor
                else:
                    # String is just a function name
                    processor_name = processor
                    
                    # Use processor name for queue name if not provided
                    if queue_name is None:
                        queue_name = processor
            
            self.config.logger.debug(f"Enqueueing operation {op_id} on {queue_name}", 
                            operation_id=op_id,
                            processor=processor_name,
                            queue_name=queue_name,
                            priority=priority,
                            has_callbacks=bool(on_success or on_failure))
            
            # Process callbacks
            has_callbacks = bool(on_success or on_failure)
            success_callback_name = None
            success_callback_module = None
            failure_callback_name = None
            failure_callback_module = None
            
            # Handle success callback
            if on_success:
                if callable(on_success):
                    # Register the callback function
                    self.config.callables.register(on_success)
                    success_callback_name = on_success.__name__
                    success_callback_module = on_success.__module__
                elif isinstance(on_success, str):
                    # Parse string callback
                    if "." in on_success:
                        parts = on_success.split(".")
                        success_callback_name = parts[-1]
                        success_callback_module = ".".join(parts[:-1])
                    else:
                        success_callback_name = on_success
                else:
                    raise ValueError("on_success must be a callable or string function name")
            
            # Handle failure callback
            if on_failure:
                if callable(on_failure):
                    # Register the callback function
                    self.config.callables.register(on_failure)
                    failure_callback_name = on_failure.__name__
                    failure_callback_module = on_failure.__module__
                elif isinstance(on_failure, str):
                    # Parse string callback
                    if "." in on_failure:
                        parts = on_failure.split(".")
                        failure_callback_name = parts[-1]
                        failure_callback_module = ".".join(parts[:-1])
                    else:
                        failure_callback_name = on_failure
                else:
                    raise ValueError("on_failure must be a callable or string function name")
            
            # Prepare the queue data
            queue_data = {
                "entity": entity,
                "operation_id": op_id,
                "entity_hash": entity_hash,
                "timestamp": time.time(),
                "attempts": 0,
                "processor": processor_name,
                "processor_module": processor_module,
            }
            
            # Add timeout if provided
            if timeout is not None:
                queue_data["timeout"] = float(timeout)
            
            # Add callback info if provided
            if success_callback_name:
                queue_data["on_success"] = success_callback_name
                queue_data["on_success_module"] = success_callback_module
            
            if failure_callback_name:
                queue_data["on_failure"] = failure_callback_name
                queue_data["on_failure_module"] = failure_callback_module
            
            # Add retry configuration if provided
            if retry_config:
                # Convert QueueRetryConfig object to dictionary if needed
                if hasattr(retry_config, 'to_dict') and callable(getattr(retry_config, 'to_dict')):
                    retry_config = retry_config.to_dict()
                queue_data.update(retry_config)
            else:
                # Default retry config from main configuration
                queue_data.update({
                    "max_attempts": self.config.retry.max_attempts,
                    "delays": self.config.retry.delays,
                    "timeout": self.config.retry.timeout,
                    "next_retry_time": time.time()
                })
            
            # Queue the operation
            self._queue_operation(queue_data, queue_name, priority, custom_serializer)
            
            # Mark as successful
            success = True
            
            # Update metrics
            acquisition_time = time.time() - start_time
            self.config.metrics.update_metric('enqueued')
            self.config.metrics.update_metric('avg_enqueue_time', acquisition_time)
            
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
                "has_callbacks": has_callbacks,
                "enqueue_time_ms": int(acquisition_time * 1000)
            }
        
        except asyncio.TimeoutError:
            # Specifically track timeouts
            error_type = 'timeout'
            self.config.metrics.update_metric('timeouts')
            self.config.metrics.update_metric('last_timeout_timestamp', time.time())
            raise
            
        except Exception as e:
            # Track different types of errors
            if isinstance(e, redis.RedisError):
                error_type = 'redis'
                self.config.metrics.update_metric('redis_errors')
            elif isinstance(e, (TypeError, ValueError)):
                error_type = 'validation'
                self.config.metrics.update_metric('validation_errors')
            else:
                error_type = 'general'
                self.config.metrics.update_metric('general_errors')
            
            # Increment total errors
            self.config.metrics.update_metric('errors')
            
            # Log with enhanced error details
            self.config.logger.error(f"Failed to enqueue operation", 
                    error_id=op_id if 'op_id' in locals() else None, 
                    entity_id=getattr(entity, 'id', None) if 'entity' in locals() else None, 
                    processor=queue_name if 'queue_name' in locals() else None,
                    error_type=error_type,
                    error_message=e.to_string() if hasattr(e, 'to_string') else str(e),
                    elapsed_time=time.time() - start_time)
            raise

    @circuit_breaker(name="queue_bacth", failure_threshold=5, recovery_timeout=30.0)
    @try_catch
    def enqueue_batch(self, 
                    entities: List[Dict[str, Any]], 
                    processor: Union[Callable, str],
                    **kwargs) -> List[Dict[str, Any]]:
        """
        Enqueue multiple operations at once for batch processing.
        
        Args:
            entities: List of data entities to process
            processor: Function that processes the entities or string name
            **kwargs: Same parameters as enqueue() method
                
        Returns:
            List of operation results with IDs and status
        """
        # Start time for performance tracking
        start_time = time.time()
        
        # No entities to process
        if not entities:
            return []
        
        # Determine processor information based on type
        processor_name = None
        processor_module = None
        
        if callable(processor):
            # If processor is a callable, register it and get its name/module
            self.config.callables.register(processor)
            processor_name = processor.__name__
            processor_module = processor.__module__
            
            # Check if the processor is async or sync and log for info
            is_async = asyncio.iscoroutinefunction(processor)
            
            self.config.logger.debug(
                f"Batch using {'async' if is_async else 'sync'} processor: {processor_name}"
            )
        else:
            # If processor is a string, parse it to get module/name
            if "." in processor:
                # String contains module path (e.g., "module.submodule.function")
                parts = processor.split(".")
                processor_name = parts[-1]
                processor_module = ".".join(parts[:-1])
            else:
                # String is just a function name
                processor_name = processor
        
        # Get common parameters
        queue_name = kwargs.get('queue_name')
        if queue_name is None and processor_module:
            queue_name = f"{processor_module}.{processor_name}"
        elif queue_name is None:
            queue_name = processor_name
        
        priority = kwargs.get('priority', 'normal')
        retry_config = kwargs.get('retry_config')
        timeout = kwargs.get('timeout')
        custom_serializer = kwargs.get('custom_serializer')
        
        # Process callbacks
        on_success = kwargs.get('on_success')
        on_failure = kwargs.get('on_failure')
        
        success_callback_name = None
        success_callback_module = None
        failure_callback_name = None
        failure_callback_module = None
        
        # Handle success callback
        if on_success:
            if callable(on_success):
                # Register the callback function
                self.config.callables.register(on_success)
                success_callback_name = on_success.__name__
                success_callback_module = on_success.__module__
            elif isinstance(on_success, str):
                # Parse string callback
                if "." in on_success:
                    parts = on_success.split(".")
                    success_callback_name = parts[-1]
                    success_callback_module = ".".join(parts[:-1])
                else:
                    success_callback_name = on_success
            else:
                raise ValueError("on_success must be a callable or string function name")
        
        # Handle failure callback
        if on_failure:
            if callable(on_failure):
                # Register the callback function
                self.config.callables.register(on_failure)
                failure_callback_name = on_failure.__name__
                failure_callback_module = on_failure.__module__
            elif isinstance(on_failure, str):
                # Parse string callback
                if "." in on_failure:
                    parts = on_failure.split(".")
                    failure_callback_name = parts[-1]
                    failure_callback_module = ".".join(parts[:-1])
                else:
                    failure_callback_name = on_failure
            else:
                raise ValueError("on_failure must be a callable or string function name")
        
        # Create a pipeline for batching Redis operations
        redis_client = self.config.redis.get_client()
        pipeline = redis_client.pipeline()
        
        # Pre-generate operation IDs
        operation_ids = [self._generate_operation_id() for _ in range(len(entities))]
        
        results = []
        
        # Process each entity
        for i, entity in enumerate(entities):
            # Generate operation ID
            op_id = operation_ids[i]
            entity_hash = self._hash_entity(entity)
            
            # Prepare queue data 
            queue_data = {
                "entity": entity,
                "operation_id": op_id,
                "entity_hash": entity_hash,
                "timestamp": time.time(),
                "attempts": 0,
                "processor": processor_name,
                "processor_module": processor_module,
            }
            
            # Add timeout if provided
            if timeout is not None:
                queue_data["timeout"] = float(timeout)
            
            # Add callback info if provided
            if success_callback_name:
                queue_data["on_success"] = success_callback_name
                queue_data["on_success_module"] = success_callback_module
            
            if failure_callback_name:
                queue_data["on_failure"] = failure_callback_name
                queue_data["on_failure_module"] = failure_callback_module
            
            # Add retry configuration if provided
            if retry_config:
                queue_data.update(retry_config)
            else:
                # Use default retry config
                queue_data.update({
                    "max_attempts": self.config.retry.max_attempts,
                    "delays": self.config.retry.delays,
                    "timeout": self.config.retry.timeout,
                    "next_retry_time": time.time()
                })
            
            # Determine queue key
            queue_key = self.config.redis.get_queue_key(queue_name, priority)
            
            # Serialize the queue data
            serialized_data = self._serialize_entity(queue_data, custom_serializer)
            
            # Add to pipeline instead of immediate execution
            pipeline.lpush(queue_key, serialized_data)
            pipeline.sadd(self.config.redis.get_registry_key(), queue_key)
            
            # Track the result
            results.append({
                "operation_id": op_id,
                "status": "queued"
            })
        
        # Execute all commands in a single network round-trip
        try:
            pipeline.execute()
            
            # Calculate performance metrics
            total_time = time.time() - start_time
            avg_time_per_op = total_time / len(entities)
            
            # Update metrics with batch data
            self.config.metrics.update_metric('enqueued', len(entities), force_log=True)
            self.config.metrics.update_metric('avg_enqueue_time', avg_time_per_op)
            self.config.metrics.update_metric(f'enqueued_batch_{priority}', len(entities))
            
            # Update queue-specific metrics
            self.config.metrics.update_metric(f'queue_{queue_name.replace(".", "_")}_total', len(entities))
            
            self.config.logger.info(
                f"Batch enqueued {len(entities)} operations successfully",
                queue_name=queue_name, 
                priority=priority,
                batch_size=len(entities),
                total_time_ms=int(total_time * 1000),
                avg_time_per_op_ms=int(avg_time_per_op * 1000)
            )
        except Exception as e:
            self.config.logger.error(f"Failed to enqueue batch operations: {e}")
            self.config.metrics.update_metric('batch_errors')
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
        queue_key = self.config.redis.get_queue_key(queue_name, priority)
        
        # Initialize Redis client
        redis_client = self.config.redis.get_client()
        
        # Serialize queue data
        serialized_data = self._serialize_entity(queue_data, custom_serializer)
            
        # Add to the queue
        redis_client.lpush(queue_key, serialized_data)
        
        # Register the queue
        redis_client.sadd(self.config.redis.get_registry_key(), queue_key)
    
    @try_catch
    @circuit_breaker(name="queue_status", failure_threshold=3, recovery_timeout=5.0)
    def get_queue_status(self):
        """Get the current status of all registered queues.
        
        Returns:
            dict: A dictionary containing the status of all queues with counts
                and additional metadata.
        """
        status = {}
        redis_client = self.config.redis.get_client()
        
        # Get all registered queues
        registered_queues = redis_client.smembers(self.config.redis.get_registry_key())
        string_queues = set()
        for queue in registered_queues:
            if isinstance(queue, bytes):
                string_queues.add(queue.decode())
            else:
                string_queues.add(queue)
        
        # Get item counts for each queue
        for queue_name in string_queues:
            count = redis_client.llen(queue_name)
            status[queue_name] = count
        
        # Add failure queue count
        failures_key = f"{self.config.redis.key_prefix}failures"
        status[failures_key] = redis_client.llen(failures_key)
        
        # Add system errors count
        system_errors_key = f"{self.config.redis.key_prefix}system_errors"
        status[system_errors_key] = redis_client.llen(system_errors_key)
        
        # Calculate total items
        total_items = sum(count for queue_name, count in status.items())
        
        # Get metrics
        metrics = self.config.metrics.get_metrics()
        
        # Add metadata as a separate dictionary
        metadata = {
            "total_items": total_items,
            "metrics": metrics,
            "status_time": time.time()
        }
        
        # Return a combined dict with both queue statuses and metadata
        result = {**status, **metadata}
        return result
    
    @circuit_breaker(name="queue_purge", failure_threshold=5, recovery_timeout=30.0)
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
        redis_client = self.config.redis.get_client()
        queue_key = self.config.redis.get_queue_key(queue_name, priority)
        
        # Get the current length
        count = redis_client.llen(queue_key)
        
        # Delete the queue
        redis_client.delete(queue_key)
        
        # Report the purge
        self.config.logger.info(f"Purged {count} items from queue {queue_name} with priority {priority}")
        
        return count