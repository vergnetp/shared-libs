import json
import time
import random
import asyncio
from typing import Any, Dict, List, Optional, Union, Callable

from .queue_config import QueueConfig

class QueueWorker:
    """
    Worker for processing queued operations - started at app startup.
    
    The QueueWorker maintains a configurable number of worker tasks that
    continuously process items from the queue according to their priority.
    It handles retries, timeouts, and failure scenarios, ensuring reliable
    execution of queued operations.
    
    Features:
        - Priority-based processing (high, normal, low)
        - Configurable retry handling with backoff
        - Timeout management for long-running operations
        - Callbacks for success and failure scenarios
        - Graceful shutdown handling
    
    Args:
        config (QueueConfig): Configuration for queue operations
        max_workers (int): Maximum number of concurrent worker tasks. Defaults to 5
        work_timeout (int): the number of seconds after which we terminate teh worker, even if still working. Defaults to 30

    """
    def __init__(self, config: QueueConfig, max_workers=5, work_timeout=30.0):
        """Initialize the queue worker."""
        self.config = config
        self.max_workers = max_workers
        self.work_timeout = work_timeout
        self.running = False
        self.tasks = []
        
    async def start(self):
        """Start processing the queue with worker tasks."""
        if self.running:
            return
            
        self.running = True
        
        # Start worker tasks
        for i in range(self.max_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self.tasks.append(task)
        
        self.config.logger.info("Queue workers started", worker_count=self.max_workers)
            
    async def stop(self):
        """Stop queue processing gracefully."""
        self.running = False
        
        # Wait for tasks to complete with proper error handling
        if self.tasks:
            try:
                # Important: Use asyncio.shield to prevent cancellation
                # and explicitly handle tasks in the current loop
                current_loop = asyncio.get_running_loop()
                
                # For each task, ensure it's in the current loop or transfer it
                safe_tasks = []
                for task in self.tasks:
                    # Only gather tasks from the current loop
                    if task._loop is current_loop:
                        safe_tasks.append(task)
                    else:
                        # Log tasks on different loops
                        self.config.logger.warning(
                            f"Task {task} is on a different event loop and cannot be gathered"
                        )
                
                # Only gather tasks if there are any safe ones
                if safe_tasks:
                    await asyncio.gather(*safe_tasks, return_exceptions=True)
            except Exception as e:
                self.config.logger.error(f"Error stopping worker", error=str(e))
                
            # Clear task list
            self.tasks = []
            
        self.config.logger.info("Queue workers stopped")
            
    async def _worker_loop(self, worker_id: int):
        """Main worker loop for processing queue items."""
        self.config.logger.info("Worker started", 
                    worker_id=worker_id, 
                    max_workers=self.max_workers)
        
        try:
            while self.running:
                # Process one item
                processed = await self._process_queue_item(worker_id)
                
                # Sleep briefly if no item was processed
                if not processed:
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.config.logger.warning("Worker cancelled", worker_id=worker_id)
        except Exception as e:
            self.config.logger.error("Worker loop error",
                        worker_id=worker_id,
                        error_type=type(e).__name__,
                        error_message=e.to_string() if hasattr(e, 'to_string') else str(e))
        finally:
            self.config.logger.info("Worker stopped", worker_count=len(self.tasks))
    
    async def _process_queue_item(self, worker_id: int) -> bool:
        """Process a single item from the queue."""
        # *** Use synchronous Redis client - KEY CHANGE ***
        redis = self.config._ensure_redis_sync()
        
        # Get all registered queues
        registered_queues = redis.smembers(self.config.registry_key)
        
        # Group by priority
        high_prefix_bytes = self.config.queue_prefixes['high'].encode()
        normal_prefix_bytes = self.config.queue_prefixes['normal'].encode()
        low_prefix_bytes = self.config.queue_prefixes['low'].encode()
        
        # Group queues by their prefix - handle both string and bytes queue names
        high_queues = []
        normal_queues = []
        low_queues = []
        
        for q in registered_queues:
            q_str = q.decode() if isinstance(q, bytes) else q
            q_bytes = q if isinstance(q, bytes) else q.encode()
            
            if q_str.startswith(self.config.queue_prefixes['high']):
                high_queues.append(q_bytes)
            elif q_str.startswith(self.config.queue_prefixes['normal']):
                normal_queues.append(q_bytes)
            elif q_str.startswith(self.config.queue_prefixes['low']):
                low_queues.append(q_bytes)
        
        # Check queues in priority order
        for queue in [*high_queues, *normal_queues, *low_queues]:
            # Try to peek at the next item without removing it
            next_item_data = redis.lindex(queue, -1)
            
            if not next_item_data:
                continue
                
            try:
                # Parse the item to check next_retry_time
                next_item = json.loads(next_item_data)
                
                # Skip if it's not time to retry yet
                if "next_retry_time" in next_item and next_item["next_retry_time"] > time.time():
                    continue
                    
                # It's time to process this item, get it from the queue
                # Using sync method with timeout (brpop still works in synchronous Redis)
                result = redis.brpop([queue], timeout=0.5)
                
                if not result:
                    # Something else grabbed it or it disappeared
                    continue
                    
                _, item_data = result
                
                # Process the item
                await self._handle_queue_item(worker_id, queue, item_data)
                
                return True
                    
            except json.JSONDecodeError:
                # Get the item to remove it from the queue
                result = redis.brpop([queue], timeout=0.5)
                if result:
                    _, item_data = result
                    self.config.logger.error("Invalid JSON in queue")
                    # Ensure the system_errors_queue is in bytes
                    system_errors_queue = self.config.queue_keys['system_errors']
                    if not isinstance(system_errors_queue, bytes):
                        system_errors_queue = system_errors_queue.encode()
                    redis.lpush(system_errors_queue, item_data)
                return True
                
        # No item processed
        return False
 
    async def _handle_queue_item(self, worker_id: int, queue: bytes, item_data: bytes) -> bool:
        """
        Handle processing of a queue item.
        
        Args:
            worker_id: ID of the worker
            queue: Queue name (as bytes)
            item_data: Raw item data
                
        Returns:
            True if processing completed, False otherwise
        """
        redis = self.config._ensure_redis_sync()
        
        # Setup outside try block - these will be used in exception handling
        start_time = time.time()
        operation_id = "unknown"  # Default value
        success = False
        
        try:
            # Parse the item
            item = json.loads(item_data)
            entity = item["entity"]
            
            # Add debug logging
            operation_id = item.get('operation_id', 'unknown')
            self.config.logger.debug("Processing queued item", operation_id=operation_id, timeout=item.get('timeout'), worker_id=worker_id)
            
            # Check if it's a legacy queue item or callback-based
            if "metadata" in item:
                # Legacy queue item
                metadata = item["metadata"]
                processor_name = item["processor"]
                processor_module = item["processor_module"]
                
                # Find the processor function
                processor = self.config.operations_registry.get(
                    metadata.get("queue_name")
                )
            else:
                # Callback-based item
                processor_name = item["processor"]
                processor_module = item["processor_module"]
                
                # Find the processor function
                processor = self.config.operations_registry.get(
                    f"{processor_module}.{processor_name}" if processor_module else processor_name
                )
            
            if not processor and processor_module:
                # Try to import the processor
                try:
                    module = __import__(processor_module, fromlist=[processor_name])
                    processor = getattr(module, processor_name)
                    # Register for future use
                    if processor:
                        self.config.operations_registry[
                            f"{processor_module}.{processor_name}"
                        ] = processor
                except (ImportError, AttributeError) as e:
                    self.config.logger.error(
                        "Error importing processor", processor_module=processor_module, processor_name=processor_name, error=str(e)
                    )
            
            if not processor:
                # Cannot find processor - move to system errors
                self.config.logger.error("No processor found for item", operation_id=operation_id, worker_id=worker_id)
                # Ensure system_errors_queue is in bytes
                system_errors_queue = self.config.queue_keys['system_errors']
                if not isinstance(system_errors_queue, bytes):
                    system_errors_queue = system_errors_queue.encode()
                redis.lpush(system_errors_queue, item_data)
                return True
            
            # Check if the item has a timeout and this isn't the first attempt
            if "timeout" in item and item["timeout"] is not None:
                # If this is the first attempt, record the start time
                if "first_attempt_time" not in item:
                    item["first_attempt_time"] = time.time()
                    self.config.logger.debug("Setting first_attempt_time for item", operation_id=operation_id, worker_id=worker_id)
                
                # Debug logging for timeout check
                current_time = time.time()
                elapsed_time = current_time - item["first_attempt_time"]
                timeout_value = item["timeout"]
                self.config.logger.debug(
                    "Item elapsed time check", elapsed_time=elapsed_time, timeout=timeout_value, operation_id=operation_id, worker_id=worker_id
                )
                
                # Check if total timeout has been reached
                if elapsed_time > item["timeout"]:

                    self.config.update_metric('timeouts')

                    # Add failure reason
                    item["failure_reason"] = f"Total timeout reached: {elapsed_time}s > {timeout_value}s"
                    
                    self.config.logger.info(
                        "Item reached timeout", elapsed_time=elapsed_time, timeout=timeout_value, operation_id=operation_id, worker_id=worker_id
                    )
                    
                    # Handle callbacks for failure if present
                    if "on_failure" in item and item["on_failure"]:
                        await self._execute_callback(
                            item["on_failure"],
                            item.get("on_failure_module"),
                            {
                                "entity": entity,
                                "error": "Operation timed out after total retry period",
                                "operation_id": item.get("operation_id")
                            }
                        )
                    
                    # Update metrics for timeout
                    self.config.update_metric('timeouts')
                    
                    # Move to failures queue - ensure failures_queue is in bytes
                    failures_queue = self.config.queue_keys['failures']
                    if not isinstance(failures_queue, bytes):
                        failures_queue = failures_queue.encode()
                    
                    # Serialize item for storage
                    item_json = json.dumps(item, default=str)
                    redis.lpush(failures_queue, item_json.encode())
                    
                    self.config.logger.debug(
                        "Moved item to failures queue", timeout=timeout_value, operation_id=operation_id, worker_id=worker_id, failure_queue=self.config.queue_keys['failures']
                    )
                    
                    return True
            
            # Process the item with timeout
            try:
                # This inner try is specifically for the processor execution
                result = await asyncio.wait_for(processor(entity), timeout=self.work_timeout)
                
                # Update success metrics
                self.config.update_metric('processed')
                
                # Check if it's a callback-based item
                if "on_success" in item and item["on_success"]:
                    # Execute success callback
                    await self._execute_callback(
                        item["on_success"],
                        item.get("on_success_module"),
                        {
                            "entity": entity,
                            "result": result,
                            "operation_id": item.get("operation_id")
                        }
                    )
                
                self.config.logger.info("Worker processed item successfully", operation_id=operation_id, worker_id=worker_id)
                success = True
                return True
                    
            except asyncio.TimeoutError:
                # Process execution timed out - handle retry
                self.config.logger.warning(
                    "Process execution timed out", work_timeout=self.work_timeout, operation_id=operation_id, worker_id=worker_id
                )
                
                # Update timeout metrics
                self.config.update_metric('timeouts')
                
                # Handle like other exceptions - increment attempt count
                raise  # Re-raise to be caught by outer exception handler
                    
            except Exception as e:
                # Processor execution failed - re-raise to be caught by outer handler
                self.config.logger.error(
                    "Process execution failed", error=str(e), operation_id=operation_id, worker_id=worker_id
                )
                raise
                
        except Exception as e:
            # Increment attempt count
            if 'item' in locals():
                item["attempts"] = item.get("attempts", 0) + 1
                
                # If this is the first attempt with a timeout, record the start time
                if "timeout" in item and item["timeout"] is not None and "first_attempt_time" not in item:
                    item["first_attempt_time"] = time.time()
                
                # Check if max attempts reached
                if item["attempts"] >= item.get("max_attempts", 5):

                    self.config.update_metric('failed')

                    # Add failure reason
                    item["failure_reason"] = e.to_string() if hasattr(e, "to_string") else str(e)
                    
                    # Update failure metrics
                    self.config.update_metric('failed')
                    
                    # Handle callbacks for failure if present
                    if "on_failure" in item and item["on_failure"]:
                        await self._execute_callback(
                            item["on_failure"],
                            item.get("on_failure_module"),
                            {
                                "entity": entity if 'entity' in locals() else None,
                                "error": e.to_string() if hasattr(e, "to_string") else str(e),
                                "operation_id": item.get("operation_id")
                            }
                        )
                    
                    # Move to failures queue - ensure failures_queue is in bytes
                    failures_queue = self.config.queue_keys['failures']
                    if not isinstance(failures_queue, bytes):
                        failures_queue = failures_queue.encode()
                    
                    redis.lpush(failures_queue, json.dumps(item, default=str).encode())
                    self.config.logger.error(
                        "Item moved to failures queue", operation_id=operation_id, worker_id=worker_id, 
                        failure_queue=self.config.queue_keys['failures'], 
                        error=e.to_string() if hasattr(e, "to_string") else str(e)
                    )
                else:
                    # Calculate next retry time using delays array
                    if "delays" in item:
                        # Use the stored delays array with bounds checking
                        index = min(item["attempts"] - 1, len(item["delays"]) - 1)
                        delay = item["delays"][index]
                        
                        # Add jitter (±10%)
                        jitter = random.uniform(0.9, 1.1)
                        retry_delay = delay * jitter
                    else:
                        # Legacy exponential backoff
                        retry_delay = min(30, 2 ** item["attempts"])
                    
                    # Set next retry time
                    item["next_retry_time"] = time.time() + retry_delay
                    
                    # Update retry metrics
                    self.config.update_metric('retried')
                    
                    # Check if total timeout would be exceeded
                    if ("timeout" in item and item["timeout"] is not None and 
                        "first_attempt_time" in item and 
                        item["next_retry_time"] - item["first_attempt_time"] > item["timeout"]):
                        
                        # Add failure reason
                        item["failure_reason"] = "Total timeout would be exceeded by next retry"
                        
                        # Update timeout metrics
                        self.config.update_metric('timeouts')
                        
                        # Handle callbacks for failure if present
                        if "on_failure" in item and item["on_failure"]:
                            await self._execute_callback(
                                item["on_failure"],
                                item.get("on_failure_module"),
                                {
                                    "entity": entity if 'entity' in locals() else None,
                                    "error": "Operation timed out after total retry period",
                                    "operation_id": item.get("operation_id")
                                }
                            )
                        
                        # Move to failures queue
                        failures_queue = self.config.queue_keys['failures']
                        if not isinstance(failures_queue, bytes):
                            failures_queue = failures_queue.encode()
                        
                        redis.lpush(failures_queue, json.dumps(item, default=str).encode())
                        self.config.logger.error(
                            "Item would exceed timeout, moved to failures queue", operation_id=operation_id, worker_id=worker_id, failure_queue=self.config.queue_keys['failures']
                        )
                    else:
                        # Requeue with the updated next retry time
                        self.config.logger.warning(
                            "Item requeued after error", operation_id=operation_id, worker_id=worker_id, attempt_nb=item['attempts'], error=e.to_string() if hasattr(e, "to_string") else str(e)
                        )
                        
                        # Add back to queue
                        redis.lpush(queue, json.dumps(item, default=str).encode())
                
                return True
            else:
                # Handle case where item is not available (e.g., JSON parse error)
                self.config.logger.error("Error processing item from queue", error=str(e), worker_id=worker_id)
                
                # Move to system errors queue
                system_errors_queue = self.config.queue_keys['system_errors']
                if not isinstance(system_errors_queue, bytes):
                    system_errors_queue = system_errors_queue.encode()
                
                redis.lpush(system_errors_queue, item_data)
                return True
                
        finally:
            # Track processing time for metrics
            process_time = time.time() - start_time
            
            if success:
                # Only update average processing time for successful operations
                self.config.update_metric('avg_process_time', process_time)
                
            # Log completion regardless of outcome
            self.config.logger.debug(f"Item processing took {process_time:.2f}s", 
                                success=success,
                                operation_id=operation_id, 
                                worker_id=worker_id)

    async def _execute_callback(self, callback_name, callback_module, data):
        """Execute a callback function."""
        try:
            # Check if callback is already registered
            callback_key = self.config.get_callback_key(callback_name, callback_module)
            callback = self.config.callbacks_registry.get(callback_key)
            
            if not callback and callback_module:
                # Try to import the callback
                try:
                    module = __import__(callback_module, fromlist=[callback_name])
                    callback = getattr(module, callback_name)
                    
                    # Register for future use
                    if callback:
                        self.config.callbacks_registry[callback_key] = callback
                except (ImportError, AttributeError) as e:
                    self.config.logger.error(
                        "Error importing callback", callback_module=callback_module, callback_name=callback_name, error=str(e)
                    )
            
            if not callback:
                self.config.logger.error("Callback not found", callback_module=callback_module, callback_name=callback_name)
                return None
                
            # Execute the callback
            if asyncio.iscoroutinefunction(callback):
                return await callback(data)
            else:
                return callback(data)
                
        except Exception as e:
            self.config.logger.error("Error executing callback",  callback_module=callback_module, callback_name=callback_name, error=e.to_string() if hasattr(e, "to_string") else str(e))
            return None