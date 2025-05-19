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

## TODO

Think about integrating different timeouts in DatabaseConfig:
* connection acquisition/creation
* pool creation
* sql execution
  


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

db = DatabaseFactory.create_database("postgres", config)

async with db.async_connection() as conn:   
    await conn.begin_transaction()    
    try:
        # Note: in the following results, we ommit the auto-generated created_at field for simplicity. Also the id would be longer (uuid).

        entities = await conn.save_entities("users",[{'name':'Phil'},{'name':'Karen','surname':'Brown'}])
        uid = entities[0].get('id', None)
        
        result = await conn.execute(
            "SELECT * FROM [users] WHERE id = ?", 
            (uid,),
            timeout=5.0,  # Query timeout in seconds
            tags={"operation": "get_user"}  # Optional query tags for logging/metrics
        ) 
        # ('Phil',None,'1','2025-05-05T11:00:00.123456')
        
        await conn.save_entity("users",{'id':uid,'name':'Bob','age':24})
        
        result = await conn.get_entity("users",uid) # {'name':'Bob','surname':None,'age':'24','id':'1','updated_at':'2025-05-05T11:00:01.789012'}
        result = await conn.get_entity("users",uid,deserialize=True) # {'name':'Bob','surname':None,'age':24,'id':'1','updated_at':datetime.datetime(2025, 5, 5, 11, 0, 1, 789012)}
        result = await conn.find_entities("users",where_clause="age <= ?",params=(30,),deserialize=False) # [{'name':'Bob','surname':None,'age':'24','id':'1','updated_at':'2025-05-05T11:00:01.789012'}]
        result = await conn.get_entity_history("users",uid,deserialize=False) # [{'name':'Phil','surname':None,'id':'1','updated_at':'2025-05-05T11:00:00.123456','version':'1'},{'name':'Bob','surname':None,'age':'24','id':'1','updated_at':'2025-05-05T11:00:01.789012','version':'2'}]
        
        old_version = await conn.get_entity_by_version("users", uid, 1)        
        await conn.save_entity("users", old_version)        
        
        result = await conn.get_entity("users",uid) # {'name':'Phil','surname':None,'id':'1','updated_at':'2025-05-05T11:00:02.345678'}
        
        await conn.commit_transaction()
    except Exception:
        await conn.rollback_transaction() # For MySql or backends that don't handle DDL well (Oracle), the rollback will be incomplete
        raise

await PoolManager.close_pool(config_hash=config.hash(),timeout=30) # Will close the pool created for this specific config, brute forcing it after 30 seconds
```

---

### Extension

To add a new backend (say Oracle), you need to write the implementation of a few classes:
* Step 1) <a href="#class-sqlgenerator">`SqlGenerator`</a>: `convert_query_to_native` `get_timeout_sql`
* Step 2) <a href="#class-connectionpool">`Connectionpool`</a>: `__init__` `acquire` `release` `close` `_test_connection` `min_size` `max_size` `size` `in_use` `idle`
* Step 3) <a href="#class-poolmanager">`PoolManager`</a>: `_create_pool`
* Step 4) <a href="#class-asyncconnection">`AsyncConnection`</a>: `__init__` `sql_generator` `_prepare_statement_async` `_execute_statement_async` `in_transaction` `begin_transaction` `commit_transaction` `rollback_transaction` `close` `get_version_details`
* Step 5) <a href="#class-syncconnection">`SyncConnection`</a>: `__init__` `sql_generator` `_prepare_statement_sync` `_execute_statement_sync` `in_transaction` `begin_transaction` `commit_transaction` `rollback_transaction` `close` `get_version_details`
* Step 6) <a href="#class-connectionmanager">`ConnectionManager`</a>: `_create_sync_connection` `create_pool` `_wrap_async_connection` `_wrap_sync_connection`

<br>

**Notes**: in the connection classes, the sql_generator property should return an instance of the class defined in Step 1.

To add the Entity Framework, you will need to define the relavant sql for the backend: simply add <a href="#class-sqlentitygenerator">`SqlEntityGenerator`</a> in the inheritance list of the class defined in Step 1 and define all the needed sql (`get_upsert_sql` etc.).
You also need to add `EntityAsyncMixin` and `EntitySyncMixin` to the `AsyncConnection` and `AsyncConnection` (step 4 and 5).

<br>

```python

import {oracle_asyn_driver} as async_driver
import {oracle_sync_driver} as sync_driver

# STEP 1
class OracleSqlGenerator(SqlGenerator, SqlEntityGenerator):
    def convert_query_to_native(self, sql: str, params: Optional[Tuple] = None) -> Tuple[str, Any]:
        if not params:
            return sql, []
        new_sql = sql # replace "?" as needed
        return new_sql, params

    def get_timeout_sql(self, timeout: Optional[float]) -> Optional[str]:
        if timeout:
            return f"SET LOCAL statement_timeout = {int(timeout * 1000)}" # adjust sql as needed
        return None  
    
    # Entity specific sqls:

    def get_upsert_sql(self, entity_name: str, fields: List[str]) -> str:
        pass

    # .. and all the other Entity specific sqls generation methods

# STEP 2
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

