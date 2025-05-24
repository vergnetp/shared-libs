# Queue System

A flexible, Redis-based queue system for asynchronous processing with configurable retry capabilities, resilience features, and comprehensive metrics tracking.

## Features

- **Priority Queues**: High, normal, and low priority processing
- **Flexible Retry Strategies**: Exponential backoff, fixed delays, or custom retry schedules
- **Circuit Breaker Pattern**: Prevents cascading failures during Redis outages
- **Smart Timeout Management**: Enforced timeouts for async processors with graceful handling
- **Thread Pool for Sync Processors**: Efficient execution of synchronous processors with thread reuse
- **Comprehensive Metrics**: Detailed metrics on operation processing and thread pool usage
- **Dynamic Callable Resolution**: String-based references to processors and callbacks

## Installation

```bash
pip install redis asyncio
```

## Main API

The system is built around two main classes:

- **QueueManager**: Enqueues tasks for processing (using the `enqueue` method - the processor of the task is specified at this point)
- **QueueWorker**: Background processor that executes the queued tasks (you only need to `start` it in the background - and `stop` before shutdown)


## Basic Usage

```python
import asyncio
from queue_system import QueueConfig, QueueManager, QueueWorker, QueueRetryConfig
from queue_system import QueueRedisConfig, QueueWorkerConfig, QueueLoggingConfig, QueueMetricsConfig

# Create component configurations
redis_config = QueueRedisConfig(url="redis://localhost:6379/0")
worker_config = QueueWorkerConfig(worker_count=3)

# Create shared configuration
config = QueueConfig(
    redis=redis_config,
    worker=worker_config
)

# Create queue manager and worker
queue = QueueManager(config=config)
worker = QueueWorker(config=config)

# Define async processor
async def async_processor(data):
    # Process the data asynchronously
    return {"status": "success", "result": data}

# Create retry configuration
custom_retry_strategy = QueueRetryConfig.exponential(
    max_attempts=3,
    min_delay=1.0,
    max_delay=30.0,
    timeout=120
)

# Enqueue operations
queue.enqueue(
    entity={"user_id": "123", "action": "update"},
    processor=async_processor, # the task processor is injected here
    priority="high",
    retry_config=custom_retry_strategy  # if the processor fails, this specifies how and when to retry
)

# Start the worker
async def main():
    await worker.start()
    try:
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

The system is configured using specialized configuration classes:

| What | Configuration | Description |
|------|--------------|-------------|
| **Redis Connection** | `QueueRedisConfig.connection_timeout` | Controls connection timeout (defaults to 5s). |
| **Per-attempt Processing Timeout** | `QueueWorkerConfig.work_timeout` | Maximum time allowed for a single processing attempt (defaults to 30s). Applied to async processors using `asyncio.wait_for()`. |
| **Retry Policy** | `QueueRetryConfig` | Controls how many times processing is attempted after failures, the delay between attempts, and optional maximum total time for all retries. |
| **Thread Pool** | `QueueWorkerConfig.thread_pool_size` | Controls how many sync processors can run concurrently (defaults to 20). |
| **Metrics Collection** | `QueueMetricsConfig.enabled` | Whether to collect detailed performance metrics (defaults to true). |
| **Logging** | `QueueLoggingConfig.logger` | Custom logger for queue operations. |


```python
# Create Redis configuration with all parameters
redis_config = QueueRedisConfig(
    url="redis://localhost:6379/0",          # Redis connection URL
    connection_timeout=5.0,                  # 5 second timeout for Redis connection
    key_prefix="queue:"                      # Prefix for all Redis keys
)

