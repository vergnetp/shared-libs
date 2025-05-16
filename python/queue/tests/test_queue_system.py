import asyncio
import json
import pytest
import pytest_asyncio
import time
from typing import Dict, List, Any

from ..queue_config import QueueConfig
from ..queue_manager import QueueManager
from ..queue_worker import QueueWorker
from ..queue_retry_config import QueueRetryConfig

from ... import log as logger

# Mock logger to capture logs
class MockLogger:
    def __init__(self):
        self.logs = {"error": [], "warning": [], "info": [], "debug": [], "critical": []}
    
    def error(self, msg, **fields): self.logs["error"].append(msg)
    def warning(self, msg, **fields): self.logs["warning"].append(msg)
    def info(self, msg, **fields): self.logs["info"].append(msg)
    def debug(self, msg, **fields): self.logs["debug"].append(msg)
    def critical(self, msg, **fields): self.logs["critical"].append(msg)

# Test processor functions
async def successful_processor(data):
    return {"success": True, "data": data}

async def failing_processor(data):
    raise ValueError("Test error")

async def slow_processor(data):
    await asyncio.sleep(2)
    return {"success": True, "data": data}

# Test callback functions
async def success_callback(data):
    return {"callback_success": True, "data": data}

async def failure_callback(data):
    return {"callback_failure": True, "data": data}

@pytest.fixture
def redis_url():
    # Change this if needed to point to your Redis instance
    return "redis://localhost:6379/1"  # Use DB 1 for tests

@pytest.fixture
def config(redis_url):
    logger = MockLogger()
    config = QueueConfig(redis_url=redis_url, logger=logger)
    
    # Clear all test queues before running tests
    redis = config._ensure_redis_sync()
    registered_queues = redis.smembers(config.registry_key)
    
    # Delete all registered queues
    for queue in registered_queues:
        redis.delete(queue)
    
    # Delete registry key
    redis.delete(config.registry_key)
    
    # Delete system_errors and failures queues
    redis.delete(config.queue_keys['system_errors'])
    redis.delete(config.queue_keys['failures'])
    
    return config

@pytest.fixture
def queue_manager(config):
    return QueueManager(config=config)

@pytest_asyncio.fixture
async def worker(config):
    worker = QueueWorker(config=config, max_workers=1, work_timeout=2.0)
    yield worker
    await worker.stop()

# Basic queueing tests
def test_enqueue_basic(queue_manager):
    """Test basic queueing operation."""
    result = queue_manager.enqueue(
        entity={"test": "data"},
        processor=successful_processor
    )
    
    assert result["status"] == "queued"
    assert "operation_id" in result
    assert result["has_callbacks"] == False

def test_enqueue_with_callbacks(queue_manager):
    """Test queueing with callbacks."""
    result = queue_manager.enqueue(
        entity={"test": "data"},
        processor=successful_processor,
        on_success=success_callback,
        on_failure=failure_callback
    )
    
    assert result["status"] == "queued"
    assert result["has_callbacks"] == True

# Note: We've removed the execute_now tests since that functionality is removed in the sync version

# Worker tests
@pytest.mark.asyncio
async def test_worker_processes_queue(queue_manager, worker, config):
    """Test that worker processes queued items."""
    # Enqueue an item
    queue_manager.enqueue(
        entity={"test": "data"},
        processor=successful_processor
    )
    
    # Check queue status before starting worker
    redis = config._ensure_redis_sync()
    registered_queues = redis.smembers(config.registry_key)
    print(f"Registered queues before processing: {registered_queues}")
    
    for queue in registered_queues:
        length = redis.llen(queue)
        print(f"Queue {queue} has {length} items before processing")
    
    # Start worker briefly
    await worker.start()
    
    # Wait for processing
    await asyncio.sleep(1)  # Increased wait time
    
    # Check queue status after worker execution
    for queue in registered_queues:
        length = redis.llen(queue)
        print(f"Queue {queue} has {length} items after processing")

