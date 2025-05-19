import json
import hashlib
from typing import Dict, Any
from ... import log as logger

class DatabaseConfig:
    """
    Holds database connection configuration parameters.
    
    This class encapsulates all settings required to establish a database connection,
    including connection parameters, environment information, and connection identification.
    It provides methods to access these settings and generate a unique hash-based 
    identifier for the connection.
    
    Args:
        database (str): Database name.
        host (str, optional): Server hostname. Defaults to "localhost".
        port (int, optional): Server port. Defaults to 5432.
        user (str, optional): Username for authentication. Defaults to None.
        password (str, optional): Password for authentication. Defaults to None.
        alias (str, optional): Friendly name for the connection. Defaults to database name.
        env (str, optional): Environment label (e.g. prod, dev, test). Defaults to "prod".
        connection_acquisition_timeout (float, optional): Maximum time in seconds to wait when acquiring a connection from the pool. Defaults to 10.0.
        pool_creation_timeout (float, optional): Maximum time in seconds to wait for pool creation and initialization. Defaults to 30.0.
        query_execution_timeout (float, optional): Default timeout in seconds for SQL query execution. Can be overridden in individual queries. Defaults to 60.0.
        connection_creation_timeout (float, optional): Maximum time in seconds to wait for an individual database connection to be established. Defaults to 15.0.
        pool_shutdown_timeout (float, optional): Maximum time in seconds to wait for graceful pool shutdown before forcing connections to close. Defaults to 30.0.
    """
    def __init__(self, 
                 database: str, 
                 host: str="localhost", 
                 port: int=5432, 
                 user: str=None, 
                 password: str=None, 
                 alias: str=None, 
                 env: str='prod',  
                 connection_acquisition_timeout: float=10.0,  # Time to acquire connection from pool
                 pool_creation_timeout: float=30.0,          # Time to create/initialize pool
                 query_execution_timeout: float=60.0,        # Default timeout for SQL queries
                 connection_creation_timeout: float=15.0,    # Time to create individual connections
                 pool_shutdown_timeout: float=30.0,          # Time for graceful pool shutdown
                 *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Validate inputs
        if not database:
            raise ValueError("Database name or connection string is required")
        
        if port is not None and not isinstance(port, int):
            raise ValueError(f"Port must be an integer, got {type(port).__name__}")
        
        if env not in ('prod', 'dev', 'test', 'staging'):
            logger.warning(f"Unrecognized environment '{env}', using anyway but this might indicate a mistake")
  
        self.__host = host
        self.__port = port
        self.__database = database
        self.__user = user
        self.__password = password
        self.__env = env
        self.__alias = alias or database or f'database'
        self.connection_acquisition_timeout = connection_acquisition_timeout
        self.pool_creation_timeout = pool_creation_timeout
        self.query_execution_timeout = query_execution_timeout
        self.connection_creation_timeout = connection_creation_timeout
        self.pool_shutdown_timeout = pool_shutdown_timeout

    def config(self) -> Dict[str, Any]:
        """
        Returns the database configuration as a dictionary.
        
        This dictionary contains all the parameters needed to establish a database
        connection and can be passed directly to database drivers.
        
        Returns:
            Dict: Dictionary containing host, port, database, user, and password.
        """
        return {
            'host': self.__host,
            'port': self.__port,
            'database': self.__database,
            'user': self.__user,
            'password': self.__password,
            'connection_acquisition_timeout': self.connection_acquisition_timeout,
            'pool_creation_timeout': self.pool_creation_timeout,
            'query_execution_timeout': self.query_execution_timeout,
            'connection_creation_timeout': self.connection_creation_timeout,
            'pool_shutdown_timeout': self.pool_shutdown_timeout
        }
    
    def database(self) -> str:
        """
        Returns the database name.
        
        Returns:
            str: The configured database name.
        """
        return self.__database
    
    def alias(self) -> str:
        """
        Returns the database connection alias.
        
        The alias is a friendly name for the connection, which defaults to the
        database name if not explicitly provided.
        
        Returns:
            str: The database connection alias.
        """
        return self.__alias
    
    def user(self) -> str:
        """
        Returns the database user.
        
        Returns:
            str: The configured database user.
        """
        return self.__user
    
    def host(self) -> str:
        """
        Returns the database host.
        
        Returns:
            str: The configured database host.
        """
        return self.__host
    
    def password(self):
        return self.__password #todo  clean this unsafe thing
    
    def port(self) -> int:
        """
        Returns the database port.
        
        Returns:
            int: The configured database port.
        """
        return self.__port
    
    def env(self) -> str:
        """
        Returns the database environment.
        
        The environment is a label (e.g., 'prod', 'dev', 'test') that identifies
        the context in which the database is being used.
        
        Returns:
            str: The database environment label.
        """
        return self.__env

    def hash(self) -> str:
        """
        Returns a stable, hash-based key for the database configuration.
        
        This hash is used to uniquely identify connection pools and can be
        used as a key in dictionaries. It is based on all configuration
        parameters except the password.
        
        Returns:
            str: MD5 hash of the JSON-serialized configuration.
        """
        cfg = self.config().copy()
        cfg.pop('password', None)  # optional, if you want pools keyed w/o password
        key_json = json.dumps(cfg, sort_keys=True)
        return hashlib.md5(key_json.encode()).hexdigest()