# Create worker configuration with all parameters
worker_config = QueueWorkerConfig(
    worker_count=5,                          # 5 concurrent worker tasks
    thread_pool_size=20,                     # 20 threads for sync processors
    work_timeout=30.0                        # 30 second default timeout for processing tasks - per attempt
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

## Retry Configuration

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
    max_attempts=5       # Maximum 5 retry attempts
)
```

### Custom Retry Schedule

```python
retry_config = QueueRetryConfig.custom(
    delays=[60, 300, 1800, 7200]  # Custom delay schedule
)
```


## Best Practices

### 1. Async Processor Design

- Use proper async libraries and context managers
- Handle cancellation gracefully
- Yield control frequently (await points)
- Properly clean up resources in finally blocks

### 2. Sync Processor Design

- Use proper resource management (context managers, try/finally)
- Avoid very long-running operations
- Be idempotent when possible (can be retried safely)

### 3. General Processor Design

We recommend **not** using `@with_timeout` or `@retry_with_backoff` decorators directly on processor functions. Instead:

1. **Use Queue-Level Retry Configuration**:
   ```python
   retry_config = QueueRetryConfig.exponential(max_attempts=5)
   
   queue.enqueue(
       entity=data,
       processor=my_processor,
       retry_config=retry_config  # QueueRetryConfig object can be used directly
   )
   ```

2. **For Internal Resilience**: Use decorators on internal functions, not on the processor itself.

3. **Design Processors to Fail Fast**: Make processors detect permanent failures quickly.

### 4. Worker Configuration

Configure workers based on your workload:

- **Mostly async processors**: More worker tasks, smaller thread pool
- **Mostly sync processors**: Fewer worker tasks, larger thread pool
- **Mixed workload**: Balance worker tasks and thread pool size

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

## String-Based References

Both processors and callbacks can be referenced by string, which is useful for decoupling or when the function isn't available in the current scope:

```python
# Reference a processor by string
queue.enqueue(
    entity={"id": 123},
    processor="myapp.processors.process_data",
    on_success="myapp.callbacks.handle_success",
    on_failure="myapp.callbacks.handle_failure"
)
```

## Batch Processing

The `enqueue_batch` method provides an efficient way to submit multiple tasks at once:

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

**Key behavior to understand:**

1. **Enqueue Optimization Only**: Batch processing is an optimization for the enqueue operation only. It uses Redis pipelining to submit all tasks in a single network round-trip, reducing overhead.

2. **Individual Task Processing**: The worker processes each task individually. From the worker's perspective, there's no difference between tasks submitted individually or as part of a batch.

3. **Individual Retry Tracking**: Each task in the batch gets its own operation ID and retry state. If one task fails, only that specific task is retried according to the retry configuration.

4. **Non-Atomic**: Batch processing is not an atomic transaction. If the worker is stopped mid-batch, some tasks may be processed while others remain in the queue.

5. **Shared Configuration**: All tasks in a batch share the same processor, priority, and retry configuration.

This approach optimizes throughput while maintaining the flexibility of individual task tracking and error handling.

## Metrics Tracking

The queue system collects extensive metrics about operations, including:

- Enqueued item counts
- Processed item counts
- Success rates
- Failure counts by type
- Retry statistics
- Thread pool utilization
- Average processing times
- Error breakdowns

These metrics can be accessed via `config.metrics.get_metrics()` or through the queue status API.



## Class API

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueManager`

