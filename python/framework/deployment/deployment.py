# shared_libs/framework/deployment.py
import os
import stat
from pathlib import Path
import jinja2
from typing import Dict, Any, Optional

def generate_deployment_scripts(config, output_dir: str):
    """
    Generate deployment scripts for the application.
    
    Args:
        config: The application configuration
        output_dir: Directory to write the scripts
    """
    # Get templates directory
    templates_dir = Path(__file__).parent / "templates"
    
    # Set up Jinja environment
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        trim_blocks=True,
        lstrip_blocks=True
    )
    
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Generate deploy.sh
    deploy_template = env.get_template("deploy.sh.j2")
    deploy_content = deploy_template.render(
        config=config,
        app_name=config.app_name,
        env=config.environment,
        api_servers=config.deployment.api_servers,
        worker_servers=config.deployment.worker_servers,
        db_password_var=config.database.password_env_var,
        redis_password_var=config.redis.password_env_var if config.redis else None,
        docker_registry=config.deployment.docker_registry
    )
    
    deploy_path = os.path.join(output_dir, "deploy.sh")
    with open(deploy_path, "w") as f:
        f.write(deploy_content)
    
    # Make executable
    os.chmod(deploy_path, os.stat(deploy_path).st_mode | stat.S_IEXEC)
    
    # Generate rollback.sh
    rollback_template = env.get_template("rollback.sh.j2")
    rollback_content = rollback_template.render(
        config=config,
        app_name=config.app_name,
        env=config.environment,
        api_servers=config.deployment.api_servers,
        worker_servers=config.deployment.worker_servers
    )
    
    rollback_path = os.path.join(output_dir, "rollback.sh")
    with open(rollback_path, "w") as f:
        f.write(rollback_content)
    
    # Make executable
    os.chmod(rollback_path, os.stat(rollback_path).st_mode | stat.S_IEXEC)