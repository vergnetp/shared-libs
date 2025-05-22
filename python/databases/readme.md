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

This library offers a simple yet powerful **abstraction layer** that makes database interactions easy and consistent across different engines such as **PostgreSQL, MySQL**, and **SQLite**.
Developers can connect to and use databases through a unified API — without worrying about the low-level details like connection pooling, retries, timeouts, or resilience strategies.
Under the hood, the solution takes care of:

- **Connection pooling and reuse**
- **Query retries with backoff**
- **Timeouts and stuck query protection**
- **Automatic failover and recovery**
- **Transaction integrity**
- **Metrics and slow query insights**
- **Circuit breaker protection**
- **Entity framework with automatic schema management**

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
- Accept **eventual consistency** for massive scale.

**⚡ This requires adding caching and async write strategies to the codebase.**

---

## Monitoring and Scaling Signals

### Built-in Metrics

- **Connections**: Acquisition times, success/failures
- **Pools**: Utilization, capacity
- **Cache**: Hit/miss, evictions
- **Errors**: Categorized rates
- **Performance**: Query durations
- **Circuit Breakers**: State changes, failure rates

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

## SQL Conventions

This layer works with multiple database backends. To write portable, safe SQL:

### Table/Column Names
* Universal: Use `[column_name]` with square brackets
* Native: Or use database-specific quoting (`"name"` PostgreSQL, `` `name` `` MySQL)

### Parameters 
* Universal: Use `?` for all value placeholders
* Native: Or use database-specific placeholders (`$1` PostgreSQL, `%s` MySQL)

The system automatically translates between formats, handling SQL keywords safely and preventing injection attacks.

Need a literal `?` in your SQL? Use double question marks `??`.

## MySQL Transaction Caveat

**Warning:**  
MySQL auto-commits DDL (`CREATE`, `ALTER`, `DROP`) even inside transactions.  
This means preceding SQL in the transaction cannot be rolled back — unlike PostgreSQL.

---

## Entity Framework

The system includes a powerful Entity Framework that provides:

- **Automatic schema creation** - Tables, metadata, and history tables created on first use
- **Dynamic schema evolution** - New fields added automatically when entities are saved
- **Type inference and serialization** - Handles complex Python types (datetime, dict, list, etc.)
- **Versioning and history** - Complete audit trail of all changes
- **Soft deletes** - Mark records as deleted without losing data
- **Flexible querying** - Rich query interface with filtering, sorting, pagination
- **Batch operations** - Efficient bulk insert/update operations

### Entity Usage Examples

```python
# Save an entity (creates table automatically)
user = await conn.save_entity("users", {
    "name": "John Doe",
    "email": "john@example.com", 
    "preferences": {"theme": "dark", "language": "en"},  # Complex types handled automatically
    "created_date": datetime.now()
})

# Get entity by ID
retrieved = await conn.get_entity("users", user['id'], deserialize=True)

# Query entities with filtering
active_users = await conn.find_entities(
    "users",
    where_clause="status = ? AND created_date > ?",
    params=("active", datetime.now() - timedelta(days=30)),
    order_by="created_date DESC",
    limit=50,
    deserialize=True
)

# Update with history tracking
await conn.save_entity("users", {
    "id": user['id'],
    "name": "John Smith",  # Name changed
    "status": "premium"    # New field added automatically
}, user_id="admin", comment="Upgraded to premium")

# View complete history
history = await conn.get_entity_history("users", user['id'])

# Restore previous version
old_version = await conn.get_entity_by_version("users", user['id'], version=1)
await conn.save_entity("users", old_version)
```

---

## Configuration and Timeouts

The system provides comprehensive timeout configuration:

```python
config = DatabaseConfig(
    database="my_database",
    host="localhost",
    port=5432,
    user="postgres",
    password="secret",
    alias="main_db",
    env="dev",
    connection_acquisition_timeout=10.0,  # Time to get connection from pool
    pool_creation_timeout=30.0,           # Time to initialize pool
    query_execution_timeout=60.0,         # Default timeout for SQL queries
    connection_creation_timeout=15.0      # Time to create individual connections
)
```

