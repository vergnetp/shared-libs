from enum import Enum
import os
from typing import Optional, Dict, Any, Union, Set

from ...config.base_config import BaseConfig

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

class LoggerConfig(BaseConfig):
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
        # Initialize all attributes
        self._service_name = service_name or f"service-{os.getpid()}"
        self._environment = environment
        self._use_redis = use_redis
        self._redis_url = redis_url
        self._log_dir = log_dir
        self._log_debug_to_file = log_debug_to_file
        self._quiet_init = quiet_init
        self._flush_interval = flush_interval
        self._add_caller_info = add_caller_info
        self._log_processor = log_processor
        self._log_batch_processor = log_batch_processor
        self._global_context = global_context or {}
        self._excluded_fields = excluded_fields or set()
        
        # Set minimum log level
        if isinstance(min_level, str):
            self._min_level = LogLevel.from_string(min_level)
        else:
            self._min_level = min_level
        
        # Configuration constants
        self.MAX_MESSAGE_SIZE = 5000
        self.DEFAULT_FLUSH_INTERVAL = 5
        
        # Call parent init and validate
        super().__init__()
        self._validate_config()
    
    # Add property methods for access
    @property
    def service_name(self) -> str:
        return self._service_name
    
    @property
    def environment(self) -> str:
        return self._environment
    
    @property
    def use_redis(self) -> bool:
        return self._use_redis
    
    @property
    def redis_url(self) -> Optional[str]:
        return self._redis_url
    
    @property
    def log_dir(self) -> Optional[str]:
        return self._log_dir
    
    @property
    def min_level(self) -> LogLevel:
        return self._min_level
    
    @property
    def log_debug_to_file(self) -> bool:
        return self._log_debug_to_file
    
    @property
    def flush_interval(self) -> int:
        return self._flush_interval
    
    @property
    def add_caller_info(self) -> bool:
        return self._add_caller_info
    
    @property
    def global_context(self) -> Dict[str, Any]:
        return self._global_context
    
    @property
    def excluded_fields(self) -> Set[str]:
        return self._excluded_fields
    
    def _validate_config(self):
        """Validate configuration values and adjust if necessary."""
        if self._flush_interval < 1:
            self._flush_interval = 1
        
        valid_envs = {"dev", "test", "staging", "prod"}
        if self._environment not in valid_envs:
            print(f"Warning: Environment '{self._environment}' not in {valid_envs}. Using anyway.")
        
        if self._use_redis and not self._redis_url:
            print("Warning: use_redis is True but redis_url is not provided. Disabling Redis logging.")
            self._use_redis = False
    
    def add_global_context(self, **context):
        """Add fields to the global context."""
        self._global_context.update(context)
        return self
    
    def remove_global_context(self, *keys):
        """Remove fields from the global context."""
        for key in keys:
            self._global_context.pop(key, None)
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'service_name': self._service_name,
            'environment': self._environment,
            'use_redis': self._use_redis,
            'redis_url': self._redis_url,
            'log_dir': self._log_dir,
            'min_level': self._min_level.name,
            'log_debug_to_file': self._log_debug_to_file,
            'flush_interval': self._flush_interval,
            'quiet_init': self._quiet_init,
            'add_caller_info': self._add_caller_info,
            'global_context': dict(self._global_context),
            'excluded_fields': list(self._excluded_fields)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LoggerConfig':
        """Create instance from dictionary."""
        return cls(
            service_name=data.get('service_name'),
            environment=data.get('environment', 'dev'),
            use_redis=data.get('use_redis', True),
            redis_url=data.get('redis_url'),
            log_dir=data.get('log_dir'),
            min_level=data.get('min_level', LogLevel.DEBUG),
            log_debug_to_file=data.get('log_debug_to_file', False),
            flush_interval=data.get('flush_interval', 5),
            quiet_init=data.get('quiet_init', False),
            log_processor=data.get('log_processor', 'log_message'),
            log_batch_processor=data.get('log_batch_processor', 'log_batch'),
            add_caller_info=data.get('add_caller_info', True),
            global_context=data.get('global_context', {}),
            excluded_fields=set(data.get('excluded_fields', []))
        )
