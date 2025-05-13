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
    
    def error(self, msg): self.logs["error"].append(msg)
    def warning(self, msg): self.logs["warning"].append(msg)
    def info(self, msg): self.logs["info"].append(msg)
    def debug(self, msg): self.logs["debug"].append(msg)
    def critical(self, msg): self.logs["critical"].append(msg)

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
    config.logger.error = lambda msg: print(f"ERROR: {msg}")
    config.logger.warning = lambda msg: print(f"WARNING: {msg}")
    config.logger.info = lambda msg: print(f"INFO: {msg}")
    
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
    config.logger.error = lambda msg: print(f"ERROR: {msg}")
    config.logger.warning = lambda msg: print(f"WARNING: {msg}")
    config.logger.info = lambda msg: print(f"INFO: {msg}")
    config.logger.debug = lambda msg: print(f"DEBUG: {msg}")
    
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
    
    # All queue names in status should be decoded strings
    assert set(status.keys()).issubset(string_keys)
    
    # Count total items
    total_items = sum(status.values())
    assert total_items == 3