Each timeout serves a specific purpose:
- **connection_acquisition_timeout**: How long to wait when the pool is busy
- **pool_creation_timeout**: How long to wait for initial pool setup
- **query_execution_timeout**: Default timeout for SQL operations (can be overridden per query)
- **connection_creation_timeout**: How long to wait for individual database connections

---

## Getting Started

To get started, initialize the database connection using your engine of choice (e.g. PostgreSQL, MySQL, SQLite). Here's an example using PostgreSQL:

```python
config = DatabaseConfig(
    database="my_database",
    host="localhost",
    port=5432,
    user="postgres",
    password="secret",
    alias="main_db",
    env="dev",
    connection_acquisition_timeout=10.0,  # Optional timeout setting
    pool_creation_timeout=30.0,           # Optional timeout setting
    query_execution_timeout=60.0,         # Optional timeout setting
    connection_creation_timeout=15.0      # Optional timeout setting
)

db = DatabaseFactory.create_database("postgres", config)

async with db.async_connection() as conn:   
    await conn.begin_transaction()    
    try:
        # Entity operations with automatic schema management
        users = await conn.save_entities("users", [
            {'name': 'Phil', 'age': 30},
            {'name': 'Karen', 'surname': 'Brown', 'age': 25}
        ])
        uid = users[0].get('id', None)
        
        # Direct SQL execution
        result = await conn.execute(
            "SELECT * FROM [users] WHERE [id] = ?", 
            (uid,),
            timeout=5.0,  # Query timeout in seconds
            tags={"operation": "get_user"}  # Optional query tags for logging/metrics
        ) 
        
        # Update entity with new fields (schema evolves automatically)
        await conn.save_entity("users", {
            'id': uid, 
            'name': 'Bob', 
            'age': 24,
            'department': 'Engineering'  # New field added automatically
        })
        
        # Get with automatic deserialization
        result = await conn.get_entity("users", uid, deserialize=True)
        # {'name': 'Bob', 'surname': None, 'age': 24, 'department': 'Engineering', 'id': '...', 'updated_at': datetime(...)}
        
        # Query with filtering and pagination
        engineers = await conn.find_entities(
            "users",
            where_clause="[department] = ?",
            params=("Engineering",),
            order_by="[name] ASC",
            limit=10,
            deserialize=True
        )
        
        # View complete change history
        history = await conn.get_entity_history("users", uid, deserialize=False)
        
        # Restore previous version
        old_version = await conn.get_entity_by_version("users", uid, 1)        
        await conn.save_entity("users", old_version)        
        
        result = await conn.get_entity("users", uid)
        
        await conn.commit_transaction()
    except Exception:
        await conn.rollback_transaction()
        raise

await PoolManager.close_pool(config_hash=config.hash(), timeout=30)
```

---

## Resilience Features

The system includes comprehensive resilience patterns:

### Circuit Breakers
Automatic protection against cascading failures:
```python
# Circuit breakers are applied automatically to all database operations
# Opens after 5 failures, recovers after 30 seconds
async with db.async_connection() as conn:
    result = await conn.execute("SELECT * FROM users")  # Protected by circuit breaker
```

### Retry with Backoff
Automatic retry for transient failures:
```python
# Database operations automatically retry on connection failures
# with exponential backoff (3 retries, up to 10s delay)
```

### Timeout Control
Multiple levels of timeout protection:
```python
# Query-specific timeout
result = await conn.execute("SELECT * FROM big_table", timeout=30.0)

# Connection acquisition timeout (from config)
# Pool creation timeout (from config)
# Individual connection timeout (from config)
```

### Performance Monitoring
Built-in slow query detection and profiling:
```python
# Queries taking longer than 2 seconds are automatically logged
# with full argument and timing information
```

