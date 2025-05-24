from abc import ABC, abstractmethod
from typing import List, Dict, Any

from ..types import ContainerRuntimeSpec, ContainerBuildSpec, ContainerImage

class ContainerImageBuilder(ABC):
    """Abstract interface for building container images."""
    
    @abstractmethod
    async def build_image(self, build_spec: ContainerBuildSpec, logger) -> bool:
        """Build a container image from specification."""
        pass
    
    @abstractmethod
    def get_build_command(self, build_spec: ContainerBuildSpec) -> List[str]:
        """Get the command that would be executed to build the image."""
        pass
    
    @abstractmethod
    async def push_image(self, image: ContainerImage, logger) -> bool:
        """Push image to registry."""
        pass

class ContainerRunner(ABC):
    """Abstract interface for running containers."""
    
    @abstractmethod
    async def run_container(self, runtime_spec: ContainerRuntimeSpec, logger) -> str:
        """Run a container and return container ID."""
        pass
    
    @abstractmethod
    async def stop_container(self, container_id: str, logger) -> bool:
        """Stop a running container."""
        pass
    
    @abstractmethod
    async def get_container_status(self, container_id: str) -> Dict[str, Any]:
        """Get status of a container."""
        pass