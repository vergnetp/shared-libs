# Database Abstraction Layer

**Smarter SQL connection handling for fast, scalable, and reliable applications.**

## Introduction

Database connections are expensive. To stay fast, apps rely on **connection pools** — pre-opened connections that avoid the cost of creating new ones. 
But managing these efficiently is critical:

- **Connections should return quickly** to avoid bottlenecks.
- **Slow or stuck queries must be terminated** to prevent resource exhaustion.
- **Concurrent users must not be stuck indefinitely** — timeouts are essential.
- **Scaling signals must be clear** — the system should tell you when to grow.



### What This Solution Provides

This library offers a simple yet powerful **abstraction layer** that makes database interactions easy and consistent across different engines such as **PostgreSQL, MySQL**, and more.
Developers can connect to and use databases through a unified API — without worrying about the low-level details like connection pooling, retries, timeouts, or resilience strategies.
Under the hood, the solution takes care of:

- **Connection pooling and reuse**
- **Query retries with backoff**
- **Timeouts and stuck query protection**
- **Automatic failover and recovery**
- **Transaction integrity**
- **Metrics and slow query insights**

In short: it hides the complexity and offers a robust, resilient, scalable, and optimized way to work with SQL databases — while giving applications clear scaling signals when limits are reached.


---

## Scaling Strategy: From Hundreds to Millions of Users

### Current Architecture

Our solution supports **200–5000 concurrent users** through horizontal scaling of app servers.
To put this in perspective, concurrent users typically represent only a fraction of total active users. Assuming a conservative 10× multiplier, this architecture could support:

- **200 concurrent users → ~2,000 active users**
- **5,000 concurrent users → ~50,000 active users**

If each active user pays **$49/month**, the potential turnover is:

| Concurrent Users | Estimated Active Users | Yearly Infra Cost | Potential Yearly Revenue |
|------------------|------------------------|-------------------|--------------------------|
| 200              | 2,000                   | $288 ($24 × 12)   | ~$1,176,000 (2,000 × $49 × 12) |
| 5,000            | 50,000                  | $15,264 ($1,272 × 12) | ~$29,400,000 (50,000 × $49 × 12) |

This illustrates how modest infrastructure costs can support a highly scalable and profitable SaaS model at scale, with the proper code.


###### App Servers Have Limited Capacity

Each application server typically limits its connection pool to ~20 connections for responsiveness (the server also has to accommodate for computation, logging etc.).

###### Database Servers Can Handle More Connections

Most relational databases (e.g. PostgreSQL, MySQL) can support 100–500 active connections, depending on hardware and configuration.
One application server with 20 connections is under-using the database. If too many concurrent users need a connection they will have to wait their turn and some will get timeout errors.

###### Horizontal Scaling (How It Works)

When timeout rates exceed 5%, this signals connection contention — the solution is to add more app servers to spread the load across more connection pools.
5 app servers × 20 connections = 100 concurrent DB connections → ~1000 concurrent users

- Assuming an average query time of **100 ms**, this setup allows the system to serve ~1000 users every second without timeouts.
- Adding more app servers increases capacity proportionally until the database connection limit is reached.


### Current Scaling (Built-in)

The current implementation supports horizontal scaling up to ~5000 concurrent users using connection pools:

| Setup | DB Spec | Max Concurrent Users | Monthly Cost |
|-------|---------|----------------------|--------------|
| Single app + DB server | Low | 200 | $24 |
| App servers + low DB | Low | 1000 | $216 |
| App servers + high DB | High | 5000 | $1272 |

- Each app server has ~20 connections.
- Database supports 100–500 connections.
- Scaling is easy: Add more app servers until DB connections are saturated.

At this stage → **No code changes needed.**

---

### Scaling Beyond This

Once database connection limits are hit, further scaling requires architectural upgrades.

#### 4️⃣ Sharding

- Divide data into **shards** (multiple DB instances).
- Route queries based on shard key.

Example:

| Shards | App Servers per Shard | Connections per App | Total Concurrent Connections |
|--------|-----------------------|---------------------|-----------------------------|
| 10     | 5                     | 20                  | 1000 (→ 50,000 concurrent users) |

