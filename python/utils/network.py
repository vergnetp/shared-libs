"""
Network utility functions for service readiness checking and connectivity.
"""
import socket
import time
import logging

logger = logging.getLogger(__name__)

def wait_for_service_ready(port, service_name="service", host='localhost', timeout=30, check_interval=1):
    """
    Wait for a service to be ready by checking if it accepts connections on the specified port.
    
    This function is useful for:
    - Waiting for services to start during testing
    - Checking dependencies before proceeding with operations
    - Implementing retry logic for network operations
    - Health checking in deployment scripts
    
    Args:
        port (int): The port number the service listens on
        service_name (str): Name of the service (for logging purposes)
        host (str): Host where the service is running
        timeout (int): Maximum time to wait in seconds
        check_interval (float): Time between connection attempts in seconds
        
    Returns:
        bool: True if service is ready, False if timeout occurred
    """
    logger.info(f"Waiting for {service_name} to be ready on {host}:{port}...")
    start_time = time.time()
    attempt = 0
    
    while time.time() - start_time < timeout:
        attempt += 1
        try:
            with socket.create_connection((host, port), timeout=min(check_interval, 3)):
                elapsed = time.time() - start_time
                logger.info(f"{service_name} is ready on {host}:{port} after {elapsed:.2f}s and {attempt} attempts")
                return True
        except (socket.timeout, ConnectionRefusedError) as e:
            elapsed = time.time() - start_time
            if int(elapsed) % 5 == 0 or attempt == 1:  # Log every 5 seconds and on first attempt
                logger.info(f"Still waiting for {service_name} ({elapsed:.1f}s, attempt {attempt}): {e}")
            time.sleep(check_interval)
    
    logger.warning(f"Timeout waiting for {service_name} on {host}:{port} after {timeout}s and {attempt} attempts")
    return False

def wait_for_http_service(url, service_name="HTTP service", timeout=30, check_interval=1):
    """
    Wait for an HTTP service to be ready by checking for a successful response.
    
    Args:
        url (str): The URL to check
        service_name (str): Name of the service (for logging purposes)
        timeout (int): Maximum time to wait in seconds
        check_interval (float): Time between connection attempts in seconds
        
    Returns:
        bool: True if service is ready, False if timeout occurred
    """
    import requests
    from requests.exceptions import RequestException
    
    logger.info(f"Waiting for {service_name} to be ready at {url}...")
    start_time = time.time()
    attempt = 0
    
    while time.time() - start_time < timeout:
        attempt += 1
        try:
            response = requests.get(url, timeout=min(check_interval, 3))
            if response.status_code < 500:  # Accept any non-server error response
                elapsed = time.time() - start_time
                logger.info(f"{service_name} is ready at {url} after {elapsed:.2f}s and {attempt} attempts")
                return True
        except RequestException as e:
            elapsed = time.time() - start_time
            if int(elapsed) % 5 == 0 or attempt == 1:
                logger.info(f"Still waiting for {service_name} ({elapsed:.1f}s, attempt {attempt}): {e}")
            time.sleep(check_interval)
    
    logger.warning(f"Timeout waiting for {service_name} at {url} after {timeout}s and {attempt} attempts")
    return False