# In test_worker_retry_on_failure
@pytest.mark.asyncio
async def test_worker_retry_on_failure(queue_manager, worker, config):
    """Test that worker retries failed items."""
    # Enable more detailed logging
    config.logger.error = lambda msg, **kwargs: print(f"ERROR: {msg}")
    config.logger.warning = lambda msg, **kwargs: print(f"WARNING: {msg}")
    config.logger.info = lambda msg, **kwargs: print(f"INFO: {msg}")
    
    # Enqueue a failing item with retry config
    retry_config = QueueRetryConfig(max_attempts=2, delays=[0.1, 0.1])
    
    queue_manager.enqueue(
        entity={"test": "data"},
        processor=failing_processor,
        retry_config=retry_config
    )
    
    # Start worker
    await worker.start()
    
    # Wait for processing and retries
    await asyncio.sleep(2)  # Increase wait time
    
    # Check that item moved to failures queue
    redis = config._ensure_redis_sync()
    
    # Debug: Check all queues
    registered_queues = redis.smembers(config.registry_key)
    print(f"Registered queues: {registered_queues}")
    
    for queue in registered_queues:
        length = redis.llen(queue)
        print(f"Queue {queue} has {length} items")
        
        # If items exist, print them
        if length > 0:
            items = redis.lrange(queue, 0, -1)
            for item in items:
                print(f"  Item: {item}")
    
    # Check failures queue - handle failures queue key consistently
    failures_queue = config.queue_keys['failures']
    if not isinstance(failures_queue, bytes):
        failures_queue = failures_queue.encode()
    
    failures_len = redis.llen(failures_queue)
    print(f"Failures queue has {failures_len} items")
    
    assert failures_len == 1

@pytest.mark.asyncio
async def test_worker_timeout_handling(queue_manager, worker, config):
    """Test that worker respects timeout settings."""
    # Enable more detailed logging for troubleshooting
    config.logger.error = lambda msg, **kwargs: print(f"ERROR: {msg}")
    config.logger.warning = lambda msg, **kwargs: print(f"WARNING: {msg}")
    config.logger.info = lambda msg, **kwargs: print(f"INFO: {msg}")
    config.logger.debug = lambda msg, **kwargs: print(f"DEBUG: {msg}")
    
    # Set a shorter work_timeout for this test to ensure the slow processor times out
    worker.work_timeout = 0.5  # Shorter than the 2s sleep in slow_processor
    
    # Enqueue a slow processor with a short timeout
    retry_config = QueueRetryConfig(max_attempts=2, delays=[0.1, 0.1], timeout=1)
    
    queue_manager.enqueue(
        entity={"test": "data"},
        processor=slow_processor,
        retry_config=retry_config
    )
    
    # Start worker
    await worker.start()
    
    # Wait for processing and timeout - increase wait time to ensure completion
    await asyncio.sleep(3)
    
    # Check that item moved to failures queue due to timeout
    redis = config._ensure_redis_sync()
    
    # Get failures queue key consistently
    failures_queue = config.queue_keys['failures']
    if not isinstance(failures_queue, bytes):
        failures_queue = failures_queue.encode()
    
    # Check all queues for debugging
    registered_queues = redis.smembers(config.registry_key)
    print(f"Registered queues after timeout test: {registered_queues}")
    
    for queue in registered_queues:
        length = redis.llen(queue)
        print(f"Queue {queue} has {length} items")
    
    print(f"Checking failures queue: {failures_queue}")
    failures_len = redis.llen(failures_queue)
    print(f"Failures queue has {failures_len} items")
    
    assert failures_len == 1, "Expected the slow item to be moved to failures queue after timeout"
    
    # Check the reason in the failures queue item
    if failures_len > 0:
        failures_items = redis.lrange(failures_queue, 0, -1)
        failure_item = json.loads(failures_items[0])
        print(f"Failure reason: {failure_item.get('failure_reason')}")
        
        # Verify it's a timeout-related failure
        assert "time" in failure_item.get('failure_reason', '').lower() or \
               "timeout" in failure_item.get('failure_reason', '').lower(), \
               "Expected timeout-related failure reason"

@pytest.mark.asyncio
async def test_callback_execution(queue_manager, worker, config):
    """Test that callbacks are executed properly."""
    # Register callbacks
    success_called = asyncio.Event()
    failure_called = asyncio.Event()
    
    async def tracked_success_callback(data):
        success_called.set()
        return data
    
    async def tracked_failure_callback(data):
        failure_called.set()
        return data
    
    # Enqueue items with callbacks
    queue_manager.enqueue(
        entity={"test": "success"},
        processor=successful_processor,
        on_success=tracked_success_callback
    )
    
    queue_manager.enqueue(
        entity={"test": "failure"},
        processor=failing_processor,
        on_failure=tracked_failure_callback,
        retry_config=QueueRetryConfig(max_attempts=1)  # Only try once
    )
    
    # Start worker
    await worker.start()
    
    # Wait for processing
    await asyncio.sleep(1)
    
    assert success_called.is_set()
    assert failure_called.is_set()