**⚡ This requires code changes** to:

- Route queries to the correct shard
- Support shard discovery/configuration

#### 5️⃣ Global Scaling with Replication

- Replicate each shard across regions.
- Handle latency and consistency challenges.

**⚡ This requires code updates** for:

- Replica awareness (read/write split)
- Conflict resolution / sync strategies

#### 6️⃣ Caching & Async

- Add **caching layers** for frequent reads.
- Use **queues and batch processing** for writes.
- Accept **eventual inconsistency** for massive scale.

**⚡ This requires adding caching and async write strategies to the codebase.**

---


## Monitoring and Scaling Signals

### Built-in Metrics

- **Connections**: Acquisition times, success/failures
- **Pools**: Utilization, capacity
- **Cache**: Hit/miss, evictions
- **Errors**: Categorized rates
- **Performance**: Query durations

### Timeout Rates → Scaling Insights

Timeouts directly correlate with concurrency and capacity planning:

| Timeout Rate | Interpretation   | Suggested Action        |
| ------------ | ---------------- | ----------------------- |
| < 0.1%       | Normal load      | No action needed        |
| 0.1% - 1%    | Mild contention  | Review slow queries     |
| 1% - 5%      | High load        | Scale vertically (bigger DB/app servers) |
| > 5%         | Critical pressure| Scale horizontally (add servers) |

**Timeouts reflect concurrency limits.**  
When users start hitting timeouts, it signals that app servers are maxing out their connections. 

To serve more users:

✅ Increase app servers → spreads connections  
✅ Upgrade database → supports more total connections

---

## Notes

### MySQL Transaction Caveat

**Warning:**  
MySQL auto-commits DDL (`CREATE`, `ALTER`, `DROP`) even inside transactions.  
This means preceding SQL in the transaction cannot be rolled back — unlike PostgreSQL.

---

## Getting Started

To get started, initialize the database connection using your engine of choice (e.g. PostgreSQL, MySQL). Here's an example using PostgreSQL:

```python
# PostgreSQL connection
db = PostgresDatabase(
    database="my_database",
    host="localhost",
    port=5432,
    user="postgres",
    password="secret",
    alias="main_db",
    env="dev",
    connection_acquisition_timeout=10.0  # Optional timeout setting
)

# Sync usage with automatic transaction management
with db.sync_transaction() as conn:
    result = conn.execute_sync("SELECT * FROM users WHERE id = ?", (1,))
    conn.execute_sync("UPDATE users SET last_login = NOW() WHERE id = ?", (1,))
    # Automatic commit on success, rollback on exception

# Async usage with automatic transaction management
async def async_example():
    async with db.async_transaction() as conn:
        result = await conn.execute_async("SELECT * FROM users WHERE id = ?", (1,))
        await conn.execute_async("UPDATE users SET last_login = NOW() WHERE id = ?", (1,))
        # Automatic commit on success, rollback on exception

# Manual transaction control
async def manual_transaction_example():
    async with db.async_connection() as conn:
        # Check if already in transaction
        in_tx = await conn.in_transaction_async()
        if not in_tx:
            await conn.begin_transaction_async()
        
        try:
            # Execute queries
            await conn.commit_transaction_async()
        except Exception:
            await conn.rollback_transaction_async()
            raise

# Add resilience with circuit breaker and retry
@circuit_breaker(name="user_operations", failure_threshold=3)
@retry_with_backoff(max_retries=3, base_delay=0.1)
async def get_user(user_id):
    async with db.async_connection() as conn:
        result = await conn.execute_async(
            "SELECT * FROM users WHERE id = ?", 
            (user_id,),
            timeout=5.0,  # Query timeout in seconds
            tags={"operation": "get_user"}  # Optional query tags for logging/metrics
        )
        return result[0] if result else None

# Proper application shutdown
async def shutdown():
    # Release any active connections and close all pools
    await BaseDatabase.close_pool(timeout=30)
```

---

## API Reference

### Main Database Classes

