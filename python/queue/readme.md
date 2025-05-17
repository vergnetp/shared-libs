# Queue System

A flexible, Redis-based queue system for asynchronous processing with configurable retry capabilities, resilience features, and comprehensive metrics tracking.

## Features

- **Priority Queues**: High, normal, and low priority processing
- **Flexible Retry Strategies**: Exponential backoff, fixed delays, or custom retry schedules
- **Circuit Breaker Pattern**: Prevents cascading failures during Redis outages
- **Timeout Control**: Enforced timeouts at both operation and function levels
- **Automatic Retries**: Smart backoff for transient failures
- **Callbacks**: Execute functions on success or failure
- **Graceful Error Handling**: Failed operations moved to dedicated queues
- **Concurrent Processing**: Multiple worker tasks process queue items in parallel
- **Automatic Import**: Dynamically import processors and callbacks by name
- **Smart Metrics Tracking**: Comprehensive metrics with intelligent event-driven logging

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
worker = QueueWorker(config=config, max_workers=2)

# Define processor function (can be async)
async def process_data(data):
    # Process the data...
    return {"status": "success", "result": data}

# Define callback function (can be async)
async def on_success(data):
    print(f"Successfully processed: {data['result']}")

# Enqueue an operation - simple, synchronous API
queue.enqueue(
    entity={"user_id": "123", "action": "update"},
    processor=process_data,
    priority="high",
    on_success=on_success
)

# Start the worker (this is async because it runs continuously)
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

## Resilience Patterns

### Timeout Control

The `with_timeout` decorator ensures functions complete within expected timeframes:

```python
@with_timeout(default_timeout=30.0)
async def critical_operation():
    # This function will raise TimeoutError if it exceeds 30 seconds
    ...
```

### Circuit Breaker

The `circuit_breaker` decorator prevents cascading failures by stopping repeated calls to failing services:

```python
@circuit_breaker(name="redis_operations", failure_threshold=5, recovery_timeout=30.0)
def redis_operation():
    # If this fails 5 times, circuit opens and immediately rejects further calls
    # After 30 seconds, it will allow a trial call to see if service recovered
    ...
```

### Retry With Backoff

The `retry_with_backoff` decorator handles transient failures with exponential backoff:

```python
@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(ConnectionError,))
def network_operation():
    # If ConnectionError occurs, retry up to 3 times with increasing delays
    ...
```

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

## Advanced Usage

### Success and Failure Callbacks

```python
async def notify_success(data):
    print(f"Operation {data['operation_id']} succeeded")

async def notify_failure(data):
    print(f"Operation {data['operation_id']} failed: {data['error']}")

queue.enqueue(
    entity={"user_id": "123"},
    processor=process_data,
    retry_config=retry_config,
    on_success=notify_success,
    on_failure=notify_failure
)
```

### Monitoring Queue Status

```python
status = queue.get_queue_status()
print(status)  # {'queue:high:process_data': 5, 'queue:normal:send_email': 10, ...}
```

### Batch Enqueuing

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

## Metrics and Monitoring

The queue system includes comprehensive metrics tracking with intelligent logging:

```python
# Get current metrics
metrics = config.get_metrics()

# Check success rate
success_rate = metrics.get('success_rate', 0)
print(f"Success rate: {success_rate:.1f}%")

# Check processing volumes
processed = metrics.get('processed', 0)
enqueued = metrics.get('enqueued', 0)
failed = metrics.get('failed', 0)
print(f"Processed: {processed}/{enqueued} (Failed: {failed})")

# Check processing times
avg_process_time = metrics.get('avg_process_time', 0)
print(f"Average processing time: {avg_process_time:.2f}ms")
```

### Event-Driven Metrics Logging

The system automatically logs metrics events based on intelligent thresholds:

- **Error metrics**: Logged on every change
- **Small counters (0-5)**: Logged on every increment
- **Medium counters**: Logged at logarithmic boundaries (10, 100, 1000)
- **Large counters**: Logged at percentage-based intervals
- **Averages**: Logged when they change by more than 10%
- **Batch operations**: Always logged with performance metrics

These logs can be sent to OpenSearch/Elasticsearch, ELK Stack, or other monitoring systems for visualization and alerting.

