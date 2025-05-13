# Queue System

A flexible queue system for asynchronous processing with retry capabilities, built on Redis.

## Features

- **Priority Queues**: High, normal, and low priority processing
- **Flexible Retry Strategies**: Exponential backoff, fixed delays, or custom retry schedules
- **Timeout Control**: Set maximum time limits for retry attempts
- **Callbacks**: Execute functions on success or failure
- **Graceful Error Handling**: Failed operations moved to dedicated queues
- **Concurrent Processing**: Multiple worker tasks process queue items in parallel
- **Automatic Import**: Dynamically import processors and callbacks by name

## Installation

```bash
pip install redis
```

## Basic Usage

```python
import asyncio
from queue_system import QueueConfig, QueueManager, QueueWorker, QueueRetryConfig

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
```

## Error Handling

Failed operations are handled in two ways:

1. **System Errors Queue**: For operations that couldn't be processed due to system-level issues (deserialization failures, missing processor functions)
2. **Failures Queue**: For operations that consistently failed to execute after the maximum retry attempts

## Architecture

The system consists of three main components:

1. **QueueConfig**: Manages Redis connections, keys, and registries
2. **QueueManager**: Handles queueing operations with a synchronous API
3. **QueueWorker**: Asynchronously processes queued items with retry handling

Queue items are stored in Redis lists with priority-based prefixes:
- `queue:high:*`: High priority operations
- `queue:normal:*`: Normal priority operations
- `queue:low:*`: Low priority operations

## Worker vs Client API

- **Synchronous API**: Adding items to queues (`enqueue()`) is synchronous for simplicity and ease of use
- **Asynchronous Processing**: The worker that processes queue items runs asynchronously for efficiency
- **Worker Methods**: `start()`, `stop()` are asynchronous since they deal with ongoing processing