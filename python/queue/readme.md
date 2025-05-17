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

Additional dependencies required by the system:
```bash
pip install asyncio concurrent.futures
```

## Main API

You will create a `QueueManager` that takes some config, and you can then `enqueue` some tasks (i.e. a processing functon and some data to process).
You wil also create a `QueueWorker` that will take teh same config and that you will `start` and `stop` in the background, to actualy perform the tasks and empty the queue.

## Configuration

The configuration encompass the queueing system itself (redis) with a `QueueRedisConfig`, the worker  with `QueueWorkerConfig` and the way to handle retries in the processing of the task (`QueueRetryConfig`).

There are also some logging and diagnostic metrics configuraion (`QueueLoggingConfig` and `QueueMetricsConfig`).






|Operation|Per-attempt Timeout|Total/Overall Timeout|Retry strategy|
|--|--|--|--|
|Redis connection|`QueueRedisConfig.connection_timeout` (per operation)|None - only individual operations have timeouts|Uses `retry_with_backoff` decorator with `max_retries=QueueRedisConfig.max_connection_retries`. After that, uses circuit breaker pattern with `circuit_breaker_threshold` failures before opening.|
|Single task enqueuing|`QueueRedisConfig.connection_timeout` (per enqueue operation)|None - only the individual enqueue operation has a timeout|Uses `try_catch` decorator, which doesn't implement retries. Redis errors here may be handled by the Redis client's internal retry mechanism.|
|Batch tasks enqueuing|`QueueRedisConfig.connection_timeout` (per batch operation)|None - only the batch operation itself has a timeout|Similar to single task, uses `try_catch` decorator without explicit retries.|
|Task processing (async)|`QueueWorkerConfig.work_timeout` or remaining time from task's total timeout, whichever is smaller (applied per attempt using `asyncio.wait_for`)|`QueueRetryConfig.timeout` from enqueue - if not specified, no overall timeout is enforced across attempts|1. System tries up to `QueueRetryConfig.max_attempts` times (from enqueue) or if not specified, uses default from QueueConfig initialization.<br>2. Between retries, waits for delay specified in `QueueRetryConfig.delays` array (from enqueue) or if not specified, generates exponential delays.<br>3. Will stop retrying if total elapsed time exceeds `timeout` value (if specified).|
|Task processing (sync)|No direct per-attempt timeout - runs in thread pool which doesn't support interruption.|Same overall `QueueRetryConfig.timeout` behavior as async tasks|Same retry configuration as async processors, plus additional handling for thread pool exhaustion where operation is requeued up to `QueueWorkerConfig.max_requeue_attempts` times with exponential backoff.|
|Callback|No default timeout. If callback has `@with_timeout` decorator, that applies independently.|None - callbacks don't have an overall timeout mechanism|No default retry. If callback has `@retry_with_backoff` decorator, that applies independently up to its max_retries limit.|
|Thread pool exhaustion|N/A - not a timeout situation|N/A - separate mechanism|When thread pool is full, operation is requeued with up to `QueueWorkerConfig.max_requeue_attempts` attempts (default 3), using exponential backoff.|






Best not to add `@with_timeout` or `@retry_with_backoff` decorator to the processing functions and let the Queue module handle them.
They are however welcome on callbacks.

