from typing import List, Dict, Any, Optional
from enum import Enum

class ContainerRuntime(Enum):
    DOCKER = "docker"
    PODMAN = "podman" 
    KUBERNETES = "kubernetes"
    CONTAINERD = "containerd"
    CLOUD_RUN = "cloud_run"

class ContainerImage:
    """Runtime-agnostic container image representation."""
    
    def __init__(
        self,
        name: str,
        tag: str,
        registry: Optional[str] = None,
        build_context: str = ".",
        container_file: str = "Containerfile"
    ):
        self.name = name
        self.tag = tag
        self.registry = registry
        self.build_context = build_context
        self.container_file = container_file
    
    @property
    def full_name(self) -> str:
        """Get fully qualified image name."""
        if self.registry:
            return f"{self.registry}/{self.name}:{self.tag}"
        return f"{self.name}:{self.tag}"
    
    def __str__(self):
        return self.full_name

class ContainerBuildSpec:
    """Runtime-agnostic build specification."""
    
    def __init__(
        self,
        image: ContainerImage,
        build_args: Dict[str, str] = None,
        labels: Dict[str, str] = None,
        target_platform: Optional[str] = None
    ):
        self.image = image
        self.build_args = build_args or {}
        self.labels = labels or {}
        self.target_platform = target_platform

class ContainerRuntimeSpec:
    """Runtime-agnostic container runtime specification."""
    
    def __init__(
        self,
        image: ContainerImage,
        ports: List[int] = None,
        environment: Dict[str, str] = None,
        volumes: List[str] = None,
        command: List[str] = None,
        health_check: Optional[str] = None,
        restart_policy: str = "unless-stopped",
        resource_limits: Dict[str, Any] = None
    ):
        self.image = image
        self.ports = ports or []
        self.environment = environment or {}
        self.volumes = volumes or []
        self.command = command or []
        self.health_check = health_check
        self.restart_policy = restart_policy
        self.resource_limits = resource_limits or {}