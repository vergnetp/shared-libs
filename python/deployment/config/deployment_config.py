import os
from typing import List, Optional, Dict, Any

from ...config.base_config import BaseConfig
from ..containers import ContainerRuntime, ContainerImage

class DeploymentConfig(BaseConfig):
    """
    Runtime-agnostic deployment configuration.   
    """
    
    def __init__(
        self,
        api_servers: List[str] = None,
        worker_servers: List[str] = None,
        container_registry: Optional[str] = None, 
        deployment_strategy: str = "rolling",
        
        # Container configuration (runtime-agnostic)
        container_files: Optional[Dict[str, str]] = None,  
        build_context: str = ".",
        build_args: Optional[Dict[str, str]] = None,
        image_templates: Optional[Dict[str, str]] = None,  
        
        # Configuration injection (same as before)
        config_injection: Optional[Dict[str, Any]] = None,
        config_mapping: Optional[Dict[str, str]] = None,
        sensitive_configs: Optional[List[str]] = None,
        
        # Runtime selection
        container_runtime: ContainerRuntime = ContainerRuntime.DOCKER,
        
        **kwargs
    ):
        self._api_servers = api_servers or ["localhost"]
        self._worker_servers = worker_servers or ["localhost"]
        self._container_registry = container_registry
        self._deployment_strategy = deployment_strategy
        
        # Default container files (could be Dockerfile, Containerfile, etc.)
        self._container_files = container_files or {
            "api": "containers/Containerfile.api",      # Generic naming
            "worker": "containers/Containerfile.worker"
        }
        self._build_context = build_context
        self._build_args = build_args or {}
        self._image_templates = image_templates or {}
        
        self._config_injection = config_injection or {}
        self._config_mapping = config_mapping or {}
        self._sensitive_configs = set(sensitive_configs or [])
        
        self._container_runtime = container_runtime
        
        super().__init__()
        self._validate_config()
    
    # Runtime-agnostic property names
    @property
    def container_files(self) -> Dict[str, str]:
        """Get container file paths (Dockerfile, Containerfile, etc.)."""
        return self._container_files
    
    @property
    def container_registry(self) -> Optional[str]:
        """Get container registry URL."""
        return self._container_registry
    
    @property
    def container_runtime(self) -> ContainerRuntime:
        """Get selected container runtime."""
        return self._container_runtime
    
    def get_container_file_path(self, service_type: str) -> str:
        """Get container file path for a service (Dockerfile, Containerfile, etc.)."""
        if service_type not in self._container_files:
            raise ValueError(f"No container file configured for service type: {service_type}")
        return self._container_files[service_type]
    
    def get_image_template(self, service_type: str) -> Optional[str]:
        """Get image naming template for a service."""
        return self._image_templates.get(service_type)
    
    def create_container_image(self, service_type: str, version: str) -> ContainerImage:
        """Create a ContainerImage specification for a service."""
        template = self.get_image_template(service_type)
        
        if template:
            name_with_tag = template.format(
                registry=self._container_registry or "",
                service=service_type,
                version=version
            ).strip("/")
            
            # Split registry/name:tag
            if ":" in name_with_tag:
                name_part, tag = name_with_tag.rsplit(":", 1)
            else:
                name_part, tag = name_with_tag, version
                
            if "/" in name_part and self._container_registry:
                registry, name = name_part.split("/", 1)
            else:
                registry, name = self._container_registry, name_part
        else:
            # Default naming
            registry = self._container_registry
            name = service_type
            tag = version
        
        return ContainerImage(
            name=name,
            tag=tag,
            registry=registry,
            build_context=self._build_context,
            container_file=self.get_container_file_path(service_type)
        )
    
    def _validate_config(self):
            """Validate deployment configuration."""
            errors = []
            
            # Validate server lists
            if not self._api_servers:
                errors.append("api_servers cannot be empty")
            
            if not self._worker_servers:
                errors.append("worker_servers cannot be empty")
            
            # Validate server entries
            for i, server in enumerate(self._api_servers):
                if not server or not isinstance(server, str):
                    errors.append(f"api_servers[{i}] must be a non-empty string")
            
            for i, server in enumerate(self._worker_servers):
                if not server or not isinstance(server, str):
                    errors.append(f"worker_servers[{i}] must be a non-empty string")        
            
            # Validate deployment strategy
            valid_strategies = {'rolling', 'blue_green', 'canary'}
            if self._deployment_strategy not in valid_strategies:
                errors.append(f"deployment_strategy must be one of {valid_strategies}, got '{self._deployment_strategy}'")
            
            # Validate container files exist
            for service_type, container_file in self._container_files.items():
                if not isinstance(container_file, str) or not container_file:
                    errors.append(f"container_file for {service_type} must be a non-empty string")
            
            # Validate build args are strings
            for key, value in self._build_args.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    errors.append(f"build_args must be string key-value pairs, got {key}={value}")
            
            if errors:
                raise ValueError(f"Deployment configuration validation failed: {'; '.join(errors)}")
    
   