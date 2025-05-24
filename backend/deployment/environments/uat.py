from ..config import DeploymentConfig, ContainerRuntime

uat_config = DeploymentConfig(
    api_servers=["staging-api1.company.com", "staging-api2.company.com"],
    worker_servers=["staging-worker1.company.com"],
    container_registry="staging-registry.company.com",
    container_runtime=ContainerRuntime.DOCKER,
    
    config_injection={
        "db": {
            "host": "staging-db1.company.com",
            "port": 5432,
            "database": "myapp_staging",
            "user": "myapp_staging", 
            "password": "staging_secure_password"
        },
        "redis": {
            "host": "staging-cache1.company.com",
            "port": 6379,
            "password": "staging_redis_password"
        },
        "app": {
            "name": "MyApp-Staging",
            "environment": "staging",
            "debug": False,
            "secret_key": "staging-secret-key"
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
    
    ssl_enabled=True,
    ssl_cert_path="/etc/ssl/certs/staging.crt",
    ssl_key_path="/etc/ssl/private/staging.key",
    domain_names=["staging-api.company.com"]
)