---

## Extension

To add a new backend (say Oracle), you need to write the implementation of a few classes:
* Step 1) <a href="#class-sqlgenerator">`SqlGenerator`</a>: `convert_query_to_native` `get_timeout_sql`
* Step 2) <a href="#class-connectionpool">`ConnectionPool`</a>: `__init__` `acquire` `release` `close` `_test_connection` `min_size` `max_size` `size` `in_use` `idle`
* Step 3) <a href="#class-poolmanager">`PoolManager`</a>: `_create_pool`
* Step 4) <a href="#class-asyncconnection">`AsyncConnection`</a>: `__init__` `sql_generator` `_prepare_statement_async` `_execute_statement_async` `in_transaction` `begin_transaction` `commit_transaction` `rollback_transaction` `close` `get_version_details`
* Step 5) <a href="#class-syncconnection">`SyncConnection`</a>: `__init__` `sql_generator` `_prepare_statement_sync` `_execute_statement_sync` `in_transaction` `begin_transaction` `commit_transaction` `rollback_transaction` `close` `get_version_details`
* Step 6) <a href="#class-connectionmanager">`ConnectionManager`</a>: `_create_sync_connection` `_wrap_async_connection` `_wrap_sync_connection`

<br>

**Notes**: in the connection classes, the sql_generator property should return an instance of the class defined in Step 1.

To add the Entity Framework, you will need to define the relevant sql for the backend: simply add <a href="#class-sqlentitygenerator">`SqlEntityGenerator`</a> in the inheritance list of the class defined in Step 1 and define all the needed sql (`get_upsert_sql` etc.).
You also need to add `EntityAsyncMixin` and `EntitySyncMixin` to the `AsyncConnection` and `SyncConnection` (step 4 and 5).

```python
import {oracle_asyn_driver} as async_driver
import {oracle_sync_driver} as sync_driver

# STEP 1
class OracleSqlGenerator(SqlGenerator, SqlEntityGenerator):
    def escape_identifier(self, identifier: str) -> str:      
        return f'"{identifier}"' # or whatever is complient for Oracle

    def _convert_parameters(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        new_sql = sql # replace "??" as "?" and "?" as oracle placeholder for the driver (e.g. ":1")
        return new_sql, params

    # Entity specific sqls:

    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        pass

    # .. and all the other Entity specific sqls generation methods

# STEP 2
class OracleConnectionPool(ConnectionPool):
    def __init__(self, pool):
        self._pool = pool # the async Oracle driver pool, created by _create_pool in OracleDatabase
    
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

    async def close(self, timeout: Optional[float] = None) -> None:
         # probably similar to: await self._pool.close(cancel_tasks=force)
        pass

    async def _test_connection(self, connection):
        # probably similar to: await connection.execute("SELECT 1 FROM DUAL")
        pass
    
    @property
    def min_size(self) -> int:
        # probably similar to: return self._pool.min
        pass
    
    @property
    def max_size(self) -> int:
        # probably similar to: return self._pool.max
        pass
    
    @property
    def size(self) -> int:       
        # probably similar to: return self._pool.size
        pass
    
    @property
    def in_use(self) -> int:      
        # probably similar to: return self._pool.size - self._pool.freesize
        pass
    
    @property
    def idle(self) -> int:     
        # probably similar to: self._pool.freesize
        pass

# STEP 3
class OraclePoolManager(PoolManager):
    async def _create_pool(self, config: DatabaseConfig) -> OracleConnectionPool:  
        min_size, max_size = self._calculate_pool_size()
        raw_pool = await asyncio.wait_for(
            async_driver.create_pool(
                min=min_size, 
                max=max_size,
                user=config.user(),
                password=config.password(),
                dsn=f"{config.host()}:{config.port()}/{config.database()}",
                timeout=config.connection_creation_timeout
            ),
            timeout=config.pool_creation_timeout
        )
        return OracleConnectionPool(raw_pool)

# STEP 4
class OracleAsyncConnection(AsyncConnection, EntityAsyncMixin):

    def __init__(self, conn, config: DatabaseConfig): 
        super().__init__(conn, config)  
        self._sql_generator = None

    @property
    def sql_generator(self) -> SqlGenerator:
        if not self._sql_generator:
            self._sql_generator = OracleSqlGenerator()
        return self._sql_generator

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

# STEP 5
class OracleSyncConnection(SyncConnection, EntitySyncMixin):
    # similar to the Async version

# STEP 6
class OracleDatabase(ConnectionManager):
    def __init__(self, config: DatabaseConfig): 
        super().__init__(config)  
        self._pool_manager = None

    @property
    def pool_manager(self):    
        if not self._pool_manager:
            self._pool_manager = OraclePoolManager(self.config)
        return self._pool_manager

    def _create_sync_connection(self, config: DatabaseConfig):     
        return sync_driver.connect(
            user=config.user(),
            password=config.password(),
            dsn=f"{config.host()}:{config.port()}/{config.database()}"
        )

    def _wrap_async_connection(self, raw_conn, config: DatabaseConfig):
        return OracleAsyncConnection(raw_conn, config)

    def _wrap_sync_connection(self, raw_conn, config: DatabaseConfig):
        return OracleSyncConnection(raw_conn, config)
```