#### `BaseDatabase`
Base class for all database implementations providing a unified interface.

```python
# General usage pattern
db = PostgresDatabase(database="my_db", user="user", password="pass")
```

| Method | Description |
|--------|-------------|
| `sync_connection()` | Context manager for sync operations |
| `async_connection()` | Context manager for async operations |
| `sync_transaction()` | Context manager with automatic transaction handling |
| `async_transaction()` | Async context manager with automatic transaction handling |
| `get_sync_connection()` | Get a sync connection directly (must release manually) |
| `get_async_connection()` | Get an async connection directly (must release manually) |
| `release_sync_connection()` | Release a sync connection obtained with get_sync_connection |
| `release_async_connection()` | Release an async connection obtained with get_async_connection |
| `is_environment_async()` | Check if running in an async environment |
| `close_pool()` | Class method to properly shut down connection pools |
| `check_for_leaked_connections()` | Identify connections held too long |
| `get_pool_status()` | Get detailed connection pool metrics |

#### Database-Specific Implementations

- `PostgresDatabase` - PostgreSQL implementation 
- `MySqlDatabase` - MySQL implementation
- `SqliteDatabase` - SQLite implementation

#### Factory Pattern

```python
# Create appropriate database instance without directly specifying the class
db = DatabaseFactory.create_database("postgres", config)
```

#### Connection Pooling Control

```python
# Properly shut down connection pools during application shutdown
async def shutdown():
    # Close one specific pool by hash
    await BaseDatabase.close_pool(config_hash="abc123", timeout=60)
    
    # Close all pools
    await BaseDatabase.close_pool(timeout=60)
    
# Get pool health status
health = await BaseDatabase.health_check_all_pools()

# Get usage metrics
metrics = BaseDatabase.get_pool_metrics()
```

### Resilience Tools

#### `CircuitBreaker`
Prevents cascading failures when a service is unavailable by temporarily blocking operations after detecting failures.

```python
@circuit_breaker(name="db_operations", failure_threshold=5)
async def database_operation():
    # Operations that might fail and should be circuit-broken
```

| Parameter | Description |
|-----------|-------------|
| `name` | Unique identifier for this circuit |
| `failure_threshold` | Number of failures before opening the circuit |
| `recovery_timeout` | Seconds to wait before attempting recovery |
| `half_open_max_calls` | Maximum calls allowed in half-open state |
| `window_size` | Time window to track failures |

**Direct CircuitBreaker Usage:**

```python
# Get existing or create new circuit breaker
breaker = CircuitBreaker.get_or_create("my_service", failure_threshold=5)

# Check if request should be allowed
if breaker.allow_request():
    try:
        # Perform operation
        result = make_request()
        breaker.record_success()
        return result
    except Exception as e:
        breaker.record_failure()
        raise
else:
    raise CircuitOpenError("Circuit is open, request blocked")
```

**CircuitBreaker States:**

| State | Description |
|-------|-------------|
| `CLOSED` | Normal operation, requests pass through |
| `OPEN` | Service unavailable, requests short-circuited |
| `HALF_OPEN` | Testing if service is back, limited requests |

#### `retry_with_backoff`
Retry operations with exponential backoff when temporary failures occur.

```python
@retry_with_backoff(max_retries=3, base_delay=0.1, total_timeout=30.0)
async def database_operation():
    # Operations that might need retrying
```

| Parameter | Description |
|-----------|-------------|
| `max_retries` | Maximum number of retry attempts |
| `base_delay` | Initial delay between retries in seconds |
| `max_delay` | Maximum delay between retries |
| `exceptions` | Tuple of exceptions to catch and retry |
| `total_timeout` | Maximum total time for all retries |

The decorator:
- Works on both sync and async functions
- Adds random jitter to delay times to prevent thundering herd
- Intelligently adjusts sleep times to respect total timeout
- Customizes which exceptions to retry (defaults to common database errors)

#### `track_slow_method`
Decorator to log performance insights for slow operations.

```python
@track_slow_method(threshold=2.0)
async def potentially_slow_operation():
    # Method will be logged if execution exceeds 2 seconds
```

