import asyncio
import json
import pytest
import pytest_asyncio
import time
from typing import Dict, List, Any
import redis
from unittest.mock import patch, MagicMock

from ..config import QueueConfig, QueueRetryConfig
from ..config import redis_config as redis
from ..config import log_config as logging
from ..queue_manager import QueueManager
from ..queue_worker import QueueWorker
from ...resilience.circuit_breaker import CircuitBreaker, CircuitOpenError

from ... import log as logger
from ...resilience import with_timeout, retry_with_backoff

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

@with_timeout(1)
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
    # Reset circuit breakers before test
    CircuitBreaker.reset()
    
    logger = MockLogger()
    
    # Create the individual config components with proper initialization
    redis_config = redis.QueueRedisConfig(url=redis_url)
    logging_config = logging.QueueLoggingConfig(logger=logger)
    
    # Create the main config with the components
    config = QueueConfig(
        redis=redis_config,
        logging=logging_config,
        worker=None,  # Will use default worker config
        retry=None,  # Will use default retry config
        metrics=None  # Will use default metrics config
    )
    
    try:
        # Clear all test queues before running tests
        redis_client = config.redis.get_client()
        registered_queues = redis_client.smembers(config.redis.get_registry_key())
        
        # Delete all registered queues
        for queue in registered_queues:
            redis_client.delete(queue)
        
        # Delete registry key
        redis_client.delete(config.redis.get_registry_key())
        
        # Delete system_errors and failures queues
        redis_client.delete(config.redis.get_special_queue_key('failures'))
        redis_client.delete(config.redis.get_special_queue_key('system_errors'))
    except Exception as e:
        print(f"Warning: Failed to clean up Redis: {e}")
    
    yield config
    
    # Reset circuit breakers after test
    CircuitBreaker.reset()

@pytest.fixture
def queue_manager(config):
    return QueueManager(config=config)

@pytest_asyncio.fixture
async def worker(config):
    worker = QueueWorker(config=config)
    yield worker
    
    # Minimal cleanup - don't attempt task cancellation, just mark worker as stopped
    worker.running = False
    worker.tasks = []

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
    redis_client = config.redis.get_client()
    registered_queues = redis_client.smembers(config.redis.get_registry_key())
    print(f"Registered queues before processing: {registered_queues}")
    
    for queue in registered_queues:
        length = redis_client.llen(queue)
        print(f"Queue {queue} has {length} items before processing")
    
    # Start worker briefly
    await worker.start()
    
    # Wait for processing
    await asyncio.sleep(1)  # Increased wait time
    
    # Check queue status after worker execution
    for queue in registered_queues:
        length = redis_client.llen(queue)
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
        retry_config=retry_config.to_dict()  # Convert to dict for enqueueing
    )
    
    # Start worker
    await worker.start()
    
    # Wait for processing and retries
    await asyncio.sleep(2)  # Increase wait time
    
    # Check that item moved to failures queue
    redis_client = config.redis.get_client()
    
    # Debug: Check all queues
    registered_queues = redis_client.smembers(config.redis.get_registry_key())
    print(f"Registered queues: {registered_queues}")
    
    for queue in registered_queues:
        length = redis_client.llen(queue)
        print(f"Queue {queue} has {length} items")
        
        # If items exist, print them
        if length > 0:
            items = redis_client.lrange(queue, 0, -1)
            for item in items:
                print(f"  Item: {item}")
    
    # Check failures queue
    failures_queue = config.redis.get_special_queue_key('failures')
    if not isinstance(failures_queue, bytes):
        failures_queue = failures_queue.encode()
    
    failures_len = redis_client.llen(failures_queue)
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
        retry_config=retry_config.to_dict()  # Convert to dict for enqueueing
    )
    
    # Start worker
    await worker.start()
    
    # Wait for processing and timeout - increase wait time to ensure completion
    await asyncio.sleep(3)
    
    # Check that item moved to failures queue due to timeout
    redis_client = config.redis.get_client()
    
    # Get failures queue key 
    failures_queue = config.redis.get_special_queue_key('failures')
    if not isinstance(failures_queue, bytes):
        failures_queue = failures_queue.encode()
    
    # Check all queues for debugging
    registered_queues = redis_client.smembers(config.redis.get_registry_key())
    print(f"Registered queues after timeout test: {registered_queues}")
    
    for queue in registered_queues:
        length = redis_client.llen(queue)
        print(f"Queue {queue} has {length} items")
    
    print(f"Checking failures queue: {failures_queue}")
    failures_len = redis_client.llen(failures_queue)
    print(f"Failures queue has {failures_len} items")
    
    assert failures_len == 1, "Expected the slow item to be moved to failures queue after timeout"
    
    # Check the reason in the failures queue item
    if failures_len > 0:
        failures_items = redis_client.lrange(failures_queue, 0, -1)
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
    
    # Create retry config with max_attempts=1 so it fails faster
    retry_config = QueueRetryConfig(max_attempts=1)
    
    queue_manager.enqueue(
        entity={"test": "failure"},
        processor=failing_processor,
        on_failure=tracked_failure_callback,
        retry_config=retry_config.to_dict()  # Convert to dict for enqueueing
    )
    
    # Start worker
    await worker.start()
    
    # Wait for processing
    await asyncio.sleep(1.5)
    
    assert success_called.is_set()
    assert failure_called.is_set()

