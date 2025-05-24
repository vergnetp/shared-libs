# AppConfig Usage Examples

## Basic Usage

```python
from myapp.config import AppConfig

# Simple initialization with defaults
app_config = AppConfig(
    app_name="my-awesome-api",
    environment="prod",
    version="2.1.0",
    debug=False
)

# Access configurations
print(f"Running {app_config.app_name} v{app_config.version} in {app_config.environment}")
print(f"Production mode: {app_config.is_production}")
```

## With Component Configurations

```python
from myapp.config import AppConfig
from myapp.databases import DatabaseConfig
from myapp.queue import QueueConfig, QueueRedisConfig, QueueWorkerConfig
from myapp.log import LoggerConfig

# Create specific component configurations
database_config = DatabaseConfig(
    database="production_db",
    host="db.example.com",
    port=5432,
    user="api_user",
    password="secure_password",
    env="prod"
)

redis_config = QueueRedisConfig(
    url="redis://cache.example.com:6379/0",
    connection_timeout=5.0,
    key_prefix="myapp:"
)

worker_config = QueueWorkerConfig(
    worker_count=10,
    thread_pool_size=50,
    work_timeout=60.0
)

queue_config = QueueConfig(
    redis=redis_config,
    worker=worker_config
)

logger_config = LoggerConfig(
    service_name="my-awesome-api",
    environment="prod",
    use_redis=True,
    redis_url="redis://logs.example.com:6379/1",
    min_level="INFO"
)

# Create comprehensive app configuration
app_config = AppConfig(
    database=database_config,
    queue=queue_config,
    logging=logger_config,
    app_name="my-awesome-api",
    environment="prod",
    version="2.1.0",
    debug=False
)
```

## Using the Configuration

```python
# Initialize application components
from myapp.databases import DatabaseFactory
from myapp.queue import QueueManager, QueueWorker

# Database connection
db = DatabaseFactory.create_database("postgres", app_config.database)

# Queue system
queue_manager = QueueManager(config=app_config.queue)
queue_worker = QueueWorker(config=app_config.queue)

# Access nested configurations
async with db.async_connection() as conn:
    # Use database with configured timeouts
    result = await conn.execute(
        "SELECT * FROM users WHERE status = ?", 
        ("active",),
        timeout=app_config.database.query_execution_timeout
    )

# Enqueue background tasks
queue_manager.enqueue(
    entity={"user_id": "123", "action": "send_email"},
    processor="myapp.tasks.send_welcome_email",
    priority="high"
)

# Start background worker
await queue_worker.start()
```

## Configuration Serialization

```python
# Convert to dictionary for storage/transmission
config_dict = app_config.to_dict()

# Save to file
import json
with open('app_config.json', 'w') as f:
    json.dump(config_dict, f, indent=2)

# Load from file
with open('app_config.json', 'r') as f:
    config_data = json.load(f)

restored_config = AppConfig.from_dict(config_data)
```

## Runtime Configuration Updates

```python
# Update app-level settings
app_config.update(
    environment="staging",
    debug=True,
    version="2.1.1"
)

# Update component configurations
app_config.database.update(
    host="staging-db.example.com",
    env="staging"
)

app_config.queue.worker.update(
    worker_count=5,
    thread_pool_size=20
)

app_config.logging.update(
    min_level="DEBUG"
)
```

## Environment-Based Configuration

```python
import os

def create_app_config():
    """Create AppConfig based on environment variables."""
    env = os.getenv('ENVIRONMENT', 'dev')
    
    if env == 'prod':
        return AppConfig(
            database=DatabaseConfig(
                database=os.getenv('DB_NAME'),
                host=os.getenv('DB_HOST'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                env='prod'
            ),
            queue=QueueConfig(
                redis=QueueRedisConfig(
                    url=os.getenv('REDIS_URL'),
                    key_prefix=f"{os.getenv('APP_NAME')}:"
                ),
                worker=QueueWorkerConfig(
                    worker_count=int(os.getenv('WORKER_COUNT', '10')),
                    thread_pool_size=int(os.getenv('THREAD_POOL_SIZE', '50'))
                )
            ),
            logging=LoggerConfig(
                service_name=os.getenv('APP_NAME'),
                environment='prod',
                redis_url=os.getenv('LOG_REDIS_URL'),
                min_level='INFO'
            ),
            app_name=os.getenv('APP_NAME'),
            environment='prod',
            version=os.getenv('APP_VERSION', '1.0.0'),
            debug=False
        )
    else:
        # Development configuration with simpler setup
        return AppConfig(
            database=DatabaseConfig(
                database="dev_db",
                host="localhost",
                user="dev_user",
                password="dev_password",
                env='dev'
            ),
            app_name="my-awesome-api-dev",
            environment='dev',
            debug=True
        )

# Usage
app_config = create_app_config()
```

## Configuration Validation

```python
try:
    app_config = AppConfig(
        app_name="",  # Invalid: empty name
        environment="invalid",  # Invalid: not in allowed values
        version="2.1.0"
    )
except ValueError as e:
    print(f"Configuration error: {e}")
    # Output: Configuration error: Application configuration validation failed: 
    #         app_name cannot be empty; environment must be one of: dev, test, staging, prod, got 'invalid'
```

## Accessing Configuration Properties

```python
# Application properties
print(f"App: {app_config.app_name}")
print(f"Version: {app_config.version}")
print(f"Environment: {app_config.environment}")
print(f"Debug mode: {app_config.debug}")
print(f"Is production: {app_config.is_production}")
print(f"Is development: {app_config.is_development}")

# Database configuration
print(f"Database: {app_config.database.database()}")
print(f"DB Host: {app_config.database.host()}")
print(f"DB Port: {app_config.database.port()}")

# Queue configuration
print(f"Redis URL: {app_config.queue.redis.url}")
print(f"Worker count: {app_config.queue.worker.worker_count}")
print(f"Max retry attempts: {app_config.queue.retry.max_attempts}")

# Logging configuration
print(f"Service name: {app_config.logging.service_name}")
print(f"Log level: {app_config.logging.min_level}")
print(f"Redis logging: {app_config.logging.use_redis}")
```

## Configuration Hashing

```python
# Generate stable hash for configuration
config_hash = app_config.hash()
print(f"Config hash: {config_hash}")

# Use for caching or change detection
previous_hash = config_hash
app_config.update(version="2.1.1")
new_hash = app_config.hash()

if new_hash != previous_hash:
    print("Configuration changed - may need to restart services")
```