```python
from queue import (
    QueueConfig, 
    QueueRedisConfig, 
    QueueWorkerConfig, 
    QueueRetryConfig,
    QueueMetricsConfig,
    QueueLoggingConfig
)

# Create Redis configuration with all parameters
redis_config = QueueRedisConfig(
    url="redis://localhost:6379/0",          # Redis connection URL
    client=None,                             # No existing client, create new one from url
    connection_timeout=5.0,                  # 5 second timeout for Redis operations (connection and enqueueing)
    max_connection_retries=3,                # Retry Redis connection up to 3 times
    circuit_breaker_threshold=5,             # Open circuit after 5 failures
    circuit_recovery_timeout=30.0,           # Wait 30s before testing if Redis is back
    key_prefix="queue:",                     # Prefix for all Redis keys
    backup_ttl=86400 * 7                     # 7 days TTL for backup data
)

# Create worker configuration with all parameters
worker_config = QueueWorkerConfig(
    worker_count=5,                          # 5 concurrent worker tasks
    thread_pool_size=20,                     # 20 threads for sync processors
    work_timeout=30.0,                       # 30 second default timeout (per processing attempt)
    grace_shutdown_period=5.0,               # 5 second wait during shutdown
    max_requeue_attempts=3                   # Max attempts on thread pool exhaustion
)

# Create retry configuration with all parameters
retry_config = QueueRetryConfig(
    max_attempts=5,                          # Maximum 5 retry attempts
    delays=[1, 2, 4, 8, 16],                 # Exponential delays (generated if not provided)
    timeout=300                              # 5 minute total timeout
)

# Create metrics configuration with all parameters
metrics_config = QueueMetricsConfig(
    enabled=True,                            # Enable metrics collection
    log_threshold=0.1                        # Log changes > 10%
)

# Create logging configuration with all parameters
logging_config = QueueLoggingConfig(
    logger=None,                             # Use default logger
    level="INFO"                             # Minimum log level
)

# Create the complete configuration
default_config = QueueConfig(
    redis=redis_config,
    worker=worker_config,
    retry=retry_config,
    metrics=metrics_config,
    logging=logging_config
)
```

## Basic Usage

```python
import asyncio
from queue_system import QueueConfig, QueueManager, QueueWorker, QueueRetryConfig

# Create shared configuration
config = QueueConfig(redis_url="redis://localhost:6379/0")

# Create queue manager and worker
queue = QueueManager(config=config)
worker = QueueWorker(config=config)

# Define async processor
async def async_processor(data):
    # Process the data asynchronously
    return {"status": "success", "result": data}

# Define sync processor (runs in thread pool)
def sync_processor(data):
    # Process the data synchronously
    return {"status": "success", "result": data}

# Define callback function
async def on_success(data):
    print(f"Successfully processed: {data['result']}")

# Enqueue operations
queue.enqueue(
    entity={"user_id": "123", "action": "update"},
    processor=async_processor,
    priority="high",
    on_success=on_success
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

## Timeout and Resilience Configuration

The system applies different timeouts and retry strategies at various levels:

### 1. Redis Connection (QueueRedisConfig)

```python
redis_config = QueueRedisConfig(
    url="redis://localhost:6379/0",
    connection_timeout=5.0,          # Timeout for individual Redis operations
    max_connection_retries=3,        # Maximum retries for Redis operations
    circuit_breaker_threshold=5,     # Failures before circuit opens
    circuit_recovery_timeout=30.0    # Seconds before testing if Redis is back
)
```

### 2. Operation Processing (QueueWorker)

```python
worker_config = QueueWorkerConfig(
    worker_count=5,                  # Number of concurrent worker tasks
    thread_pool_size=20,             # Maximum threads for sync processors
    work_timeout=30.0,               # Default timeout for processing operations
    grace_shutdown_period=5.0,       # Time to wait for clean shutdown
    max_requeue_attempts=3           # Max retries on thread pool exhaustion
)
```

### 3. Business Logic Retries (QueueRetryConfig)

```python
retry_config = QueueRetryConfig(
    max_attempts=5,                  # Maximum retry attempts
    delays=[1, 2, 4, 8, 16],         # Retry delays in seconds
    timeout=300                      # Total timeout for all retries
)
```

### 4. Processor Timeouts

When defining a processor, you can add a timeout decorator:

```python
from resilience import with_timeout

@with_timeout(default_timeout=60.0)  # Processor-specific timeout
async def long_running_processor(data):
    # Process data
    return result