## Integration with FastAPI

```python
from fastapi import FastAPI, BackgroundTasks
from queue_system import QueueConfig, QueueManager, QueueWorker, QueueRetryConfig

app = FastAPI()

# Create shared configuration
config = QueueConfig(redis_url="redis://localhost:6379/0")

# Create manager and worker
queue = QueueManager(config=config)
worker = QueueWorker(config=config, max_workers=2)

@app.on_event("startup")
async def startup_event():
    await worker.start()

@app.on_event("shutdown")
async def shutdown_event():
    await worker.stop()

@app.post("/process")
async def process_request(data: dict):
    # Synchronous API for queueing
    result = queue.enqueue(
        entity=data,
        processor=process_data,
        retry_config=QueueRetryConfig.exponential(timeout=3600)
    )
    return {"operation_id": result["operation_id"], "status": "queued"}

@app.post("/process-batch")
async def process_batch(data: list):
    # Batch API for higher throughput
    results = queue.enqueue_batch(
        entities=data,
        processor=process_data,
        retry_config=QueueRetryConfig.exponential(timeout=3600)
    )
    return {"operation_count": len(results), "status": "queued"}
```

## Error Handling

Failed operations are handled in two ways:

1. **System Errors Queue**: For operations that couldn't be processed due to system-level issues (deserialization failures, missing processor functions)
2. **Failures Queue**: For operations that consistently failed to execute after the maximum retry attempts

You can inspect these queues for diagnostic purposes:

```python
# Get queue status
status = queue.get_queue_status()

# Check failures and system errors
failures_count = status.get('queue:failures', 0)
system_errors_count = status.get('queue:system_errors', 0)

print(f"Failed operations: {failures_count}")
print(f"System errors: {system_errors_count}")
```

## Monitoring and Visualization

The queue system automatically integrates with your existing logging infrastructure:

### OpenSearch/Elasticsearch Integration

Since your logging system already sends logs to OpenSearch, the queue metrics are automatically available for visualization:

```python
# Metrics logs are automatically sent to your configured log storage
# No additional configuration needed - just use your existing logger:

# When a metric changes significantly
config.update_metric('processed', 1)  # This will log when crossing thresholds

# Force logging for important updates
config.update_metric('success_rate', current_rate, force_log=True)
```

In OpenSearch, you can create dashboards to visualize queue metrics with queries like:

```json
// Find all queue metric updates
GET logs-*/_search
{
  "query": {
    "match_phrase": {
      "message": "Queue metric update"
    }
  },
  "sort": [
    {
      "timestamp": {
        "order": "desc"
      }
    }
  ]
}

// Track success rate over time
GET logs-*/_search
{
  "query": {
    "bool": {
      "must": [
        { "match_phrase": { "message": "Queue metric update" } },
        { "match": { "metric_name": "success_rate" } }
      ]
    }
  },
  "sort": [
    {
      "timestamp": {
        "order": "asc"
      }
    }
  ],
  "aggs": {
    "success_rate_over_time": {
      "date_histogram": {
        "field": "timestamp",
        "calendar_interval": "hour"
      },
      "aggs": {
        "avg_success_rate": {
          "avg": {
            "field": "metric_value"
          }
        }
      }
    }
  }
}
```

## Architecture

The system consists of four main components:

1. **QueueConfig**: Manages Redis connections, keys, and registries
2. **QueueManager**: Handles queueing operations with a synchronous API
3. **QueueWorker**: Asynchronously processes queued items with retry handling
4. **QueueRetryConfig**: Configures retry behavior for failed operations

Queue items are stored in Redis lists with priority-based prefixes:
- `queue:high:*`: High priority operations
- `queue:normal:*`: Normal priority operations
- `queue:low:*`: Low priority operations

## Graceful Shutdown and Cleanup

To properly shut down workers and clean up resources:

```python
# 1. Signal that workers should stop processing new items
await worker.stop()

# 2. Optionally flush any metrics or logs
config.logger.info("Shutting down queue system")

# 3. Close Redis connections explicitly if needed
if hasattr(config, 'redis_client') and config.redis_client:
    config.redis_client.close()
```

## Troubleshooting

### Queue items not being processed

