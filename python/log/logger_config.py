from enum import Enum
import os
from typing import Optional, Dict, Any, List, Union, Set

class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    CRITICAL = 50
    
    @classmethod
    def from_string(cls, level_str: str) -> "LogLevel":
        """Convert string level name to enum"""
        return getattr(cls, level_str.upper(), cls.INFO)

class LoggerConfig:
    """
    Configuration class for the AsyncLogger.
    
    This class centralizes all logging configuration options and provides
    methods to modify and validate configuration at runtime.
    """
    def __init__(self, 
                 service_name: str = None,
                 environment: str = "dev",
                 use_redis: bool = True,
                 redis_url: Optional[str] = None,
                 log_dir: Optional[str] = None,
                 min_level: Union[LogLevel, str] = LogLevel.DEBUG,
                 log_debug_to_file: bool = False,
                 flush_interval: int = 5,
                 quiet_init: bool = False,
                 log_processor: str = "log_message",
                 log_batch_processor: str = "log_batch",
                 add_caller_info: bool = True,
                 global_context: Optional[Dict[str, Any]] = None,
                 excluded_fields: Optional[Set[str]] = None):
        """
        Initialize the logging configuration.
        
        Args:
            service_name: Identifier for this service instance
            environment: Environment name (dev, test, staging, prod)
            use_redis: Whether to use Redis as primary logging destination
            redis_url: Redis connection URL
            log_dir: Directory for local log files
            min_level: Minimum log level to process
            log_debug_to_file: If True, debug messages will be written to file
            flush_interval: How often to flush logs to disk/Redis (seconds)
            quiet_init: If True, suppresses printing the initialization message
            log_processor: Name of the processor function for single logs
            log_batch_processor: Name of the processor function for log batches
            add_caller_info: Automatically add component and subcomponent
            global_context: Dictionary of fields to add to all log messages
            excluded_fields: Set of field names to exclude from log output
        """
        # Service identification
        self.service_name = service_name or f"service-{os.getpid()}"
        self.environment = environment
        
        # Core settings
        self.log_dir = log_dir
        self.log_debug_to_file = log_debug_to_file
        self.quiet_init = quiet_init
        self.flush_interval = flush_interval
        self.add_caller_info = add_caller_info
        
        # Set minimum log level
        if isinstance(min_level, str):
            self.min_level = LogLevel.from_string(min_level)
        else:
            self.min_level = min_level
        
        # Redis settings
        self.redis_url = redis_url
        self.use_redis = use_redis and redis_url is not None
        
        # Processor names
        self.log_processor = log_processor
        self.log_batch_processor = log_batch_processor
        
        # Context and field management
        self.global_context = global_context or {}
        self.excluded_fields = excluded_fields or set()
        
        # Configuration constants
        self.MAX_MESSAGE_SIZE = 5000
        self.DEFAULT_FLUSH_INTERVAL = 5  # seconds

        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration values and adjust if necessary."""
        # Ensure valid flush interval
        if self.flush_interval < 1:
            self.flush_interval = 1
        
        # Validate environment
        valid_envs = {"dev", "test", "staging", "prod"}
        if self.environment not in valid_envs:
            print(f"Warning: Environment '{self.environment}' not in {valid_envs}. Using anyway.")
        
        # Check Redis URL if use_redis is True
        if self.use_redis and not self.redis_url:
            print("Warning: use_redis is True but redis_url is not provided. Disabling Redis logging.")
            self.use_redis = False
    
    def update(self, **kwargs):
        """
        Update configuration with new values.
        
        Args:
            **kwargs: New configuration values to set
            
        Returns:
            self: The updated configuration object
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                # Special handling for min_level
                if key == 'min_level' and isinstance(value, str):
                    setattr(self, key, LogLevel.from_string(value))
                else:
                    setattr(self, key, value)
        
        # Re-validate after updates
        self._validate_config()
        return self
    
    def add_global_context(self, **context):
        """
        Add fields to the global context that will be included in all log messages.
        
        Args:
            **context: Key-value pairs to add to global context
            
        Returns:
            self: The updated configuration object  
        """
        self.global_context.update(context)
        return self
    
    def remove_global_context(self, *keys):
        """
        Remove fields from the global context.
        
        Args:
            *keys: Keys to remove from global context
            
        Returns:
            self: The updated configuration object
        """
        for key in keys:
            self.global_context.pop(key, None)
        return self
    
    def to_dict(self):
        """
        Convert configuration to dictionary.
        
        Returns:
            Dict: Dictionary representation of configuration
        """
        return {
            'service_name': self.service_name,
            'environment': self.environment,
            'use_redis': self.use_redis,
            'redis_url': self.redis_url,
            'log_dir': self.log_dir,
            'min_level': self.min_level.name,
            'log_debug_to_file': self.log_debug_to_file,
            'flush_interval': self.flush_interval,
            'quiet_init': self.quiet_init,
            'add_caller_info': self.add_caller_info,
            'global_context': dict(self.global_context),
            'excluded_fields': list(self.excluded_fields)
        }
    
    def __str__(self):
        """String representation with sensitive fields masked."""
        config_dict = self.to_dict()
        # Mask sensitive information
        if config_dict.get('redis_url'):
            config_dict['redis_url'] = '***masked***'
        return f"LogConfig({', '.join([f'{k}={v}' for k, v in config_dict.items()])})"