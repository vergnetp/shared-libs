import time
from typing import Dict, Any

from .config import DeploymentConfig, ConfigurationResolver
from .containers import ContainerBuildSpec, ContainerRuntimeFactory


async def deploy_containers_runtime_agnostic(
    config: DeploymentConfig,
    version: str,
    service_type: str = "all",
    dry_run: bool = False,
    logger = None
) -> Dict[str, Any]:
    """
    Deploy containers using any supported runtime.
    The same function works for Docker, Kubernetes, Podman, etc.
    """
    logger.info(f"Deploying containers using {config.container_runtime.value} runtime")
    
    # Create runtime-appropriate implementations
    image_builder = ContainerRuntimeFactory.create_image_builder(config)
    container_runner = ContainerRuntimeFactory.create_container_runner(config)
    
    # Resolve configuration values
    resolver = ConfigurationResolver(config)
    resolved_args = resolver.resolve_all_config_values(mask_sensitive=False)
    
    # Build images for each service
    built_images = {}
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
                    "app.name": config._config_injection.get("app", {}).get("app_name", "unknown"),
                    "app.version": version,
                    "build.timestamp": str(int(time.time())),
                    "service.type": service
                }
            )
            
            if dry_run:
                logger.info(f"[DRY RUN] Would build: {container_image}")
                built_images[service] = str(container_image)
                continue
            
            # Build the image (works with any runtime)
            success = await image_builder.build_image(build_spec, logger)
            
            if success:
                built_images[service] = str(container_image)
                
                # Push to registry if configured
                if config.container_registry:
                    await image_builder.push_image(container_image, logger)
            
        except Exception as e:
            logger.error(f"Failed to build {service}: {e}")
    
    return {"images_built": built_images}