```

## Thread Pool for Synchronous Processors

The system handles different types of processors differently:

### Async Processors
- Executed directly in the asyncio event loop
- Timeout is applied using `asyncio.wait_for()`
- If timeout occurs, processor is cancelled at the next await point
- Proper cancellation handling ensures resources are cleaned up

### Sync Processors
- Executed in a dedicated thread pool
- Thread pool manages concurrency and prevents worker exhaustion
- Thread pool metrics are tracked for monitoring
- If thread pool is exhausted, tasks are requeued with backoff

## Thread Pool Exhaustion Handling

When the thread pool is exhausted (all threads busy):

1. Task requeued with exponential backoff
2. Metrics updated to track thread pool exhaustion
3. After max retries, task moved to failures queue

This approach ensures:
- Predictable resource usage (fixed thread pool size)
- Clear failure modes (thread pool exhaustion is tracked and handled)

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
#     'success_rate': 83.5
#   },
#   'status_time': 1621345678.123
# }
```

## Callback Execution

The system can execute callbacks on success or failure:

```python
# Define callbacks
async def on_success(data):
    print(f"Operation succeeded: {data}")

async def on_failure(data):
    print(f"Operation failed: {data}")

# Enqueue with callbacks
queue.enqueue(
    entity={"id": 123},
    processor=process_data,
    on_success=on_success,
    on_failure=on_failure
)
```

Callbacks will be executed with appropriate data:
- Success callbacks receive: `{"entity": original_entity, "result": processor_result, "operation_id": id}`
- Failure callbacks receive: `{"entity": original_entity, "error": error_message, "operation_id": id}`

## Batch Processing

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

## Priority Processing

The system processes queues in strict priority order:

1. **High Priority**: Processed first, ideal for urgent operations
2. **Normal Priority**: Processed after all high priority items
3. **Low Priority**: Processed only when no high or normal priority items remain

## Exception Handling and Retry Flow

1. **Redis Connection Errors**:
   - Retry with exponential backoff via `retry_with_backoff`
   - Circuit breaker prevents repeated attempts when Redis is down
   - After max retries, exception propagates to caller

2. **Operation Execution Errors**:
   - Processor exceptions are caught and retry is attempted
   - Retry delay follows configured schedule (exponential, fixed, or custom)
   - After max retries, operation moved to failures queue
   - Failure callback executed if configured

3. **Timeouts**:
   - Async processor timeouts trigger retry with backoff
   - Timeout counter incremented in metrics
   - After max retries or total timeout exceeded, operation moved to failures queue

4. **Thread Pool Exhaustion**:
   - Operation requeued with backoff
   - Thread pool exhaustion counter incremented
   - After max requeue attempts, operation moved to failures queue

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

## Implementation Details

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueConfig`

Central configuration for the entire queue system.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `to_dict` | | `Dict[str, Any]` | Configuration | Convert the complete configuration to a dictionary. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `redis: Optional[QueueRedisConfig] = None`, `worker: Optional[QueueWorkerConfig] = None`, `retry: Optional[QueueRetryConfig] = None`, `metrics: Optional[QueueMetricsConfig] = None`, `logging: Optional[QueueLoggingConfig] = None` | | Initialization | Initialize queue system configuration. |
</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueManager`

Manager for queueing operations - used in API endpoints.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `@try_catch` | `enqueue` | `entity: Dict[str, Any]`, `processor: Union[Callable, str]`, `queue_name: Optional[str] = None`, `priority: str = "normal"`, `operation_id: Optional[str] = None`, `retry_config: Optional[Dict[str, Any]] = None`, `on_success: Optional[Union[Callable, str]] = None`, `on_failure: Optional[Union[Callable, str]] = None`, `timeout: Optional[float] = None`, `deduplication_key: Optional[str] = None`, `custom_serializer: Optional[Callable] = None` | `Dict[str, Any]` | Queueing | Enqueue an operation for asynchronous processing. |
| `@try_catch` | `enqueue_batch` | `entities: List[Dict[str, Any]]`, `processor: Callable`, `**kwargs` | `List[Dict[str, Any]]` | Queueing | Enqueue multiple operations for batch processing. |
| `@try_catch` <br> `@circuit_breaker` | `get_queue_status` | | `Dict[str, Any]` | Monitoring | Returns the status of all registered queues with counts and metrics. |
| `@try_catch` | `purge_queue` | `queue_name: str`, `priority: str = "normal"` | `int` | Management | Remove all items from a specific queue. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: QueueConfig` | | Initialization | Initialize the queue manager with a configuration. |
| | `_generate_operation_id` | | `str` | Utilities | Generate a unique operation ID. |
| | `_hash_entity` | `entity: Dict[str, Any]` | `str` | Utilities | Generate a hash for an entity for deduplication. |
| | `_serialize_entity` | `entity`, `default_serializer=None` | `str` | Utilities | Serialize entity to JSON with custom handling for complex types. |
| `@try_catch` | `_queue_operation` | `queue_data: Dict[str, Any]`, `queue_name: str`, `priority: str = "normal"`, `custom_serializer: Optional[Callable] = None` | | Queueing | Queue an operation for later processing. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueWorker`

