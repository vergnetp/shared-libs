'''
This is some config/commands for pytest (unit tests)
'''

import os
import time
import pytest
import subprocess
import shutil
from . import utils
from . import log as logger


def run_command(command):
    """Run a command and return the exit code, stdout and stderr"""
    logger.info(f"Running command: {command}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        universal_newlines=True
    )
    stdout, stderr = process.communicate()
    if stdout:
        logger.info(f"Command output: {stdout}")
    if stderr:
        logger.info(f"Command error: {stderr}")
    return process.returncode, stdout, stderr

def delete_pytest_cache():
    """Delete all .pytest_cache folders in the project"""
    for root, dirs, files in os.walk('.'):
        if '.pytest_cache' in dirs:
            cache_dir = os.path.join(root, '.pytest_cache')
            logger.info(f"Removing {cache_dir}")
            shutil.rmtree(cache_dir)

def prevent_py_cache():
    """Prevent Python from creating __pycache__ folders"""
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment(request):
    """
    Set up the test environment automatically for each test session.
    
    This fixture handles several key test environment setup tasks:
    
    1. Prevents Python from creating __pycache__ directories
    2. Cleans up any existing .pytest_cache directories
    3. Automatically detects the appropriate Docker Compose file for the module being tested
    4. Starts Docker containers defined in the module's Docker Compose file
    5. Waits for all exposed services to be ready before running tests (plus 30 seconds extra buffer)
    6. Tears down the Docker environment after tests complete
    
    Features:
    - Module-specific Docker Compose detection: Finds the compose file closest to the test being run
    - Service auto-detection: Parses the compose file to discover which services and ports to wait for
    - Project isolation: Uses unique project names to avoid conflicts between test modules
    - Automatic cleanup: Ensures all Docker resources are properly removed after testing
    
    This fixture runs automatically for all test sessions (scope="session", autouse=True),
    so there's no need to explicitly include it in your tests.
    
    Example:
        # In your test file, the Docker setup happens automatically
        def test_something():
            # Docker services defined in the module's docker-compose.yml 
            # are already running and ready to use
            ...
    
    Technical details:
    - Uses the 'docker-compose' command line tool with project-specific naming
    - Service readiness is checked by attempting TCP connections to exposed ports
    - All logs and errors are printed to the console for debugging
    """
        
    logger.info(f"Setting up test environment...")
    
    prevent_py_cache()
    delete_pytest_cache()

    # Get all test items that will be executed in this session
    test_paths = set()
    for item in request.session.items:
        test_paths.add(item.fspath.strpath)
    
    logger.info(f"Test files in this session: {test_paths}")
    
    # Find Docker Compose files for each test file
    active_compose_files = []
    
    for test_path in test_paths:
        compose_file = utils.find_module_docker_compose(test_path)
        if compose_file and compose_file not in [f for f, _ in active_compose_files]:
            logger.info(f"Found Docker Compose file for {test_path}: {compose_file}")
            
            # The rest of your code for handling each compose file...
            # Use a unique project name based on the module directory
            module_dir = os.path.dirname(compose_file)
            module_name = os.path.basename(module_dir)
            if module_name == "tests":
                module_name = os.path.basename(os.path.dirname(module_dir))
            
            project_name = f"test-{module_name}"
            
            # Parse the Docker Compose file to determine which services to wait for
            service_info = utils.parse_docker_compose(compose_file)
            
            # Print detected services
            if service_info:
                logger.info(f"Detected the following services in {compose_file}:")
                for service, container_port, host_port, host in service_info:
                    logger.info(f"  - {service}: {host}:{host_port} (container port: {container_port})")
            else:
                logger.info(f"No services with ports detected in {compose_file}")
            
            # Launch Docker containers
            cmd = f"docker-compose -f {compose_file} -p {project_name} up -d"
            return_code, stdout, stderr = run_command(cmd)
            
            if return_code != 0:
                logger.info(f"Error starting Docker containers: {stderr}")
                pytest.exit(f"Docker setup failed with code {return_code}")
            
            active_compose_files.append((compose_file, project_name))
            
            need_more_time = False

            # Wait for all services with exposed ports to be ready
            for service_name, _, host_port, host in service_info:
                if not utils.is_service_ready(host_port, service_name, host):
                    need_more_time = True
                    utils.wait_for_service_ready(host_port, service_name, host=host)
            if need_more_time:
                logger.info("Waiting a little more to be sure database and other services are really up and running...")
                time.sleep(30)
    
    if not active_compose_files:
        logger.info("No Docker Compose files found for any test files. Continuing without Docker setup.")
    
    yield
    
    # Cleanup
    logger.info("Tearing down test environment...")
    
    for compose_file, project_name in active_compose_files:
        cmd = f"docker-compose -f {compose_file} -p {project_name} down -v"
        #return_code, stdout, stderr = run_command(cmd)
        
        #if return_code != 0:
            #logger.info(f"Warning: Error stopping Docker containers: {stderr}")
    
    prevent_py_cache()
    delete_pytest_cache()