# STEP 3
class OraclePoolManager(PoolManager):

    async def _create_pool(self, config: Dict) -> OracleConnectionPool:  
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

# STEP 4
class OracleAsyncConnection(AsyncConnection, EntityAsyncMixin):
    def __init__(self, conn):
        super().__init__(conn)
        self._conn = conn # The async Oracle driver's connection (generated in the Pool acquire method)
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
        def __init__(self, **kwargs):
        super().__init__(**kwargs) 
        self._pool_manager = None
        
    # region -- Implementation of Abstract methods ---------
    @property
    def pool_manager(self):
        if not self._pool_manager:
            self._pool_manager = OraclePoolManager(self.config.alias(), self.config.hash(), self.connection_acquisition_timeout)
        return self._pool_manager

    def _create_sync_connection(self, config: Dict):     
        # probably: return sync_driver.connect(**config)
        pass 

    def _wrap_async_connection(self, raw_conn):
        return OracleAsyncConnection(raw_conn)

    def _wrap_sync_connection(self, raw_conn):
        return OracleSyncConnection(raw_conn)

```
---

## Code Structure

#### Module: 
```pyhon
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

#### Inheritence: 
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

## 📖 Public API


You will first have to define a the details needed to connect to a database, and can do so by creating an instance of:


<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">


### class `DatabaseConfig`

Base configuration object for databases.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `config` | | `Dict[str, Any]` | Configuration | Returns database configuration as a dictionary containing host, port, database, user, and password. |
| | `database` | | `str` | Configuration | Returns the database name. |
| | `alias` | | `str` | Configuration | Returns the database connection alias, a friendly name defaulting to database name. |
| | `host` | | `str` | Configuration | Returns the database host. |
| | `port` | | `int` | Configuration | Returns the database port. |
| | `env` | | `str` | Configuration | Returns the database environment ('prod', 'dev', 'test', etc.). |
| | `hash` | | `str` | Configuration | Returns a stable, hash-based key for the database configuration based on all parameters except password. |

</details>

<br>



<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `database: str`, `host: str="localhost"`, `port: int=5432`, `user: str=None`, `password: str=None`, `alias: str=None`, `env: str='prod'` | | Initialization | Initializes database configuration with connection parameters. |
</details>

<br>


</div>


You can then pass this config to the factory below:


<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `DatabaseFactory`
Factory for creating database instances.

<details>
<summary><strong>Public Methods</strong></summary>

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
<code style="background-color:gainsboro">@staticmethod</code>| `create_database` |`db_type:str` <code>db_config:<a href="#class-databaseconfig">DatabaseConfig</a></code>|<a href="#class-connectionmanager">`ConnectionManager`</a>|Factory| Factory method to create the appropriate database instance (PostgreSQL, MySQL, SQLite). |

</details>

<br>


</div>


The factory (or direct instanciation) will then give you a:


<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `ConnectionManager`

Manages synchronized and asynchronous database connection lifecycles. Provides a unified interface for obtaining both sync and async database connections, with proper resource management through context managers. Handles connection pooling for async connections and caching for sync connections.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `is_environment_async` | | `bool` | Environment Detection | Determines if code is running in an async environment by checking for event loop. |
| | `get_sync_connection` | | `SyncConnection` | Connection Management | Returns a synchronized database connection, either cached or newly created. |
| | `release_sync_connection` | | `None` | Connection Management | Closes and releases the cached synchronous connection. |
| `@contextlib.contextmanager` | `sync_connection` | | `Iterator[SyncConnection]` | Connection Management | Context manager for safe synchronous connection usage that ensures proper release. |
| <code style="background-color:lightpink">@async_method</code> | `get_async_connection` | | `AsyncConnection` | Connection Management | Acquires an asynchronous connection from the pool, initializing if needed. |
| <code style="background-color:lightpink">@async_method</code> | `release_async_connection` | `async_conn: AsyncConnection` | | Connection Management | Releases an asynchronous connection back to the pool. |
| <code style="background-color:lightpink">@async_method</code> `@contextlib.asynccontextmanager` | `async_connection` | | `Iterator[AsyncConnection]` | Connection Management | Async context manager for safe asynchronous connection usage. |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: DatabaseConfig=None`, `database: str=None`, `host: str="localhost"`, `port: int=5432`, `user: str=None`, `password: str=None`, `alias: str=None`, `env: str='prod'`, `connection_acquisition_timeout: float=10.0` | | Initialization | Initializes connection manager with database configuration parameters. |
| | `__del__` | | | Resource Management | Destructor that ensures connections are released when object is garbage collected. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_wrap_sync_connection` | `raw_conn: Any` | `SyncConnection` | Connection Wrapping | Wraps a raw database connection in the SyncConnection interface. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_wrap_async_connection` | `raw_conn: Any` | `AsyncConnection` | Connection Wrapping | Wraps a raw database connection in the AsyncConnection interface. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_create_sync_connection` | `config: Dict` | `Any` | Connection Creation | Creates a new synchronous database connection. |

</details>

#### Current implementations: `PostgresDatabase`, `Mysqldatabase`, `SqliteDatabase`

</div>