Logs detailed information when methods exceed the specified threshold:
- Class and method name
- Execution time
- Arguments and keyword arguments (sanitized)
- Works with both sync and async methods

### Connection Management

#### `AsyncConnection` and `SyncConnection`
Abstract base classes defining standardized interfaces for database connections.

**Usage through context managers:**

```python
# Synchronous
with db.sync_connection() as conn:
    result = conn.execute_sync("SELECT * FROM users WHERE id = ?", (1,))

# Asynchronous
async with db.async_connection() as conn:
    result = await conn.execute_async("SELECT * FROM users WHERE id = ?", (1,))
```

**Transaction handling:**

```python
# Automatic transaction management (commit on success, rollback on exception)
async with db.async_transaction() as conn:
    await conn.execute_async("INSERT INTO users (name) VALUES (?)", ("Alice",))
    await conn.execute_async("UPDATE counts SET value = value + 1")

# Manual transaction management
async with db.async_connection() as conn:
    await conn.begin_transaction_async()  # Start transaction
    try:
        # Do work...
        await conn.commit_transaction_async()
    except Exception:
        await conn.rollback_transaction_async()
        raise
```

#### Key Connection Methods

| Method | Description |
|--------|-------------|
| `execute_sync/execute_async` | Execute a query with placeholders |
| `executemany_sync/executemany_async` | Execute multiple parameter sets |
| `begin_transaction_sync/begin_transaction_async` | Start a transaction |
| `commit_transaction_sync/commit_transaction_async` | Commit a transaction |
| `rollback_transaction_sync/rollback_transaction_async` | Rollback a transaction |
| `in_transaction_sync/in_transaction_async` | Check if in an active transaction |
| `close_sync/close_async` | Directly close the connection (bypass pool) |
| `get_raw_connection` | Access the underlying database driver connection |
| `get_version_details_sync/get_version_details_async` | Get database version info |
| `mark_active` | Update last activity timestamp |

#### `_auto_transaction` and `_auto_transaction_async`
Context managers used internally for automatic transaction handling:

```python
# Used internally by executemany methods
async with self._auto_transaction_async():
    # Operations that need transaction safety
```

### Connection Pool Management

#### `ConnectionPool` Interface
Abstract base class for database connection pools with standardized methods.

| Method | Description |
|--------|-------------|
| `acquire(timeout)` | Acquire a connection with optional timeout |
| `release(connection)` | Return a connection to the pool |
| `close(force, timeout)` | Close the pool (force=True for immediate shutdown) |
| `health_check()` | Check if the pool is healthy |
| `execute_on_pool(sql, params)` | Execute a query without explicit acquire/release |

#### Pool Properties

| Property | Description |
|----------|-------------|
| `min_size` | Minimum number of connections |
| `max_size` | Maximum number of connections |
| `size` | Current total number of connections |
| `in_use` | Number of checked-out connections |
| `idle` | Number of available connections |

#### `AsyncPoolManager`
Base class for async connection pool management.

| Method | Description |
|--------|-------------|
| `get_pool_status()` | Get detailed pool status information |
| `_initialize_pool_if_needed()` | Lazily initialize pool on first use |
| `_leak_detection_task()` | Background task to detect connection leaks |
| `check_for_leaked_connections()` | Find connections held too long |

```python
# Get pool status and metrics
status = db.get_pool_status()
print(f"Pool size: {status['current_size']}/{status['max_size']}")
print(f"Active connections: {status['active_connections']}")
print(f"Total acquired: {status['metrics']['total_acquired']}")
```

#### Automatic Pool Sizing

The library provides automatic connection pooling with:

- Automatic pool sizing based on system resources
- Connection health monitoring
- Leak detection and prevention
- Proper cleanup on application shutdown
- Built-in metrics
- Timeout handling

```python
# Optional: customize pool parameters
min_size, max_size = db._calculate_pool_size()
# Default sizing is based on CPU cores and available memory
```

### Advanced Tools

#### `StatementCache`
Thread-safe cache for prepared SQL statements with dynamic sizing.

