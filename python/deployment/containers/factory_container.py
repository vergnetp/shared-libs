
from ..config import DeploymentConfig
from .interface_container import ContainerImageBuilder, ContainerRuntime, ContainerRunner
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