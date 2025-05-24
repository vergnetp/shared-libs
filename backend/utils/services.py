"""
Serivices utility functions for service readiness checking and connectivity.
"""
import socket
import time
from .. import log as logger

def wait_for_service(service='postgres', host='localhost', port=5432, user='postgres', 
                    password='postgres', dbname='postgres', timeout=30):
    """
    Wait for the service to be ready with robust checking and better error reporting
    Using PyMySQL for MySQL connections
    """
    
    logger.info(f"Waiting for {service} to be ready at {host}:{port}...")
    start_time = time.time()
    
    # Initialize variables for error reporting
    last_error = None
    tcp_connected = False
    
    while time.time() - start_time < timeout:
        # First try to establish a TCP connection
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((host, int(port)))
            sock.close()
            tcp_connected = True
            logger.info(f"TCP connection to {host}:{port} successful")
        except Exception as e:
            tcp_connected = False
            last_error = f"TCP connection failed: {str(e)}"
            time.sleep(1)
            continue
            
        # If TCP connection works, try the real connection
        try:
            if service == 'mysql':
                import pymysql
                # PyMySQL uses 'db' parameter instead of 'database' or 'dbname'
                conn = pymysql.connect(
                    host=host,
                    port=int(port),
                    user=user,
                    password=password,
                    db=dbname,  # Note: PyMySQL uses 'db', not 'database' or 'dbname'
                    connect_timeout=5
                )
                conn.close()
                logger.info(f"{service} at {host}:{port} is ready!")
                return True
            elif service == 'postgres':
                import psycopg2
                conn = psycopg2.connect(
                    host=host,
                    port=int(port),
                    user=user,
                    password=password,
                    dbname=dbname,
                    connect_timeout=5
                )
                conn.close()
                logger.info(f"{service} at {host}:{port} is ready!")
                return True
            elif service == 'redis':                
                import redis
                r = redis.Redis(host=host, port=int(port))
                if r.ping():
                    logger.info(f"{service} at {host}:{port} is ready!")
                    return True
            else:
                # If we don't have special handling, assume TCP connection is sufficient
                logger.info(f"{service} at {host}:{port} is ready (TCP connection successful)!")
                return True
        except Exception as e:
            last_error = str(e)
            logger.info(f"{service} connection attempt failed: {last_error}")
        
        time.sleep(1)
    
    # Report detailed error on timeout
    if tcp_connected:
        logger.info(f"{service} at {host}:{port} failed to become ready within {timeout} seconds. TCP connection works but service connection failed with: {last_error}")
    else:
        logger.info(f"{service} at {host}:{port} failed to become ready within {timeout} seconds. Could not establish TCP connection: {last_error}")
    
    return False