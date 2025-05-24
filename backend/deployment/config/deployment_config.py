import os
from typing import List, Optional, Dict, Any

from ...config.base_config import BaseConfig
from ..types import ContainerRuntime, ContainerImage

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
        sensitive_configs: Optional[List[str]] = None,
        
        # Runtime selection
        container_runtime: ContainerRuntime = ContainerRuntime.DOCKER,
        
        nginx_enabled: bool = True,
        nginx_template: Optional[str] = None,
        ssl_enabled: bool = False,
        ssl_cert_path: Optional[str] = None,
        ssl_key_path: Optional[str] = None,
        domain_names: List[str] = None,
        **kwargs
    ):
        """
        Initialize deployment configuration for container-based applications.
        
        This configuration supports multiple container runtimes (Docker, Kubernetes, etc.)
        and provides a unified interface for deploying applications with optional nginx
        load balancing and SSL termination.
        
        Args:
            api_servers (List[str], optional): List of servers where API containers will be deployed.
                Defaults to ["localhost"]. Each server should be a hostname or IP address.
                Example: ["web1.company.com", "web2.company.com"]
                
            worker_servers (List[str], optional): List of servers where worker containers will be deployed.
                Defaults to ["localhost"]. Workers typically handle background tasks.
                Example: ["worker1.company.com", "worker2.company.com"]
                
            container_registry (str, optional): Container registry URL for pushing/pulling images.
                If None, images are only built locally. Supports Docker Hub, AWS ECR, etc.
                Example: "registry.company.com" or "123456789012.dkr.ecr.us-east-1.amazonaws.com"
                
            deployment_strategy (str, optional): Strategy for rolling out updates.
                Defaults to "rolling". Options: "rolling", "blue_green", "canary".
                
            container_files (Dict[str, str], optional): Mapping of service types to their container files.
                Defaults to {"api": "containers/Containerfile.api", "worker": "containers/Containerfile.worker"}.
                Supports Dockerfile, Containerfile, or any OCI-compatible build file.
                Example: {"api": "docker/api.dockerfile", "worker": "docker/worker.dockerfile"}
                
            build_context (str, optional): Directory used as build context for container builds.
                Defaults to ".". All container files should be accessible from this directory.
                
            build_args (Dict[str, str], optional): Static build arguments passed to all container builds.
                These are literal values, not configuration references.
                Example: {"NODE_ENV": "production", "VERSION": "1.2.3"}
                
            image_templates (Dict[str, str], optional): Templates for generating image names.
                Supports format strings with {registry}, {service}, {version} placeholders.
                Example: {"api": "{registry}/myapp-{service}:{version}"}
                
            config_injection (Dict[str, Any], optional): Configuration objects to inject into builds.                
                Example: {"db": database_config, "app": app_config}  
                
            sensitive_configs (List[str], optional): List of configuration paths containing sensitive data.
                These values will be masked in logs and dry-run output for security.
                Example: ["db.password", "app.api_key"]
                
            container_runtime (ContainerRuntime, optional): Container runtime to use for deployment.
                Defaults to ContainerRuntime.DOCKER. Options: DOCKER, KUBERNETES, PODMAN, etc.
                
            nginx_enabled (bool, optional): Whether to deploy nginx as a reverse proxy/load balancer.
                Defaults to True. When enabled, nginx will be configured to balance across API servers.
                
            nginx_template (str, optional): Path to custom nginx configuration template.
                If provided, this template will be used instead of the auto-generated configuration.
                Template should support format strings for upstream servers and SSL settings.
                
            ssl_enabled (bool, optional): Whether to enable SSL/TLS termination in nginx.
                Defaults to False. Requires ssl_cert_path and ssl_key_path when enabled.
                
            ssl_cert_path (str, optional): Path to SSL certificate file for HTTPS.
                Required when ssl_enabled=True. Should be accessible to nginx container.
                
            ssl_key_path (str, optional): Path to SSL private key file for HTTPS.
                Required when ssl_enabled=True. Should be accessible to nginx container.
                
            domain_names (List[str], optional): Domain names that nginx should respond to.
                Defaults to ["localhost"]. Used in nginx server_name directive.
                Example: ["api.company.com", "www.company.com"]
                
        Raises:
            ValueError: If configuration validation fails. Common issues include:
                - Empty server lists
                - Invalid deployment strategy
                - Missing SSL files when SSL is enabled
                - Invalid configuration mappings
                
        Example:
            >>> # Basic configuration
            >>> config = DeploymentConfig(
            ...     api_servers=["web1", "web2"],
            ...     worker_servers=["worker1"]
            ... )
            
            >>> # Production configuration with SSL
            >>> config = DeploymentConfig(
            ...     api_servers=["api1.company.com", "api2.company.com"],
            ...     worker_servers=["worker1.company.com"],
            ...     container_registry="registry.company.com",
            ...     ssl_enabled=True,
            ...     ssl_cert_path="/etc/ssl/certs/company.crt",
            ...     ssl_key_path="/etc/ssl/private/company.key",
            ...     domain_names=["api.company.com"]
            ... )
            
            >>> # Configuration with database injection
            >>> db_config = DatabaseConfig(host="db.company.com", database="myapp")
            >>> config = DeploymentConfig(
            ...     api_servers=["web1", "web2"],
            ...     config_injection={"db": db_config},
            ...     sensitive_configs=["db.password"]
            ... )
        """
        self._api_servers = api_servers or ["localhost"]
        self._worker_servers = worker_servers or ["localhost"]
        self._container_registry = container_registry
        self._deployment_strategy = deployment_strategy
        
        # Default container files (could be Dockerfile, Containerfile, etc.)
        self._container_files = container_files or {
            "api": "containers/Containerfile.api",      # Generic naming
            "worker": "containers/Containerfile.worker",
            "nginx":"containers/Containerfile.nginx"
        }
        self._build_context = build_context
        self._build_args = build_args or {}
        self._image_templates = image_templates or {}
        
        self._config_injection = config_injection or {}        
        self._sensitive_configs = set(sensitive_configs or [])
        
        self._container_runtime = container_runtime
        
        self._nginx_enabled = nginx_enabled
        self._nginx_template = nginx_template or "containers/nginx.conf.template"
        self._ssl_enabled = ssl_enabled
        self._ssl_cert_path = ssl_cert_path
        self._ssl_key_path = ssl_key_path
        self._domain_names = domain_names or ["localhost"]

        if nginx_enabled and not self._container_files.get("nginx", None):
            self._container_files["nginx"] = "containers/Containerfile.nginx"

        super().__init__()
        self._validate_config()    

    @property
    def container_files(self) -> Dict[str, str]:
        """Get container file paths (Dockerfile, Containerfile, etc.)."""
        return self._container_files

    @property
    def sensitive_configs(self) -> set:
        """Get sensitive configuration keys."""
        return self._sensitive_configs
        
    @property
    def container_registry(self) -> Optional[str]:
        """Get container registry URL."""
        return self._container_registry
    
    @property
    def container_runtime(self) -> ContainerRuntime:
        """Get selected container runtime."""
        return self._container_runtime

    @property
    def api_servers(self) -> List[str]:
        """Get API server list."""
        return self._api_servers
    
    @property
    def worker_servers(self) -> List[str]:
        """Get worker server list."""
        return self._worker_servers
    
    @property
    def deployment_strategy(self) -> str:
        """Get deployment strategy."""
        return self._deployment_strategy
    
    @property
    def build_context(self) -> str:
        """Get build context directory."""
        return self._build_context
    
    @property
    def build_args(self) -> Dict[str, str]:
        """Get build arguments."""
        return self._build_args
    
    @property
    def config_injection(self) -> Dict[str, Any]:
        """Get configuration injection mapping."""
        return self._config_injection
  
    # Add methods referenced in readme examples
    @property
    def total_server_count(self) -> int:
        """Get total number of servers."""
        return len(self._api_servers) + len(self._worker_servers)
    
    @property
    def all_servers(self) -> List[str]:
        """Get all servers combined."""
        return self._api_servers + self._worker_servers

    @property
    def ssl_enabled(self) -> bool:
        """Get SSL enabled status."""
        return self._ssl_enabled
    
    @property
    def ssl_cert_path(self) -> Optional[str]:
        """Get SSL certificate path."""
        return self._ssl_cert_path
    
    @property
    def ssl_key_path(self) -> Optional[str]:
        """Get SSL key path."""
        return self._ssl_key_path
    
    @property
    def domain_names(self) -> List[str]:
        """Get domain names."""
        return self._domain_names
    
    @property
    def nginx_enabled(self) -> bool:
        """Get nginx enabled status."""
        return self._nginx_enabled
       
    def get_servers_by_type(self, server_type: str) -> List[str]:
        """Get servers by type (api or worker)."""
        if server_type == "api":
            return self._api_servers
        elif server_type == "worker":
            return self._worker_servers
        else:
            raise ValueError(f"Unknown server type: {server_type}")

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
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'api_servers': self._api_servers,
            'worker_servers': self._worker_servers,
            'container_registry': self._container_registry,
            'deployment_strategy': self._deployment_strategy,
            'container_files': self._container_files,
            'build_context': self._build_context,
            'build_args': self._build_args,
            'image_templates': self._image_templates,
            'config_injection': self._config_injection,
            'config_mapping': self._config_mapping,
            'sensitive_configs': list(self._sensitive_configs),
            'container_runtime': self._container_runtime.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeploymentConfig':
        """Create instance from dictionary."""
        # Convert container_runtime back to enum
        runtime = data.get('container_runtime', 'docker')
        if isinstance(runtime, str):
            runtime = ContainerRuntime(runtime)
        
        return cls(
            api_servers=data.get('api_servers'),
            worker_servers=data.get('worker_servers'),
            container_registry=data.get('container_registry'),
            deployment_strategy=data.get('deployment_strategy', 'rolling'),
            container_files=data.get('container_files'),
            build_context=data.get('build_context', '.'),
            build_args=data.get('build_args'),
            image_templates=data.get('image_templates'),
            config_injection=data.get('config_injection'),
            config_mapping=data.get('config_mapping'),
            sensitive_configs=data.get('sensitive_configs'),
            container_runtime=runtime
        )
    
    @classmethod
    def from_environment(cls) -> 'DeploymentConfig':
        """Create configuration from environment variables."""
        api_servers_str = os.getenv('DEPLOY_API_SERVERS', 'localhost')
        worker_servers_str = os.getenv('DEPLOY_WORKER_SERVERS', 'localhost')
        
        return cls(
            api_servers=api_servers_str.split(','),
            worker_servers=worker_servers_str.split(','),
            container_registry=os.getenv('DEPLOY_DOCKER_REGISTRY'),
            deployment_strategy=os.getenv('DEPLOY_STRATEGY', 'rolling'),
            container_runtime=ContainerRuntime(os.getenv('DEPLOY_RUNTIME', 'docker'))
        )
    
    def generate_nginx_config(self, api_instances: List[str]) -> str:
        """Generate nginx configuration for load balancing."""
        if self._nginx_template and os.path.exists(self._nginx_template):
            with open(self._nginx_template, 'r') as f:
                template = f.read()
            
            # Replace template variables
            return template.format(
                upstream_servers="\n    ".join([f"server {instance};" for instance in api_instances]),
                domain_names=' '.join(self._domain_names),
                ssl_cert_path=self._ssl_cert_path,
                ssl_key_path=self._ssl_key_path
            )
        

        upstream_servers = "\n    ".join([
            f"server {instance};" for instance in api_instances
        ])
        
        ssl_config = ""
        if self._ssl_enabled:
            ssl_config = f"""
    listen 443 ssl;
    ssl_certificate {self._ssl_cert_path};
    ssl_certificate_key {self._ssl_key_path};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;"""
        
        # Add HTTP to HTTPS redirect if SSL is enabled
        redirect_config = ""
        if self._ssl_enabled:
            redirect_config = """
server {
    listen 80;
    server_name """ + ' '.join(self._domain_names) + """;
    return 301 https://$server_name$request_uri;
}
"""
        
        return f"""{redirect_config}
upstream api_backend {{
    {upstream_servers}
}}

server {{
    {"listen 80;" if not self._ssl_enabled else ""}
    {ssl_config}
    server_name {' '.join(self._domain_names)};
    
    location / {{
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }}
    
    location /health {{
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }}
}}
"""
   