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
    env="dev"
)

# Sync usage
with db.sync_transaction() as conn:
    result = conn.execute("SELECT * FROM users WHERE id = ?", (1,))
    # Process result...

# Async usage
async def async_example():
    async with db.async_transaction() as conn:
        result = await conn.execute_async("SELECT * FROM users WHERE id = ?", (1,))
        # Process result...

# Shutdown
async def shutdown():
    await PostgresDatabase.close_pool()