This manager give access to a connection (either sync or async) that offer database manipulations methods:

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `AsyncConnection`
Abstract base class defining the interface for asynchronous database connections.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:azure">@track_slow_method</code> <code style="background-color:orange">@circuit_breaker</code> | `execute` | `sql: str`, `params: Optional[tuple] = None`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]]=None` | `List[Tuple]` | Query Execution | Asynchronously executes a SQL query with standard ? placeholders. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> <code style="background-color:azure">@track_slow_method</code> <code style="background-color:orange">@circuit_breaker</code> | `executemany` | `sql: str`, `param_list: List[tuple]`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]]=None` | `List[Tuple]` | Query Execution | Asynchronously executes a SQL query multiple times with different parameters. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `in_transaction` | | `bool` | Transaction Management | Return True if connection is in an active transaction. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `begin_transaction` | | `None` | Transaction Management | Begins a database transaction. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `commit_transaction` | | `None` | Transaction Management | Commits the current transaction. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `rollback_transaction` | | `None` | Transaction Management | Rolls back the current transaction. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `close` | | `None` | Connection Management | Closes the database connection. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `get_version_details` | | `Dict[str, str]` | Diagnostic | Returns {'db_server_version', 'db_driver'} |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `get_entity` |`entity_name:str` `entity_id:str` `include_deleted:bool=False` `deserialize:bool=False`|`Optional[Dict[str,Any]]`| Entity | Fetch an entity by ID. Returns None if not found. If deserialize=True, converts field values to appropriate Python types based on metadata. |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `save_entity` |`entity_name:str` `entity:Dict[str,Any]` `user_id:str=None` `comment:str=None`|`Dict[str,Any]`| Entity | Save an entity (create or update). Adds id, created_at, updated_at, and other system fields. Uses upsert to efficiently handle both new entities and updates. Adds an entry to the history table. |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `save_entities` |`entity_name:str` `entities:List[Dict[str,Any]]` `user_id:str=None` `comment:str=None`|`List[Dict[str,Any]]`| Entity | Save a list of entities in bulk. Processes each entity similar to save_entity. Returns the list of saved entities with their IDs. |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `delete_entity` |`entity_name:str` `entity_id:str` `user_id:str=None` `permanent:bool=False`|`bool`| Entity | Delete an entity. By default performs a soft delete (sets deleted_at), but can permanently remove the record if permanent=True. |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `restore_entity` |`entity_name:str` `entity_id:str` `user_id:str=None`|`bool`| Entity | Restore a soft-deleted entity by clearing the deleted_at field. Returns True if successful. |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `find_entities` |`entity_name:str` `where_clause:str=None` `params:Tuple=None` `order_by:str=None` `limit:int=None` `offset:int=None` `include_deleted:bool=False` `deserialize:bool=False`|`List[Dict[str,Any]]`| Entity | Query entities with flexible filtering. Returns a list of matching entities. |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `count_entities` |`entity_name:str` `where_clause:str=None` `params:Tuple=None` `include_deleted:bool=False`|`int`| Entity | Count entities matching the criteria. |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `get_entity_history` |`entity_name:str` `entity_id:str` `deserialize:bool=False`|`List[Dict[str,Any]]`| Entity | Get the history of all previous versions of an entity. Returns a list of historical entries ordered by version. |
|<code style="background-color:pink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code>| `get_entity_version` |`entity_name:str` `entity_id:str` `version:int` `deserialize:bool=False`|`Optional[Dict[str,Any]]`| Entity | Get a specific version of an entity from its history or None if not found. |
|| `register_serializer` |`type_name:str` `serializer_func:Callable` `deserializer_func:Callable`|`None`|Serialization| Register custom serialization functions for handling non-standard types. The `serializer_func` should convert the custom type to a string, and the `deserializer_func` should convert the string back to the custom type. |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `conn: Any` | | Initialization | Initializes async connection with tracking information. |
| | `_get_raw_connection` | | `Any` | Connection Management | Return the underlying database connection (as defined by the driver). |
| | `_mark_active` | | | Connection Management | Mark the connection as active (used recently). |
| | `_is_idle` | `timeout_seconds: int=1800` | `bool` | Connection Management | Check if connection has been idle for too long (default 30 mins). |
| | `_mark_leaked` | | | Connection Management | Mark this connection as leaked. |
| <code style="background-color:gainsboro">@property</code> | `_is_leaked` | | `bool` | Connection Management | Check if this connection has been marked as leaked. |
</details>

<br>

**Notes:**
- An Entity is a dictionary of any serializable values
- The <code style="background-color:lightgreen">@auto_transaction</code> decorator ensures that each operation runs within a transaction, creating one if needed or using an existing one
- Schema creation and metadata updates happen automatically when using `save_entity` and `save_entities`
- Entity values are automatically serialized to database types, but by default are not deserialized (deserialize=False)
- Set deserialize=True when you need to perform computation on the entity data in your application logic

#### Current implementations: `PostgresAsyncConnection`, `MysqlAsyncConnection`, `SqliteAsyncConnection`

The <a href="#class-syncconnection">`SyncConnection`</a> class exposes the same public methods.


</div>


That's all you need to safely write and read from the database, but if you're using the async features, you will have the responsabilty of manually closing the connection(s) properly, by calling the `close_pool` class method of:

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">