```python
# Create a statement cache with custom sizing
cache = StatementCache(initial_size=100, min_size=50, max_size=500)

# Used internally, but can be accessed for diagnostics
hit_ratio = connection._statement_cache.hit_ratio

# Core methods
sql_hash = StatementCache.hash(sql)
statement = cache.get(sql_hash)
cache.put(sql_hash, statement, sql)
```

Features:
- Dynamic resizing based on hit ratio and usage patterns
- LRU (Least Recently Used) eviction policy
- Performance metrics tracking
- Thread-safe operations

#### `SqlParameterConverter` Family
Standardized query parameter handling across different database engines, with specialized implementations:

- `PostgresAsyncConverter` - Convert placeholders for asyncpg ($1, $2, etc.)
- `PostgresSyncConverter` - Convert placeholders for psycopg2 (%s)
- `MySqlConverter` - Convert placeholders for MySQL (%s)
- `SqliteConverter` - Handle SQLite placeholders (no conversion needed)

```python
# Convert standard ? placeholders to database-specific format
converter = PostgresAsyncConverter()
converted_sql, params = converter.convert_query("SELECT * FROM users WHERE id = ?", (1,))
# Result: "SELECT * FROM users WHERE id = $1", (1,)

# Add query timeout if supported
timeout_sql = converter.make_timeout_sql(10.0)  # 10 second timeout
# For PostgreSQL: "SET LOCAL statement_timeout = 10000"

# Add query tags as SQL comments
comment_sql = converter.make_comment_sql({"request_id": "abc123"})
# Result: "/* request_id=abc123 */"
```

#### `DatabaseConfig`
Holds database connection configuration parameters.

```python
# Create a database config
config = DatabaseConfig(
    database="my_database",
    host="db.example.com",
    port=5432,
    user="postgres",
    password="secret",
    alias="main_db",
    env="prod"
)

# Access configuration
connection_params = config.config()  # Get dict for driver
db_name = config.database()
friendly_name = config.alias()
host = config.host()
environment = config.env()
config_hash = config.hash()  # Unique identifier for this configuration
```

#### Utility Decorators

##### `overridable`
Marks a method as overridable for documentation / IDE purposes.

```python
@overridable
def method_that_can_be_overridden():
    # Default implementation that subclasses can override
```

##### `CircuitOpenError`
Exception raised when a circuit breaker prevents an operation.

```python
try:
    result = perform_operation()
except CircuitOpenError as e:
    # Handle circuit open condition
    logger.warning(f"Operation prevented: {e}")
```

### Entity Manager API

The `EntityManager` class provides a high-level abstraction for managing entities stored in the database. It offers automatic schema evolution, serialization/deserialization, and history tracking.

#### Core Features

- **Auto Schema Creation**: Tables and columns created automatically based on entity structure
- **Type Detection & Validation**: Automatic type inference and validation
- **JSON Serialization**: Complex types (dict, list, etc.) stored as JSON
- **History Tracking**: Optional versioning with rollback capability
- **Soft Deletion**: Entities can be marked as deleted without removing data
- **Query Builder**: Fluent query API for complex queries

#### Usage Examples

```python
# Basic Entity Management
class MyDatabase(PostgresDatabase, EntityManager):
    pass

# Initialize with both database connection and entity management
db = MyDatabase(database="my_db", user="user", password="pass")

# Create and save an entity
user = {
    "id": "user-123",  # Optional, auto-generated if not provided
    "name": "John Doe",
    "email": "john@example.com",
    "settings": {"theme": "dark", "notifications": True},  # Complex types handled automatically
    "tags": ["customer", "premium"]
}

# Synchronous save
user_id = db.save_entity_sync("users", user, user_id="admin", comment="Initial creation")

# Asynchronous save
user_id = await db.save_entity_async("users", user, user_id="admin", comment="Initial creation")

# Retrieve entities
user = db.get_entity_sync("users", "user-123")
users = db.get_entities_sync("users", {"status": "active"}, limit=10)

user = await db.get_entity_async("users", "user-123")
users = await db.get_entities_async("users", {"status": "active"}, limit=10)

# Delete entities
db.delete_entity_sync("users", "user-123", soft_delete=True, user_id="admin", comment="User requested deletion")
await db.delete_entity_async("users", "user-123", soft_delete=True)

# Restore soft-deleted entities
db.restore_entity_sync("users", "user-123")
await db.restore_entity_async("users", "user-123")

# Enable history tracking
db.enable_history_sync("users")
await db.enable_history_async("users")

# Access version history
history = db.get_entity_history_sync("users", "user-123", limit=10)
history = await db.get_entity_history_async("users", "user-123", limit=10)

# Rollback to a previous version
db.rollback_to_version_sync("users", "user-123", 3, user_id="admin", comment="Rollback to fix data issue")
await db.rollback_to_version_async("users", "user-123", 3)
```

