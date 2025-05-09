import yaml
import os
from pathlib import Path

def parse_docker_compose(compose_file):
    """
    Parse a Docker Compose file and extract service name, ports, and host mappings.
    
    Returns:
        List of tuples: [(service_name, container_port, host_port, host)]
    """
    try:
        with open(compose_file, 'r') as f:
            compose_data = yaml.safe_load(f)
        
        service_info = []
        if not compose_data or 'services' not in compose_data:
            print(f"Warning: No services defined in {compose_file}")
            return service_info
        
        for service_name, service_config in compose_data['services'].items():
            # Skip services without port mappings
            if 'ports' not in service_config:
                continue
            
            for port_mapping in service_config['ports']:
                # Port mapping can be a string like "8080:80" or a dict with "published" and "target"
                if isinstance(port_mapping, str):
                    # Handle different formats: "8080:80", "127.0.0.1:8080:80", "8080"
                    parts = port_mapping.split(':')
                    if len(parts) == 3:  # "127.0.0.1:8080:80"
                        host, host_port, container_port = parts
                    elif len(parts) == 2:  # "8080:80"
                        host_port, container_port = parts
                        host = 'localhost'
                    else:  # "8080"
                        host_port = container_port = parts[0]
                        host = 'localhost'
                elif isinstance(port_mapping, dict):
                    # Docker Compose v3 format
                    host_port = port_mapping.get('published', '')
                    container_port = port_mapping.get('target', '')
                    host = port_mapping.get('host', 'localhost')
                else:
                    # Skip invalid port mappings
                    continue
                
                # Convert ports to integers if possible
                try:
                    host_port = int(host_port)
                    container_port = int(container_port)
                    service_info.append((service_name, container_port, host_port, host))
                except (ValueError, TypeError):
                    # Skip invalid port values
                    continue
        
        return service_info
    
    except Exception as e:
        print(f"Error parsing Docker Compose file {compose_file}: {e}")
        return []
    
def find_module_docker_compose(root_path: str=None):
    """
    Find the Docker Compose file for the module being tested
    
    This function tries to determine which module's test is being run
    and then looks for a docker-compose.yml file in that module's tests directory.
    """
    if root_path is None:
        root_path = os.curdir

    # Convert to Path object for easier path manipulation
    wrapped_path = Path(root_path)
    
    # Find the module directory (parent of the test file)
    module_dir = wrapped_path.parent
    
    # Look for docker-compose in the same directory as the test
    compose_file = module_dir / "docker-compose.yml"
    if compose_file.exists():
        return str(compose_file)
    
    # If not found, look for it in a "tests" subdirectory of the module
    if "tests" in str(module_dir):
        # We're already in a tests directory
        module_tests_dir = module_dir
    else:
        # Look for a tests directory
        module_tests_dir = module_dir / "tests"
    
    compose_file = module_tests_dir / "docker-compose.yml"
    if compose_file.exists():
        return str(compose_file)
    
    # If still not found, check for yaml extension
    compose_file = module_tests_dir / "docker-compose.yaml"
    if compose_file.exists():
        return str(compose_file)
    
    # If we're in a nested module structure, walk up the directories
    # looking for docker-compose.yml in tests directories
    current_dir = module_dir
    max_levels = 3  # Prevent infinite loop
    
    for _ in range(max_levels):
        # Go up one level
        current_dir = current_dir.parent
        if not current_dir or current_dir == Path('.'):
            break
            
        # Check for docker-compose.yml in this directory
        compose_file = current_dir / "docker-compose.yml"
        if compose_file.exists():
            return str(compose_file)
        
        # Check in tests subdirectory
        tests_dir = current_dir / "tests"
        compose_file = tests_dir / "docker-compose.yml"
        if compose_file.exists():
            return str(compose_file)
    
    # If no specific docker-compose file found, return the default one
    default_compose = Path("docker-compose.yml")
    if default_compose.exists():
        return str(default_compose)
    
    return None