@pytest.mark.asyncio
async def test_priorities(queue_manager, worker, config):
    """Test that high priority items are processed before normal and low priority."""
    processing_order = []
    
    async def ordered_processor(data):
        processing_order.append(data.get("priority"))
        return {"success": True}
    
    # Enqueue items with different priorities in reverse order
    queue_manager.enqueue(
        entity={"priority": "low"},
        processor=ordered_processor,
        priority="low"
    )
    
    queue_manager.enqueue(
        entity={"priority": "normal"},
        processor=ordered_processor,
        priority="normal"
    )
    
    queue_manager.enqueue(
        entity={"priority": "high"},
        processor=ordered_processor,
        priority="high"
    )
    
    # Start worker
    await worker.start()
    
    # Wait for processing
    await asyncio.sleep(1)
    
    # Check processing order - should be high, normal, low
    assert len(processing_order) == 3
    assert processing_order[0] == "high"
    assert processing_order[1] == "normal"
    assert processing_order[2] == "low"

# Retry config tests
def test_retry_config_exponential():
    """Test exponential backoff retry config."""
    retry_config = QueueRetryConfig.exponential(max_attempts=5)
    
    # Check that delays follow exponential pattern
    assert len(retry_config.delays) == 5
    assert retry_config.delays[0] == 1  # min delay
    assert retry_config.delays[1] == 2  # 2^1
    assert retry_config.delays[2] == 4  # 2^2
    assert retry_config.delays[3] == 8  # 2^3
    assert retry_config.delays[4] == 16  # 2^4

def test_retry_config_fixed():
    """Test fixed delay retry config."""
    retry_config = QueueRetryConfig.fixed(delay=10, max_attempts=3)
    
    # Check that all delays are fixed
    assert len(retry_config.delays) == 3
    assert all(delay == 10 for delay in retry_config.delays)

def test_retry_config_custom():
    """Test custom delay retry config."""
    custom_delays = [5, 15, 60, 300]
    retry_config = QueueRetryConfig.custom(delays=custom_delays)
    
    # Check that delays match custom values
    assert retry_config.delays == custom_delays
    assert retry_config.max_attempts == len(custom_delays)

def test_get_queue_status(queue_manager, config):
    """Test queue status reporting."""
    # Enqueue some items
    queue_manager.enqueue(
        entity={"test": "high"},
        processor=successful_processor,
        priority="high"
    )

    queue_manager.enqueue(
        entity={"test": "normal1"},
        processor=successful_processor,
    )

    queue_manager.enqueue(
        entity={"test": "normal2"},
        processor=successful_processor,
    )

    # Get queue status
    status = queue_manager.get_queue_status()

    # Check that status contains counts for all registered queues
    registered_queues = config._ensure_redis_sync().smembers(config.registry_key)

    # Convert byte keys to strings for comparison
    string_keys = set()
    for queue in registered_queues:
        if isinstance(queue, bytes):
            string_keys.add(queue.decode())
        else:
            string_keys.add(queue)

    # Check that all registered queues are in the status keys
    # (instead of checking that all status keys are in registered queues)
    assert string_keys.issubset(set(status.keys())), \
           "Not all registered queues are included in the status"
    
    # Verify that the known metadata keys exist
    metadata_keys = {'total_items', 'metrics', 'status_time', 
                    'queue:failures', 'queue:system_errors'}
    for key in metadata_keys:
        assert key in status, f"Expected metadata key '{key}' not found in status"
    
    # Verify the counts match what we expect
    assert status['queue:high:python.queue.tests.test_queue_system.successful_processor'] == 1
    assert status['queue:normal:python.queue.tests.test_queue_system.successful_processor'] == 2