### class `PoolManager`

Class to manage the lifecycle of asynchronous connection pools. Pools are created lazily, shared across instances with the same configuration, and can be properly closed during application shutdown.
This class offers a few metrics and other diagnostic tools to monitor the health of the pool and its connections.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `alias` | | `str` | Configuration | Returns the friendly name of this pool manager. |
| | `hash` | | `str` | Configuration | Returns the unique hash for this pool manager. |
| | `get_pool_status` | | `Dict[str, Any]` | Diagnostic | Gets comprehensive status information about the connection pool. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@classmethod</code> | `health_check_all_pools` | | `Dict[str, bool]` | Diagnostic | Checks the health of all connection pools. |
| <code style="background-color:gainsboro">@classmethod</code> | `get_pool_metrics` | `config_hash=None` | `Dict` | Metrics | Get metrics for specific or all connection pools. |
| <code style="background-color:lightpink">@async_method</code> | `check_for_leaked_connections` | `threshold_seconds=300` | `List[Tuple[AsyncConnection, float, str]]` | Leak Detection | Check for connections that have been active for longer than the threshold. |
| <code style="background-color:gainsboro">@classmethod</code> | `close_pool` | `config_hash: Optional[str] = None`, `timeout: Optional[float]=60` | `None` | Resource Management | Closes one or all shared connection pools with proper cleanup. |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `alias: str=uuid.uuid4()`, `hash: str=uuid.uuid4()` | | Initialization | Initializes a pool manager with unique identifiers. |
| | `_calculate_pool_size` | | `Tuple[int, int]` | Configuration | Calculate optimal pool size based on workload characteristics, system resources, and expected concurrency. |
| | `_track_metrics` | `is_new: bool=True`, `error: Exception=None`, `is_timeout: bool=False` | | Metrics | Track connection acquisition and release metrics for monitoring. |
| <code style="background-color:gainsboro">@property</code> | `_pool` | | `Optional[Any]` | Pool Management | Gets the connection pool for this instance's configuration. |
| `@_pool.setter` | `_pool` | `value: Any` | `None` | Pool Management | Sets or clears the connection pool for this instance's configuration. |
| <code style="background-color:gainsboro">@property</code> | `_pool_lock` | | `asyncio.Lock` | Concurrency | Gets the lock for this instance's configuration to ensure thread-safe initialization. |
| <code style="background-color:gainsboro">@property</code> | `_connections` | | `Set[AsyncConnection]` | Connection Management | Gets the set of active connections for this instance's configuration. |
| | `_get_connection_from_pool` | `wrap_raw_connection: Callable` | `AsyncConnection` | Connection Management | Acquires a connection from the pool with timeout handling and leak tracking. |
| | `_release_connection_to_pool` | `async_conn: AsyncConnection` | `None` | Connection Management | Releases a connection back to the pool with proper error handling. |
| | `_initialize_pool_if_needed` | | `None` | Pool Management | Initializes the connection pool if it doesn't exist or isn't usable. |
| | `_test_connection` | `conn: Any` | `None` | Diagnostic | Tests if a connection is usable by executing a simple query. |
| <code style="background-color:gainsboro">@classmethod</code> | `_cleanup_connection` | `async_conn: AsyncConnection` | | Resource Management | Clean up a connection by committing and releasing it properly. |
| <code style="background-color:gainsboro">@classmethod</code> | `_release_pending_connections` | `key`, `timeout` | | Resource Management | Release all active connections for a specific pool configuration. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_create_pool` | `config: Dict` | `ConnectionPool` | Pool Management | Creates a new connection pool for the specific database backend. |
| | `_leak_detection_task` | | | Background Task | Background task that periodically checks for and recovers from connection leaks. |

</details>

<br>


</div>

-------
`

## 📖 Utilities


<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `BaseConnection`

This is the base class of <a href="#class-asyncconnection">`AsyncConnection`</a> and <a href="#class-syncconnection">`SyncConnection`</a>.
Internally, it normalizes the results from all backends to list of tuples (instead of records or whatever the database drivers' are sending back), inject timeout and comment into any sql, and harbor a <a href="#class-statementcache">`StatementCache`</a> to cache the conversions of sqls into satements (potentially saving up to 5ms in a given query). 


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | | | Initialization | Initializes a base connection with statement cache. |
| | `_normalize_result` | `raw_result: Any` | `List[Tuple]` | Data Conversion | Normalizes query results to a list of tuples regardless of input format. |
| | `_finalize_sql` | `sql: str`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]] = None` | `str` | Query Preparation | Combines SQL with timeout and comment directives. |
| | `_get_statement_async` | `sql: str`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]] = None` | `Any` | Statement Management | Gets or creates a prepared statement asynchronously. |
| | `_get_statement_sync` | `sql: str`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]] = None` | `Any` | Statement Management | Gets or creates a prepared statement synchronously. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_prepare_statement_sync` | `native_sql: str` | `Any` | Statement Management | Prepares a statement using database-specific sync API. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_execute_statement_sync` | `statement: Any`, `params=None` | `Any` | Statement Management | Executes a prepared statement with parameters synchronously. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_prepare_statement_async` | `native_sql: str` | `Any` | Statement Management | Prepares a statement using database-specific async API. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `_execute_statement_async` | `statement: Any`, `params=None` | `Any` | Statement Management | Executes a prepared statement with parameters asynchronously. |
| <code style="background-color:gainsboro">@property</code> <code style="background-color:gainsboro">@abstractmethod</code> | `_sql_generator` | | `SqlGenerator` | Configuration | Returns the parameter converter for this connection. |
</details>

