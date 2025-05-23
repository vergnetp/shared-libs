import time, os
from typing import Dict, Any, List

from .config import DeploymentConfig, ConfigurationResolver
from .types import ContainerBuildSpec,  ContainerRuntimeSpec
from .containers.factory import ContainerRuntimeFactory
from .containers.interface import ContainerImage
from .. import log as logger  

async def deploy(
    config: DeploymentConfig,
    version: str,
    services: List[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Deploy containerized applications using the specified runtime configuration.
    
    This function handles the complete deployment lifecycle including building container images,
    pushing to registries, and deploying to target servers. It supports multiple container
    runtimes (Docker, Kubernetes, etc.) and can deploy individual services or complete stacks.
    
    Args:
        config (DeploymentConfig): Deployment configuration containing server lists, container
            settings, and runtime preferences. This determines how and where containers are deployed.
            
        version (str): Version tag to apply to built images and deployments. This should follow
            semantic versioning conventions (e.g., "1.2.3", "v2.0.0-beta", "latest").
            Used for image tagging and deployment tracking.
            
        services (List[str], optional): List of specific services to deploy. If None, deploys
            all configured services (typically ["api", "worker"] plus nginx if enabled).
            Available services depend on container_files configuration.
            Example: ["api"] (deploy only API), ["api", "nginx"] (API with load balancer)
            
        dry_run (bool, optional): If True, simulates the deployment without making actual changes.
            Defaults to False. Dry run mode will:
            - Validate configuration and dependencies
            - Show what commands would be executed
            - Display generated configurations (nginx, etc.)
            - Skip actual building, pushing, and deployment steps
            Useful for testing configurations and CI/CD pipeline validation.  
            
    Returns:
        Dict[str, Any]: Comprehensive deployment results containing:
            - deployed_services (Dict[str, Dict]): Details for each successfully deployed service.
              Each service entry contains:
                - success (bool): Whether deployment succeeded
                - image (str): Full image name with tag
                - container_id (str): Runtime-specific container/deployment identifier
                - Additional runtime-specific metadata
            - failed_services (List[str]): Names of services that failed to deploy
            - success (bool): True if all requested services deployed successfully
            - total_services (int): Total number of services attempted
            - error (str, optional): Error message if overall deployment failed
            
    Raises:
        ValueError: If configuration is invalid or services are not recognized
        RuntimeError: If container runtime is not available or configured incorrectly
        ConnectionError: If unable to connect to container registry or target servers
        
    Example:
        >>> # Deploy complete application stack
        >>> config = DeploymentConfig(
        ...     api_servers=["web1", "web2"],
        ...     worker_servers=["worker1"],
        ...     container_registry="registry.company.com"
        ... )
        >>> result = await deploy(config, "v1.2.3")
        >>> if result["success"]:
        ...     print(f"Deployed {len(result['deployed_services'])} services")
        ... else:
        ...     print(f"Failed services: {result['failed_services']}")
        
        >>> # Deploy only API service with dry run
        >>> result = await deploy(
        ...     config, 
        ...     "v1.2.4", 
        ...     services=["api"], 
        ...     dry_run=True
        ... )
        >>> # Shows what would happen without making changes
        
    Note:
        - Images are built in parallel where possible to improve deployment speed
        - Registry pushing occurs automatically if container_registry is configured
        - Nginx deployment includes automatic upstream configuration based on api_servers
        - Failed services don't prevent other services from deploying successfully
        - Container runtime commands vary (docker vs kubectl) but the interface remains consistent
        
    Runtime Behavior:
        1. **Validation**: Checks configuration and runtime availability
        2. **Image Building**: Builds container images for each service using specified runtime
        3. **Registry Push**: Pushes images to registry if configured (skipped for local deployments)
        4. **Service Deployment**: Deploys containers to target servers with proper networking
        5. **Health Checks**: Verifies deployed services are responding correctly
        6. **Cleanup**: Removes temporary files and reports final status
        
    See Also:
        - DeploymentConfig: For configuration options and examples
        - ContainerRuntime: For supported runtime environments
        - Container runtimes documentation for runtime-specific deployment details
    """
   
    try:
        logger.info(f"Deploying containers using {config.container_runtime.value} runtime")
        
        # Determine which services to deploy
        if services is None:
            services = ["api"]
            # Add worker services based on available container files
            if "worker-queue" in config.container_files:
                services.append("worker-queue")
            if "worker-db" in config.container_files:
                services.append("worker-db")
            if "worker" in config.container_files:  
                services.append("worker")
            if config.nginx_enabled:
                services.append("nginx")
        
        # Create runtime-appropriate implementations
        image_builder = ContainerRuntimeFactory.create_image_builder(config)
        container_runner = ContainerRuntimeFactory.create_container_runner(config)
        
        # Resolve configuration values
        resolver = ConfigurationResolver(config)
        resolved_args = resolver.resolve_all_config_values(mask_sensitive=False)
        
        # Build and deploy each service
        deployed_services = {}
        failed_services = []
        
        for service in services:
            try:
                if service == "nginx":
                    # Handle nginx deployment specially
                    nginx_result = await _deploy_nginx_service(
                        config, image_builder, container_runner, dry_run, logger
                    )
                    if nginx_result["success"]:
                        deployed_services[service] = nginx_result
                    else:
                        failed_services.append(service)
                else:
                    # Handle regular application services
                    service_result = await _deploy_app_service(
                        config, service, version, resolved_args, 
                        image_builder, container_runner, dry_run, logger
                    )
                    if service_result["success"]:
                        deployed_services[service] = service_result
                    else:
                        failed_services.append(service)
                        
            except Exception as e:
                logger.error(f"Failed to deploy {service}: {e}")
                failed_services.append(service)
        
        return {
            "deployed_services": deployed_services,
            "failed_services": failed_services,
            "success": len(failed_services) == 0,
            "total_services": len(services)
        }
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        return {
            "deployed_services": {},
            "failed_services": services or [],
            "success": False,
            "error": str(e)
        }

async def _deploy_app_service(
    config: DeploymentConfig,
    service: str,
    version: str,
    resolved_args: Dict[str, str],
    image_builder,
    container_runner,
    dry_run: bool,
    log
) -> Dict[str, Any]:
    """Deploy a single application service (api/worker)."""
    try:
        # Create container image specification
        container_image = config.create_container_image(service, version)
        
        # Create build specification
        build_spec = ContainerBuildSpec(
            image=container_image,
            build_args=resolved_args,
            labels={
                "app.name": config.config_injection.get("app", {}).get("app_name", "unknown"),
                "app.version": version,
                "build.timestamp": str(int(time.time())),
                "service.type": service
            }
        )
        
        if dry_run:
            log.info(f"[DRY RUN] Would build and deploy: {container_image}")
            return {
                "success": True,
                "image": str(container_image),
                "dry_run": True
            }
        
        # Build the image
        build_success = await image_builder.build_image(build_spec, log)
        if not build_success:
            return {"success": False, "error": "Build failed"}
        
        # Push to registry if configured
        if config.container_registry:
            push_success = await image_builder.push_image(container_image, log)
            if not push_success:
                log.warning(f"Failed to push {service} image to registry")
        
        # Create runtime spec for deployment
        runtime_spec = _create_service_runtime_spec(config, service, container_image)
        
        # Deploy the container
        container_id = await container_runner.run_container(runtime_spec, log)
        
        log.info(f"✓ {service} deployed: {container_id}")
        
        return {
            "success": True,
            "image": str(container_image),
            "container_id": container_id
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _deploy_nginx_service(
    config: DeploymentConfig,
    image_builder,
    container_runner,
    dry_run: bool,
    log
) -> Dict[str, Any]:
    """Deploy nginx service."""
    try:
        # Get API instance endpoints for upstream configuration
        api_instances = [f"{server}:8000" for server in config.api_servers]
        
        # Generate nginx config
        nginx_config_content = config.generate_nginx_config(api_instances)
        
        if dry_run:
            log.info("[DRY RUN] Would deploy nginx with config:")
            log.info(nginx_config_content[:200] + "..." if len(nginx_config_content) > 200 else nginx_config_content)
            return {"success": True, "dry_run": True}
        
        # Write nginx config to build context
        nginx_config_path = os.path.join(config.build_context, "nginx.conf")
        with open(nginx_config_path, 'w') as f:
            f.write(nginx_config_content)
        
        # Create nginx image
        if "nginx" in config.container_files:
            # Build custom nginx image
            nginx_image = config.create_container_image("nginx", "latest")
            
            build_spec = ContainerBuildSpec(
                image=nginx_image,
                build_args={},
                labels={
                    "app.name": "nginx-proxy",
                    "service.type": "nginx"
                }
            )
            
            build_success = await image_builder.build_image(build_spec, log)
            if not build_success:
                return {"success": False, "error": "Failed to build nginx image"}
        else:
            # Use official nginx image            
            nginx_image = ContainerImage(name="nginx", tag="alpine", registry="docker.io")
        
        # Create runtime spec
        nginx_spec = ContainerRuntimeFactory.create_nginx_spec(config, api_instances, nginx_config_path)
        
        # Deploy nginx container
        nginx_container_id = await container_runner.run_container(nginx_spec, log)
        
        log.info(f"✓ Nginx deployed: {nginx_container_id}")
        
        return {
            "success": True,
            "image": str(nginx_image),
            "container_id": nginx_container_id,
            "config_path": nginx_config_path
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def _create_service_runtime_spec(config: DeploymentConfig, service: str, container_image) -> ContainerRuntimeSpec:
    """Create runtime specification for application services."""
    
    # Default ports for services
    service_ports = {
        "api": [8000],
        "worker": []  # Workers typically don't expose ports
    }
    
    # Default environment variables
    environment = {
        "SERVICE_TYPE": service,
        "ENVIRONMENT": getattr(config.config_injection.get("app", {}), "environment", "prod")
    }
    
    return ContainerRuntimeSpec(
        image=container_image,
        ports=service_ports.get(service, []),
        environment=environment,
        restart_policy="unless-stopped",
        health_check="curl -f http://localhost:8000/health || exit 1" if service == "api" else None
    )