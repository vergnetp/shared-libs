from typing import Optional, Dict, Any

from ...config.base_config import BaseConfig
from ...databases import DatabaseConfig
from ...queue import QueueConfig
from ...log import LoggerConfig

class AppConfig(BaseConfig):
    """
    Central application configuration that aggregates all component configurations.
    """
    
    def __init__(
        self,
        database: Optional[DatabaseConfig] = None,
        queue: Optional[QueueConfig] = None,
        logging: Optional[LoggerConfig] = None,
        app_name: str = "application",
        environment: str = "dev",
        version: str = "1.0.0",
        debug: bool = False
    ):
        """
        Initialize application configuration.
        
        Args:
            database: Database configuration instance
            queue: Queue system configuration instance  
            logging: Logging configuration instance
            app_name: Name of the application
            environment: Environment (dev, test, staging, prod)
            version: Application version
            debug: Enable debug mode
        """
        self._database = database or DatabaseConfig()
        self._queue = queue or QueueConfig()
        self._logging = logging or LoggerConfig()
        self._app_name = app_name
        self._environment = environment
        self._version = version
        self._debug = debug
        
        super().__init__()
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration parameters."""
        errors = []
        
        if not self._app_name:
            errors.append("app_name cannot be empty")
        
        if self._environment not in ['dev', 'test', 'staging', 'prod']:
            errors.append(f"environment must be one of: dev, test, staging, prod, got '{self._environment}'")
        
        if errors:
            raise ValueError(f"Application configuration validation failed: {'; '.join(errors)}")
    
    @property
    def database(self) -> DatabaseConfig:
        """Get database configuration."""
        return self._database
    
    @property 
    def queue(self) -> QueueConfig:
        """Get queue configuration."""
        return self._queue
    
    @property
    def logging(self) -> LoggerConfig:
        """Get logging configuration."""
        return self._logging
    
    @property
    def app_name(self) -> str:
        """Get application name."""
        return self._app_name
    
    @property
    def environment(self) -> str:
        """Get environment."""
        return self._environment
    
    @property
    def version(self) -> str:
        """Get application version."""
        return self._version
    
    @property
    def debug(self) -> bool:
        """Get debug mode status."""
        return self._debug
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self._environment == "prod"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self._environment == "dev"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'app_name': self._app_name,
            'environment': self._environment, 
            'version': self._version,
            'debug': self._debug,
            'database': self._database.to_dict(),  
            'queue': self._queue.to_dict(),
            'logging': self._logging.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """
        Create AppConfig from dictionary.
        
        Args:
            data: Configuration dictionary
            
        Returns:
            AppConfig instance
        """
        # Extract component configs if they exist as dictionaries
        database_config = None
        if 'database' in data and isinstance(data['database'], dict):
            database_config = DatabaseConfig.from_dict(data['database']) 
        
        queue_config = None
        if 'queue' in data and isinstance(data['queue'], dict):
            queue_config = QueueConfig.from_dict(data['queue'])  
        
        logging_config = None  
        if 'logging' in data and isinstance(data['logging'], dict):
            logging_config = LoggerConfig.from_dict(data['logging']) 
        
        return cls(
            database=database_config,
            queue=queue_config,
            logging=logging_config,
            app_name=data.get('app_name', 'application'),
            environment=data.get('environment', 'dev'),
            version=data.get('version', '1.0.0'),
            debug=data.get('debug', False)
        )