<br>


</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `SyncConnection`

Abstract base class defining the interface for synchronous database connections.

Has the same API as AsyncConnection (minus the async keyword).

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:yellow">@with_timeout</code> <code style="background-color:azure">@track_slow_method</code> <code style="background-color:orange">@circuit_breaker</code> | `execute` | `sql: str`, `params: Optional[tuple] = None`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]]=None` | `List[Tuple]` | Query Execution | Synchronously executes a SQL query with standard ? placeholders. |
| <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> <code style="background-color:orange">@circuit_breaker</code> `@overridable` | `executemany` | `sql: str`, `param_list: List[tuple]`, `timeout: Optional[float] = None`, `tags: Optional[Dict[str, Any]]=None` | `List[Tuple]` | Query Execution | Synchronously executes a SQL query multiple times with different parameters. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `in_transaction` | | `bool` | Transaction Management | Return True if connection is in an active transaction. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `begin_transaction` | | `None` | Transaction Management | Begins a database transaction. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `commit_transaction` | | `None` | Transaction Management | Commits the current transaction. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `rollback_transaction` | | `None` | Transaction Management | Rolls back the current transaction. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `close` | | `None` | Connection Management | Closes the database connection. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_version_details` | | `Dict[str, str]` | Diagnostic | Returns {'db_server_version', 'db_driver'} |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `conn: Any` | | Initialization | Initializes sync connection with statement cache. |
| | `_get_raw_connection` | | `Any` | Connection Management | Return the underlying database connection (as defined by the driver). |
| <code style="background-color:gainsboro">@property</code> <code style="background-color:gainsboro">@abstractmethod</code> | `_sql_generator` | | `SqlGenerator` | Configuration | Returns the parameter converter for this connection. |
</details>

#### Current implementations: `PostgresSyncConnection`, `MysqlSyncConnection`, `SqliteSyncConnection`

</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `SqlGenerator`

Internally used by <a href="#class-asyncconnection">`AsyncConnection`</a> and its sync equivalent.
Abstract base class for SQL parameter placeholder conversion and sql generation for usual operations. This class provides a way to convert between a standard format (? placeholders) and database-specific formats for positional parameters.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `<code style="background-color:lightblue">@final</code>` | `get_comment_sql` | `tags: Optional[Dict[str, Any]]` | `Optional[str]` | Query Conversion | Return SQL comment with tags if supported by database. |
| `@overridable` | `get_timeout_sql` | `timeout: Optional[float]` | `Optional[str]` | Query Conversion | Return a SQL statement to enforce query timeout if applicable to the database. |
| `@overridable` | `convert_query_to_native` | `sql: str`, `params: Optional[Tuple] = None` | `Tuple[str, Any]` | Query Conversion | Converts a standard SQL query with ? placeholders to a database-specific format. |

</details>

<br>


</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `SqlEntityGenerator`

Internally used by <a href="#class-entityasyncmixin">`EntityAsyncMixin`</a> and its sync equivalent.
Inherits from <a href="#class-sqlgenerator">`SqlGenerator`</a>
Abstract class that offers Entity manipulation sqls.
The subclasses must implement the generaton of the sql matching the targeted database.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_upsert_sql` | `entity_name: str`, `fields: List[str]` | `str` | SQL Generation | Generate database-specific upsert SQL for an entity. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_create_table_sql` | `entity_name: str`, `columns: List[Tuple[str, str]]` | `str` | SQL Generation | Generate database-specific CREATE TABLE SQL. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_create_meta_table_sql` | `entity_name: str` | `str` | SQL Generation | Generate database-specific SQL for creating a metadata table. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_create_history_table_sql` | `entity_name: str`, `columns: List[Tuple[str, str]]` | `str` | SQL Generation | Generate database-specific history table SQL. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_list_tables_sql` | | `Tuple[str, tuple]` | SQL Generation | Get SQL to list all tables in the database. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_list_columns_sql` | `table_name: str` | `Tuple[str, tuple]` | SQL Generation | Get SQL to list all columns in a table. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_meta_upsert_sql` | `entity_name: str` | `str` | SQL Generation | Generate database-specific upsert SQL for a metadata table. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_add_column_sql` | `table_name: str`, `column_name: str` | `str` | SQL Generation | Generate SQL to add a column to an existing table. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_check_table_exists_sql` | `table_name: str` | `Tuple[str, tuple]` | SQL Generation | Generate SQL to check if a table exists. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_check_column_exists_sql` | `table_name: str`, `column_name: str` | `Tuple[str, tuple]` | SQL Generation | Generate SQL to check if a column exists in a table. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_entity_by_id_sql` | `entity_name: str`, `include_deleted: bool = False` | `str` | SQL Generation | Generate SQL to retrieve an entity by ID. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_entity_history_sql` | `entity_name: str`, `id: str` | `Tuple[str, tuple]` | SQL Generation | Generate SQL to retrieve the history of an entity. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_entity_version_sql` | `entity_name: str`, `id: str`, `version: int` | `Tuple[str, tuple]` | SQL Generation | Generate SQL to retrieve a specific version of an entity. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_soft_delete_sql` | `entity_name: str` | `str` | SQL Generation | Generate SQL for soft-deleting an entity. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_restore_entity_sql` | `entity_name: str` | `str` | SQL Generation | Generate SQL for restoring a soft-deleted entity. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_count_entities_sql` | `entity_name: str`, `where_clause: Optional[str] = None`, `include_deleted: bool = False` | `str` | SQL Generation | Generate SQL for counting entities, optionally with a WHERE clause. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_query_builder_sql` | `entity_name: str`, `where_clause: Optional[str] = None`, `order_by: Optional[str] = None`, `limit: Optional[int] = None`, `offset: Optional[int] = None`, `include_deleted: bool = False` | `str` | SQL Generation | Generate SQL for a flexible query with various clauses. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_update_fields_sql` | `entity_name: str`, `fields: List[str]` | `str` | SQL Generation | Generate SQL for updating specific fields of an entity. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_pragma_or_settings_sql` | | `List[str]` | SQL Generation | Get a list of database-specific PRAGMA or settings statements. |
| <code style="background-color:gainsboro">@abstractmethod</code> | `get_next_sequence_value_sql` | `sequence_name: str` | `Optional[str]` | SQL Generation | Generate SQL to get the next value from a sequence. |

