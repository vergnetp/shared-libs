# Queue System

A flexible, Redis-based queue system for asynchronous processing with configurable retry capabilities, resilience features, and comprehensive metrics tracking.

## Features

- **Priority Queues**: High, normal, and low priority processing
- **Flexible Retry Strategies**: Exponential backoff, fixed delays, or custom retry schedules
- **Circuit Breaker Pattern**: Prevents cascading failures during Redis outages
- **Smart Timeout Management**: Enforced timeouts for async processors with graceful handling
- **Thread Pool for Sync Processors**: Efficient execution of synchronous processors with thread reuse
- **Comprehensive Metrics**: Detailed metrics on operation processing and thread pool usage

## Installation

```bash
pip install redis asyncio
```

## Main API

The system is built around two main classes:

- **QueueManager**: Enqueues tasks for processing (using the `enqueue` method - the processor of the task is specified at this point)
- **QueueWorker**: Background processor that executes the queued tasks (you only needs to `start` it in teh background - and `stop` before shutdown)


## Basic Usage

```python
import asyncio
from queue_system import QueueConfig, QueueManager, QueueWorker, QueueRetryConfig

# Create shared configuration
config = QueueConfig(
    redis=QueueRedisConfig(url="redis://localhost:6379/0"),
    worker=QueueWorkerConfig(worker_count=3)
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
    retry_config=custom_retry_strategy  # if the porcessor fail, this specified how and when to retry
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
| **Redis Connection** | `QueueRedisConfig.connection_timeout` | Controls connection timeout (default to 5s). |
| **Per-attempt Processing Timeout** | `QueueWorkerConfig.work_timeout` | Maximum time allowed for a single processing attempt (default to 30s). Applied to async processors using `asyncio.wait_for()`. |
| **Retry Policy** | `QueueRetryConfig` | Controls how many times processing is attempted after failures, the delay between attempts, and optional maximum total time for all retries. |
| **Thread Pool** | `QueueWorkerConfig.thread_pool_size` | Controls how many sync processors can run concurrently (default to 20). |


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
    connection_timeout=5.0,                  # 5 second timeout for Redis connection
    key_prefix="queue:"                      # Prefix for all Redis keys
)

# Create worker configuration with all parameters
worker_config = QueueWorkerConfig(
    worker_count=5,                          # 5 concurrent worker tasks
    thread_pool_size=20,                     # 20 threads for sync processors
    work_timeout=30.0,                       # 30 second default timeout for processing tasks - per attempt
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


## Processor Function Design

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

## Best Practices

### 1. Async Processor Design

Async processors should:
- Use proper async libraries and context managers
- Handle cancellation gracefully
- Yield control frequently (await points)
- Properly clean up resources in finally blocks

### 2. Sync Processor Design

Sync processors should:
- Use proper resource management (context managers, try/finally)
- Avoid very long-running operations
- Be idempotent when possible (can be retried safely)

### 3. Worker Configuration

Configure workers based on your workload:

- **Mostly async processors**: More worker tasks, smaller thread pool
- **Mostly sync processors**: Fewer worker tasks, larger thread pool
- **Mixed workload**: Balance worker tasks and thread pool size

## Class API

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueManager`

Manager for queueing operations - used in API endpoints.

<details>
<summary><strong>Public Methods</strong></summary>

| Method | Description |
|--------|-------------|
| `enqueue(entity, processor, ...)` | Enqueue an operation for asynchronous processing. |
| `enqueue_batch(entities, processor, ...)` | Enqueue multiple operations for batch processing. |
| `get_queue_status()` | Returns the status of all registered queues with counts and metrics. |
| `purge_queue(queue_name, priority)` | Remove all items from a specific queue. |

</details>
</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueWorker`

Worker for processing queued operations - started at app startup.

<details>
<summary><strong>Public Methods</strong></summary>

| Method | Description |
|--------|-------------|
| `start()` | Start processing the queue with worker tasks. |
| `stop()` | Stop queue processing gracefully. |

</details>
</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `QueueRetryConfig`

Configuration for retry behavior in queue operations.

<details>
<summary><strong>Public Methods</strong></summary>

| Method | Description |
|--------|-------------|
| `fixed(delay, max_attempts, timeout)` | Create a fixed delay retry configuration. |
| `exponential(base, min_delay, max_delay, max_attempts, timeout)` | Create an exponential backoff retry configuration. |
| `custom(delays, max_attempts, timeout)` | Create a custom delay retry configuration. |
| `to_dict()` | Convert configuration to dictionary. |

</details>
</div>
