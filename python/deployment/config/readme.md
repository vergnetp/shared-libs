# DeploymentConfig Usage Examples

## Basic Usage

```python
from myapp.config import DeploymentConfig

# Simple deployment configuration
deploy_config = DeploymentConfig(
    api_servers=["api1.example.com", "api2.example.com"],
    worker_servers=["worker1.example.com", "worker2.example.com"],
    docker_registry="registry.example.com",
    deployment_strategy="rolling"
)

print(f"Deploying to {deploy_config.total_server_count} servers")
print(f"API servers: {deploy_config.api_servers}")
print(f"Worker servers: {deploy_config.worker_servers}")
```

## Production Configuration

```python
# Production deployment with comprehensive settings
production_deploy = DeploymentConfig(
    api_servers=[
        "api1.prod.example.com",
        "api2.prod.example.com", 
        "api3.prod.example.com"
    ],
    worker_servers=[
        "worker1.prod.example.com",
        "worker2.prod.example.com",
        "worker3.prod.example.com",
        "worker4.prod.example.com"
    ],
    docker_registry="registry.prod.example.com",
    docker_username_env_var="PROD_DOCKER_USER",
    docker_password_env_var="PROD_DOCKER_PASS",
    deployment_timeout=600.0,  # 10 minutes
    health_check_timeout=120.0,  # 2 minutes
    rollback_on_failure=True,
    max_parallel_deployments=2,  # Conservative for production
    deployment_strategy="blue_green"
)
```

## Environment-Based Configuration

```python
import os

# Set environment variables
os.environ['DEPLOY_API_SERVERS'] = "api1.example.com,api2.example.com,api3.example.com"
os.environ['DEPLOY_WORKER_SERVERS'] = "worker1.example.com,worker2.example.com"
os.environ['DEPLOY_DOCKER_REGISTRY'] = "registry.example.com"
os.environ['DEPLOY_STRATEGY'] = "canary"
os.environ['DEPLOY_MAX_PARALLEL'] = "5"

# Create from environment variables
deploy_config = DeploymentConfig.from_environment()
print(f"Loaded {len(deploy_config.api_servers)} API servers from environment")
```

## Docker Integration

```python
# Check Docker configuration
if deploy_config.has_docker_registry:
    print(f"Using Docker registry: {deploy_config.docker_registry}")
    
    if deploy_config.is_docker_authenticated():
        creds = deploy_config.get_docker_credentials()
        print(f"Docker username: {creds['username']}")
        print("Docker password: [MASKED]")
    else:
        print("Warning: Docker credentials not found in environment")
        print(f"Set {deploy_config.docker_username_env_var} and {deploy_config.docker_password_env_var}")
```

## Deployment Logic Integration

```python
async def deploy_application(deploy_config: DeploymentConfig, app_version: str):
    """Deploy application using the deployment configuration."""
    
    print(f"Starting {deploy_config.deployment_strategy} deployment...")
    print(f"Version: {app_version}")
    print(f"Timeout: {deploy_config.deployment_timeout}s")
    
    try:
        # Deploy to API servers
        api_servers = deploy_config.get_servers_by_type('api')
        await deploy_to_servers(
            servers=api_servers,
            service_type="api",
            version=app_version,
            max_parallel=deploy_config.max_parallel_deployments,
            timeout=deploy_config.deployment_timeout
        )
        
        # Deploy to worker servers
        worker_servers = deploy_config.get_servers_by_type('worker')
        await deploy_to_servers(
            servers=worker_servers,
            service_type="worker", 
            version=app_version,
            max_parallel=deploy_config.max_parallel_deployments,
            timeout=deploy_config.deployment_timeout
        )
        
        # Health checks
        await perform_health_checks(
            servers=deploy_config.all_servers,
            timeout=deploy_config.health_check_timeout
        )
        
        print("Deployment completed successfully!")
        
    except DeploymentError as e:
        if deploy_config.rollback_on_failure:
            print(f"Deployment failed: {e}")
            print("Rolling back...")
            await rollback_deployment(deploy_config.all_servers)
        else:
            print(f"Deployment failed: {e}")
            print("Rollback disabled - manual intervention required")
            raise

async def deploy_to_servers(servers, service_type, version, max_parallel, timeout):
    """Deploy to a list of servers with parallel execution."""
    import asyncio
    
    semaphore = asyncio.Semaphore(max_parallel)
    
    async def deploy_single_server(server):
        async with semaphore:
            print(f"Deploying {service_type} v{version} to {server}...")
            # Simulate deployment
            await asyncio.sleep(2)
            print(f"✓ {server} deployment complete")
    
    tasks = [deploy_single_server(server) for server in servers]
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=timeout)
```

## Configuration Validation

```python
try:
    # Invalid configuration
    bad_config = DeploymentConfig(
        api_servers=[],  # Empty list - invalid
        worker_servers=["worker1"],
        deployment_timeout=-1,  # Negative timeout - invalid
        deployment_strategy="invalid_strategy"  # Invalid strategy
    )
except ValueError as e:
    print(f"Configuration error: {e}")
    # Output: Configuration error: Deployment configuration validation failed: 
    #         api_servers cannot be empty; deployment_timeout must be positive, got -1; 
    #         deployment_strategy must be one of {'rolling', 'blue_green', 'canary'}, got 'invalid_strategy'
```

## Serialization and Storage

```python
# Convert to dictionary
config_dict = deploy_config.to_dict()

# Save to JSON file
import json
with open('deployment_config.json', 'w') as f:
    json.dump(config_dict, f, indent=2)

# Load from JSON file
with open('deployment_config.json', 'r') as f:
    config_data = json.load(f)

restored_config = DeploymentConfig.from_dict(config_data)
```

## Integration with AppConfig

```python
from myapp.config import AppConfig, DeploymentConfig

# Add deployment config to main app configuration
class AppConfig(BaseConfig):
    def __init__(
        self,
        database: Optional[DatabaseConfig] = None,
        queue: Optional[QueueConfig] = None,
        logging: Optional[LoggerConfig] = None,
        deployment: Optional[DeploymentConfig] = None,  # Add deployment config
        app_name: str = "application",
        environment: str = "dev",
        version: str = "1.0.0",
        debug: bool = False
    ):
        # ... existing initialization ...
        self._deployment = deployment or DeploymentConfig()
    
    @property
    def deployment(self) -> DeploymentConfig:
        """Get deployment configuration."""
        return self._deployment

# Usage
app_config = AppConfig(
    deployment=DeploymentConfig(
        api_servers=["api1.example.com", "api2.example.com"],
        worker_servers=["worker1.example.com"],
        deployment_strategy="rolling"
    ),
    app_name="my-awesome-api",
    environment="prod"
)

# Deploy the application
await deploy_application(app_config.deployment, app_config.version)
```

## Different Deployment Strategies

```python
# Rolling deployment (default)
rolling_config = DeploymentConfig(
    api_servers=["api1", "api2", "api3"],
    deployment_strategy="rolling",
    max_parallel_deployments=1  # One at a time
)

# Blue-green deployment
blue_green_config = DeploymentConfig(
    api_servers=["blue-api1", "blue-api2", "green-api1", "green-api2"],
    deployment_strategy="blue_green",
    max_parallel_deployments=4  # All at once
)

# Canary deployment
canary_config = DeploymentConfig(
    api_servers=["canary-api1", "prod-api1", "prod-api2", "prod-api3"],
    deployment_strategy="canary",
    max_parallel_deployments=1,  # Start with canary only
    health_check_timeout=300.0  # Longer health checks for canary
)
```