</details>

#### Current implementations: `PostgresSqlGenerator`, `MysqlSqlGenerator`, `SqliteSqlGenerator`

</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `EntityUtility`

Offers way to serialize/deserialize an Entity (which is a dictionary).
You can add your custom serializer with the `register_serializer` method, that will be exposed in <a href="#class-asyncconnection">`AsyncConnection`</a> and <a href="#class-syncconnection">`SyncConnection`</a> (via injection of the subclasses <a href="#class-entityasyncmixin">`EntityAsyncMixin`</a> and <a href="#class-entityasyncmixin">`EntitySyncMixin`</a> by the <code style="background-color:azure">@inject_mixin</code> decorator)

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `register_serializer` | `type_name: str`, `serializer_func`, `deserializer_func` | | Serialization | Register custom serialization functions for handling non-standard types. |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | | | Initialization | Initializes entity utilities with serializers and deserializers. |
| | `_init_serializers` | | | Serialization | Initialize standard serializers and deserializers for different types. |
| | `_infer_type` | `value: Any` | `str` | Type Handling | Infer the type of a value as a string identifier. |
| | `_serialize_value` | `value: Any`, `value_type: Optional[str] = None` | `str` | Serialization | Serialize a value based on its type. |
| | `_deserialize_value` | `value: Optional[str]`, `value_type: str` | `Any` | Serialization | Deserialize a value based on its type. |
| | `_serialize_entity` | `entity: Dict[str, Any]`, `meta: Optional[Dict[str, str]] = None` | `Dict[str, Optional[str]]` | Serialization | Serialize all values in an entity to strings. |
| | `_deserialize_entity` | `entity_name: str`, `entity: Dict[str, Optional[str]]` | `Dict[str, Any]` | Serialization | Deserialize entity values based on metadata. |
| | `_prepare_entity` | `entity_name: str`, `entity: Dict[str, Any]`, `user_id: Optional[str] = None`, `comment: Optional[str] = None` | `Dict[str, Any]` | Entity Preparation | Prepare an entity for storage by adding required fields. |
| | `_to_json` | `entity: Dict[str, Any]` | `str` | Serialization | Convert an entity to a JSON string. |
| | `_from_json` | `json_str: str` | `Dict[str, Any]` | Serialization | Convert a JSON string to an entity dictionary. |
| | `_internal_operation` | `is_async: bool`, `func_sync`, `func_async`, `*args`, `**kwargs` | | Utility | Execute an operation in either sync or async mode. |
| | `_create_sync_method` | `internal_method`, `*args`, `**kwargs` | `Callable` | Utility | Create a synchronous wrapper for an internal method. |
| | `_create_async_method` | `internal_method`, `*args`, `**kwargs` | `Callable` | Utility | Create an asynchronous wrapper for an internal method. |

</details>

<br>


</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `EntityAsyncMixin`