Worker for processing queued operations - started at app startup.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `start` | | `None` | Lifecycle | Start processing the queue with worker tasks. |
| | `stop` | | `None` | Lifecycle | Stop queue processing gracefully, including thread pool shutdown. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: QueueConfig` | | Initialization | Initialize the queue worker. |
| `@with_timeout` | `_worker_loop` | `worker_id: int` | | Processing | Main worker loop for processing queue items. |
| `@circuit_breaker` | `_process_queue_item` | `worker_id: int` | `bool` | Processing | Process a single item from the queue. |
| | `_handle_queue_item` | `worker_id: int`, `queue: bytes`, `item_data: bytes` | `bool` | Processing | Handle processing of a queue item, dispatching to the appropriate processor type. |
| | `_find_processor` | `processor_name: str`, `processor_module: Optional[str] = None` | `Optional[Callable]` | Processing | Find the processor function by name and module. |
| | `_calculate_effective_timeout` | `item: Dict[str, Any]` | `float` | Processing | Calculate the effective timeout for an async processor execution. |
| | `_execute_sync_processor` | `processor: Callable`, `entity: Dict[str, Any]`, `operation_id: str` | `Any` | Processing | Execute a synchronous processor in the thread pool with exhaustion handling. |
| | `_update_thread_metrics` | `start_time: float` | | Metrics | Update metrics related to thread pool usage. |
| | `_handle_pool_exhaustion` | `item: Dict[str, Any]`, `entity: Dict[str, Any]`, `operation_id: str`, `queue: bytes`, `redis: Any`, `worker_id: int` | `bool` | Error Handling | Handle thread pool exhaustion for a sync processor. |
| | `_handle_timeout_exceeded` | `item: Dict[str, Any]`, `entity: Dict[str, Any]`, `operation_id: str`, `redis: Any` | `bool` | Error Handling | Handle case where total timeout has been exceeded. |
| | `_handle_execution_timeout` | `item: Dict[str, Any]`, `entity: Dict[str, Any]`, `operation_id: str`, `effective_timeout: float`, `queue: bytes`, `redis: Any`, `worker_id: int` | `bool` | Error Handling | Handle timeout during async processor execution. |
| | `_handle_would_exceed_timeout` | `item: Dict[str, Any]`, `entity: Dict[str, Any]`, `operation_id: str`, `redis: Any` | `bool` | Error Handling | Handle case where next retry would exceed total timeout. |
| | `_handle_processing_exception` | `exception: Exception`, `item: Optional[Dict[str, Any]]`, `entity: Optional[Dict[str, Any]]`, `operation_id: str`, `worker_id: int`, `queue: bytes`, `redis: Any`, `item_data: Optional[bytes] = None` | `bool` | Error Handling | Handle general processing exception. |
| `@retry_with_backoff` | `_execute_callback` | `callback_name`, `callback_module`, `data` | | Callbacks | Execute a callback function, handling both async and sync callbacks. |

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
| | `get_delay_for_attempt` | `attempt: int` | `float` | Configuration | Get the delay for a specific attempt with jitter. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Convert configuration to dictionary for queue storage. |
| | `would_exceed_timeout` | `first_attempt_time: float`, `current_time: float` | `bool` | Utilities | Check if the next retry would exceed the total timeout. |
| `@classmethod` | `from_dict` | `data: Dict[str, Any]` | `QueueRetryConfig` | Factory | Create instance from dictionary. |
| `@classmethod` | `fixed` | `delay: float`, `max_attempts: int = 5`, `timeout: Optional[float] = None` | `QueueRetryConfig` | Factory | Create a fixed delay retry configuration. |
| `@classmethod` | `exponential` | `base: float = 2.0`, `min_delay: float = 1.0`, `max_delay: float = 60.0`, `max_attempts: int = 5`, `timeout: Optional[float] = None` | `QueueRetryConfig` | Factory | Create an exponential backoff retry configuration. |
| `@classmethod` | `custom` | `delays: List[float]`, `max_attempts: Optional[int] = None`, `timeout: Optional[float] = None` | `QueueRetryConfig` | Factory | Create a custom delay retry configuration. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `max_attempts: int = 5`, `delays: Optional[List[float]] = None`, `timeout: Optional[float] = None` | | Initialization | Initialize retry configuration. |
| | `_generate_exponential_delays` | | `List[float]` | Utilities | Generate exponential backoff delays with fixed parameters. |
| | `_validate_config` | | | Validation | Validate retry configuration parameters. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueRedisConfig`

