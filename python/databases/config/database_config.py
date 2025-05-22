import json
import hashlib
from typing import Dict, Any
from ... import log as logger

from ...config.base_config import BaseConfig

class DatabaseConfig(BaseConfig):
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
                 connection_acquisition_timeout: float=10.0, # Time to acquire connection from pool
                 pool_creation_timeout: float=30.0,          # Time to create/initialize pool
                 query_execution_timeout: float=60.0,        # Default timeout for SQL queries
                 connection_creation_timeout: float=15.0     # Time to create individual connections                
                ):      
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._env = env
        self._alias = alias or database or 'database'
        self._connection_acquisition_timeout = connection_acquisition_timeout
        self._pool_creation_timeout = pool_creation_timeout
        self._query_execution_timeout = query_execution_timeout
        self._connection_creation_timeout = connection_creation_timeout
        
        super().__init__()
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration."""
        errors = []
        
        if not self._database:
            errors.append("Database name cannot be empty")
        
        if self._port is not None and (not isinstance(self._port, int) or self._port <= 0):
            errors.append(f"Port must be a positive integer, got {self._port}")
        
        if self._connection_acquisition_timeout <= 0:
            errors.append(f"connection_acquisition_timeout must be positive, got {self._connection_acquisition_timeout}")
        
        if self._pool_creation_timeout <= 0:
            errors.append(f"pool_creation_timeout must be positive, got {self._pool_creation_timeout}")
        
        if self._query_execution_timeout <= 0:
            errors.append(f"query_execution_timeout must be positive, got {self._query_execution_timeout}")
        
        if self._connection_creation_timeout <= 0:
            errors.append(f"connection_creation_timeout must be positive, got {self._connection_creation_timeout}")
        
        # For environment, we can be more lenient but still validate
        valid_envs = {'prod', 'dev', 'test', 'staging'}
        if self._env not in valid_envs:
            # Could be a warning instead of error, but for consistency:
            errors.append(f"Environment must be one of {valid_envs}, got '{self._env}'")
        
        if errors:
            raise ValueError(f"Database configuration validation failed: {'; '.join(errors)}")

    def config(self) -> Dict[str, Any]:
        """
        Returns the database configuration as a dictionary.
        
        This dictionary contains all the parameters needed to establish a database
        connection and can be passed directly to database drivers.
        
        Returns:
            Dict: Dictionary containing host, port, database, user, and password.
        """
        return {
            'host': self._host,
            'port': self._port,
            'database': self._database,
            'user': self._user,
            'password': self._password,
            'connection_acquisition_timeout': self._connection_acquisition_timeout,
            'pool_creation_timeout': self._pool_creation_timeout,
            'query_execution_timeout': self._query_execution_timeout,
            'connection_creation_timeout': self._connection_creation_timeout
        }
    
    def database(self) -> str:
        """
        Returns the database name.
        
        Returns:
            str: The configured database name.
        """
        return self._database
    
    def alias(self) -> str:
        """
        Returns the database connection alias.
        
        The alias is a friendly name for the connection, which defaults to the
        database name if not explicitly provided.
        
        Returns:
            str: The database connection alias.
        """
        return self._alias
    
    def user(self) -> str:
        """
        Returns the database user.
        
        Returns:
            str: The configured database user.
        """
        return self._user
    
    def host(self) -> str:
        """
        Returns the database host.
        
        Returns:
            str: The configured database host.
        """
        return self._host
    
    def password(self):
        return self._password #todo  clean this unsafe thing
    
    def port(self) -> int:
        """
        Returns the database port.
        
        Returns:
            int: The configured database port.
        """
        return self._port
    
    def env(self) -> str:
        """
        Returns the database environment.
        
        The environment is a label (e.g., 'prod', 'dev', 'test') that identifies
        the context in which the database is being used.
        
        Returns:
            str: The database environment label.
        """
        return self._env


    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.config()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DatabaseConfig':
        """Create instance from dictionary."""
        return cls(
            database=data.get('database', ''),
            host=data.get('host', 'localhost'),
            port=data.get('port', 5432),
            user=data.get('user'),
            password=data.get('password'),
            alias=data.get('alias'),
            env=data.get('env', 'prod'),
            connection_acquisition_timeout=data.get('connection_acquisition_timeout', 10.0),
            pool_creation_timeout=data.get('pool_creation_timeout', 30.0),
            query_execution_timeout=data.get('query_execution_timeout', 60.0),
            connection_creation_timeout=data.get('connection_creation_timeout', 15.0)
        )