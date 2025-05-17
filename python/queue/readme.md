# Queue System

A flexible, Redis-based queue system for asynchronous processing with configurable retry capabilities, resilience features, and comprehensive metrics tracking.

## Features

- **Priority Queues**: High, normal, and low priority processing
- **Flexible Retry Strategies**: Exponential backoff, fixed delays, or custom retry schedules
- **Circuit Breaker Pattern**: Prevents cascading failures during Redis outages
- **Smart Timeout Management**: Enforced timeouts for async processors with graceful handling
- **Thread Pool for Sync Processors**: Efficient execution of synchronous processors with thread reuse
- **Automatic Retries**: Smart backoff for transient failures
- **Callbacks**: Execute functions on success or failure
- **Graceful Error Handling**: Failed operations moved to dedicated queues
- **Concurrent Processing**: Multiple worker tasks process queue items in parallel
- **Automatic Import**: Dynamically import processors and callbacks by name
- **Comprehensive Metrics**: Detailed metrics on operation processing, thread pool usage, and system health

## Installation

```bash
pip install redis
```

## Basic Usage

```python
import asyncio
from queue_system import QueueConfig, QueueManager, QueueWorker, QueueRetryConfig
from utils import with_timeout, circuit_breaker, retry_with_backoff

# Create shared configuration
config = QueueConfig(redis_url="redis://localhost:6379/0")

# Create queue manager and worker
queue = QueueManager(config=config)
worker = QueueWorker(config=config, max_workers=2, thread_pool_size=20)

# Define async processor (with timeout support)
async def async_processor(data):
    # Process the data asynchronously
    return {"status": "success", "result": data}

# Define sync processor (runs in thread pool without timeout)
def sync_processor(data):
    # Process the data synchronously
    return {"status": "success", "result": data}

# Define callback function
async def on_success(data):
    print(f"Successfully processed: {data['result']}")

# Enqueue operations
queue.enqueue(
    entity={"user_id": "123", "action": "update"},
    processor=async_processor,  # Will execute with timeout
    priority="high",
    on_success=on_success
)

queue.enqueue(
    entity={"order_id": "456", "action": "process"},
    processor=sync_processor,  # Will execute in thread pool without timeout
    priority="normal"
)

# Start the worker
async def main():
    await worker.start()
    try:
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        # Stop the worker on Ctrl+C
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Architecture Overview

The system consists of three main components:

1. **QueueConfig**: Configuration for Redis connection, queue keys, and shared registries
2. **QueueManager**: Client for enqueueing operations with priority, retries, and callbacks
3. **QueueWorker**: Service that processes queued operations with proper timeout and error handling

## Timeout and Thread Pool Management

The system handles different types of processors differently:

### Async Processors
- Executed directly in the asyncio event loop
- Timeout is applied using `asyncio.wait_for()`
- If timeout occurs, processor is cancelled at the next await point
- Proper cancellation handling ensures resources are cleaned up

### Sync Processors
- Executed in a dedicated thread pool
- No timeout is applied (sync code doesn't support clean timeouts)
- Thread pool manages concurrency and prevents worker exhaustion
- Fallback mechanism for thread pool exhaustion

## Thread Pool Exhaustion Handling

When the thread pool is exhausted (all threads busy):

1. The task is requeued with exponential backoff
2. Metrics are updated to track thread pool exhaustion
3. After max retries, the task is moved to the failures queue

This approach ensures:
- Predictable resource usage (fixed thread pool size)
- Clear failure modes (thread pool exhaustion is tracked and handled)
- Horizontal scalability (add more worker instances rather than increasing threads)

## Retry Configuration

For business logic retries (distinct from connection retries), use QueueRetryConfig:

### Default Exponential Backoff

```python
retry_config = QueueRetryConfig()  # Uses exponential backoff (base=2, min=1s)
```

### Fixed Delay

```python
retry_config = QueueRetryConfig.fixed(
    delay=30,            # 30-second delay between retries
    max_attempts=3,      # Maximum 3 retry attempts
    timeout=300          # Stop retrying after 5 minutes
)
```

### Exponential Backoff

```python
retry_config = QueueRetryConfig.exponential(
    base=2.0,            # Multiply delay by 2 each retry
    min_delay=1.0,       # Start with 1 second delay
    max_delay=60.0,      # Maximum 60 second delay
    max_attempts=5,      # Maximum 5 retry attempts
    timeout=3600         # Stop retrying after 1 hour
)
```

### Custom Retry Schedule

```python
retry_config = QueueRetryConfig.custom(
    delays=[60, 300, 1800, 7200],  # Custom delay schedule
    timeout=86400                  # Stop retrying after 1 day
)
```

## Monitoring Queue Status

```python
status = queue.get_queue_status()
print(status)
# {
#   'queue:high:async_processor': 5,
#   'queue:normal:sync_processor': 10,
#   'queue:failures': 2,
#   'queue:system_errors': 0,
#   'total_items': 17,
#   'metrics': {
#     'enqueued': 115,
#     'processed': 98,
#     'failed': 2,
#     'retried': 5,
#     'timeouts': 1,
#     'thread_pool_exhaustion': 3,
#     'thread_pool_utilization': 85.0,
#     'success_rate': 83.5,
#     ...
#   },
#   'status_time': 1621345678.123
# }
```

## Batch Enqueuing

For higher throughput, use batch operations:

```python
# Process multiple items in a single call
entities = [
    {"id": 1, "name": "Item 1"},
    {"id": 2, "name": "Item 2"},
    {"id": 3, "name": "Item 3"}
]

