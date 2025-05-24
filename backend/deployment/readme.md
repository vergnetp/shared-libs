# Deployment Module

A comprehensive, runtime-agnostic deployment system for containerized applications with support for multiple container runtimes, nginx load balancing, SSL termination, and configuration injection.

## Features

- **Multi-Runtime Support**: Deploy to Docker, Kubernetes, Podman, or other container runtimes
- **Unified Interface**: Same API works across all supported runtimes
- **Nginx Integration**: Automatic reverse proxy setup with load balancing
- **SSL/TLS Support**: Built-in SSL termination and certificate management
- **Configuration Injection**: Dynamic build-time configuration from multiple sources
- **Dry Run Mode**: Preview deployments without making changes
- **Service Selection**: Deploy specific services or complete application stacks
- **Registry Support**: Push images to Docker Hub, AWS ECR, or private registries
- **Health Checks**: Automatic service health verification after deployment

## Architecture

The deployment system consists of three main layers:

```
┌─────────────────────────────────────────────────────────────┐
│                    Deployment API                           │
│                   (deploy function)                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              Configuration & Resolution                     │
│         (DeploymentConfig, ConfigurationResolver)          │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                Container Runtime Layer                      │
│           (Docker, Kubernetes, Podman adapters)            │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Basic Deployment

```python
from myapp.deployment import DeploymentConfig, deploy
from myapp.deployment.containers import ContainerRuntime

# Simple configuration
config = DeploymentConfig(
    api_servers=["web1.company.com", "web2.company.com"],
    worker_servers=["worker1.company.com"],
    container_registry="registry.company.com"
)

# Deploy complete stack
result = await deploy(config, version="v1.2.3")

if result["success"]:
    print(f"✓ Deployed {len(result['deployed_services'])} services")
else:
    print(f"✗ Failed services: {result['failed_services']}")
```

### Production Configuration with SSL

```python
config = DeploymentConfig(
    # Server configuration
    api_servers=["api1.company.com", "api2.company.com"],
    worker_servers=["worker1.company.com", "worker2.company.com"],
    
    # Container settings
    container_registry="123456789012.dkr.ecr.us-east-1.amazonaws.com",
    container_runtime=ContainerRuntime.KUBERNETES,
    
    # SSL configuration
    ssl_enabled=True,
    ssl_cert_path="/etc/ssl/certs/company.crt",
    ssl_key_path="/etc/ssl/private/company.key",
    domain_names=["api.company.com", "www.company.com"],
    
    # Custom container files
    container_files={
        "api": "docker/api.dockerfile",
        "worker": "docker/worker.dockerfile",
        "nginx": "docker/nginx.dockerfile"
    }
)

# Deploy with dry run first
result = await deploy(config, "v2.0.0", dry_run=True)
print("Deployment plan:", result)

# Execute actual deployment
if input("Proceed? (y/n): ") == "y":
    result = await deploy(config, "v2.0.0")
```

## Configuration Injection

Inject dynamic configuration values into container builds:

```python
from myapp.database import DatabaseConfig
from myapp.app import AppConfig

# Create configuration objects
db_config = DatabaseConfig(
    host="db.company.com",
    database="myapp_prod",
    user="app_user"
)

app_config = AppConfig(
    app_name="MyApp",
    environment="production",
    debug=False
)

# Configure deployment with injection
config = DeploymentConfig(
    api_servers=["web1", "web2"],
    
    # Inject configuration objects
    config_injection={
        "db": db_config,
        "app": app_config
    },
    
    # Map configuration paths to build arguments
    config_mapping={
        "DATABASE_HOST": "db.host",
        "DATABASE_NAME": "db.database",
        "DATABASE_USER": "db.user",
        "APP_NAME": "app.app_name",
        "ENVIRONMENT": "app.environment",
        "DEBUG_MODE": "app.debug"
    },
    
    # Mark sensitive configuration
    sensitive_configs=["db.password", "app.secret_key"]
)

# These values become available as build args in your Containerfile:
# ARG DATABASE_HOST
# ARG APP_NAME
# ENV DATABASE_HOST=${DATABASE_HOST}
# ENV APP_NAME=${APP_NAME}
```

## Container Runtime Support

### Docker Deployment

```python
config = DeploymentConfig(
    container_runtime=ContainerRuntime.DOCKER,
    api_servers=["localhost"],
    container_files={
        "api": "Dockerfile.api",
        "worker": "Dockerfile.worker"
    }
)

