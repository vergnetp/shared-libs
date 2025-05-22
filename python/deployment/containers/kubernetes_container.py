import asyncio
from typing import Dict, Any, List

from ..config import DeploymentConfig, ConfigurationResolver
from .interface_container import ContainerBuildSpec, ContainerImage, ContainerRuntimeSpec, ContainerRunner, ContainerImageBuilder

class KubernetesImageBuilder(ContainerImageBuilder):
    """Kubernetes-specific implementation using buildah or similar."""
    
    def __init__(self, config: DeploymentConfig):
        self.config = config
        self.resolver = ConfigurationResolver(config)
    
    async def build_image(self, build_spec: ContainerBuildSpec, logger) -> bool:
        """Build image using buildah for Kubernetes."""
        try:
            # Use buildah instead of docker
            build_cmd = self.get_build_command(build_spec)
            logger.info(f"Building image with buildah: {build_spec.image}")
            
            process = await asyncio.create_subprocess_exec(*build_cmd)
            await process.wait()
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"Exception during buildah build: {e}")
            return False
    
    def get_build_command(self, build_spec: ContainerBuildSpec) -> List[str]:
        """Generate buildah build command."""
        cmd = ["buildah", "build"]
        cmd.extend(["-f", build_spec.image.container_file])
        cmd.extend(["-t", build_spec.image.full_name])
        
        for arg_name, arg_value in build_spec.build_args.items():
            cmd.extend(["--build-arg", f"{arg_name}={arg_value}"])
        
        cmd.append(build_spec.image.build_context)
        return cmd
    
    async def push_image(self, image: ContainerImage, logger) -> bool:
        """Push image using buildah."""
        push_cmd = ["buildah", "push", image.full_name]
        process = await asyncio.create_subprocess_exec(*push_cmd)
        await process.wait()
        return process.returncode == 0

class KubernetesRunner(ContainerRunner):
    """Kubernetes-specific implementation using kubectl."""
    
    async def run_container(self, runtime_spec: ContainerRuntimeSpec, logger) -> str:
        """Deploy container to Kubernetes."""
        # Generate Kubernetes deployment YAML
        deployment_yaml = self._generate_deployment_yaml(runtime_spec)
        
        # Apply to cluster
        cmd = ["kubectl", "apply", "-f", "-"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate(input=deployment_yaml.encode())
        
        if process.returncode == 0:
            return f"deployment-{runtime_spec.image.name}"  # Deployment name
        else:
            raise Exception(f"Failed to deploy to Kubernetes: {stderr.decode()}")
    
    def _generate_deployment_yaml(self, runtime_spec: ContainerRuntimeSpec) -> str:
        """Generate Kubernetes deployment YAML."""
        # This would generate proper Kubernetes YAML
        return f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deployment-{runtime_spec.image.name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {runtime_spec.image.name}
  template:
    metadata:
      labels:
        app: {runtime_spec.image.name}
    spec:
      containers:
      - name: {runtime_spec.image.name}
        image: {runtime_spec.image.full_name}
        ports:
        {self._generate_port_yaml(runtime_spec.ports)}
        env:
        {self._generate_env_yaml(runtime_spec.environment)}
"""
    
    def _generate_port_yaml(self, ports: List[int]) -> str:
        """Generate ports YAML section."""
        if not ports:
            return ""
        port_lines = [f"        - containerPort: {port}" for port in ports]
        return "\n".join(port_lines)
    
    def _generate_env_yaml(self, environment: Dict[str, str]) -> str:
        """Generate environment YAML section."""
        if not environment:
            return ""
        env_lines = [f"        - name: {k}\n          value: '{v}'" for k, v in environment.items()]
        return "\n".join(env_lines)
    
    async def stop_container(self, deployment_name: str, logger) -> bool:
        """Delete Kubernetes deployment."""
        cmd = ["kubectl", "delete", "deployment", deployment_name]
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.wait()
        return process.returncode == 0
    
    async def get_container_status(self, deployment_name: str) -> Dict[str, Any]:
        """Get Kubernetes deployment status."""
        cmd = ["kubectl", "get", "deployment", deployment_name, "-o", "json"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            import json
            deployment_data = json.loads(stdout.decode())
            return {
                "name": deployment_data["metadata"]["name"],
                "status": deployment_data["status"].get("phase", "unknown"),
                "replicas": deployment_data["status"].get("replicas", 0),
                "ready_replicas": deployment_data["status"].get("readyReplicas", 0)
            }
        else:
            return {"status": "unknown"}