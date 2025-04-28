# shared_libs/framework/docker.py
import os
import yaml
from pathlib import Path
import jinja2
from typing import Dict, Any, Optional

def generate_docker_compose(config, output_path: Optional[str] = None) -> str:
    """
    Generate a docker-compose.yml file based on the application config.
    
    Args:
        config: The application configuration object
        output_path: Path to write the file (if None, returns the content as string)
        
    Returns:
        str: The generated docker-compose.yml content
    """
    # Get the templates directory
    templates_dir = Path(__file__).parent / "templates"
    
    # Set up Jinja environment
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        trim_blocks=True,
        lstrip_blocks=True
    )
    
    # Load the docker-compose template
    template = env.get_template("docker-compose.yml.j2")
    
    # Render the template with the config
    compose_content = template.render(
        config=config,
        app_name=config.app_name,
        env=config.environment,
        db_type=config.database.type,
        use_redis=config.redis and config.redis.enabled,
        use_opensearch=config.opensearch and config.opensearch.enabled
    )
    
    # Write to file if output_path is provided
    if output_path:
        with open(output_path, 'w') as f:
            f.write(compose_content)
    
    return compose_content