Manager for queueing operations - used in API endpoints.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `@circuit_breaker`, `@try_catch` | `enqueue` | `entity: Dict[str, Any]`, `processor: Union[Callable, str]`, `queue_name: Optional[str] = None`, `priority: str = "normal"`, `operation_id: Optional[str] = None`, `retry_config: Optional[Union[Dict[str, Any], QueueRetryConfig]] = None`, `on_success: Optional[Union[Callable, str]] = None`, `on_failure: Optional[Union[Callable, str]] = None`, `timeout: Optional[float] = None`, `deduplication_key: Optional[str] = None`, `custom_serializer: Optional[Callable] = None` | `Dict[str, Any]` | Queueing | Enqueue an operation for asynchronous processing with optional retry and callback behavior. |
| `@circuit_breaker`, `@try_catch` | `enqueue_batch` | `entities: List[Dict[str, Any]]`, `processor: Union[Callable, str]`, `**kwargs` | `List[Dict[str, Any]]` | Queueing | Enqueue multiple operations at once for batch processing. |
| `@try_catch`, `@circuit_breaker` | `get_queue_status` | | `Dict[str, Any]` | Monitoring | Get the current status of all registered queues with counts and metrics. |
| `@circuit_breaker`, `@try_catch` | `purge_queue` | `queue_name: str`, `priority: str = "normal"` | `int` | Administration | Remove all items from a specific queue. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: QueueConfig` | | Initialization | Initialize the queue manager with configuration. |
| | `_generate_operation_id` | | `str` | Utility | Generate a unique operation ID. |
| | `_hash_entity` | `entity: Dict[str, Any]` | `str` | Utility | Generate a hash for an entity for deduplication. |
| | `_serialize_entity` | `entity`, `default_serializer=None` | `str` | Utility | Serialize entity to JSON with custom handling for complex types. |
| `@try_catch` | `_queue_operation` | `queue_data: Dict[str, Any]`, `queue_name: str`, `priority: str = "normal"`, `custom_serializer: Optional[Callable] = None` | `None` | Implementation | Queue an operation for later processing. |

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
| `@try_catch` | `start` | | `None` | Lifecycle | Start processing the queue with worker tasks. |
|  `@try_catch`| `stop` | | `None` | Lifecycle | Stop queue processing gracefully. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: QueueConfig` | | Initialization | Initialize the worker with configuration. |
| | `_worker_loop` | `worker_id: int` | | Implementation | Main worker loop for processing queue items. |
| `@circuit_breaker` | `_process_queue_item` | `worker_id: int` | `bool` | Implementation | Process a single item from the queue. |
| `@try_catch` | `_handle_queue_item` | `worker_id: int`, `queue: bytes`, `item_data: bytes` | `bool` | Implementation | Handle processing of a queue item. |
| `@try_catch` | `_find_processor` | `processor_name: str`, `processor_module: Optional[str] = None` | `Optional[Callable]` | Utility | Find the processor function by name and module. |
| `@try_catch` | `_execute_sync_processor` | `processor: Callable`, `entity: Dict[str, Any]`, `operation_id: str` | `Any` | Implementation | Execute a synchronous processor in the thread pool. |
| | `_update_thread_metrics` | `start_time: float` | | Monitoring | Update metrics related to thread pool usage. |
| | `_calculate_effective_timeout` | `item: Dict[str, Any]` | `float` | Utility | Calculate the effective timeout for an async processor execution. |
| | `_get_bytes_key` | `key_name: str` | `bytes` | Utility | Get a queue key as bytes. |
| | `_handle_task_failure` | `item: Optional[Dict[str, Any]]`, `entity: Optional[Dict[str, Any]]`, `operation_id: str`, `queue: bytes`, `redis_client: Any`, `worker_id: int`, `error_reason: str = "Unknown error"`, `item_data: Optional[bytes] = None` | `bool` | Implementation | Handle any task processing failure with unified retry logic. |
| | `_execute_callback` | `callback_name: str`, `callback_module: Optional[str] = None`, `data: Dict[str, Any] = None` | | Implementation | Execute a callback function. |

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
| | `get_delay_for_attempt` | `attempt: int` | `float` | Utility | Get the delay for a specific attempt with jitter. |
| | `would_exceed_timeout` | `first_attempt_time: float`, `current_time: float` | `bool` | Utility | Check if the next retry would exceed the total timeout. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Convert configuration to dictionary. |
| `@classmethod` | `from_dict` | `data: Dict[str, Any]` | `QueueRetryConfig` | Deserialization | Create instance from dictionary. |
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
| | `_validate_config` | | | Validation | Validate retry configuration parameters. |
| | `_generate_exponential_delays` | | `List[float]` | Utility | Generate exponential backoff delays with fixed parameters. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueConfig`

Central configuration for the entire queue system.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `@property` | `logger` | | `Any` | Utility | Get the configured logger. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Convert the complete configuration to a dictionary. |

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

### class `QueueRedisConfig`

Configuration for Redis connection and behavior.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `@circuit_breaker`, `@retry_with_backoff` | `get_client` | | `redis.Redis` | Connection | Get or create Redis client with retries and circuit breaker. |
| | `get_queue_key` | `name: str`, `priority: Union[str, QueuePriority]` | `str` | Utility | Get full Redis key for a queue with the given name and priority. |
| | `get_special_queue_key` | `name: str` | `str` | Utility | Get full Redis key for a special queue like failures or errors. |
| | `get_registry_key` | | `str` | Utility | Get the Redis key for the queue registry. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Convert configuration to dictionary with sensitive data masked. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `url: str`, `connection_timeout: float = 5.0`, `key_prefix: str = "queue:"` | | Initialization | Initialize Redis configuration. |
| | `_validate_config` | | | Validation | Validate Redis configuration parameters. |
| | `_mask_connection_url` | `url: str` | `str` | Security | Mask password in connection URL for logging safety. |

</details>

<br>

</div>
