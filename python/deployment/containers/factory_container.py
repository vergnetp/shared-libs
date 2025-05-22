from typing import List

from ..config import DeploymentConfig
from .interface_container import ContainerImageBuilder, ContainerRuntime, ContainerRunner, ContainerRuntimeSpec, ContainerImage
from .docker_container import DockerImageBuilder, DockerRunner
from .kubernetes_container import KubernetesImageBuilder, KubernetesRunner

class ContainerRuntimeFactory:
    """Factory to create appropriate runtime implementations."""
    
    @staticmethod
    def create_image_builder(config: DeploymentConfig) -> ContainerImageBuilder:
        """Create appropriate image builder based on runtime."""
        runtime = config.container_runtime
        
        if runtime == ContainerRuntime.DOCKER:
            return DockerImageBuilder(config)
        elif runtime == ContainerRuntime.KUBERNETES:
            return KubernetesImageBuilder(config)
        else:
            raise ValueError(f"Unsupported container runtime: {runtime}")
    
    @staticmethod
    def create_container_runner(config: DeploymentConfig) -> ContainerRunner:
        """Create appropriate container runner based on runtime."""
        runtime = config.container_runtime
        
        if runtime == ContainerRuntime.DOCKER:
            return DockerRunner()
        elif runtime == ContainerRuntime.KUBERNETES:
            return KubernetesRunner()
        else:
            raise ValueError(f"Unsupported container runtime: {runtime}")
    
    @staticmethod
    def create_nginx_spec(config: DeploymentConfig, api_instances: List[str]) -> ContainerRuntimeSpec:
        """Create nginx container specification."""
        nginx_config = config.generate_nginx_config(api_instances)
        
        # Write config to temporary file (or use volume mount)
        config_volume = f"{config.build_context}/nginx.conf:/etc/nginx/nginx.conf:ro"
        
        nginx_image = ContainerImage(
            name="nginx",
            tag="alpine",
            registry="docker.io"  # Use official nginx image
        )
        
        return ContainerRuntimeSpec(
            image=nginx_image,
            ports=[80, 443] if config._ssl_enabled else [80],
            volumes=[config_volume],
            health_check="curl -f http://localhost/health || exit 1",
            restart_policy="unless-stopped"
        )