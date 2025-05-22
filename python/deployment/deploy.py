import time, os
from typing import Dict, Any, List

from .config import DeploymentConfig, ConfigurationResolver
from .containers import ContainerBuildSpec, ContainerRuntimeFactory, ContainerImage
from .. import log as logger  


async def deploy_containers_runtime_agnostic(
    config: DeploymentConfig,
    version: str,
    service_type: str = "all",
    dry_run: bool = False,
    custom_logger = None
) -> Dict[str, Any]:
    """
    Deploy containers using any supported runtime.
    The same function works for Docker, Kubernetes, Podman, etc.
    
    Args:
        config: Deployment configuration
        version: Version tag for the containers
        service_type: Type of service to deploy ("all", "api", "worker")
        dry_run: If True, only show what would be done
        custom_logger: Optional logger instance
        
    Returns:
        Dictionary with deployment results
    """
    # Use provided logger or default
    log = custom_logger if custom_logger else logger
    
    try:
        log.info(f"Deploying containers using {config.container_runtime.value} runtime")
        
        # Create runtime-appropriate implementations
        image_builder = ContainerRuntimeFactory.create_image_builder(config)
        container_runner = ContainerRuntimeFactory.create_container_runner(config)
        
        # Resolve configuration values
        resolver = ConfigurationResolver(config)
        resolved_args = resolver.resolve_all_config_values(mask_sensitive=False)
        
        # Build images for each service
        built_images = {}
        failed_services = []
        services = ["api", "worker"] if service_type == "all" else [service_type]
        
        for service in services:
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
                    log.info(f"[DRY RUN] Would build: {container_image}")
                    built_images[service] = str(container_image)
                    continue
                
                # Build the image (works with any runtime)
                success = await image_builder.build_image(build_spec, log)
                
                if success:
                    built_images[service] = str(container_image)
                    
                    # Push to registry if configured
                    if config.container_registry:
                        push_success = await image_builder.push_image(container_image, log)
                        if not push_success:
                            log.warning(f"Failed to push {service} image to registry")
                else:
                    failed_services.append(service)
                    
            except Exception as e:
                log.error(f"Failed to build {service}: {e}")
                failed_services.append(service)
        
        return {
            "images_built": built_images,
            "failed_services": failed_services,
            "success": len(failed_services) == 0
        }
        
    except Exception as e:
        log.error(f"Deployment failed: {e}")
        return {
            "images_built": {},
            "failed_services": services,
            "success": False,
            "error": str(e)
        }

async def _deploy_nginx(config: DeploymentConfig, api_instances: List[str], dry_run: bool, log) -> Dict[str, Any]:
        """Deploy nginx with proper configuration."""
        try:
            # Generate nginx config
            nginx_config_content = config.generate_nginx_config(api_instances)
            
            if dry_run:
                log.info("[DRY RUN] Would deploy nginx with config:")
                log.info(nginx_config_content[:200] + "..." if len(nginx_config_content) > 200 else nginx_config_content)
                return {"nginx_deployed": True, "dry_run": True}
            
            # Write nginx config to build context
            nginx_config_path = os.path.join(config.build_context, "nginx.conf")
            with open(nginx_config_path, 'w') as f:
                f.write(nginx_config_content)
            
            # Create nginx image if using custom build
            if "nginx" in config.container_files:
                nginx_image = config.create_container_image("nginx", "latest")
                
                # Build nginx image
                image_builder = ContainerRuntimeFactory.create_image_builder(config)
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
                    return {"nginx_deployed": False, "error": "Failed to build nginx image"}
            else:
                # Use official nginx image
                nginx_image = ContainerImage(name="nginx", tag="alpine", registry="docker.io")
            
            # Create runtime spec
            container_runner = ContainerRuntimeFactory.create_container_runner(config)
            nginx_spec = ContainerRuntimeFactory.create_nginx_spec(config, api_instances, nginx_config_path)
            
            # Deploy nginx container
            nginx_container_id = await container_runner.run_container(nginx_spec, log)
            
            log.info(f"✓ Nginx deployed: {nginx_container_id}")
            
            return {
                "nginx_deployed": True,
                "nginx_container_id": nginx_container_id,
                "nginx_config_path": nginx_config_path
            }
            
        except Exception as e:
            log.error(f"Nginx deployment failed: {e}")
            return {"nginx_deployed": False, "error": str(e)}
        

async def deploy_with_nginx(
    config: DeploymentConfig,
    version: str,
    dry_run: bool = False,
    custom_logger = None
) -> Dict[str, Any]:
    """Deploy complete stack including nginx."""
    
    log = custom_logger or logger
    
    try:
        # 1. Deploy application containers first
        app_result = await deploy_containers_runtime_agnostic(
            config, version, "all", dry_run, log
        )
        
        if not app_result["success"]:
            return app_result
        
        # 2. Deploy nginx if enabled
        if config.nginx_enabled:
            log.info("Deploying nginx reverse proxy...")
            
            # Get API instance endpoints
            api_instances = [f"{server}:8000" for server in config.api_servers]
            
            # Deploy nginx
            nginx_result = await _deploy_nginx(config, api_instances, dry_run, log)
            
            return {
                **app_result,
                **nginx_result
            }
        
        return app_result
        
    except Exception as e:
        log.error(f"Deployment with nginx failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }