# Structured Logging System

A flexible, high-performance logging system with structured data support, Redis queuing, and OpenSearch integration.

## Features

- **Thread-safe synchronous logging** with file, console, and Redis outputs
- **Structured logging** with arbitrary field support
- **Automatic component/subcomponent detection** based on caller context
- **Redis integration** for asynchronous log processing
- **OpenSearch storage** for log aggregation and analysis
- **Configurable log levels** with runtime adjustment
- **Robust error handling** with graceful fallbacks
- **Performance optimized** with buffered file writing
- **Log rotation** based on date and size

## Architecture

The system consists of three main components:

1. **Logger**: Captures and formats log messages, writes to local files and console, and queues to Redis
2. **Queue System**: Processes log messages from Redis and forwards to storage
3. **Storage Backend**: Stores logs in OpenSearch with index management

```
+-------------+     +--------------+     +---------------+
|   Logger    |---->| Queue System |---->| OpenSearch    |
| (logging.py)|     | (jobs.py)    |     | (storage.py)  |
+-------------+     +--------------+     +---------------+
       |
       v
  +----------+
  | Log Files |
  +----------+
```

## Installation

```bash
# Assuming your project uses pip for dependencies
pip install opensearch-py requests-aws4auth redis
```

## Usage

### Basic Logging

```python
from myapp.log.logging import info, error, debug, warning, critical

# Simple logging
info("Application started")
debug("Connecting to database")

# With indentation for readability
info("Processing files:")
for filename in files:
    info(f"Processing {filename}", indent=1)

# Error reporting
error("Failed to connect to database", indent=0)
```

### Structured Logging

```python
from myapp.log.logging import info, error

# Add structured fields to your logs
info("User login successful", 
     user_id="user123", 
     ip_address="192.168.1.1", 
     login_method="oauth")

# Error with context
error("Database query failed",
      query_time_ms=1532,
      database="products",
      table="inventory",
      error_code="DB-5432")

# Transaction logging
info("Order processed",
     order_id="ORD-9876",
     customer_id="CUST-1234",
     items_count=5,
     total_amount=129.99,
     payment_method="credit_card")
```

### Automatic Component and Subcomponent

The logging system automatically captures important context for each log entry:

- **timestamp**: Current time in "YYYY-MM-DD HH:MM:SS.mmm" format
- **request_id**: Current request ID (if available from request_id_var)
- **component**: Class name of the caller
- **subcomponent**: Method name of the caller

In text logs (console/file), this appears as a prefix:

```
[INFO] YourClass - your_method - Processing started
```

In OpenSearch, these are separate fields:

```json
{
  "level": "INFO",
  "message": "Processing started",
  "component": "YourClass",
  "subcomponent": "your_method",
  "timestamp": "2025-05-15 12:34:56.789",
  "request_id": "45ef-a123-b456-789c"
}
```

You can override these automatic fields when needed:

```python
debug("Custom categorization", 
      component="Authentication", 
      subcomponent="OAuth")
```

## Configuration

### Logger Configuration

```python
from myapp.log import initialize_logger
from myapp.log.config.logger_config import LogLevel

# Initialize with custom settings
logger = initialize_logger(
    service_name="api-service",
    redis_url="redis://localhost:6379/0",
    log_dir="/var/log/myapp",
    min_level=LogLevel.INFO,
    log_debug_to_file=False,
    flush_interval=5
)

# Or change settings at runtime
logger.config.update(min_level=LogLevel.DEBUG)
logger.config.add_global_context(environment="production", version="1.2.3")
```

### Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| service_name | Identifier for the service | service-{pid} |
| environment | Environment name (dev, test, staging, prod) | dev |
| use_redis | Enable Redis integration | True |
| redis_url | Redis connection URL | None |
| log_dir | Directory for log files | ../../../logs/ |
| min_level | Minimum log level | LogLevel.INFO |
| log_debug_to_file | Write DEBUG logs to file | False |
| flush_interval | Seconds between file flushes | 5 |
| quiet_init | Suppress initialization messages | False |
| add_caller_info | Add component and subcomponent info | True |
| global_context | Dictionary of fields for all logs | {} |
| excluded_fields | Set of field names to exclude | set() |

## Running the Log Processing Worker

To process logs from Redis and store them in OpenSearch, run the log processing worker:

```bash
# From your project's root directory
python -m myapp.log.jobs
```

Alternatively, you can run the worker programmatically:

```python
import asyncio
from myapp.log.jobs import run_worker

# Run the worker
asyncio.run(run_worker())

# For a background thread
import threading
def run_worker_thread():
    asyncio.run(run_worker())

worker_thread = threading.Thread(target=run_worker_thread, daemon=True)
worker_thread.start()
```

## Customizing Log Storage

You can initialize the log storage with custom settings:

```python
from myapp.log.jobs import initialize_storage
from myapp.log.opensearch_storage import OpenSearchLogStorage

# Configure OpenSearch storage
storage = initialize_storage(
    storage_class=OpenSearchLogStorage,
    host="opensearch.example.com",
    port=9200,
    use_ssl=True,
    index_prefix="myapp-logs",
    auth_type="basic",
    username="admin",
    password="password"
)
```

### Implementing a Custom Storage Backend

Create a new storage class by implementing the `LogStorageInterface`:

```python
from myapp.log.log_storage import LogStorageInterface

class MyCustomStorage(LogStorageInterface):
    def store_log(self, log_record):
        # Implement your storage logic
        return {"status": "stored"}
    
    def store_batch(self, log_records):
        # Implement batch storage
        return {"status": "batch_stored", "count": len(log_records)}

# Use your custom storage
from myapp.log.jobs import initialize_storage
initialize_storage(storage_class=MyCustomStorage)
```

## Advanced Usage

### Customizing Log Processing

You can register custom log processors for specialized handling:

```python
from myapp.log.logging import Logger

# Create a custom processor
def my_custom_processor(log_record):
    # Do something with the log record
    return {"status": "processed"}

# Register the processor
logger = Logger.get_instance()
logger.register_log_processor(my_custom_processor)
```

### Log Rotation

The logging system automatically rotates logs based on:

1. **Date**: A new log file is created each day
2. **Size**: Logs are rotated when they exceed 100MB

Rotated logs follow the naming pattern:
- Daily logs: `YYYY_MM_DD.log`
- Size-based rotation: `YYYY_MM_DD.log.HHMMSS`

### Thread Safety

All logging operations are thread-safe:
- File writing is protected with locks
- Instance creation uses a singleton pattern with thread-safe initialization
- Buffer management handles concurrent access correctly

## Query Examples for OpenSearch

Here are some example queries to retrieve logs from OpenSearch:

### Basic Queries

```json
// Get all errors
GET logs-2025.05.14/_search
{
  "query": {
    "term": {
      "level": "ERROR"
    }
  }
}

// Find logs for a specific service
GET logs-2025.05.14/_search
{
  "query": {
    "term": {
      "service": "api-service"
    }
  }
}

// Find all database-related errors
GET logs-*/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "level": "ERROR" } },
        { "match": { "message": "database" } }
      ]
    }
  }
}
```

### Structured Field Queries

With structured logging, you can query specific fields:

```json
// Find all logs from a specific component
GET logs-*/_search
{
  "query": {
    "term": {
      "component": "PoolManager"
    }
  }
}

// Find all leak detection logs
GET logs-*/_search
{
  "query": {
    "term": {
      "subcomponent": "LeakDetection"
    }
  }
}

// Find slow database queries
GET logs-*/_search
{
  "query": {
    "bool": {
      "must": [
        { "exists": { "field": "query_time_ms" } }
      ],
      "filter": [
        { "range": { "query_time_ms": { "gt": 1000 } } }
      ]
    }
  }
}
```

## Best Practices

1. **Be consistent with field names** - Use a standard naming convention for structured fields
2. **Add context, not just messages** - Include relevant data fields that can be searched
3. **Use the automatic component/subcomponent** - Let the system track the source of logs
4. **Override component/subcomponent when needed** - For logical grouping that differs from code structure
5. **Include correlation IDs** - Add request_id, transaction_id, or trace_id to connect related logs
6. **Add timestamps for events** - Include duration_ms for performance monitoring
7. **Keep message text human-readable** - The message is for humans, the fields are for machines
8. **Don't repeat field values in message text** - Avoid redundancy between message and fields

## Performance Considerations

The logging system is designed for high-performance operation:

- **Buffered file writing** reduces I/O operations
- **Redis queuing** prevents blocking the application thread
- **Batch processing** in the worker improves OpenSearch ingestion
- **Thread safety** with minimal contention
- **Configurable flush intervals** balance latency and throughput

For extremely high-volume environments, consider:
- Increasing the buffer size
- Adjusting flush intervals
- Setting up multiple worker instances
- Configuring OpenSearch for higher ingest performance