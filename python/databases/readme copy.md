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
config = DatabaseConfig(
    database="my_database",
    host="localhost",
    port=5432,
    user="postgres",
    password="secret",
    alias="main_db",
    env="dev",
    connection_acquisition_timeout=10.0  # Optional timeout setting
)

# Create appropriate database instance without directly specifying the class
db = DatabaseFactory.create_database("postgres", config)

async with db.async_connection() as conn:   
    await conn.begin_transaction()    
    try:
        result = await conn.execute(
            "SELECT * FROM users WHERE id = ?", 
            ('user_id',),
            timeout=5.0,  # Query timeout in seconds
            tags={"operation": "get_user"}  # Optional query tags for logging/metrics
        )
        await conn.commit_transaction()
    except Exception:
        await conn.rollback_transaction()
        raise

await PoolManager.close_pool(config_hash=config.hash(),timeout=30) # Will close the pool created for this specific config, brute forcing it after 30 seconds
```

---

### Extension

To add a new backend (say Oracle);

```python

import {oracle_asyn_driver} as async_driver
import {oracle_sync_driver} as sync_driver

class OracleSqlGenerator(SqlGenerator):
    def convert_query_to_native(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        if not params:
            return sql, []
        new_sql = sql # replace "?" as needed
        return new_sql, params

    def get_timeout_sql(self, timeout: Optional[float]) -> Optional[str]:
        if timeout:
            return f"SET LOCAL statement_timeout = {int(timeout * 1000)}" # adjust sql as needed
        return None  

class OracleConnectionPool(ConnectionPool):
    def __init__(self, pool, timeout: float = 10.0):
        self._pool = pool # the async Oracle driver pool, created by _create_pool in OracleDatabase
        self._timeout = timeout # default connection acquisition in seconds
    
    async def acquire(self, timeout: Optional[float] = None) -> Any:
        # need to aquire from native pool, but also handle timeout, e.g. like so:
        """
        timeout = timeout if timeout is not None else self._timeout
        try:
            return await asyncio.wait_for(self._pool.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for Oracle connection after {timeout}s")
        """
        pass

    async def release(self, connection: Any) -> None:
        # probably similar to: await self._pool.release(connection)
        pass

    async def close(self, force: bool = False, timeout: Optional[float] = None) -> None:
         # probably similar to: await self._pool.close(cancel_tasks=force)
        pass

    async def _test_connection(self, connection):
        # probably similar to: await connection.execute("SELECT 1")
        pass
    
    @property
    def min_size(self) -> int:
        # probably similar to: return self._pool.minsize
        pass
    
    @property
    def max_size(self) -> int:
        # probably similar to: return self._pool.maxsize
        pass
    
    @property
    def size(self) -> int:       
        # probably similar to: return self._pool.size
        pass
    
    @property
    def in_use(self) -> int:      
        # probably similar to: return self._pool.size - len(self._pool._free)
        pass
    
    @property
    def idle(self) -> int:     
        # probably similar to: return len(self._pool._free)
        pass

class OracleAsyncConnection(AsyncConnection):
    def __init__(self, conn):
        self._conn = conn # The async Oracle driver's connection (generated in the Pool acquire method)
        self._param_converter = OracleSqlGenerator()

    @property
    def parameter_converter(self) -> SqlGenerator:
        return self._param_converter

    async def _prepare_statement_async(self, native_sql: str) -> Any:
        pass

    async def _execute_statement_async(self, statement: Any, params=None) -> Any:
        pass
    
    async def in_transaction(self) -> bool:
        pass

    async def begin_transaction(self):
        # probably similar to: await self._conn.execute("BEGIN")
        pass

    async def commit_transaction(self):
        # probably similar to: await self._conn.commit()
        pass

    async def rollback_transaction(self):
        # probably similar to: await self._conn.rollback()
        pass

    async def close(self):
        # probably similar to: await self._conn.close()
        pass

    async def get_version_details(self) -> Dict[str, str]:
        return {'db_server_version':'to do', 'db_driver':'to do'}

class OracleSyncConnection(SyncConnection):
    # similar to the Async version

class OracleDatabase(ConnectionManager):
    def _create_sync_connection(self, config: Dict):     
        # probably: return sync_driver.connect(**config)
        pass      

    async def _create_pool(self, config: Dict) -> ConnectionPool:  
        # probably:
        """     
        min_size, max_size = self._calculate_pool_size()
        raw_pool = await async_driver.create_pool(
            min_size=min_size, 
            max_size=max_size, 
            command_timeout=60.0, 
            **config
        )
        return OracleConnectionPool(
            raw_pool, 
            timeout=self.connection_acquisition_timeout
        )
        """
        pass

    def _wrap_async_connection(self, raw_conn):
        return OracleAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        return OracleSyncConnection(raw_conn)

```
---

## 📖 Public API

### class `DatabaseConfig`
Base configuration object for databases.

|Decorators| Method |Args|Returns| Category| Description | 
| ------------------------------ |---| --|---| --| -------------------------------- | 
|| `config` ||`Dict[str, Any]`|| Return config dict containing host, port, database, user, and password. | 
|| `database` ||`str`|| Get database name. | 
|| `alias` | |`str`||Get alias, which is a friendly name for the connection. | 
|| `host` | |`str`||Get host. | 
|| `port` | |`int`||Get port. | 
|| `env` | |`str`||Get environment (e.g. 'prod', 'dev', 'test'). | 
|| `hash` || `str`||Get unique MD5 hash for pool keying based on all configuration parameters except password. |

-------
### class `PoolManager`
Abstract base class to manage the lifecycle of asynchronous connection pools. Pools are created lazily, shared across instances with the same configuration, and can be properly closed during application shutdown.

|Decorators| Method |Args|Returns| Category| Description | 
| ------------------------------ |---| --|---| --| -------------------------------- | 
|<code style="background-color:pink">@async</code> <code style="background-color:lightblue">@classmethod</code>| `close_pool` |`config_hash: str=None` `timeout: float=60`| | Resources Management| Close all or specific pools with proper cleanup. First prevents new connections from being acquired, then attempts to gracefully commit and release all active connections before closing the pool. | 
|| `get_pool_status` ||`Dict[str, Any]`|Diagnostic|Returns comprehensive status information about the connection pool (initialized, alias, hash, sizes, metrics, etc.) | 
|<code style="background-color:lightblue">@classmethod</code>|`health_check_all_pools` || `Dict[str, bool]`|Diagnostic|Checks the health of all connection pools.|
|<code style="background-color:lightblue">@classmethod</code>|`get_pool_metrics`| `config_hash=None` | `Dict[str, Any]`|Diagnostic|Returns metrics (total_acquired, total_released, current_active, peak_active, errors, timeouts, etc.) for specific or all pools.|
|<code style="background-color:pink">@async</code>| `check_for_leaked_connections`| `threshold_seconds=300` | `List[Tuple[AsyncConnection, float, str]]`|Diagnostic|Returns a list of (connection, duration, stack) tuples for connections that have been active for longer than the threshold.|

-------
### class `ConnectionManager`(<a href="#class-databaseconfig">DatabaseConfig</a>,<a href="#class-poolmanager">PoolManager</a>)
Manages synchronized and asynchronous database connection lifecycles. Provides a unified interface for obtaining both sync and async database connections, with proper resource management through context managers. Handles connection pooling for async connections and caching for sync connections.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|| `get_sync_connection` ||<a href="#class-syncconnection">`SyncConnection`</a>|Connection Management| Returns a synchronized database connection. Returns an existing connection if one is already cached, or creates a new one if needed. |
|| `release_sync_connection` |||Connection Management| Closes and releases the cached synchronous connection. The next call to get_sync_connection() will create a new connection. |
|| `sync_connection` ||<a href="#class-syncconnection">`SyncConnection`</a>|Connection Management| Context manager for safe synchronous connection usage that ensures proper release of resources. |
|<code style="background-color:pink">@async</code>| `get_async_connection` ||<a href="#class-asyncconnection">`AsyncConnection`</a>|Connection Management| Acquires an asynchronous connection from the pool. Ensures the connection pool is initialized, then acquires a connection from it. |
|<code style="background-color:pink">@async</code>| `release_async_connection` |`async_conn:`<a href="#class-asyncconnection">`AsyncConnection`</a>||Connection Management| Releases an asynchronous connection back to the pool when no longer needed to make it available for reuse. |
|<code style="background-color:pink">@async</code>| `async_connection` ||<a href="#class-asyncconnection">`AsyncConnection`</a>|Connection Management| Async context manager for safe asynchronous connection usage that ensures proper release of resources. |
|| `is_environment_async` || `bool` |Environment Detection| Determines if code is running in an async environment by checking if an event loop is running in the current thread. |

#### Current implementations: `PostgresDatabase`, `Mysqldatabase`, `SqliteDatabase`

-------
### class `AsyncConnection`
Abstract base class defining the interface for asynchronous database connections.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:lightblue">@property</code>| `parameter_converter` ||<a href="#class-sqlgenerator">`SqlGenerator`</a>|Configuration| Returns the parameter converter for this connection. |
|<code style="background-color:pink">@async</code>| `in_transaction` ||`bool`|Transaction Management| Return True if connection is in an active transaction. |
|<code style="background-color:pink">@async</code>| `begin_transaction` |||Transaction Management| Asynchronously begins a database transaction. |
|<code style="background-color:pink">@async</code>| `commit_transaction` |||Transaction Management| Asynchronously commits the current transaction. |
|<code style="background-color:pink">@async</code>| `rollback_transaction` |||Transaction Management| Asynchronously rolls back the current transaction. |
|<code style="background-color:pink">@async</code>| `close` |||Resource Management| Asynchronously closes the database connection. |
|<code style="background-color:pink">@async</code>| `get_version_details` ||`Dict[str, str]`|Diagnostic| Returns {'db_server_version', 'db_driver'} with version information. |
|<code style="background-color:pink">@async</code>| `execute` |`sql:str` `params:tuple` `timeout:float=None` `tags:Dict[str, Any]=None`|`List[Tuple]`|Query Execution| Asynchronously executes a SQL query with standard ? placeholders. |
|<code style="background-color:pink">@async</code>| `executemany` |`sql:str` `param_list:List[tuple]` `timeout:float=None` `tags:Dict[str, Any]=None`|`List[Tuple]`|Query Execution| Asynchronously executes a SQL query multiple times with different parameters. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `get_entity` |`entity_name:str` `entity_id:str` `include_deleted:bool=False` `deserialize:bool=False`|`Optional[Dict[str,Any]]`| Entity | Fetch an entity by ID. Returns None if not found. If deserialize=True, converts field values to appropriate Python types based on metadata. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `save_entity` |`entity_name:str` `entity:Dict[str,Any]` `user_id:str=None` `comment:str=None`|`Dict[str,Any]`| Entity | Save an entity (create or update). Adds id, created_at, updated_at, and other system fields. For updates, only updates the provided fields. Adds an entry to the history table. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `save_entities` |`entity_name:str` `entities:List[Dict[str,Any]]` `user_id:str=None` `comment:str=None`|`List[str]`| Entity | Save a list of entities in bulk. Returns their ids. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `delete_entity` |`entity_name:str` `entity_id:str` `user_id:str=None` `permanent:bool=False`|`bool`| Entity | Delete an entity. By default performs a soft delete (sets deleted_at), but can permanently remove the record if permanent=True. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `restore_entity` |`entity_name:str` `entity_id:str` `user_id:str=None`|`bool`| Entity | Restore a soft-deleted entity by clearing the deleted_at field. Returns True if successful. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `find_entities` |`entity_name:str` `where_clause:str=None` `params:Tuple=None` `order_by:str=None` `limit:int=None` `offset:int=None` `include_deleted:bool=False` `deserialize:bool=False`|`List[Dict[str,Any]]`| Entity | Query entities with flexible filtering. Returns a list of matching entities. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `count_entities` |`entity_name:str` `where_clause:str=None` `params:Tuple=None` `include_deleted:bool=False`|`int`| Entity | Count entities matching the criteria. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `get_entity_history` |`entity_name:str` `entity_id:str` `deserialize:bool=False`|`List[Dict[str,Any]]`| Entity | Get the history of all previous versions of an entity. Returns a list of historical entries ordered by version. |
|<code style="background-color:pink">@async</code> <code style="background-color:lightgreen">@auto_transaction</code>| `get_entity_by_version` |`entity_name:str` `entity_id:str` `version:int` `deserialize:bool=False`|`Optional[Dict[str,Any]]`| Entity | Get a specific version of an entity from its history or None if nout found. |



#### Current implementations: `PostgresAsyncConnection`, `MysqlAsyncConnection`, `SqliteAsyncConnection`

-------
### class `SyncConnection`
Abstract base class defining the interface for synchronous database connections.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:lightblue">@property</code>| `parameter_converter` ||<a href="#class-sqlgenerator">`SqlGenerator`</a>|Configuration| Returns the parameter converter for this connection. |
|| `in_transaction` ||`bool`|Transaction Management| Return True if connection is in an active transaction. |
|| `begin_transaction` |||Transaction Management| Begins a database transaction. |
|| `commit_transaction` |||Transaction Management| Commits the current transaction. This permanently applies all changes made since begin_transaction() was called. |
|| `rollback_transaction` |||Transaction Management| Rolls back the current transaction. This discards all changes made since begin_transaction() was called. |
|| `close` |||Resource Management| Closes the database connection. The connection should not be used after calling this method. |
|| `get_version_details` ||`Dict[str, str]`|Diagnostic| Returns {'db_server_version', 'db_driver'} with version information. |
|| `execute` |`sql:str` `params:tuple` `timeout:float=None` `tags:Dict[str, Any]=None`|`List[Tuple]`|Query Execution| Synchronously executes a SQL query with standard ? placeholders. |
|| `executemany` |`sql:str` `param_list:List[tuple]` `timeout:float=None` `tags:Dict[str, Any]=None`|`List[Tuple]`|Query Execution| Synchronously executes a SQL query multiple times with different parameters. |

#### Current implementations: `PostgresSyncConnection`, `MysqlSyncConnection`, `SqliteSyncConnection`

-----
### class `SqlGenerator`
Abstract base class for SQL parameter placeholder conversion and sql generation for usual operations. This class provides a way to convert between a standard format (? placeholders) and database-specific formats for positional parameters.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|| `convert_query_to_native` |`sql:str` `params:Tuple=None`|`Tuple[str,Any]`|Query Conversion| Converts a standard SQL query with ? placeholders to a database-specific format. |
|| `get_timeout_sql` |`timeout:float=None`|`Optional[str]`|Query Conversion| Return a SQL statement to enforce query timeout if applicable to the database. |
|| `get_comment_sql` |`tags:Dict[str,Any]=None`|`Optional[str]`|Query Conversion| Return SQL comment with tags if supported by database. |


#### Current implementations: `PostgresSqlGenerator`, `MysqlSqlGenerator`, `SqliteSqlGenerator`

------
### class `DatabaseFactory`
Factory for creating database instances.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:lightblue">@staticmethod</code>| `create_database` |`db_type:str` <code>db_config:<a href="#class-databaseconfig">DatabaseConfig</a></code>|<a href="#class-connectionmanagerdatabaseconfigpoolmanager">`ConnectionManager`</a>|Factory| Factory method to create the appropriate database instance (PostgreSQL, MySQL, SQLite). |

## 📖 Utilities


### class `ConnectionPool`
Abstract connection pool interface that standardizes behavior across database drivers. This interface provides a consistent API for connection pool operations, regardless of the underlying database driver. It abstracts away driver-specific details and ensures that all pools implement the core functionality needed by the connection management system.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:pink">@async</code>| `acquire` |`timeout: Optional[float] = None`|`Any`|Connection Management| Acquires a connection from the pool with optional timeout. |
|<code style="background-color:pink">@async</code>| `release` |`connection: Any`||Connection Management| Releases a connection back to the pool. |
|<code style="background-color:pink">@async</code>| `close` |`force: bool = False, timeout: Optional[float] = None`||Resource Management| Closes the pool and all connections. When force=False, waits for all connections to be released naturally. When force=True, terminates any executing operations (may cause data loss). |
|<code style="background-color:pink">@async</code>| `health_check` ||`bool`|Diagnostic| Checks if the pool is healthy by testing a connection. |
|<code style="background-color:lightblue">@property</code>| `min_size` ||`int`|Configuration| Gets the minimum number of connections the pool maintains. |
|<code style="background-color:lightblue">@property</code>| `max_size` ||`int`|Configuration| Gets the maximum number of connections the pool can create. |
|<code style="background-color:lightblue">@property</code>| `size` ||`int`|Diagnostic| Gets the current number of connections in the pool (both in-use and idle). |
|<code style="background-color:lightblue">@property</code>| `in_use` ||`int`|Diagnostic| Gets the number of connections currently in use (checked out from the pool). |
|<code style="background-color:lightblue">@property</code>| `idle` ||`int`|Diagnostic| Gets the number of idle connections in the pool (available for checkout). |


-----
### class `StatementCache`
Thread-safe cache for prepared SQL statements with dynamic sizing.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:lightblue">@staticmethod</code>| `hash` |`sql: str`|`str`|Utility| Hash a SQL statement for cache lookup using MD5. |
|<code style="background-color:lightblue">@property</code>| `hit_ratio` ||`float`|Diagnostic| Calculate the cache hit ratio (hits / total operations). |
|| `get` |`sql_hash`|`Optional[Tuple[Any, str]]`|Cache Management| Get a prepared statement from the cache in a thread-safe manner. |
|| `put` |`sql_hash, statement, sql`||Cache Management| Add a prepared statement to the cache in a thread-safe manner. |

-----
### class `CircuitBreaker`
Circuit breaker implementation that can be used as a decorator for sync and async methods. The circuit breaker pattern prevents cascading system failures by monitoring error rates. If too many failures occur within a time window, the circuit 'opens' and immediately rejects new requests without attempting to call the failing service. After a recovery timeout period, the circuit transitions to 'half-open' state, allowing a few test requests through. If these succeed, the circuit 'closes' and normal operation resumes; if they fail, the circuit opens again to protect system resources.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:lightblue">@classmethod</code>| `get_or_create` |`name, failure_threshold=5, recovery_timeout=30.0, half_open_max_calls=3, window_size=60.0`|`CircuitBreaker`|Factory| Get an existing circuit breaker or create a new one with the specified parameters. |
|<code style="background-color:lightblue">@property</code>| `state` ||`CircuitState`|State| Get the current state of the circuit breaker (CLOSED, OPEN, or HALF_OPEN). |
|| `record_success` |||State Management| Record a successful call through the circuit breaker. |
|| `record_failure` |||State Management| Record a failed call through the circuit breaker. |
|| `allow_request` ||`bool`|State Management| Check if a request should be allowed through the circuit breaker. |

-----
### Functions

|Decorators| Function |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|| `circuit_breaker` |`name=None, failure_threshold=5, recovery_timeout=30.0, half_open_max_calls=3, window_size=60.0`|`Callable`|Resilience| Decorator that applies circuit breaker pattern to a function or method. |
|| `retry_with_backoff` |`max_retries=3, base_delay=0.1, max_delay=10.0, exceptions=None, total_timeout=30.0`|`Callable`|Resilience| Decorator for retrying functions with exponential backoff on specified exceptions. |
|| `track_slow_method` |`threshold=2.0`|`Callable`|Instrumentation| Decorator that logs a warning if the execution of the method took longer than the threshold (in seconds). |
|| `overridable` |`method`|`Callable`|Documentation| Marks a method as overridable for documentation / IDE purposes. |