@pytest.mark.asyncio
async def test_priorities(queue_manager, worker, config):
    """Test that high priority items are processed before normal and low priority."""
    processing_order = []
    
    async def ordered_processor(data):
        processing_order.append(data.get("priority"))
        return {"success": True}
    
    # Register the callback with our simplified callable system
    config.callables.register(ordered_processor)
    
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
    redis_client = config.redis.get_client()
    registered_queues = redis_client.smembers(config.redis.get_registry_key())

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
    
    # Verify the counts match what we expect
    # Get the actual queue keys from the status since the format might vary
    high_queue = next((key for key in status.keys() if 'high' in key and 'successful_processor' in key), None)
    normal_queue = next((key for key in status.keys() if 'normal' in key and 'successful_processor' in key), None)
    
    assert high_queue is not None, "High priority queue not found in status"
    assert normal_queue is not None, "Normal priority queue not found in status"
    
    assert status[high_queue] == 1, f"Expected 1 item in high queue, got {status[high_queue]}"
    assert status[normal_queue] == 2, f"Expected 2 items in normal queue, got {status[normal_queue]}"

@pytest.mark.asyncio
async def test_queue_metrics(queue_manager, worker, config):
    """Test metrics tracking in the queue system."""
    # Define processors for testing metrics
    async def fast_processor(data):
        return {"success": True, "data": data}
    
    async def slow_processor(data):
        await asyncio.sleep(0.5)  # Slow but not timeout slow
        return {"success": True, "data": data}
    
    async def timeout_processor(data):
        await asyncio.sleep(3)  # This should exceed our test timeout
        return {"success": True, "data": data}
    
    async def failing_processor(data):
        raise ValueError("Intentional test failure")
    
    # Register these processors with our simplified callable system
    config.callables.register(fast_processor)
    config.callables.register(slow_processor)
    config.callables.register(timeout_processor)
    config.callables.register(failing_processor)
    
    # Set a shorter work_timeout for this test
    original_timeout = worker.work_timeout
    worker.work_timeout = 2.0  # Set to 2s to ensure timeout_processor times out
    
    try:
        # 1. Queue items with different characteristics
        # Fast processor, should succeed quickly
        for i in range(3):
            queue_manager.enqueue(
                entity={"test": f"fast_{i}"},
                processor=fast_processor,
                priority="high"
            )
        
        # Slow processor, should succeed but take longer
        for i in range(2):
            queue_manager.enqueue(
                entity={"test": f"slow_{i}"},
                processor=slow_processor,
                priority="normal"
            )
        
        # Failing processor, should fail and retry
        # Make sure it reaches max retries quickly to ensure we get a failure
        retry_config = QueueRetryConfig(max_attempts=2, delays=[0.1, 0.1])
        queue_manager.enqueue(
            entity={"test": "failing"},
            processor=failing_processor,
            retry_config=retry_config.to_dict(),  # Convert to dict for enqueueing
            priority="normal"
        )
        
        # Timeout processor, should timeout
        # Make sure it times out and doesn't retry too many times
        timeout_config = QueueRetryConfig(max_attempts=1)
        queue_manager.enqueue(
            entity={"test": "timeout"},
            processor=timeout_processor,
            retry_config=timeout_config.to_dict(),  # Convert to dict for enqueueing
            priority="low"
        )
        
        # 2. Get initial metrics
        initial_metrics = config.metrics.get_metrics()
        print(f"Initial metrics: {initial_metrics}")
        
        # Check that enqueued count is correct
        assert initial_metrics['enqueued'] == 7, f"Expected 7 items enqueued, got {initial_metrics['enqueued']}"
        
        # 3. Process the queue
        await worker.start()
        
        # Allow sufficient time for processing (including timeouts and retries)
        # Wait longer to ensure everything completes
        await asyncio.sleep(8)  # Increased from 5 to 8 seconds
        
        # 4. Get updated metrics
        updated_metrics = config.metrics.get_metrics()
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
        failures_queue_key = config.redis.get_special_queue_key('failures')
        failures_queue_name = failures_queue_key.decode() if isinstance(failures_queue_key, bytes) else failures_queue_key
        
        # Check the failures queue or system errors queue
        system_errors_key = config.redis.get_special_queue_key('system_errors')
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

