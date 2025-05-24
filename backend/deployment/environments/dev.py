from ..config import DeploymentConfig, ContainerRuntime

dev_config = DeploymentConfig(
    api_servers=["localhost"],
    worker_servers=["localhost"],
    container_registry=None,  # No registry for local dev
    container_runtime=ContainerRuntime.DOCKER,
    
    config_injection={
        "db": {
            "host": "localhost",
            "port": 5432,
            "database": "myapp_dev",
            "user": "myapp",
            "password": "devpassword"
        },
        "redis": {
            "host": "localhost", 
            "port": 6379,
            "password": "devpassword"
        },
        "app": {
            "name": "MyApp-Dev",
            "environment": "development",
            "debug": True,
            "secret_key": "dev-secret-not-secure"
        }
    },
    
    config_mapping={
        "DATABASE_HOST": "db.host",
        "DATABASE_PORT": "db.port",
        "DATABASE_NAME": "db.database",
        "DATABASE_USER": "db.user", 
        "DATABASE_PASSWORD": "db.password",
        "REDIS_URL": "redis://:{redis.password}@{redis.host}:{redis.port}/0",
        "APP_NAME": "app.name",
        "ENVIRONMENT": "app.environment"
    },
    
    ssl_enabled=False,
    domain_names=["localhost"],
    nginx_enabled=True
)