#### Query Builder

```python
# Synchronous Query Builder
users = db.query_builder_sync("users")
           .where("status", "active")
           .where("age", ">", 21)
           .order_by("last_login", "DESC")
           .limit(10)
           .offset(20)
           .execute()

# Count query
count = db.query_builder_sync("users")
           .where("status", "active")
           .count()

# First record only
user = db.query_builder_sync("users")
          .where("email", "john@example.com")
          .first()

# Asynchronous Query Builder
users = await db.query_builder_async("users")
                 .where("status", "active")
                 .order_by("created_at", "DESC")
                 .limit(10)
                 .execute()
```

#### Entity Storage and Retrieval Methods

| Method | Description |
|--------|-------------|
| `save_entity_sync/save_entity_async` | Create or update an entity |
| `save_entities_sync/save_entities_async` | Create or update multiple entities in a transaction |
| `get_entity_sync/get_entity_async` | Get an entity by ID |
| `get_entity_by_sync/get_entity_by_async` | Get an entity by any field value |
| `get_entities_sync/get_entities_async` | Get multiple entities with filtering |
| `count_entities_sync/count_entities_async` | Count entities matching criteria |
| `delete_entity_sync/delete_entity_async` | Delete or soft-delete an entity |
| `update_entity_fields_sync/update_entity_fields_async` | Update specific fields of an entity |
| `entity_exists_sync/entity_exists_async` | Check if an entity exists |
| `restore_entity_sync/restore_entity_async` | Restore a soft-deleted entity |

#### History and Versioning Methods

| Method | Description |
|--------|-------------|
| `enable_history_sync/enable_history_async` | Enable history tracking for an entity type |
| `get_entity_history_sync/get_entity_history_async` | Get version history of an entity |
| `rollback_to_version_sync/rollback_to_version_async` | Revert an entity to a previous version |

#### Schema and Metadata Methods

| Method | Description |
|--------|-------------|
| `list_entities_sync/list_entities_async` | List all entity types in the database |
| `get_entity_schema_sync/get_entity_schema_async` | Get field names and types for an entity |
| `to_json/from_json` | Convert entities to/from JSON |
| `execute_raw_sql_sync/execute_raw_sql_async` | Execute raw SQL for advanced needs |

#### Internals

The `EntityManager` class handles:

- **Automatic Table Creation**: Creates tables and metadata tables as needed
- **Column Management**: Adds columns when new fields appear in entities
- **Type Inference**: Determines the most appropriate type for each field
- **Serialization**: Converts complex types to/from string representations
- **Transaction Safety**: Ensures ACID compliance with proper transaction handling
- **Database Dialect Handling**: Supports different SQL dialects (PostgreSQL, MySQL, SQLite)

> **Note**: MySQL has a limitation with DDL statements (CREATE, ALTER) within transactions. They cause an implicit commit, which can break transaction atomicity. Be cautious when saving entities that might trigger schema changes in a MySQL transaction.

```python
# Example: What happens internally when you save an entity
# 1. Prepare entity (add ID, timestamps, user info)
# 2. Check if tables exist, create if needed
# 3. Check for missing columns, add if needed
# 4. Serialize values (complex types to JSON)
# 5. Generate and execute upsert SQL
# 6. Save to history table if enabled
# 7. Return entity ID
```