Injected into <a href="#class-asyncconnection">`AsyncConnection`</a> via the <code style="background-color:azure">@inject_mixin</code> decorator.
Inherit from <a href="#class-entityutility">`EntityUtility`</a>.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `get_entity` | `entity_name: str`, `entity_id: str`, `include_deleted: bool = False`, `deserialize: bool = False` | `Optional[Dict[str, Any]]` | Entity Operations | Fetch an entity by ID, optionally including soft-deleted entities and deserializing values. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `save_entity` | `entity_name: str`, `entity: Dict[str, Any]`, `user_id: Optional[str] = None`, `comment: Optional[str] = None`, `timeout: Optional[float] = 60` | `Dict[str, Any]` | Entity Operations | Save an entity (create or update), preparing it with system fields and updating metadata. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `save_entities` | `entity_name: str`, `entities: List[Dict[str, Any]]`, `user_id: Optional[str] = None`, `comment: Optional[str] = None`, `timeout: Optional[float] = 60` | `List[Dict[str, Any]]` | Entity Operations | Save multiple entities in a single transaction with batch operations. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `delete_entity` | `entity_name: str`, `entity_id: str`, `user_id: Optional[str] = None`, `permanent: bool = False` | `bool` | Entity Operations | Delete an entity by ID, either permanently or with soft-delete. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `restore_entity` | `entity_name: str`, `entity_id: str`, `user_id: Optional[str] = None` | `bool` | Entity Operations | Restore a soft-deleted entity by clearing the deleted_at field. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `find_entities` | `entity_name: str`, `where_clause: Optional[str] = None`, `params: Optional[Tuple] = None`, `order_by: Optional[str] = None`, `limit: Optional[int] = None`, `offset: Optional[int] = None`, `include_deleted: bool = False`, `deserialize: bool = False` | `List[Dict[str, Any]]` | Entity Operations | Query entities with flexible filtering, ordering, and pagination. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `count_entities` | `entity_name: str`, `where_clause: Optional[str] = None`, `params: Optional[Tuple] = None`, `include_deleted: bool = False` | `int` | Entity Operations | Count entities matching criteria, optionally including soft-deleted. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `get_entity_history` | `entity_name: str`, `entity_id: str`, `deserialize: bool = False` | `List[Dict[str, Any]]` | Entity Operations | Get the history of an entity with all previous versions. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:yellow">@with_timeout</code> <code style="background-color:lightgreen">@auto_transaction</code> | `get_entity_by_version` | `entity_name: str`, `entity_id: str`, `version: int`, `deserialize: bool = False` | `Optional[Dict[str, Any]]` | Entity Operations | Get a specific version of an entity from history. |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code> | `_ensure_entity_schema` | `entity_name: str`, `sample_entity: Optional[Dict[str, Any]] = None` | `None` | Schema Management | Ensure entity tables and metadata exist, creating if needed. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code> | `_update_entity_metadata` | `entity_name: str`, `entity: Dict[str, Any]` | `None` | Schema Management | Update metadata table based on entity fields and their types. |
| <code style="background-color:lightpink">@async_method</code> | `_get_entity_metadata` | `entity_name: str`, `use_cache: bool = True` | `Dict[str, str]` | Schema Management | Get metadata for an entity type, mapping field names to types. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:lightgreen">@auto_transaction</code> | `_add_to_history` | `entity_name: str`, `entity: Dict[str, Any]`, `user_id: Optional[str] = None`, `comment: Optional[str] = None` | `None` | Entity Operations | Add an entry to entity history, tracking versions. |
| <code style="background-color:lightpink">@async_method</code> | `_deserialize_entity` | `entity_name: str`, `entity: Dict[str, Optional[str]]` | `Dict[str, Any]` | Serialization | Deserialize entity values based on metadata from strings to typed values. |

</details>

<br>

`EntitySyncMixin` is the same class (except that the methods are turned into sync versions via asyncio) and is injected into <a href="#class-syncconnection">`SyncConnection`</a> via the <code style="background-color:azure">@inject_mixin</code> decorator.


</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `ConnectionPool`

Used internally by <a href="#class-poolmanager">`PoolManager`</a>.

Abstract connection pool interface that standardizes behavior across database drivers. This interface provides a consistent API for connection pool operations, regardless of the underlying database driver. It abstracts away driver-specific details and ensures that all pools implement the core functionality needed by the connection management system.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:lightpink">@async_method</code> | `health_check` | | `bool` | Diagnostic | Checks if the pool is healthy by testing a connection. To avoid excessive health checks, this caches the result for a short time. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `acquire` | `timeout: Optional[float] = None` | `Any` | Connection Management | Acquires a connection from the pool with optional timeout. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `release` | `connection: Any` | `None` | Connection Management | Releases a connection back to the pool. |
| <code style="background-color:lightpink">@async_method</code> <code style="background-color:gainsboro">@abstractmethod</code> | `close` | `force: bool = False`, `timeout: Optional[float] = None` | `None` | Resource Management | Closes the pool and all connections. |
| <code style="background-color:gainsboro">@property</code> <code style="background-color:gainsboro">@abstractmethod</code> | `min_size` | | `int` | Configuration | Gets the minimum number of connections the pool maintains. |
| <code style="background-color:gainsboro">@property</code> <code style="background-color:gainsboro">@abstractmethod</code> | `max_size` | | `int` | Configuration | Gets the maximum number of connections the pool can create. |
| <code style="background-color:gainsboro">@property</code> <code style="background-color:gainsboro">@abstractmethod</code> | `size` | | `int` | Diagnostic | Gets the current number of connections in the pool. |
| <code style="background-color:gainsboro">@property</code> <code style="background-color:gainsboro">@abstractmethod</code> | `in_use` | | `int` | Diagnostic | Gets the number of connections currently in use. |
| <code style="background-color:gainsboro">@property</code> <code style="background-color:gainsboro">@abstractmethod</code> | `idle` | | `int` | Diagnostic | Gets the number of idle connections in the pool. |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:gainsboro">@abstractmethod</code> | `_test_connection` | `connection: Any` | `None` | Diagnostic | Run a database-specific test query on the connection. |
</details>

