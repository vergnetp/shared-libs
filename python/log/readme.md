# Structured Logging System

A flexible, high-performance logging system with structured data support and OpenSearch integration.

## Features

- **Thread-safe synchronous logging** with file output
- **Structured logging** with arbitrary field support
- **Automatic component/subcomponent detection** based on caller context
- **Redis integration** for asynchronous log processing
- **OpenSearch storage** for log aggregation and analysis
- **Configurable log levels** with runtime adjustment
- **Robust error handling** with graceful fallbacks

## Architecture

The system consists of three main components:

1. **Logger**: Captures and formats log messages, writes to local files, and queues to Redis
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

## Logging Formats

The logging system uses different formats for different output channels:

### Console and File Logs

Console and file logs use a human-readable format that includes all information:

```
2025-05-15 12:34:56.789 [ERROR] PoolManager - LeakDetection - Failed to process item | operation_id=op-123 | error_type=ConnectionError
```

Format components:
- **Timestamp**: ISO format with milliseconds
- **Log Level**: In brackets in file logs ([INFO], [ERROR], etc.)
- **Component/Subcomponent**: Automatically detected from caller
- **Message**: The main log message
- **Fields**: All structured fields in `key=value` format (truncated if too long)

### OpenSearch Logs

OpenSearch logs use a structured format with clean separation of concerns:

```json
{
  "timestamp": "2025-05-15 12:34:56.789",
  "level": "ERROR",
  "message": "Failed to process item",
  "component": "PoolManager",
  "subcomponent": "LeakDetection",
  "operation_id": "op-123",
  "error_type": "ConnectionError"
}
```

Key differences from text logs:
- **Clean Message**: Contains only the message without prefixes
- **Separate Fields**: All metadata in dedicated fields for better querying
- **Non-truncated Values**: All values are stored in full without truncation
- **Top-level Fields**: Context fields are moved to the top level

## Running the Log Processing Worker

To process logs from Redis and store them in OpenSearch, run the log processing worker:

```bash
# From your project's root directory
python -m myapp.log.jobs
```

Alternatively, you can run the worker programmatically:

```python
import time
from myapp.log.jobs import run_worker

# Run the worker
run_worker()

# For a background thread
from threading import Thread
worker_thread = Thread(target=run_worker, daemon=True)
worker_thread.start()
```

## Configuration

### Logger Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| use_redis | Enable Redis integration | False |
| redis_url | Redis connection URL | None |
| log_dir | Directory for log files | ../../../logs/ |
| service_name | Identifier for the service | service-{pid} |
| min_level | Minimum log level | LogLevel.INFO |
| log_debug_to_file | Write DEBUG logs to file | False |
| flush_interval | Seconds between file flushes | 5 |

### OpenSearch Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| host | OpenSearch host | localhost |
| port | OpenSearch port | 9200 |
| use_ssl | Use SSL for connection | False |
| index_prefix | Prefix for index names | logs |
| auth_type | Auth type (none, basic, aws) | none |
| region | AWS region for aws auth | us-east-1 |
| username | Username for basic auth | None |
| password | Password for basic auth | None |
| verify_certs | Verify SSL certificates | False |
| timeout | Connection timeout in seconds | 30 |
| batch_size | Max logs in a batch | 100 |

## Advanced Usage

### Customizing Log Processing

You can register custom log processors for specialized handling:

```python
from myapp.log.logging import AsyncLogger

# Create a custom processor
def my_custom_processor(log_record):
    # Do something with the log record
    return {"status": "processed"}

# Register the processor
logger = AsyncLogger.get_instance()
logger.register_log_processor(my_custom_processor)
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