---

## Code Structure

#### Module: 
```python
python/databases/
├── backends/
│   ├── mysql/
│   │   ├── connections.py       # MysqlSyncConnection, MysqlAsyncConnection
│   │   ├── database.py          # MySqlDatabase
│   │   ├── generators.py        # MySqlSqlGenerator
│   │   └── pools.py             # MySqlConnectionPool, MySqlPoolManager
│   ├── postgres/                # Similar structure as mysql
│   └── sqlite/                  # Similar structure as mysql
├── config/
│   └── database_config.py       # DatabaseConfig
├── connections/
│   ├── async_connection.py      # AsyncConnection (abstract)
│   ├── connection.py            # Connection, ConnectionInterface (abstract)
│   └── sync_connection.py       # SyncConnection (abstract)
├── database/
│   └── connection_manager.py    # ConnectionManager (abstract)
├── entity/
│   ├── generators/
│   │   └── entity_generators.py # SqlEntityGenerator (abstract)
│   └── mixins/
│       ├── async_mixin.py       # EntityAsyncMixin
│       ├── sync_mixin.py        # EntitySyncMixin
│       └── utils_mixin.py       # EntityUtilsMixin
├── factory.py                   # DatabaseFactory
├── generators/
│   └── generators.py            # SqlGenerator (abstract)
├── pools/
│   ├── connection_pool.py       # ConnectionPool (abstract)
│   └── pool_manager.py          # PoolManager (abstract)
├── utils/
│   ├── caching.py               # StatementCache
│   └── decorators.py            # auto_transaction
└── tests/
    ├── docker-compose.yml
    └── test_dal.py              # Test cases
```

#### Inheritance: 
```python
ConnectionInterface (ABC)
    ├── Connection
    │       ├── AsyncConnection (ABC) ────┬── PostgresAsyncConnection
    │       │                             ├── MysqlAsyncConnection 
    │       │                             └── SqliteAsyncConnection
    │       └── SyncConnection (ABC) ──────┬── PostgresSyncConnection
    │                                      ├── MysqlSyncConnection
    │                                      └── SqliteSyncConnection
    ├── EntityAsyncMixin
    │       └── (mixed into AsyncConnection implementations)
    └── EntitySyncMixin
            └── (mixed into SyncConnection implementations)

ConnectionManager (ABC)
    ├── PostgresDatabase
    ├── MySqlDatabase
    └── SqliteDatabase

ConnectionPool (ABC)
    ├── PostgresConnectionPool
    ├── MySqlConnectionPool
    └── SqliteConnectionPool

PoolManager (ABC)
    ├── PostgresPoolManager
    ├── MySqlPoolManager
    └── SqlitePoolManager

SqlGenerator (ABC)
    ├── PostgresSqlGenerator
    ├── MySqlSqlGenerator
    └── SqliteSqlGenerator

SqlEntityGenerator (ABC)
    └── (implemented by SqlGenerator implementations)

EntityUtilsMixin 
    ├── EntityAsyncMixin
    └── EntitySyncMixin
```