results = queue.enqueue_batch(
    entities=entities,
    processor=process_data,
    priority="high",
    retry_config=retry_config
)

print(f"Enqueued {len(results)} items")
```

## Best Practices

### 1. Async Processor Design

Async processors should:
- Use proper async libraries and context managers
- Handle cancellation gracefully
- Yield control frequently (await points)
- Properly clean up resources in finally blocks

```python
async def well_designed_async_processor(entity):
    try:
        # Use async database driver
        async with database.connection() as conn:
            async with conn.transaction():
                # Process data...
                result = await conn.fetch("SELECT * FROM items WHERE id = $1", entity["id"])
                
                # Allow cancellation point
                await asyncio.sleep(0)
                
                # More processing...
                processed = await some_other_async_operation(result)
                
                return {"success": True, "data": processed}
    except asyncio.CancelledError:
        # Clean up any resources not handled by context managers
        logger.info(f"Processing cancelled for entity {entity.get('id')}")
        raise  # Re-raise to propagate cancellation
```

### 2. Sync Processor Design

Sync processors should:
- Use proper resource management (context managers, try/finally)
- Avoid very long-running operations
- Be idempotent when possible (can be retried safely)

```python
def well_designed_sync_processor(entity):
    # Use context managers for resource cleanup
    with open(entity["filepath"], "r") as file:
        data = file.read()
    
    # Process data...
    processed = compute_results(data)
    
    # Use another context manager for database
    with database.connection() as conn:
        with conn.transaction():
            conn.execute("INSERT INTO results VALUES (?)", [processed])
    
    return {"status": "success", "result": processed}
```

### 3. Worker Configuration

Configure workers based on your workload:

- **Mostly async processors**: More worker tasks, smaller thread pool
- **Mostly sync processors**: Fewer worker tasks, larger thread pool
- **Mixed workload**: Balance worker tasks and thread pool size

### 4. Monitoring and Alerting

Set up alerts for critical metrics:

- Thread pool exhaustion rate > 5%
- Worker task failures
- Growing failure queue size
- Increasing retry counts

## Scaling Guidelines

When scaling the queue system:

1. **Monitor Thread Pool Utilization**:
   - Below 50%: Consider reducing thread pool size
   - Above 80%: Consider horizontal scaling (adding more workers)

2. **Monitor Worker Task Count**:
   - If all workers busy > 90% of time: Add more worker tasks

3. **Prefer Horizontal Scaling**:
   - Add more worker instances rather than increasing threads per instance
   - Use container orchestration (Kubernetes, ECS) for auto-scaling

## Implementation Details

### Key Components

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueConfig`

