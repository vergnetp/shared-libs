import asyncio
from typing import Dict, Any, List

from ..config import DeploymentConfig, ConfigurationResolver
from .interface_container import ContainerBuildSpec, ContainerImage, ContainerRuntimeSpec, ContainerRunner, ContainerImageBuilder


class DockerImageBuilder(ContainerImageBuilder):
    """Docker-specific implementation of container image building."""
    
    def __init__(self, config: DeploymentConfig):
        self.config = config
        self.resolver = ConfigurationResolver(config)
    
    async def build_image(self, build_spec: ContainerBuildSpec, logger) -> bool:
        """Build image using Docker."""
        try:
            build_cmd = self.get_build_command(build_spec)
            logger.info(f"Building image: {build_spec.image}")
            
            process = await asyncio.create_subprocess_exec(
                *build_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"✓ Successfully built {build_spec.image}")
                return True
            else:
                logger.error(f"✗ Failed to build {build_spec.image}")
                logger.error(f"Error: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Exception during Docker build: {e}")
            return False
    
    def get_build_command(self, build_spec: ContainerBuildSpec) -> List[str]:
        """Generate Docker build command."""
        cmd = ["docker", "build"]
        cmd.extend(["-f", build_spec.image.container_file])
        cmd.extend(["-t", build_spec.image.full_name])
        
        # Add build arguments
        for arg_name, arg_value in build_spec.build_args.items():
            cmd.extend(["--build-arg", f"{arg_name}={arg_value}"])
        
        # Add labels
        for label_name, label_value in build_spec.labels.items():
            cmd.extend(["--label", f"{label_name}={label_value}"])
        
        # Add platform if specified
        if build_spec.target_platform:
            cmd.extend(["--platform", build_spec.target_platform])
        
        cmd.append(build_spec.image.build_context)
        return cmd
    
    async def push_image(self, image: ContainerImage, logger) -> bool:
        """Push image using Docker."""
        try:
            push_cmd = ["docker", "push", image.full_name]
            logger.info(f"Pushing image: {image}")
            
            process = await asyncio.create_subprocess_exec(
                *push_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"Exception during Docker push: {e}")
            return False

class DockerRunner(ContainerRunner):
    """Docker-specific implementation of container running."""
    
    async def run_container(self, runtime_spec: ContainerRuntimeSpec, logger) -> str:
        """Run container using Docker."""
        cmd = ["docker", "run", "-d"]
        
        # Add restart policy
        cmd.extend(["--restart", runtime_spec.restart_policy])
        
        # Add ports
        for port in runtime_spec.ports:
            cmd.extend(["-p", f"{port}:{port}"])
        
        # Add environment variables
        for env_name, env_value in runtime_spec.environment.items():
            cmd.extend(["-e", f"{env_name}={env_value}"])
        
        # Add volumes
        for volume in runtime_spec.volumes:
            cmd.extend(["-v", volume])
        
        # Add health check
        if runtime_spec.health_check:
            cmd.extend(["--health-cmd", runtime_spec.health_check])
        
        # Add image
        cmd.append(runtime_spec.image.full_name)
        
        # Add command if specified
        if runtime_spec.command:
            cmd.extend(runtime_spec.command)
        
        # Execute
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return stdout.decode().strip()  # Container ID
        else:
            raise Exception(f"Failed to run container: {stderr.decode()}")
    
    async def stop_container(self, container_id: str, logger) -> bool:
        """Stop container using Docker."""
        cmd = ["docker", "stop", container_id]
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.wait()
        return process.returncode == 0
    
    async def get_container_status(self, container_id: str) -> Dict[str, Any]:
        """Get container status using Docker."""
        cmd = ["docker", "inspect", container_id]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            import json
            inspect_data = json.loads(stdout.decode())[0]
            return {
                "id": inspect_data["Id"],
                "status": inspect_data["State"]["Status"],
                "image": inspect_data["Config"]["Image"],
                "created": inspect_data["Created"]
            }
        else:
            return {"status": "unknown"}