---

## 📖 Public API

You will first have to define the details needed to connect to a database by creating an instance of:

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `DatabaseConfig`

Base configuration object for databases with comprehensive timeout settings.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `config` | | `Dict[str, Any]` | Configuration | Returns database configuration as a dictionary containing host, port, database, user, password, and all timeout settings. |
| | `database` | | `str` | Configuration | Returns the database name. |
| | `alias` | | `str` | Configuration | Returns the database connection alias, a friendly name defaulting to database name. |
| | `host` | | `str` | Configuration | Returns the database host. |
| | `port` | | `int` | Configuration | Returns the database port. |
| | `user` | | `str` | Configuration | Returns the database user. |
| | `password` | | `str` | Configuration | Returns the database password. |
| | `env` | | `str` | Configuration | Returns the database environment ('prod', 'dev', 'test', etc.). |
| | `hash` | | `str` | Configuration | Returns a stable, hash-based key for the database configuration based on all parameters except password. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `database: str`, `host: str="localhost"`, `port: int=5432`, `user: str=None`, `password: str=None`, `alias: str=None`, `env: str='prod'`, `connection_acquisition_timeout: float=10.0`, `pool_creation_timeout: float=30.0`, `query_execution_timeout: float=60.0`, `connection_creation_timeout: float=15.0` | | Initialization | Initializes database configuration with connection parameters and comprehensive timeout settings. |

</details>

<br>

</div>

You can then pass this config to the factory below:

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `DatabaseFactory`

Factory for creating database instances.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:gainsboro">@staticmethod</code> | `create_database` | `db_type: str`, `db_config: DatabaseConfig` | `ConnectionManager` | Factory | Factory method to create the appropriate database instance (PostgreSQL, MySQL, SQLite). |

</details>

<br>

</div>

The factory (or direct instantiation) will then give you a:

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `ConnectionManager`

Manages synchronized and asynchronous database connection lifecycles with comprehensive timeout configuration.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `is_environment_async` | | `bool` | Environment Detection | Determines if code is running in an async environment by checking for event loop. |
| | `get_sync_connection` | | `SyncConnection` | Connection Management | Returns a synchronized database connection, either cached or newly created. |
| | `release_sync_connection` | | `None` | Connection Management | Closes and releases the cached synchronous connection. |
| <code style="background-color:gainsboro">@contextlib.contextmanager</code> | `sync_connection` | | `Iterator[SyncConnection]` | Connection Management | Context manager for safe synchronous connection usage that ensures proper release. |
| <code style="background-color:lightpink">@async_method</code> | `get_async_connection` | | `AsyncConnection` | Connection Management | Acquires an asynchronous connection from the pool, initializing if needed. |
| <code style="background-color:lightpink">@async_method</code> | `release_async_connection` | `async_conn: AsyncConnection` | | Connection Management | Releases an asynchronous connection back to the pool. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@contextlib.asynccontextmanager</code> | `async_connection` | | `Iterator[AsyncConnection]` | Connection Management | Async context manager for safe asynchronous connection usage. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: DatabaseConfig` | | Initialization | Initializes connection manager with database configuration parameters and timeout settings. |
| | `__del__` | | | Resource Management | Destructor that ensures connections are released when object is garbage collected. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_wrap_sync_connection` | `raw_conn: Any`, `config: DatabaseConfig` | `SyncConnection` | Connection Wrapping | Wraps a raw database connection in the SyncConnection interface. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_wrap_async_connection` | `raw_conn: Any`, `config: DatabaseConfig` | `AsyncConnection` | Connection Wrapping | Wraps a raw database connection in the AsyncConnection interface. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_create_sync_connection` | `config: DatabaseConfig` | `Any` | Connection Creation | Creates a new synchronous database connection. |

