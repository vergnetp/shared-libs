# Processing Module

A module for reliable processing of operations with different criticality levels.

## Overview

The Processing Module provides a structured approach to handle both critical operations (like payment processing) and non-critical operations (like sending emails or updating analytics) with appropriate reliability guarantees.

Key features:
- Different handling for critical vs. non-critical operations
- Automatic backup of critical operations to Redis
- Queue-based processing for non-critical operations
- Worker implementation for processing queued operations
- Recovery mechanisms for failed operations
- Monitoring and health check capabilities

## Core Concepts

### Critical vs. Non-Critical Operations

The module distinguishes between two types of operations:

1. **Critical Operations**:
   - Must complete successfully (e.g., payment processing, order creation)
   - Executed directly with comprehensive backup mechanisms
   - Failures trigger alerts and emergency recovery procedures
   - User experience prioritized over backend considerations

2. **Non-Critical Operations**:
   - Can be processed asynchronously (e.g., sending emails, analytics updates)
   - Queued for later processing
   - Executed with retries and deadletter queues
   - Backend scalability prioritized over immediate execution

## Main Components

### `ProcessingManager`

The core class that provides:
- `process_critical()` - For executing critical operations
- `process()` - For queueing non-critical operations
- Emergency backup management
- Queue status monitoring

### `ProcessingWorker`

Worker implementation for processing queued operations:
- Processes queues in priority order (high, normal, low)
- Handles retries with exponential backoff
- Moves failed items to deadletter queue after max attempts
- Provides graceful shutdown

### Convenience Functions

The module provides two main convenience functions for simpler usage:

```python
# For critical operations
await process_critical(entity, processor_function, **options)

# For non-critical operations
await process(entity, processor_function, **options)
```

## Usage Examples

### Processing a Paid Order (Critical Operation)

```python
async def create_order_endpoint(order_data):
    try:
        result = await process_critical(
            entity=order_data,
            processor=process_payment_order,
            tags=[
                f"customer:{order_data['customer_id']}",
                f"payment_method:{order_data['payment_info']['method']}"
            ]
        )
        
        return {
            "success": True,
            "order_id": result["order_id"],
            "message": "Your order has been processed successfully"
        }
    except UserError as e:
        return {
            "success": False,
            "message": e.user_message()
        }
    except Exception:
        # For any other error, the critical data has been backed up
        # We can still return success to the user
        return {
            "success": True,
            "message": "Your order has been received and is being processed."
        }
```

### Updating Inventory (Non-Critical Operation)

```python
# Queue inventory updates after order processing
await process(
    entity={
        "items": order_data["items"],
        "order_id": result["order_id"]
    },
    processor=update_inventory,
    queue_name="inventory_updates",
    priority="normal"
)
```

### Handling Database Failures

The module provides patterns for handling database failures in critical operations:

```python
# Payment succeeded but database failed
try:
    # Try to save to database
    # ...
except Exception as db_error:
    # Critical failure after payment - emergency backup created
    # Return success to user with minimal order info
    return {
        "order_id": generated_id,
        "status": "processing",
        "message": "Your order has been received and is being processed."
    }
```

### Starting Worker Processes

```python
async def start_workers():
    # Configure manager with Redis
    manager = configure(redis_url=REDIS_URL)
    
    # Create worker
    worker = ProcessingWorker(manager, max_workers=3)
    
    # Start worker
    await worker.start()
    
    try:
        # Keep running until stopped
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        # Stop gracefully
        await worker.stop()

if __name__ == "__main__":
    # Run the worker process
    asyncio.run(start_workers())
```

## Integration with Other Systems

The module can be integrated with:

1. **Database Layer**: Works with the Entity system for storing and retrieving data
2. **Error Handling**: Uses the Error/UserError system for proper error handling
3. **Circuit Breakers**: Can be combined with circuit breakers for self-healing
4. **Microservices**: Fits in event-driven microservice architectures

## Best Practices

1. **For Critical Operations**:
   - Keep critical processor functions focused on the essentials
   - Move non-critical work to separate queued operations
   - Always have a fallback return value for the user

2. **For Non-Critical Operations**:
   - Set appropriate priority levels
   - Use queue names that reflect the operation type
   - Implement proper error handling in processor functions

3. **Recovery Procedures**:
   - Implement admin interfaces to view and manage emergency backups
   - Create automated recovery processes for common failures
   - Monitor queue sizes and deadletter queue activity

## Configuration

Configure the module using:

```python
from processing import configure

configure(
    redis_url="redis://localhost:6379/0",  # Redis connection URL
    emergency_prefix="emergency:",         # Prefix for emergency backup keys
    queue_prefix="queue:",                # Prefix for queue keys
    backup_ttl=86400*7                    # TTL for emergency backups (7 days)
)
```

## Advanced Usage

For more advanced scenarios, you can directly use the `ProcessingManager` class:

```python
from processing import ProcessingManager

# Create a custom manager
manager = ProcessingManager(
    redis_client=my_redis_client,
    emergency_prefix="custom:emergency:",
    queue_prefix="custom:queue:"
)

# Get pending emergencies
emergencies = await manager.get_pending_emergencies()

# Get queue status
queue_status = await manager.get_queue_status()

# Retry a failed operation
success = await manager.retry_emergency(operation_id)
```