Configuration for Redis connection and behavior.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `@circuit_breaker` <br> `@retry_with_backoff` | `get_client` | | `Redis` | Connection | Get or create Redis client with retries and circuit breaker. |
| | `get_queue_key` | `name: str`, `priority: Union[str, QueuePriority]` | `str` | Keys | Get full Redis key for a queue with the given name and priority. |
| | `get_special_queue_key` | `name: str` | `str` | Keys | Get full Redis key for a special queue like failures or errors. |
| | `get_registry_key` | | `str` | Keys | Get the Redis key for the queue registry. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Convert configuration to dictionary with sensitive data masked. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `url: Optional[str] = None`, `client: Optional[Any] = None`, `connection_timeout: float = 5.0`, `max_connection_retries: int = 3`, `circuit_breaker_threshold: int = 5`, `circuit_recovery_timeout: float = 30.0`, `key_prefix: str = "queue:"`, `backup_ttl: int = 86400 * 7` | | Initialization | Initialize Redis configuration. |
| | `_validate_config` | | | Validation | Validate Redis configuration parameters. |
| | `_mask_connection_url` | `url: str` | `str` | Utilities | Mask password in connection URL for logging safety. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueMetricsConfig`

Configuration for metrics collection and reporting.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `update_metric` | `metric_name: str`, `value: Any = 1`, `force_log: bool = False`, `logger=None` | | Metrics | Update a metric counter or value and log significant changes. |
| | `get_metrics` | | `Dict[str, Any]` | Metrics | Get current metrics with computed fields. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Convert configuration to dictionary. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `enabled: bool = True`, `log_threshold: float = 0.1` | | Initialization | Initialize metrics configuration. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueWorkerConfig`

Configuration for worker execution and thread pool.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `to_dict` | | `Dict[str, Any]` | Serialization | Convert configuration to dictionary. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `worker_count: int = 5`, `thread_pool_size: int = 20`, `work_timeout: float = 30.0`, `grace_shutdown_period: float = 5.0`, `max_requeue_attempts: int = 3` | | Initialization | Initialize worker configuration. |
| | `_validate_config` | | | Validation | Validate worker configuration parameters. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueCallableConfig`

Configuration for managing callable functions within the queue system.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `register` | `callable_func: Callable` | `str` | Registration | Register a callable function for later use. |
| | `get` | `name: str`, `module: str` | `Optional[Callable]` | Access | Get a callable by name and module, attempting to import it if not found. |
| | `to_dict` | | `Dict[str, Dict[str, str]]` | Serialization | Convert configuration to dictionary. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `logger=None` | | Initialization | Initialize the callable registry. |

</details>

<br>

</div>