</details>

<br>

#### Current implementations: `PostgresDatabase`, `MySqlDatabase`, `SqliteDatabase`

</div>

This manager give access to a connection (either sync or async) that offer database manipulations methods:

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `AsyncConnection`

Abstract base class defining the interface for asynchronous database connections with resilience patterns.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> <code style="background-color:orange">@circuit_breaker</code> <code style="background-color:azure">@track_slow_method</code> <code style="background-color:lightblue">@profile</code> | `execute` | `sql: str`, `params: Optional[tuple] = None`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]]=None` | `List[Tuple]` | Query Execution | Asynchronously executes a SQL query with standard ? placeholders. Protected by circuit breaker, timeout control, and includes automatic profiling. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> <code style="background-color:orange">@circuit_breaker</code> <code style="background-color:azure">@track_slow_method</code> <code style="background-color:lightblue">@profile</code> | `executemany` | `sql: str`, `param_list: List[tuple]`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]]=None` | `List[Tuple]` | Query Execution | Asynchronously executes a SQL query multiple times with different parameters. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `in_transaction` | | `bool` | Transaction Management | Return True if connection is in an active transaction. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `begin_transaction` | | `None` | Transaction Management | Begins a database transaction. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `commit_transaction` | | `None` | Transaction Management | Commits the current transaction. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `rollback_transaction` | | `None` | Transaction Management | Rolls back the current transaction. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `close` | | `None` | Connection Management | Closes the database connection. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `get_version_details` | | `Dict[str, str]` | Diagnostic | Returns {'db_server_version', 'db_driver'} |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `get_entity` | `entity_name: str`, `entity_id: str`, `include_deleted: bool = False`, `deserialize: bool = False` | `Optional[Dict[str, Any]]` | Entity | Fetch an entity by ID. Returns None if not found. If deserialize=True, converts field values to appropriate Python types based on metadata. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `save_entity` | `entity_name: str`, `entity: Dict[str, Any]`, `user_id: Optional[str] = None`, `comment: Optional[str] = None`, `timeout: Optional[float] = 60.0` | `Dict[str, Any]` | Entity | Save an entity (create or update). Adds id, created_at, updated_at, and other system fields. Uses upsert to efficiently handle both new entities and updates. Adds an entry to the history table. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `save_entities` | `entity_name: str`, `entities: List[Dict[str, Any]]`, `user_id: Optional[str] = None`, `comment: Optional[str] = None`, `timeout: Optional[float] = 60.0` | `List[Dict[str, Any]]` | Entity | Save a list of entities in bulk. Processes each entity similar to save_entity. Returns the list of saved entities with their IDs. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `delete_entity` | `entity_name: str`, `entity_id: str`, `user_id: Optional[str] = None`, `permanent: bool = False` | `bool` | Entity | Delete an entity. By default performs a soft delete (sets deleted_at), but can permanently remove the record if permanent=True. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `restore_entity` | `entity_name: str`, `entity_id: str`, `user_id: Optional[str] = None` | `bool` | Entity | Restore a soft-deleted entity by clearing the deleted_at field. Returns True if successful. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `find_entities` | `entity_name: str`, `where_clause: Optional[str] = None`, `params: Optional[Tuple] = None`, `order_by: Optional[str] = None`, `limit: Optional[int] = None`, `offset: Optional[int] = None`, `include_deleted: bool = False`, `deserialize: bool = False` | `List[Dict[str, Any]]` | Entity | Query entities with flexible filtering. Returns a list of matching entities. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `count_entities` | `entity_name: str`, `where_clause: Optional[str] = None`, `params: Optional[Tuple] = None`, `include_deleted: bool = False` | `int` | Entity | Count entities matching the criteria. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `get_entity_history` | `entity_name: str`, `entity_id: str`, `deserialize: bool = False` | `List[Dict[str, Any]]` | Entity | Get the history of all previous versions of an entity. Returns a list of historical entries ordered by version. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `get_entity_by_version` | `entity_name: str`, `entity_id: str`, `version: int`, `deserialize: bool = False` | `Optional[Dict[str, Any]]` | Entity | Get a specific version of an entity from its history or None if not found. |
| | `register_serializer` | `type_name: str`, `serializer_func: Callable`, `deserializer_func: Callable` | `None` | Serialization | Register custom serialization functions for handling non-standard types. The `serializer_func` should convert the custom type to a string, and the `deserializer_func` should convert the string back to the custom type. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `conn: Any`, `config: DatabaseConfig` | | Initialization | Initializes async connection with tracking information and configuration. |
| | `_get_raw_connection` | | `Any` | Connection Management | Return the underlying database connection (as defined by the driver). |
| | `_mark_active` | | | Connection Management | Mark the connection as active (used recently). |
| | `_is_idle` | `timeout_seconds: int=1800` | `bool` | Connection Management | Check if connection has been idle for too long (default 30 mins). |
| | `_mark_leaked` | | | Connection Management | Mark this connection as leaked. |
| <code style="background-color:gainsboro">@property</code> | `_is_leaked` | | `bool` | Connection Management | Check if this connection has been marked as leaked. |
| <code style="background-color:lightpink">@async_method</code> | `_get_field_names` | `entity_name: str`, `is_history: bool = False` | `List[str]` | Entity Framework | Get field names for an entity table from schema or metadata cache. |
| <code style="background-color:lightpink">@async_method</code> | `_ensure_entity_schema` | `entity_name: str`, `sample_entity: Optional[Dict[str, Any]] = None` | `None` | Entity Framework | Ensure entity tables and metadata exist, creating them if necessary. |
| <code style="background-color:lightpink">@async_method</code> | `_update_entity_metadata` | `entity_name: str`, `entity: Dict[str, Any]` | `None` | Entity Framework | Update metadata table based on entity fields and add missing columns to tables. |
| <code style="background-color:lightpink">@async_method</code> | `_get_entity_metadata` | `entity_name: str`, `use_cache: bool = True` | `Dict[str, str]` | Entity Framework | Get metadata for an entity type, mapping field names to types. |
| <code style="background-color:lightpink">@async_method</code> | `_add_to_history` | `entity_name: str`, `entity: Dict[str, Any]`, `user_id: Optional[str] = None`, `comment: Optional[str] = None` | `None` | Entity Framework | Add an entry to entity history table with version tracking. |
| <code style="background-color:lightpink">@async_method</code> | `_check_column_exists` | `table_name: str`, `column_name: str` | `bool` | Entity Framework | Check if a column exists in a table, handling different database formats. |