Configuration for queue operations, managing Redis connections and queue naming.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `get_queue_key` | `queue_name: str`, `priority: str = "normal"` | `str` | Configuration | Returns the full Redis key for a queue with specified priority. |
| | `get_registry_key` | | `str` | Configuration | Returns the Redis key for the queue registry. |
| | `get_callback_key` | `callback_name: str`, `callback_module: Optional[str] = None` | `str` | Configuration | Returns the key for a callback function in the registry. |
| | `register_callback` | `callback: Callable`, `name: Optional[str] = None`, `module: Optional[str] = None` | | Registration | Registers a callback function for later use. |
| | `update_metric` | `metric_name: str`, `value: Any = 1`, `force_log: bool = False` | | Metrics | Updates a metric counter or value in the metrics registry with intelligent logging. |
| | `get_metrics` | | `Dict[str, Any]` | Metrics | Returns current metrics with computed fields like success rate and thread pool statistics. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `redis_client=None`, `redis_url=None`, `queue_prefix="queue:"`, `backup_ttl=86400*7`, `logger=None`, `connection_timeout=5.0`, `max_connection_retries=3` | | Initialization | Initializes configuration with Redis connection parameters. |
| | `_define_queue_keys` | | | Initialization | Defines keys for processing queues and failure queues. |
| `@circuit_breaker` <br> `@retry_with_backoff` | `_ensure_redis_sync` | `retry_count=None` | `Redis` | Connection | Ensures Redis client is initialized with retry logic. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueManager`

Manager for queueing operations with a synchronous API.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `@try_catch` | `enqueue` | `entity: Dict[str, Any]`, `processor: Union[Callable, str]`, `queue_name: Optional[str] = None`, `priority: str = "normal"`, `operation_id: Optional[str] = None`, `retry_config: Optional[QueueRetryConfig] = None`, `on_success: Optional[Union[Callable, str]] = None`, `on_failure: Optional[Union[Callable, str]] = None`, `timeout: Optional[float] = None`, `deduplication_key: Optional[str] = None`, `custom_serializer: Optional[Callable] = None` | `Dict[str, Any]` | Queueing | Enqueues an operation for asynchronous processing, detecting whether the processor is sync or async. |
| `@try_catch` | `enqueue_batch` | `entities: List[Dict[str, Any]]`, `processor: Callable`, `**kwargs` | `List[Dict[str, Any]]` | Queueing | Enqueues multiple operations for batch processing with efficient metrics tracking. |
| `@try_catch` <br> `@circuit_breaker` | `get_queue_status` | | `Dict[str, Any]` | Monitoring | Returns the status of all registered queues with counts and metrics. |
| `@try_catch` | `purge_queue` | `queue_name: str`, `priority: str = "normal"` | `int` | Management | Removes all items from a specific queue. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: QueueConfig` | | Initialization | Initializes the queue manager with a configuration. |
| | `_generate_operation_id` | | `str` | Utilities | Generates a unique operation ID. |
| | `_hash_entity` | `entity: Dict[str, Any]` | `str` | Utilities | Generates a hash for an entity for deduplication. |
| | `_serialize_entity` | `entity`, `default_serializer=None` | `str` | Utilities | Serializes entity to JSON with custom handling for complex types. |
| `@try_catch` | `_queue_operation` | `queue_data: Dict[str, Any]`, `queue_name: str`, `priority: str = "normal"`, `custom_serializer: Optional[Callable] = None` | | Queueing | Queues an operation for later processing. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueWorker`

Worker for processing queued operations asynchronously.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|----------|-------------|
| | `start` | | `None` | Lifecycle | Starts processing the queue with worker tasks. |
| | `stop` | | `None` | Lifecycle | Stops queue processing gracefully, including thread pool shutdown. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: QueueConfig`, `max_workers=5`, `work_timeout=30.0`, `thread_pool_size=20` | | Initialization | Initializes the queue worker with configuration and concurrency settings. |
| `@with_timeout` | `_worker_loop` | `worker_id: int` | | Processing | Main worker loop for processing queue items. |
| `@circuit_breaker` | `_process_queue_item` | `worker_id: int` | `bool` | Processing | Processes a single item from the queue. |
| | `_handle_queue_item` | `worker_id: int`, `queue: bytes`, `item_data: bytes` | `bool` | Processing | Handles processing of a queue item, dispatching to the appropriate processor type. |
| | `_find_processor` | `processor_name: str`, `processor_module: Optional[str] = None` | `Optional[Callable]` | Processing | Finds the processor function by name and module. |
| | `_calculate_effective_timeout` | `item: Dict[str, Any]` | `float` | Processing | Calculates the effective timeout for an async processor execution. |
| | `_execute_sync_processor` | `processor: Callable`, `entity: Dict[str, Any]`, `operation_id: str` | `Any` | Processing | Executes a synchronous processor in the thread pool with exhaustion handling. |
| | `_update_thread_metrics` | `start_time: float` | | Metrics | Updates metrics related to thread pool usage. |
| | `_handle_pool_exhaustion` | `item: Dict[str, Any]`, `entity: Dict[str, Any]`, `operation_id: str`, `queue: bytes`, `redis: Any`, `worker_id: int` | `bool` | Error Handling | Handles thread pool exhaustion for a sync processor. |
| | `_handle_timeout_exceeded` | `item: Dict[str, Any]`, `entity: Dict[str, Any]`, `operation_id: str`, `redis: Any` | `bool` | Error Handling | Handles case where total timeout has been exceeded. |
| | `_handle_execution_timeout` | `item: Dict[str, Any]`, `entity: Dict[str, Any]`, `operation_id: str`, `effective_timeout: float`, `queue: bytes`, `redis: Any`, `worker_id: int` | `bool` | Error Handling | Handles timeout during async processor execution. |
| | `_handle_would_exceed_timeout` | `item: Dict[str, Any]`, `entity: Dict[str, Any]`, `operation_id: str`, `redis: Any` | `bool` | Error Handling | Handles case where next retry would exceed total timeout. |
| | `_handle_processing_exception` | `exception: Exception`, `item: Optional[Dict[str, Any]]`, `entity: Optional[Dict[str, Any]]`, `operation_id: str`, `worker_id: int`, `queue: bytes`, `redis: Any`, `item_data: Optional[bytes] = None` | `bool` | Error Handling | Handles general processing exception. |
| `@retry_with_backoff` | `_execute_callback` | `callback_name`, `callback_module`, `data` | | Callbacks | Executes a callback function, handling both async and sync callbacks. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueRetryConfig`

Configuration for retry behavior in queue operations.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `get_delay_for_attempt` | `attempt: int` | `float` | Configuration | Gets the delay for a specific attempt with jitter. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Converts to dictionary for queue storage. |
| | `would_exceed_timeout` | `first_attempt_time: float`, `current_time: float` | `bool` | Utilities | Checks if the next retry would exceed the total timeout. |
| `@classmethod` | `from_dict` | `data: Dict[str, Any]` | `QueueRetryConfig` | Factory | Creates instance from dictionary. |
| `@classmethod` | `fixed` | `delay: float`, `max_attempts: int = 5`, `timeout: Optional[float] = None` | `QueueRetryConfig` | Factory | Creates a fixed delay retry configuration. |
| `@classmethod` | `exponential` | `base: float = 2.0`, `min_delay: float = 1.0`, `max_delay: float = 60.0`, `max_attempts: int = 5`, `timeout: Optional[float] = None` | `QueueRetryConfig` | Factory | Creates an exponential backoff retry configuration. |
| `@classmethod` | `custom` | `delays: List[float]`, `max_attempts: Optional[int] = None`, `timeout: Optional[float] = None` | `QueueRetryConfig` | Factory | Creates a custom delay retry configuration. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `max_attempts: int = 5`, `delays: Optional[List[float]] = None`, `timeout: Optional[float] = None` | | Initialization | Initializes retry configuration. |
| | `_generate_exponential_delays` | | `List[float]` | Utilities | Generates exponential backoff delays with fixed parameters. |

</details>

<br>

</div>

## Thread Pool Exhaustion Handling

The queue system handles thread pool exhaustion (when all threads are busy) intelligently:

1. **Detection**: When submitting a task to the thread pool, a short timeout (100ms) detects if the pool is saturated
2. **Metrics**: Updates `thread_pool_exhaustion` metric to track occurrence rate
3. **Requeue**: The task is requeued with exponential backoff
4. **Dead Letter Queue**: After max retries, the task is moved to the failures queue

This approach provides clear failure semantics without creating unlimited threads:

```
Worker detects thread pool exhaustion
  │
  ├─ Update metrics (thread_pool_exhaustion += 1)
  │
  ├─ Increment attempt count
  │
  ├─ Check max attempts reached?
  │   ├─ Yes ─→ Move to failures queue
  │   │         Execute failure callback if defined
  │   │
  │   └─ No ──→ Calculate next retry time
  │             Check if would exceed total timeout
  │             Requeue with exponential backoff
  │
  └─ Log appropriate message
```

