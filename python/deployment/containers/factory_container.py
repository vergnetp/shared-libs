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
    def create_nginx_spec(config: DeploymentConfig, api_instances: List[str], nginx_config_path: str = None) -> ContainerRuntimeSpec:
        """Create nginx container specification."""
        
        # Use custom nginx image if configured, otherwise official
        if "nginx" in config.container_files:
            nginx_image = config.create_container_image("nginx", "latest")
        else:
            nginx_image = ContainerImage(
                name="nginx",
                tag="alpine",
                registry="docker.io"
            )
        
        # Set up volumes
        volumes = []
        if nginx_config_path:
            volumes.append(f"{nginx_config_path}:/etc/nginx/nginx.conf:ro")
        
        # Add SSL certificates if enabled
        if config._ssl_enabled and config._ssl_cert_path and config._ssl_key_path:
            volumes.extend([
                f"{config._ssl_cert_path}:/etc/nginx/ssl/cert.pem:ro",
                f"{config._ssl_key_path}:/etc/nginx/ssl/key.pem:ro"
            ])
        
        # Determine ports
        ports = [80]
        if config._ssl_enabled:
            ports.append(443)
        
        return ContainerRuntimeSpec(
            image=nginx_image,
            ports=ports,
            volumes=volumes,
            health_check="curl -f http://localhost/health || exit 1",
            restart_policy="unless-stopped",
            environment={
                "NGINX_HOST": ",".join(config._domain_names),
                "NGINX_PORT": "80"
            }
        )