</details>

<br>

#### Current implementations: `PostgresAsyncConnection`, `MysqlAsyncConnection`, `SqliteAsyncConnection`

Notes:

* An Entity is a dictionary of any serializable values
* The `@auto_transaction` decorator ensures that each operation runs within a transaction, creating one if needed or using an existing one
* Schema creation and metadata updates happen automatically when using save_entity and save_entities
* Entity values are automatically serialized to database types, but by default are not deserialized (deserialize=False)
* Set deserialize=True when you need to perform computation on the entity data in your application logic
* The `SyncConnection` class exposes the same public methods.

</div>

That's all you need to safely write and read from the database, but if you're using the async features, you will have the responsibility of manually closing the connection(s) properly, by calling the close_pool class method of:

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `PoolManager`

Class to manage the lifecycle of asynchronous connection pools with comprehensive monitoring and leak detection.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `alias` | | `str` | Configuration | Returns the friendly name of this pool manager. |
| | `hash` | | `str` | Configuration | Returns the unique hash for this pool manager. |
| | `get_pool_status` | | `Dict[str, Any]` | Diagnostic | Gets comprehensive status information about the connection pool including metrics, sizes, and health status. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@classmethod</code> | `health_check_all_pools` | | `Dict[str, bool]` | Diagnostic | Checks the health of all connection pools. |
| <code style="background-color:gainsboro">@classmethod</code> | `get_pool_metrics` | `config_hash=None` | `Dict` | Metrics | Get metrics for specific or all connection pools including acquisition counts, timeouts, and errors. |
| <code style="background-color:lightpink">@async_method</code> | `check_for_leaked_connections` | `threshold_seconds=300` | `List[Tuple[AsyncConnection, float, str]]` | Leak Detection | Check for connections that have been active for longer than the threshold. Returns list of (connection, duration, stack_trace) tuples. |
| <code style="background-color:gainsboro">@classmethod</code> | `close_pool` | `config_hash: Optional[str] = None`, `timeout: Optional[float]=60` | `None` | Resource Management | Closes one or all shared connection pools with proper cleanup. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: DatabaseConfig` | | Initialization | Initializes a pool manager with configuration and starts background leak detection task. |
| | `_calculate_pool_size` | | `Tuple[int, int]` | Configuration | Calculate optimal pool size based on workload characteristics, system resources, and expected concurrency. |
| | `_track_metrics` | `is_new: bool=True`, `error: Exception=None`, `is_timeout: bool=False` | | Metrics | Track connection acquisition and release metrics for monitoring and scaling insights. |
| | `_leak_detection_task` | | | Background Task | Background task that periodically checks for and recovers from connection leaks and idle connections. |
| <code style="background-color:gainsboro">@property</code> | `_pool` | | `Optional[Any]` | Pool Management | Gets the connection pool for this instance's configuration. |
| <code style="background-color:gainsboro">@property</code> | `_pool_lock` | | `asyncio.Lock` | Concurrency | Gets the lock for this instance's configuration to ensure thread-safe initialization. |
| <code style="background-color:gainsboro">@property</code> | `_connections` | | `Set[AsyncConnection]` | Connection Management | Gets the set of active connections for this instance's configuration. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### Functions

| Decorators | Function | Args | Returns | Category | Description |
|------------|----------|------|---------|----------|-------------|
| | `with_timeout` | `default_timeout: float = 60.0` | `Callable` | Timeout Management | Decorator that adds timeout functionality to both async and sync methods. The decorated method will have a timeout applied, which can be passed directly as a 'timeout' parameter or use the default_timeout value. |
| | `circuit_breaker` | `name=None`, `failure_threshold=5`, `recovery_timeout=30.0`, `half_open_max_calls=3`, `window_size=60.0` | `Callable` | Resilience | Decorator that applies circuit breaker pattern to prevent cascading failures. Opens after failure_threshold failures within window_size, recovers after recovery_timeout seconds. |
| | `retry_with_backoff` | `max_retries=3`, `base_delay=0.1`, `max_delay=10.0`, `exceptions=None`, `total_timeout=30.0` | `Callable` | Resilience | Decorator for retrying functions with exponential backoff on database exceptions. |
| | `track_slow_method` | `threshold=2.0` | `Callable` | Instrumentation | Decorator that logs a warning if method execution exceeds threshold seconds, including arguments and timing information. |
| | `profile` | `max_length=200` | `Callable` | Instrumentation | Decorator that profiles and logs execution time, arguments, and results for debugging and performance analysis. |
| | `auto_transaction` | `func` | `Callable` | Transaction | Decorator that automatically wraps a function in a transaction. If a transaction is already in progress, uses the existing transaction. |

</div>