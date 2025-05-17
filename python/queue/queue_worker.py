import json
import time
import random
import asyncio
import threading
import concurrent.futures
from typing import Any, Dict, List, Optional, Union, Callable

from .queue_config import QueueConfig
from ..resilience import with_timeout, circuit_breaker, retry_with_backoff

class ThreadPoolExhaustionError(Exception):
    """Error raised when the thread pool is exhausted and cannot accept new tasks."""
    pass

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
        - Timeout management for async operations
        - Callbacks for success and failure scenarios
        - Graceful shutdown handling
    
    Args:
        config (QueueConfig): Configuration for queue operations
        max_workers (int): Maximum number of concurrent worker tasks. Defaults to 5
        work_timeout (int): Timeout in seconds for async processors. Defaults to 30
        thread_pool_size (int): Size of thread pool for sync processors. Defaults to 20
    """
    def __init__(self, config: QueueConfig, max_workers=5, work_timeout=30.0, thread_pool_size=20):
        """Initialize the queue worker."""
        self.config = config
        self.max_workers = max_workers
        self.work_timeout = work_timeout
        self.running = False
        self.tasks = []
        
        # Create a thread pool for sync functions
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=thread_pool_size,
            thread_name_prefix="queue_worker_sync_"
        )
        
        # Thread pool metrics
        self._thread_pool_size = thread_pool_size
        self._thread_metrics_lock = threading.Lock()
        
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
        
        # Improved task cleanup to prevent "Task was destroyed but is pending" warnings
        if self.tasks:
            try:
                # Cancel all tasks explicitly
                for task in self.tasks:
                    if not task.done():
                        task.cancel()
                
                # Wait for a moment to allow tasks to process cancellation
                await asyncio.sleep(0.5)
                
                # Create a list of tasks that are still not done
                pending_tasks = [t for t in self.tasks if not t.done()]
                
                # If we have pending tasks, wait for them with a timeout
                if pending_tasks:
                    # Use wait with a timeout instead of gather to prevent hanging
                    done, pending = await asyncio.wait(
                        pending_tasks, 
                        timeout=2.0,
                        return_when=asyncio.ALL_COMPLETED
                    )
                    
                    # If we still have pending tasks, log a warning
                    if pending:
                        self.config.logger.warning(
                            f"Some worker tasks ({len(pending)}) could not be stopped gracefully"
                        )
            except Exception as e:
                self.config.logger.error(f"Error stopping worker", error=str(e))
            finally:
                # Clear task list
                self.tasks = []
        
        # Shutdown thread pool
        try:
            self._thread_pool.shutdown(wait=False)
        except Exception as e:
            self.config.logger.error(f"Error shutting down thread pool", error=str(e))
        
        self.config.logger.info("Queue workers stopped")
            
    @with_timeout(default_timeout=60.0)  
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
    
    @circuit_breaker(name="process_queue", failure_threshold=5, recovery_timeout=10.0)
    async def _process_queue_item(self, worker_id: int) -> bool:
        """Process a single item from the queue."""
        # Use synchronous Redis client
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
                    system_errors_queue = self._get_bytes_key('system_errors')
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
            self.config.logger.debug("Processing queued item", 
                          operation_id=operation_id, 
                          timeout=item.get('timeout'), 
                          worker_id=worker_id)
            
            # Find the processor function
            processor = self._find_processor(
                item["processor"], 
                item.get("processor_module")
            )
            
            if not processor:
                # Cannot find processor - move to system errors
                self.config.logger.error("No processor found for item", 
                               operation_id=operation_id, 
                               worker_id=worker_id)
                system_errors_queue = self._get_bytes_key('system_errors')
                redis.lpush(system_errors_queue, item_data)
                return True
            
            # Initialize timeout tracking if needed
            if "timeout" in item and "first_attempt_time" not in item:
                item["first_attempt_time"] = time.time()
            
            # Check if total timeout already exceeded
            if "timeout" in item and "first_attempt_time" in item:
                elapsed = time.time() - item["first_attempt_time"]
                if elapsed > item["timeout"]:
                    return await self._handle_timeout_exceeded(item, entity, operation_id, redis)
            
            # Calculate effective timeout for async processors
            effective_timeout = self._calculate_effective_timeout(item)
            
            # Execute processor with appropriate handling based on type
            try:
                if asyncio.iscoroutinefunction(processor):
                    # Async processor - apply timeout
                    result = await asyncio.wait_for(
                        processor(entity), 
                        timeout=effective_timeout
                    )
                else:
                    # Sync processor - run in thread pool without timeout
                    try:
                        result = await self._execute_sync_processor(
                            processor, entity, operation_id
                        )
                    except ThreadPoolExhaustionError:
                        # Thread pool exhausted - handle specially
                        return await self._handle_pool_exhaustion(
                            item, entity, operation_id, queue, redis, worker_id
                        )
                
                # Process was successful
                self.config.update_metric('processed')
                
                # Execute success callback if present
                if "on_success" in item and item["on_success"]:
                    await self._execute_callback(
                        item["on_success"],
                        item.get("on_success_module"),
                        {
                            "entity": entity,
                            "result": result,
                            "operation_id": operation_id
                        }
                    )
                
                self.config.logger.info("Worker processed item successfully", 
                             operation_id=operation_id, 
                             worker_id=worker_id)
                success = True
                return True
                    
            except asyncio.TimeoutError:
                # Only async processors can time out
                return await self._handle_execution_timeout(
                    item, entity, operation_id, effective_timeout, queue, redis, worker_id
                )
                
        except Exception as e:
            # Handle general processing error
            return await self._handle_processing_exception(
                e, item if 'item' in locals() else None,
                entity if 'entity' in locals() else None,
                operation_id, worker_id, queue, redis, item_data
            )
                
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

    def _find_processor(self, processor_name: str, processor_module: Optional[str] = None) -> Optional[Callable]:
        """
        Find the processor function by name and module.
        
        Args:
            processor_name: Name of the processor function
            processor_module: Optional module name
            
        Returns:
            Processor function or None if not found
        """
        # Check in operations registry first
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
                    "Error importing processor", 
                    processor_module=processor_module, 
                    processor_name=processor_name, 
                    error=str(e)
                )
        
        return processor

    def _calculate_effective_timeout(self, item: Dict[str, Any]) -> float:
        """
        Calculate the effective timeout for an async processor execution.
        
        Args:
            item: Queue item with timeout information
            
        Returns:
            Effective timeout in seconds
        """
        # Default to worker timeout
        effective_timeout = self.work_timeout
        
        # If item has a timeout and first_attempt_time, calculate remaining time
        if "timeout" in item and item["timeout"] is not None and "first_attempt_time" in item:
            remaining_timeout = item["timeout"] - (time.time() - item["first_attempt_time"])
            if remaining_timeout > 0:
                # Use the smaller of worker timeout and remaining time
                effective_timeout = min(effective_timeout, remaining_timeout)
                
        return effective_timeout
    
    def _get_bytes_key(self, key_name: str) -> bytes:
        """
        Get a queue key as bytes.
        
        Args:
            key_name: Name of the key in config.queue_keys
            
        Returns:
            Key as bytes
        """
        queue_key = self.config.queue_keys[key_name]
        if not isinstance(queue_key, bytes):
            queue_key = queue_key.encode()
        return queue_key
    
    async def _execute_sync_processor(self, processor: Callable, entity: Dict[str, Any], 
                                    operation_id: str) -> Any:
        """
        Execute a synchronous processor in the thread pool.
        
        Args:
            processor: Sync processor function
            entity: Entity to process
            operation_id: Operation ID for logging
            
        Returns:
            Result from the processor
            
        Raises:
            ThreadPoolExhaustionError: If thread pool is exhausted
            Exception: Other errors from processor execution
        """
        # Track metrics for sync processors
        start_time = time.time()
        
        try:
            # Create a Future that can be awaited
            loop = asyncio.get_running_loop()
            future_submit = loop.create_future()
            
            # Try to submit to thread pool with a short queue timeout
            def submit_to_pool():
                try:
                    # This executes in a very short-lived thread
                    future = self._thread_pool.submit(processor, entity)
                    loop.call_soon_threadsafe(
                        future_submit.set_result, future
                    )
                except Exception as e:
                    loop.call_soon_threadsafe(
                        future_submit.set_exception, e
                    )
            
            # Quick thread to check if pool accepts submission
            submit_thread = threading.Thread(target=submit_to_pool)
            submit_thread.daemon = True
            submit_thread.start()
            
            # Wait briefly for submission to succeed (100ms)
            try:
                # Just wait to see if we can get a thread quickly
                task_future = await asyncio.wait_for(future_submit, timeout=0.1)
                # If we get here, we got a thread! Now wait for the actual task
                result = await asyncio.wrap_future(task_future)
                
                # Update sync processor metrics
                self._update_thread_metrics(start_time)
                
                return result
            except asyncio.TimeoutError:
                # Could not get a thread quickly - pool is exhausted
                self.config.logger.warning(
                    "Thread pool exhausted, could not submit task", 
                    operation_id=operation_id
                )
                self.config.update_metric('thread_pool_exhaustion')
                raise ThreadPoolExhaustionError("Thread pool exhausted, task rejected")
                
        except ThreadPoolExhaustionError:
            # Propagate pool exhaustion
            raise
        except Exception as e:
            # Handle other errors
            self.config.logger.error(
                f"Error in sync processor execution: {e}", 
                operation_id=operation_id
            )
            raise
    
    def _update_thread_metrics(self, start_time: float):
        """
        Update metrics related to thread pool usage.
        
        Args:
            start_time: Start time of the processor execution
        """
        process_time = time.time() - start_time
        
        with self._thread_metrics_lock:
            # Update average processing time
            total_time = self.config._metrics.get('total_thread_time', 0) + process_time
            count = self.config._metrics.get('thread_tasks_completed', 0) + 1
            self.config._metrics['total_thread_time'] = total_time
            self.config._metrics['thread_tasks_completed'] = count
            self.config._metrics['avg_thread_processing_time'] = total_time / count
            
            # Update current thread usage approximation
            active_threads = self._thread_pool_size - self._thread_pool._work_queue.qsize()
            self.config._metrics['thread_pool_usage'] = active_threads
            
            # Update max thread usage
            if active_threads > self.config._metrics.get('thread_pool_max_usage', 0):
                self.config._metrics['thread_pool_max_usage'] = active_threads
                
            # Calculate utilization percentage
            utilization = (active_threads / self._thread_pool_size) * 100
            self.config._metrics['thread_pool_utilization'] = utilization
    
    async def _handle_pool_exhaustion(self, item: Dict[str, Any], entity: Dict[str, Any],
                                   operation_id: str, queue: bytes, redis: Any,
                                   worker_id: int) -> bool:
        """
        Handle thread pool exhaustion for a sync processor.
        
        Args:
            item: Queue item
            entity: Entity to process
            operation_id: Operation ID for logging
            queue: Queue name as bytes
            redis: Redis client
            worker_id: Worker ID
            
        Returns:
            True if handling is complete
        """
        # Increment attempt count
        item["attempts"] = item.get("attempts", 0) + 1
        
        # Check if max attempts reached
        if item["attempts"] >= item.get("max_attempts", 5):
            # Add failure reason
            item["failure_reason"] = "Thread pool exhaustion after max retries"
            
            # Move to failures queue
            failures_queue = self._get_bytes_key('failures')
            redis.lpush(failures_queue, json.dumps(item, default=str).encode())
            
            # Execute failure callback if present
            if "on_failure" in item and item["on_failure"]:
                await self._execute_callback(
                    item["on_failure"],
                    item.get("on_failure_module"),
                    {
                        "entity": entity,
                        "error": "Thread pool exhaustion after max retries",
                        "operation_id": operation_id
                    }
                )
            
            self.config.logger.error(
                "Item moved to failures queue due to thread pool exhaustion", 
                operation_id=operation_id, 
                worker_id=worker_id,
                attempts=item["attempts"]
            )
        else:
            # Calculate next retry time using delays array or exponential backoff
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
            if "timeout" in item and item["timeout"] is not None and "first_attempt_time" in item:
                if item["next_retry_time"] - item["first_attempt_time"] > item["timeout"]:
                    # Total timeout would be exceeded
                    return await self._handle_would_exceed_timeout(item, entity, operation_id, redis)
            
            # Requeue with the updated next retry time
            self.config.logger.warning(
                "Thread pool exhausted, requeuing item", 
                operation_id=operation_id, 
                worker_id=worker_id, 
                attempt=item["attempts"],
                next_retry=time.strftime('%H:%M:%S', time.localtime(item["next_retry_time"]))
            )
            
            # Add back to queue
            redis.lpush(queue, json.dumps(item, default=str).encode())
        
        return True
    
    async def _handle_timeout_exceeded(self, item: Dict[str, Any], entity: Dict[str, Any],
                                     operation_id: str, redis: Any) -> bool:
        """
        Handle case where total timeout has been exceeded.
        
        Args:
            item: Queue item
            entity: Entity to process
            operation_id: Operation ID
            redis: Redis client
            
        Returns:
            True if handling is complete
        """
        self.config.update_metric('timeouts')

        # Add failure reason
        item["failure_reason"] = "Total timeout reached"
        
        # Execute failure callback if present
        if "on_failure" in item and item["on_failure"]:
            await self._execute_callback(
                item["on_failure"],
                item.get("on_failure_module"),
                {
                    "entity": entity,
                    "error": "Operation timed out after total retry period",
                    "operation_id": operation_id
                }
            )
        
        # Move to failures queue
        failures_queue = self._get_bytes_key('failures')
        redis.lpush(failures_queue, json.dumps(item, default=str).encode())
        
        self.config.logger.debug(
            "Moved item to failures queue due to total timeout", 
            operation_id=operation_id
        )
        
        return True
    
    async def _handle_execution_timeout(self, item: Dict[str, Any], entity: Dict[str, Any],
                                      operation_id: str, effective_timeout: float,
                                      queue: bytes, redis: Any, worker_id: int) -> bool:
        """
        Handle timeout during async processor execution.
        
        Args:
            item: Queue item
            entity: Entity to process
            operation_id: Operation ID
            effective_timeout: Timeout that was applied
            queue: Queue name as bytes
            redis: Redis client
            worker_id: Worker ID
            
        Returns:
            True if handling is complete
        """
        self.config.logger.warning(
            "Async processor execution timed out", 
            work_timeout=effective_timeout, 
            operation_id=operation_id, 
            worker_id=worker_id
        )
        
        # Update timeout metrics
        self.config.update_metric('timeouts')
        
        # Check if max retries reached
        if item.get("attempts", 0) >= item.get("max_attempts", 5) - 1:
            # Add failure reason
            item["failure_reason"] = f"Execution timed out after {effective_timeout}s"
            
            # Move to failures queue
            failures_queue = self._get_bytes_key('failures')
            item_json = json.dumps(item, default=str)
            redis.lpush(failures_queue, item_json.encode())
            
            self.config.logger.debug(
                "Moved timed out item to failures queue", 
                operation_id=operation_id, 
                worker_id=worker_id
            )
            
            return True
        
        # Otherwise handle like regular exception - increment and requeue
        item["attempts"] = item.get("attempts", 0) + 1
        
        # Calculate next retry time using delays array or exponential backoff
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
        
        # Check if next retry would exceed total timeout
        if "timeout" in item and item["timeout"] is not None and "first_attempt_time" in item:
            if item["next_retry_time"] - item["first_attempt_time"] > item["timeout"]:
                return await self._handle_would_exceed_timeout(item, entity, operation_id, redis)
        
        # Requeue with the updated next retry time
        self.config.logger.warning(
            "Item requeued after timeout", 
            operation_id=operation_id, 
            worker_id=worker_id, 
            attempt=item['attempts']
        )
        
        # Add back to queue
        redis.lpush(queue, json.dumps(item, default=str).encode())
        return True
    
    async def _handle_would_exceed_timeout(self, item: Dict[str, Any], entity: Dict[str, Any],
                                         operation_id: str, redis: Any) -> bool:
        """
        Handle case where next retry would exceed total timeout.
        
        Args:
            item: Queue item
            entity: Entity to process
            operation_id: Operation ID
            redis: Redis client
            
        Returns:
            True if handling is complete
        """
        # Add failure reason
        item["failure_reason"] = "Total timeout would be exceeded by next retry"
        
        # Update timeout metrics
        self.config.update_metric('timeouts')
        
        # Execute failure callback if present
        if "on_failure" in item and item["on_failure"]:
            await self._execute_callback(
                item["on_failure"],
                item.get("on_failure_module"),
                {
                    "entity": entity,
                    "error": "Operation timed out after total retry period",
                    "operation_id": operation_id
                }
            )
        
        # Move to failures queue
        failures_queue = self._get_bytes_key('failures')
        redis.lpush(failures_queue, json.dumps(item, default=str).encode())
        
        self.config.logger.error(
            "Item would exceed timeout, moved to failures queue", 
            operation_id=operation_id
        )
        
        return True
    
    async def _handle_processing_exception(self, exception: Exception, 
                                        item: Optional[Dict[str, Any]], 
                                        entity: Optional[Dict[str, Any]],
                                        operation_id: str, worker_id: int, 
                                        queue: bytes, redis: Any,
                                        item_data: Optional[bytes] = None) -> bool:
        """
        Handle general processing exception.
        
        Args:
            exception: The exception that occurred
            item: Queue item if available
            entity: Entity to process if available
            operation_id: Operation ID
            worker_id: Worker ID
            queue: Queue name as bytes
            redis: Redis client
            item_data: Raw item data (used if item parsing failed)
            
        Returns:
            True if handling is complete
        """
        if item:
            # Increment attempt count
            item["attempts"] = item.get("attempts", 0) + 1
            
            # If this is the first attempt with a timeout, record the start time
            if "timeout" in item and item["timeout"] is not None and "first_attempt_time" not in item:
                item["first_attempt_time"] = time.time()
            
            # Check if max attempts reached
            if item["attempts"] >= item.get("max_attempts", 5):
                # Add failure reason
                item["failure_reason"] = exception.to_string() if hasattr(exception, "to_string") else str(exception)
                
                # Update failure metrics
                self.config.update_metric('failed')
                
                # Execute failure callback if present
                if "on_failure" in item and item["on_failure"]:
                    await self._execute_callback(
                        item["on_failure"],
                        item.get("on_failure_module"),
                        {
                            "entity": entity,
                            "error": item["failure_reason"],
                            "operation_id": operation_id
                        }
                    )
                
                # Move to failures queue
                failures_queue = self._get_bytes_key('failures')
                redis.lpush(failures_queue, json.dumps(item, default=str).encode())
                
                self.config.logger.error(
                    "Item moved to failures queue after max retries", 
                    operation_id=operation_id, 
                    worker_id=worker_id,
                    error=item["failure_reason"]
                )
            else:
                # Calculate next retry time using delays array or exponential backoff
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
                    
                    return await self._handle_would_exceed_timeout(item, entity, operation_id, redis)
                
                # Requeue with the updated next retry time
                self.config.logger.warning(
                    "Item requeued after error", 
                    operation_id=operation_id, 
                    worker_id=worker_id, 
                    attempt=item['attempts'],
                    error=str(exception)
                )
                
                # Add back to queue
                redis.lpush(queue, json.dumps(item, default=str).encode())
                
            return True
        else:
            # Handle case where item is not available (e.g., JSON parse error)
            self.config.logger.error(
                "Error processing item from queue", 
                error=str(exception), 
                worker_id=worker_id
            )
            
            # Move to system errors queue
            system_errors_queue = self._get_bytes_key('system_errors')
            
            redis.lpush(system_errors_queue, item_data)
            return True
            
    @retry_with_backoff(max_retries=3, base_delay=0.1, exceptions=(ImportError, AttributeError))
    async def _execute_callback(self, callback_name, callback_module, data):
        """Execute a callback function."""
        try:
            # Check if callback is already registered
            callback_key = self.config.get_callback_key(callback_name, callback_module)
            callback = self.config.callbacks_registry.get(callback_key)
            
            if not callback and callback_module:
                # Try to import the callback
                module = __import__(callback_module, fromlist=[callback_name])
                callback = getattr(module, callback_name)
                
                # Register for future use
                if callback:
                    self.config.callbacks_registry[callback_key] = callback
            
            if not callback:
                self.config.logger.error("Callback not found", 
                               callback_module=callback_module, 
                               callback_name=callback_name)
                return None
                
            # Execute the callback
            if asyncio.iscoroutinefunction(callback):
                return await callback(data)
            else:
                # For sync callbacks, run in thread pool to avoid blocking
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, lambda: callback(data))
                
        except Exception as e:
            self.config.logger.error("Error executing callback", 
                          callback_module=callback_module, 
                          callback_name=callback_name, 
                          error=e.to_string() if hasattr(e, "to_string") else str(e))
            return None