result = await deploy(config, "v1.0.0")
```

### Kubernetes Deployment

```python
config = DeploymentConfig(
    container_runtime=ContainerRuntime.KUBERNETES,
    api_servers=["k8s-node1", "k8s-node2"],
    container_files={
        "api": "Containerfile.api",
        "worker": "Containerfile.worker"
    }
)

result = await deploy(config, "v1.0.0")
# Creates Kubernetes deployments and services
```

## Service-Specific Deployment

Deploy individual services or subsets:

```python
# Deploy only API service
result = await deploy(config, "v1.2.3", services=["api"])

# Deploy API with nginx load balancer
result = await deploy(config, "v1.2.3", services=["api", "nginx"])

# Deploy workers only (for scaling)
result = await deploy(config, "v1.2.3", services=["worker"])

# Deploy everything (default)
result = await deploy(config, "v1.2.3")  # api + worker + nginx
```

## Nginx Configuration

The system automatically generates nginx configuration for load balancing:

### Generated Configuration Example

```nginx
upstream api_backend {
    server web1.company.com:8000;
    server web2.company.com:8000;
}

server {
    listen 80;
    listen 443 ssl;
    server_name api.company.com www.company.com;
    
    ssl_certificate /etc/ssl/certs/company.crt;
    ssl_certificate_key /etc/ssl/private/company.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

### Custom Nginx Templates

```python
config = DeploymentConfig(
    nginx_enabled=True,
    nginx_template="templates/custom-nginx.conf.template"
)

# Template supports format strings:
# upstream api_backend {
#     {upstream_servers}
# }
# server_name {domain_names};
```

## Image Templates and Naming

Customize how container images are named and tagged:

```python
config = DeploymentConfig(
    container_registry="registry.company.com",
    image_templates={
        "api": "{registry}/myapp-{service}:{version}",
        "worker": "{registry}/myapp-{service}:{version}",
        "nginx": "{registry}/myapp-proxy:latest"
    }
)

# Results in images like:
# registry.company.com/myapp-api:v1.2.3
# registry.company.com/myapp-worker:v1.2.3
# registry.company.com/myapp-proxy:latest
```

## Deployment Strategies

```python
# Rolling deployment (default)
config = DeploymentConfig(
    deployment_strategy="rolling",
    api_servers=["web1", "web2", "web3"]
)

# Blue-green deployment
config = DeploymentConfig(
    deployment_strategy="blue_green",
    api_servers=["blue-web1", "blue-web2"],
    # Additional configuration for blue-green switching
)

# Canary deployment
config = DeploymentConfig(
    deployment_strategy="canary",
    api_servers=["web1", "web2", "canary-web1"]
)
```

## Error Handling and Monitoring

```python
import logging

# Custom logging
logger = logging.getLogger("deployment")
result = await deploy(config, "v1.2.3", custom_logger=logger)

# Check deployment results
if not result["success"]:
    print(f"Failed services: {result['failed_services']}")
    for service in result["failed_services"]:
        print(f"  {service}: Check logs for details")

# Monitor successful deployments
for service_name, service_info in result["deployed_services"].items():
    print(f"✓ {service_name}: {service_info['image']}")
    print(f"  Container ID: {service_info['container_id']}")
```

## Environment-Based Configuration

Create configurations from environment variables:

```python
# Set environment variables
# DEPLOY_API_SERVERS=web1.company.com,web2.company.com
# DEPLOY_WORKER_SERVERS=worker1.company.com
# DEPLOY_DOCKER_REGISTRY=registry.company.com
# DEPLOY_RUNTIME=kubernetes

# Load from environment
config = DeploymentConfig.from_environment()
result = await deploy(config, "v1.2.3")
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
- name: Deploy Application
  run: |
    python -c "
    import asyncio
    from myapp.deployment import DeploymentConfig, deploy
    
    config = DeploymentConfig(
        api_servers=['${{ secrets.API_SERVERS }}'].split(','),
        worker_servers=['${{ secrets.WORKER_SERVERS }}'].split(','),
        container_registry='${{ secrets.REGISTRY_URL }}',
        ssl_enabled=True,
        ssl_cert_path='/etc/ssl/app.crt',
        ssl_key_path='/etc/ssl/app.key'
    )
    
    result = asyncio.run(deploy(config, '${{ github.ref_name }}'))
    exit(0 if result['success'] else 1)
    "
```

### Jenkins Pipeline Example

```groovy
pipeline {
    agent any
    stages {
        stage('Deploy') {
            steps {
                script {
                    def deployScript = """
                    from myapp.deployment import DeploymentConfig, deploy
                    import asyncio
                    
                    config = DeploymentConfig(
                        api_servers=['web1', 'web2'],
                        worker_servers=['worker1'],
                        container_registry='${env.REGISTRY_URL}'
                    )
                    
                    result = asyncio.run(deploy(config, '${env.BUILD_NUMBER}'))
                    print('Deployment:', 'SUCCESS' if result['success'] else 'FAILED')
                    """
                    
                    sh "python -c \"${deployScript}\""
                }
            }
        }
    }
}
```

## Advanced Configuration

### Multi-Environment Setup

```python
class EnvironmentConfig:
    @staticmethod
    def get_config(environment: str) -> DeploymentConfig:
        configs = {
            "development": DeploymentConfig(
                api_servers=["localhost"],
                worker_servers=["localhost"],
                container_runtime=ContainerRuntime.DOCKER,
                nginx_enabled=False
            ),
            
            "staging": DeploymentConfig(
                api_servers=["staging-web1", "staging-web2"],
                worker_servers=["staging-worker1"],
                container_registry="staging-registry.company.com",
                ssl_enabled=True,
                domain_names=["staging-api.company.com"]
            ),
            
            "production": DeploymentConfig(
                api_servers=["prod-web1", "prod-web2", "prod-web3"],
                worker_servers=["prod-worker1", "prod-worker2"],
                container_registry="prod-registry.company.com",
                container_runtime=ContainerRuntime.KUBERNETES,
                ssl_enabled=True,
                ssl_cert_path="/etc/ssl/prod.crt",
                ssl_key_path="/etc/ssl/prod.key",
                domain_names=["api.company.com", "www.company.com"]
            )
        }
        return configs[environment]

# Usage
config = EnvironmentConfig.get_config("production")
result = await deploy(config, "v2.0.0")
```

### Custom Runtime Implementation

```python
from myapp.deployment.containers import ContainerImageBuilder, ContainerRunner

class CustomRuntimeBuilder(ContainerImageBuilder):
    async def build_image(self, build_spec, logger):
        # Custom build logic
        pass
    
    def get_build_command(self, build_spec):
        # Return custom build command
        pass

class CustomRuntimeRunner(ContainerRunner):
    async def run_container(self, runtime_spec, logger):
        # Custom deployment logic
        pass

# Register custom runtime
from myapp.deployment.containers import ContainerRuntimeFactory
ContainerRuntimeFactory._builders[ContainerRuntime.CUSTOM] = CustomRuntimeBuilder
ContainerRuntimeFactory._runners[ContainerRuntime.CUSTOM] = CustomRuntimeRunner
```

## Best Practices

### 1. **Always Use Dry Run First**

```python
# Test configuration
result = await deploy(config, "v1.2.3", dry_run=True)
if result["success"]:
    # Proceed with actual deployment
    result = await deploy(config, "v1.2.3")
```

### 2. **Separate Configuration by Environment**

```python
# Use environment-specific configurations
production_config = DeploymentConfig(...)
staging_config = DeploymentConfig(...)
development_config = DeploymentConfig(...)
```

### 3. **Version Your Deployments**

```python
# Use semantic versioning
await deploy(config, "v1.2.3")  # ✓ Good
await deploy(config, "latest")   # ✗ Avoid in production
```

### 4. **Handle Sensitive Data Properly**

```python
config = DeploymentConfig(
    config_mapping={"DB_PASSWORD": "db.password"},
    sensitive_configs=["db.password"]  # Masks in logs
)
```

### 5. **Monitor Deployment Results**

```python
result = await deploy(config, version)
if not result["success"]:
    # Alert monitoring system
    alert_system.send_alert(f"Deployment failed: {result['failed_services']}")
```

## Troubleshooting

### Common Issues

**Container Build Failures**
```python
# Check build context and container files
config = DeploymentConfig(
    build_context=".",  # Ensure this contains all necessary files
    container_files={"api": "containers/Dockerfile.api"}  # Verify path exists
)
```

**Registry Push Failures**
```python
# Verify registry authentication
# For AWS ECR: aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <registry-url>
# For Docker Hub: docker login
```

**Nginx Configuration Issues**
```python
# Generate config first to debug
config = DeploymentConfig(...)
nginx_config = config.generate_nginx_config(["web1:8000", "web2:8000"])
print(nginx_config)  # Inspect generated configuration
```

**SSL Certificate Problems**
```python
# Verify certificate paths and permissions
config = DeploymentConfig(
    ssl_enabled=True,
    ssl_cert_path="/path/to/cert.crt",  # Must be readable by nginx container
    ssl_key_path="/path/to/cert.key"   # Must be readable by nginx container
)
```

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable verbose logging
result = await deploy(config, version, custom_logger=logging.getLogger())
```

## API Reference

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `DeploymentConfig`

Runtime-agnostic deployment configuration for containerized applications.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `@property` | `api_servers` | | `List[str]` | Configuration | Returns list of API server hostnames/IPs where API containers will be deployed. |
| `@property` | `worker_servers` | | `List[str]` | Configuration | Returns list of worker server hostnames/IPs where worker containers will be deployed. |
| `@property` | `container_registry` | | `Optional[str]` | Configuration | Returns container registry URL for pushing/pulling images. |
| `@property` | `container_runtime` | | `ContainerRuntime` | Configuration | Returns selected container runtime (DOCKER, KUBERNETES, etc.). |
| `@property` | `build_context` | | `str` | Configuration | Returns build context directory for container builds. |
| `@property` | `ssl_enabled` | | `bool` | Configuration | Returns whether SSL/TLS termination is enabled in nginx. |
| `@property` | `nginx_enabled` | | `bool` | Configuration | Returns whether nginx reverse proxy is enabled. |
| `@classmethod` | `from_environment` | | `DeploymentConfig` | Factory | Creates configuration from environment variables (DEPLOY_API_SERVERS, etc.). |
| `@classmethod` | `from_dict` | `data: Dict[str, Any]` | `DeploymentConfig` | Factory | Creates configuration instance from dictionary representation. |
| | `get_servers_by_type` | `server_type: str` | `List[str]` | Utility | Returns servers by type ("api" or "worker"). |
| | `create_container_image` | `service_type: str`, `version: str` | `ContainerImage` | Factory | Creates ContainerImage specification for a service with proper naming and registry. |
| | `generate_nginx_config` | `api_instances: List[str]` | `str` | Generation | Generates nginx configuration for load balancing across API instances. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Returns configuration as dictionary for storage or debugging. |
| | `hash` | | `str` | Utility | Returns stable hash of configuration (excludes sensitive fields). |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `api_servers: List[str]=None`, `worker_servers: List[str]=None`, `container_registry: Optional[str]=None`, `deployment_strategy: str="rolling"`, `container_files: Optional[Dict[str, str]]=None`, `build_context: str="."`, `build_args: Optional[Dict[str, str]]=None`, `image_templates: Optional[Dict[str, str]]=None`, `config_injection: Optional[Dict[str, Any]]=None`, `config_mapping: Optional[Dict[str, str]]=None`, `sensitive_configs: Optional[List[str]]=None`, `container_runtime: ContainerRuntime=ContainerRuntime.DOCKER`, `nginx_enabled: bool=True`, `nginx_template: Optional[str]=None`, `ssl_enabled: bool=False`, `ssl_cert_path: Optional[str]=None`, `ssl_key_path: Optional[str]=None`, `domain_names: List[str]=None` | | Initialization | Initializes deployment configuration with server lists, container settings, and runtime preferences. |
| | `_validate_config` | | `None` | Validation | Validates configuration parameters and raises ValueError for invalid settings. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### function `deploy`

Deploy containerized applications using the specified runtime configuration.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `DeploymentConfig` | Required | Deployment configuration containing server lists, container settings, and runtime preferences. |
| `version` | `str` | Required | Version tag to apply to built images and deployments (e.g., "v1.2.3", "latest"). |
| `services` | `List[str]` | `None` | List of specific services to deploy. If None, deploys all configured services. |
| `dry_run` | `bool` | `False` | If True, simulates deployment without making actual changes. |
| `custom_logger` | `Any` | `None` | Custom logger instance for deployment output. |

**Returns:** `Dict[str, Any]` containing deployment results with deployed_services, failed_services, success status, and error details.

</div>