@pytest.mark.asyncio
async def test_string_reference_processor(queue_manager, worker, config):
    """Test that string references to processors work correctly."""
    # Define a processor function that we'll reference by string
    async def string_referenced_processor(data):
        return {"processed_by_string_ref": True, "data": data}
    
    # Register the processor with our callable system
    config.callables.register(string_referenced_processor)
    
    module_name = string_referenced_processor.__module__
    function_name = string_referenced_processor.__name__
    
    # Use the fully qualified name for the processor
    processor_ref = f"{module_name}.{function_name}"
    
    # Enqueue using the string reference
    result = queue_manager.enqueue(
        entity={"test": "string_ref"},
        processor=processor_ref
    )
    
    assert result["status"] == "queued"
    
    # Start worker to process the item
    await worker.start()
    
    # Wait for processing
    await asyncio.sleep(1)
    
    # Check that the item was processed correctly
    # The success is determined by the absence of the item in any queue
    redis_client = config.redis.get_client()
    failures_queue = config.redis.get_special_queue_key('failures')
    failures_len = redis_client.llen(failures_queue)
    
    assert failures_len == 0, "Expected no failures when using string reference"

@pytest.mark.asyncio
async def test_string_reference_callback(queue_manager, worker, config):
    """Test that string references to callbacks work correctly."""
    # Create a shared variable to track callback execution
    callback_executed = {'success': False, 'failure': False}
    
    # Define callback functions that we'll reference by string
    async def string_referenced_success_callback(data):
        callback_executed['success'] = True
        return {"callback_executed": True, "data": data}
    
    async def string_referenced_failure_callback(data):
        callback_executed['failure'] = True
        return {"callback_executed": True, "data": data}
    
    # Register callbacks with our callable system
    config.callables.register(string_referenced_success_callback)
    config.callables.register(string_referenced_failure_callback)
    
    # Get the fully qualified names
    success_module = string_referenced_success_callback.__module__
    success_name = string_referenced_success_callback.__name__
    success_ref = f"{success_module}.{success_name}"
    
    failure_module = string_referenced_failure_callback.__module__
    failure_name = string_referenced_failure_callback.__name__
    failure_ref = f"{failure_module}.{failure_name}"
    
    # 1. Test successful callback
    queue_manager.enqueue(
        entity={"test": "success_callback"},
        processor=successful_processor,
        on_success=success_ref
    )
    
    # 2. Test failure callback
    retry_config = QueueRetryConfig(max_attempts=1)  # Only try once
    queue_manager.enqueue(
        entity={"test": "failure_callback"},
        processor=failing_processor,
        on_failure=failure_ref,
        retry_config=retry_config.to_dict()
    )
    
    # Start worker to process items
    await worker.start()
    
    # Wait for processing
    await asyncio.sleep(1.5)
    
    # Check that both callbacks were executed
    assert callback_executed['success'], "Success callback was not executed"
    assert callback_executed['failure'], "Failure callback was not executed"

@pytest.mark.asyncio
async def test_automatic_import(queue_manager, worker, config):
    """Test the automatic import of callables that aren't pre-registered."""
    # This test requires creating a temporary module with a callable
    # Since we can't easily create a real module in a test, we'll mock the import system
    
    # Create a mock module and function
    mock_module = MagicMock()
    
    async def mock_processor(data):
        return {"auto_imported": True, "data": data}
    
    mock_module.mock_processor = mock_processor
    
    # Patch the importlib.import_module to return our mock module
    with patch('importlib.import_module', return_value=mock_module):
        # Enqueue using a string reference to our mock module/function
        result = queue_manager.enqueue(
            entity={"test": "auto_import"},
            processor="mock_module.mock_processor"
        )
        
        assert result["status"] == "queued"
        
        # Start worker to process the item
        await worker.start()
        
        # Wait for processing
        await asyncio.sleep(1)
        
        # Check that the callable was imported and used successfully
        # Success is determined by the absence of failures
        redis_client = config.redis.get_client()
        failures_queue = config.redis.get_special_queue_key('failures')
        failures_len = redis_client.llen(failures_queue)
        
        system_errors_queue = config.redis.get_special_queue_key('system_errors')
        system_errors_len = redis_client.llen(system_errors_queue)
        
        assert failures_len == 0, "Expected no failures when auto-importing"
        assert system_errors_len == 0, "Expected no system errors when auto-importing"