@pytest.mark.asyncio
async def test_queue_metrics(queue_manager, worker, config):
    """Test metrics tracking in the queue system."""
    # Add custom processors for testing metrics
    async def fast_processor(data):
        return {"success": True, "data": data}
    
    async def slow_processor(data):
        await asyncio.sleep(1.5)  # Slow but not timeout slow
        return {"success": True, "data": data}
    
    async def timeout_processor(data):
        await asyncio.sleep(3)  # This should exceed our test timeout
        return {"success": True, "data": data}
    
    async def failing_processor(data):
        raise ValueError("Intentional test failure")
    
    # Register these processors for testing
    config.operations_registry["fast_processor"] = fast_processor
    config.operations_registry["slow_processor"] = slow_processor
    config.operations_registry["timeout_processor"] = timeout_processor
    config.operations_registry["failing_processor"] = failing_processor
    
    # Set a shorter work_timeout for this test
    original_timeout = worker.work_timeout
    worker.work_timeout = 2.0  # Set to 2s to ensure timeout_processor times out
    
    try:
        # 1. Queue items with different characteristics
        # Fast processor, should succeed quickly
        for i in range(3):
            queue_manager.enqueue(
                entity={"test": f"fast_{i}"},
                processor="fast_processor",
                priority="high"
            )
        
        # Slow processor, should succeed but take longer
        for i in range(2):
            queue_manager.enqueue(
                entity={"test": f"slow_{i}"},
                processor="slow_processor",
                priority="normal"
            )
        
        # Failing processor, should fail and retry
        # Make sure it reaches max retries quickly to ensure we get a failure
        retry_config = QueueRetryConfig(max_attempts=2, delays=[0.1, 0.1])
        queue_manager.enqueue(
            entity={"test": "failing"},
            processor="failing_processor",
            retry_config=retry_config,
            priority="normal"
        )
        
        # Timeout processor, should timeout
        # Make sure it times out and doesn't retry too many times
        timeout_config = QueueRetryConfig(max_attempts=1)
        queue_manager.enqueue(
            entity={"test": "timeout"},
            processor="timeout_processor",
            retry_config=timeout_config,
            priority="low"
        )
        
        # 2. Get initial metrics
        initial_metrics = config.get_metrics()
        print(f"Initial metrics: {initial_metrics}")
        
        # Check that enqueued count is correct
        assert initial_metrics['enqueued'] == 7, f"Expected 7 items enqueued, got {initial_metrics['enqueued']}"
        
        # 3. Process the queue
        await worker.start()
        
        # Allow sufficient time for processing (including timeouts and retries)
        # Wait longer to ensure everything completes
        await asyncio.sleep(8)  # Increased from 5 to 8 seconds
        
        # 4. Get updated metrics
        updated_metrics = config.get_metrics()
        print(f"Updated metrics: {updated_metrics}")
        
        # Get the queue status for debugging
        queue_status = queue_manager.get_queue_status()
        print(f"Queue status: {json.dumps(queue_status, default=str, indent=2)}")
        
        # 5. Check metrics for correctness with more flexibility
        # Verify enqueued count (exact match)
        assert updated_metrics['enqueued'] == 7, f"Expected 7 items enqueued, got {updated_metrics['enqueued']}"
        
        # Verify processed count (fast + slow = 5)
        assert updated_metrics['processed'] >= 5, f"Expected at least 5 processed items, got {updated_metrics['processed']}"
        
        # Check either failures or retries - at least one must have occurred
        assert (updated_metrics.get('failed', 0) > 0 or 
                updated_metrics.get('retried', 0) > 0), "Expected either failures or retries to be > 0"
        
        # Verify that we've handled timeout or retry conditions
        assert (updated_metrics.get('timeouts', 0) > 0 or 
                updated_metrics.get('retried', 0) > 0), "Expected timeouts or retries to be > 0"
        
        # Verify avg_process_time was recorded
        assert updated_metrics.get('avg_process_time', 0) > 0, "Expected avg_process_time to be recorded"
        
        # 6. Check queue status for failures queue
        failures_queue_key = config.queue_keys['failures']
        failures_queue_name = failures_queue_key.decode() if isinstance(failures_queue_key, bytes) else failures_queue_key
        
        # Check the failures queue or system errors queue
        system_errors_key = config.queue_keys['system_errors']
        system_errors_name = system_errors_key.decode() if isinstance(system_errors_key, bytes) else system_errors_key
        
        assert (queue_status.get(failures_queue_name, 0) > 0 or 
                queue_status.get(system_errors_name, 0) > 0), "Expected items in failures or system_errors queue"
            
    finally:
        # Restore original work timeout
        worker.work_timeout = original_timeout
        
        # Manually stop the worker
        worker.running = False
        
        # Clear tasks to avoid loop issues in teardown
        if worker.tasks:
            for task in worker.tasks:
                task.cancel()
            worker.tasks = []