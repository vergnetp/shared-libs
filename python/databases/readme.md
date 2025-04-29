# Databases Module

This module provides a unified interface for working with different database types (SQLite, MySQL, PostgreSQL) with both synchronous and asynchronous APIs.

## Overview

The databases module allows you to:

- Connect to SQLite, MySQL, or PostgreSQL databases
- Execute SQL queries with parameterized statements
- Work with transactions (begin, commit, rollback)
- Store and retrieve entity objects with dynamic schema evolution
- Use both synchronous and asynchronous APIs with the same interface

## Quick Start

```python
from python.databases import DatabaseFactory

# Create a SQLite database
db = DatabaseFactory("sqlite", database="mydata.db")

# Store an entity
user = {"id": "user1", "name": "John Doe", "email": "john@example.com"}
db.save_entity("users", user)

# Retrieve an entity
retrieved_user = db.get_entity("users", "user1")
print(retrieved_user)  # {"id": "user1", "name": "John Doe", "email": "john@example.com"}

# Use transactions
with db.transaction():
    db.save_entity("orders", {"id": "order1", "user_id": "user1", "total": 99.99})
    db.save_entity("order_items", {"id": "item1", "order_id": "order1", "product": "Widget"})

# Close the connection when done
db.close()
```

## Configuration

The database module can be configured with these parameters:

### SQLite
```python
db = DatabaseFactory(
    "sqlite",
    database="path/to/database.db",  # Database file path
    alias="my_db",                    # Optional friendly name
    env="dev"                         # Environment (prod, dev, test)
)
```

### MySQL
```python
db = DatabaseFactory(
    "mysql", 
    database="mydatabase",            # Database name
    host="localhost",                 # Host
    port=3306,                        # Port
    user="dbuser",                    # Username
    password="dbpass",                # Password
    alias="my_mysql_db"               # Optional friendly name
)
```

### PostgreSQL
```python
db = DatabaseFactory(
    "postgres",
    database="mydatabase",            # Database name
    host="localhost",                 # Host
    port=5432,                        # Port
    user="dbuser",                    # Username
    password="dbpass",                # Password
    alias="my_postgres_db"            # Optional friendly name
)
```

## Entity API

The entity API provides a higher-level abstraction for storing schema-less data in relational databases:

```python
# Save an entity
db.save_entity("collection_name", {"id": "entity_id", "field1": "value1", "field2": 42})

# Save multiple entities
db.save_entities("collection_name", [
    {"id": "id1", "name": "Entity 1"},
    {"id": "id2", "name": "Entity 2"}
])

# Get a single entity by ID
entity = db.get_entity("collection_name", "entity_id")

# Get all entities in a collection
all_entities = db.get_entities("collection_name")

# Get entities with a filter
filtered = db.get_entities("collection_name", "field1 = 'value1'")

# Async versions
await db.save_entity_async("collection_name", entity_data)
await db.save_entities_async("collection_name", entities_list)
entity = await db.get_entity_async("collection_name", "entity_id")
entities = await db.get_entities_async("collection_name", filter_condition)
```

## SQL API

The module also provides direct SQL execution capabilities:

```python
# Execute SQL query with parameters
results = db.execute_sql("SELECT * FROM users WHERE age > %s", (30,))

# Execute batch SQL
db.executemany_sql(
    "INSERT INTO logs (timestamp, message) VALUES (%s, %s)",
    [
        ("2025-04-29 10:00:00", "Log message 1"),
        ("2025-04-29 10:01:00", "Log message 2")
    ]
)

# Async versions
results = await db.execute_sql_async("SELECT * FROM users WHERE age > $1", (30,))
await db.executemany_sql_async("INSERT INTO logs VALUES ($1, $2)", batch_parameters)
```

## Transaction API

Transactions can be used in both synchronous and asynchronous code:

```python
# Synchronous with explicit begin/commit
db.begin_transaction()
try:
    db.execute_sql("INSERT INTO users VALUES (%s, %s)", ("user1", "John"))
    db.execute_sql("INSERT INTO profiles VALUES (%s, %s)", ("user1", "bio"))
    db.commit_transaction()
except Exception:
    db.rollback_transaction()
    raise

# Synchronous with context manager
with db.transaction():
    db.execute_sql("INSERT INTO users VALUES (%s, %s)", ("user2", "Jane"))
    db.execute_sql("INSERT INTO profiles VALUES (%s, %s)", ("user2", "bio"))
    # Auto-commits on success, auto-rolls back on exception

# Asynchronous with explicit begin/commit
await db.begin_transaction_async()
try:
    await db.execute_sql_async("INSERT INTO users VALUES ($1, $2)", ("user3", "Bob"))
    await db.execute_sql_async("INSERT INTO profiles VALUES ($1, $2)", ("user3", "bio"))
    await db.commit_transaction_async()
except Exception:
    await db.rollback_transaction_async()
    raise

# Asynchronous with decorator
@db.async_transaction
async def create_user(user_data):
    await db.execute_sql_async("INSERT INTO users VALUES ($1, $2)", 
                              (user_data["id"], user_data["name"]))
    await db.execute_sql_async("INSERT INTO profiles VALUES ($1, $2)", 
                              (user_data["id"], user_data["bio"]))
    # Auto-commits on success, auto-rolls back on exception
```

## Testing

The module includes a comprehensive test suite with tests for each database type. To run tests:

```bash
cd python
scripts/run_unit_tests.bat  # On Windows
# OR
pytest -xvs  # On any platform with pytest installed
```

Database tests require Docker to be running, as they use docker-compose to start test database containers.

## Connection Pooling

For MySQL and PostgreSQL databases, the module maintains connection pools for asynchronous operations. The pools are initialized on demand and can be explicitly closed:

```python
# MySQL pool
await MySqlDatabase.close_pool()

# PostgreSQL pool
await PostgresDatabase.close_pool()
```

## Schema Evolution

The module automatically handles schema evolution as you add new fields to entities:

```python
# Initial entity
db.save_entity("users", {"id": "user1", "name": "John"})

# Later, add a new field
db.save_entity("users", {"id": "user2", "name": "Jane", "email": "jane@example.com"})

# Update the first entity with the new field
db.save_entity("users", {"id": "user1", "name": "John", "email": "john@example.com"})
```

The module will automatically update the database schema to accommodate the new field.

## Closing Connections

Always close database connections when you're done with them:

```python
# Synchronous close
db.close()

# Asynchronous close
await db.close_async()
```

For applications using connection pools, close the pools at application shutdown:

```python
# Close pools at application shutdown
async def shutdown():
    await MySqlDatabase.close_pool()
    await PostgresDatabase.close_pool()
```

## Error Handling

All database errors are wrapped in `TrackError` from the `errors` module:

```python
from python.errors import TrackError

try:
    db.execute_sql("INVALID SQL")
except TrackError as e:
    print(f"Database error: {e}")
    # Original exception is available as e.error
```

## Compatibility

- Requires Python 3.8 or later
- Dependencies:
  - SQLite: `sqlite3` (standard library) and `aiosqlite`
  - MySQL: `pymysql` and `aiomysql`
  - PostgreSQL: `psycopg2` and `asyncpg`
  - Common: `nest_asyncio` for handling nested event loops