from ..config import DeploymentConfig, ContainerRuntime
from ...databases.config import DatabaseConfig

# Production configuration
prod_config = DeploymentConfig(
    # Production servers
    api_servers=[
        "prod-api1.company.com",
        "prod-api2.company.com", 
        "prod-api3.company.com"
    ],
    
    worker_servers=[
        "prod-worker1.company.com",
        "prod-worker2.company.com"
    ],
    
    # Container settings
    container_registry="prod-registry.company.com",
    container_runtime=ContainerRuntime.KUBERNETES,
    build_context=".",
    
    # Container files
    container_files={
        "api": "containers/Containerfile.api",
        "worker-queue": "containers/Containerfile.worker-queue", 
        "worker-db": "containers/Containerfile.worker-db",
        "nginx": "containers/Containerfile.nginx",
        "postgres": "containers/Containerfile.postgres",
        "redis": "containers/Containerfile.redis",
        "opensearch": "containers/Containerfile.opensearch"
    },
    
    # Configuration injection
    config_injection={
        "db": DatabaseConfig(
            host="prod-db-cluster.company.com",
            port=5432,
            database="myapp_production", 
            user= "myapp_prod",
            password= "super_secure_production_password"
        )
       
    },   

    
    # Sensitive configurations
    sensitive_configs=[
        "db.password",
        "redis.password", 
        "opensearch.password",
        "app.secret_key"
    ],
    
    # SSL configuration
    ssl_enabled=True,
    ssl_cert_path="/etc/ssl/certs/company.crt",
    ssl_key_path="/etc/ssl/private/company.key",
    domain_names=[
        "api.company.com",
        "www.company.com",
        "app.company.com"
    ],
    
    # Nginx enabled
    nginx_enabled=True
)