1. Check that Redis is running and accessible
2. Verify that the worker is running with `worker.running` property
3. Inspect the queue status with `queue.get_queue_status()`
4. Check processor functions are callable and properly registered

### Circuit breaker opening unexpectedly

1. Check Redis connectivity and performance
2. Consider adjusting circuit breaker parameters:
   ```python
   @circuit_breaker(failure_threshold=10, recovery_timeout=60.0)
   ```

### Timeouts occurring too frequently

1. Review operation complexity and expected duration
2. Adjust timeout values for specific operations:
   ```python
   @with_timeout(default_timeout=120.0)  # Increase for longer operations
   ```

### Redis connection failing

1. Check Redis server is running and accessible
2. Verify network connectivity and firewall settings
3. Consider adjusting retry parameters:
   ```python
   @retry_with_backoff(max_retries=5, base_delay=1.0, max_delay=30.0)
   ```

## Performance Considerations

- **Batch Operations**: Use `enqueue_batch()` for higher throughput
- **Concurrency**: Adjust `max_workers` based on CPU cores and workload
- **Timeouts**: Set appropriate work timeouts to prevent worker stalling
- **Connection Pooling**: Redis connection is reused for better performance
- **Serialization**: Custom serializers can be used for complex data types

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
| | `get_metrics` | | `Dict[str, Any]` | Metrics | Returns current metrics with computed fields like success rate. |

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
| `@try_catch` | `enqueue` | `entity: Dict[str, Any]`, `processor: Union[Callable, str]`, `queue_name: Optional[str] = None`, `priority: str = "normal"`, `operation_id: Optional[str] = None`, `retry_config: Optional[QueueRetryConfig] = None`, `on_success: Optional[Union[Callable, str]] = None`, `on_failure: Optional[Union[Callable, str]] = None`, `timeout: Optional[float] = None`, `deduplication_key: Optional[str] = None`, `custom_serializer: Optional[Callable] = None` | `Dict[str, Any]` | Queueing | Enqueues an operation for asynchronous processing. |
| `@try_catch` | `enqueue_batch` | `entities: List[Dict[str, Any]]`, `processor: Callable`, `**kwargs` | `List[Dict[str, Any]]` | Queueing | Enqueues multiple operations for batch processing with efficient metrics tracking. |
| `@try_catch` <br> `@circuit_breaker` | `get_queue_status` | | `Dict[str, Any]` | Monitoring | Returns the status of all registered queues with counts. |
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
|------------|--------|------|---------|----------|-------------|
| | `start` | | `None` | Lifecycle | Starts processing the queue with worker tasks. |
| | `stop` | | `None` | Lifecycle | Stops queue processing gracefully. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: QueueConfig`, `max_workers=5`, `work_timeout=30.0` | | Initialization | Initializes the queue worker with configuration and concurrency settings. |
| `@with_timeout` | `_worker_loop` | `worker_id: int` | | Processing | Main worker loop for processing queue items. |
| `@circuit_breaker` <br> `@with_timeout` | `_process_queue_item` | `worker_id: int` | `bool` | Processing | Processes a single item from the queue. |
| `@with_timeout` | `_handle_queue_item` | `worker_id: int`, `queue: bytes`, `item_data: bytes` | `bool` | Processing | Handles processing of a queue item. |
| `@retry_with_backoff` | `_execute_callback` | `callback_name`, `callback_module`, `data` | | Processing | Executes a callback function. |

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

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### Decorator Functions

Utility decorators for improving resilience and error handling.

<details>
<summary><strong>Public Decorators</strong></summary>

| Decorator | Args | Description |
|-----------|------|-------------|
| `with_timeout` | `default_timeout: float = 60.0` | Adds timeout functionality to both async and sync methods. |
| `circuit_breaker` | `name=None`, `failure_threshold=5`, `recovery_timeout=30.0`, `half_open_max_calls=3`, `window_size=60.0` | Applies circuit breaker pattern to prevent cascading failures. |
| `retry_with_backoff` | `max_retries=3`, `base_delay=0.1`, `max_delay=10.0`, `exceptions=None`, `total_timeout=30.0` | Retries functions with exponential backoff on specified exceptions. |

</details>

<br>

</div>