<br>


</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `StatementCache`

Ussed internally by <a href="#class-baseconnection">`BaseConnection`</a>.

Thread-safe cache for prepared SQL statements with dynamic sizing.


<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:gainsboro">@staticmethod</code> | `hash` | `sql: str` | `str` | Cache Management | Generate a stable hash for SQL statements using MD5. |
| <code style="background-color:gainsboro">@property</code> | `hit_ratio` | | `float` | Metrics | Calculate the cache hit ratio (hits / total operations). |
| | `get` | `sql_hash` | `Optional[Tuple[Any, str]]` | Cache Management | Get a prepared statement from the cache in a thread-safe manner. |
| | `put` | `sql_hash`, `statement`, `sql` | | Cache Management | Add a prepared statement to the cache in a thread-safe manner, using LRU eviction. |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `initial_size=100`, `min_size=50`, `max_size=500`, `auto_resize=True` | | Initialization | Initialize a thread-safe cache for prepared SQL statements with dynamic sizing. |
| | `_check_resize` | | | Cache Management | Dynamically resize the cache based on hit ratio and usage patterns. |
</details>

<br>


</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `CircuitBreaker`

Used internally by the <code style="background-color:orange">@circuit_breaker</code> decorator.

Circuit breaker implementation that can be used as a decorator for sync and async methods. The circuit breaker pattern prevents cascading system failures by monitoring error rates. If too many failures occur within a time window, the circuit 'opens' and immediately rejects new requests without attempting to call the failing service. After a recovery timeout period, the circuit transitions to 'half-open' state, allowing a few test requests through. If these succeed, the circuit 'closes' and normal operation resumes; if they fail, the circuit opens again to protect system resources.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| <code style="background-color:gainsboro">@classmethod</code> | `get_or_create` | `name`, `failure_threshold=5`, `recovery_timeout=30.0`, `half_open_max_calls=3`, `window_size=60.0` | `CircuitBreaker` | Factory | Get an existing circuit breaker or create a new one with specified parameters. |
| <code style="background-color:gainsboro">@property</code> | `state` | | `CircuitState` | State Management | Get the current state of the circuit breaker (CLOSED, OPEN, or HALF_OPEN). |
| | `record_success` | | | State Management | Record a successful call through the circuit breaker. |
| | `record_failure` | | | State Management | Record a failed call through the circuit breaker. |
| | `allow_request` | | `bool` | State Management | Check if a request should be allowed through the circuit breaker based on current state. |

</details>

<br>


<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `name`, `failure_threshold=5`, `recovery_timeout=30.0`, `half_open_max_calls=3`, `window_size=60.0` | | Initialization | Initialize a new circuit breaker with failure tracking and recovery settings. |
| | `_check_state_transitions` | | | State Management | Check and apply state transitions based on timing and success/failure counts. |
</details>

<br>


</div>
<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### Functions

|Decorators| Function |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|| `with_timeout` | `default_timeout: float = 60.0` | `Callable` | Timeout Management | Decorator that adds timeout functionality to both async and sync methods. The decorated method will have a timeout applied, which can be: 1) Passed directly as a 'timeout' parameter to the method, or 2) Use the default_timeout value if none is specified. For sync methods, implements a "soft timeout" that periodically checks elapsed time. |
|| `inject_mixin` | `mixin_class` | `Callable` | Class Extension | Class decorator that adds all public methods from a mixin class to the decorated class without inheritance. Gets all public methods (non-underscore methods) from the mixin and adds them to the target class. This allows for composition-based code reuse without inheritance chains. |
|| `async_method` |`func`|`Callable`|Documentation| Marks a function as asynchronous for documentation clarity. This is a pass-through decorator that helps identify async methods in the codebase. |
|| `circuit_breaker` |`name=None, failure_threshold=5, recovery_timeout=30.0, half_open_max_calls=3, window_size=60.0`|`Callable`|Resilience| Decorator that applies circuit breaker pattern to a function or method. |
|| `retry_with_backoff` |`max_retries=3, base_delay=0.1, max_delay=10.0, exceptions=None, total_timeout=30.0`|`Callable`|Resilience| Decorator for retrying functions with exponential backoff on specified exceptions. |
|| `track_slow_method` |`threshold=2.0`|`Callable`|Instrumentation| Decorator that logs a warning if the execution of the method took longer than the threshold (in seconds). |
|| `overridable` |`method`|`Callable`|Documentation| Marks a method as overridable for documentation / IDE purposes. |
|| `auto_transaction` |`func`|`Callable`|Transaction| Decorator that automatically wraps a function in a transaction. If a transaction is already in progress, uses the existing transaction. Otherwise, creates a new transaction, commits if successful, or rolls back on exception. Works with both sync and async methods. Must be applied to methods of a class that offers in_transaction, begin_transaction, commit_transaction, and rollback_transaction methods. |

</div>