from typing import Any, Dict, Optional

from ...config.base_config import BaseConfig


class QueueLoggingConfig(BaseConfig):
    """
    Configuration for logging behavior.
    
    Controls log levels, formats, and integration with 
    external logging systems for the queue system.
    """
    def __init__(
        self,
        logger: Optional[Any] = None,
        level: str = "INFO"
    ):
        """
        Initialize logging configuration.
        
        Args:
            logger: Custom logger instance to use (default: simple console logger)
            level: Minimum log level to record (default: "INFO")
        """
        self._logger = logger or self._create_default_logger()
        self._level = level
        
        super().__init__()
        self._validate_config()
    
    @property
    def logger(self) -> Any:
        return self._logger
    
    @property
    def level(self) -> str:
        return self._level
    
    def _create_default_logger(self):
        """Create a simple default logger that outputs to console."""
        return type('SimpleLogger', (), {
            'error': lambda msg, **kwargs: print(f"ERROR: {msg}"),
            'warning': lambda msg, **kwargs: print(f"WARNING: {msg}"),
            'info': lambda msg, **kwargs: print(f"INFO: {msg}"),
            'debug': lambda msg, **kwargs: print(f"DEBUG: {msg}"),
            'critical': lambda msg, **kwargs: print(f"CRITICAL: {msg}")
        })()
    
    def _validate_config(self):
        """Validate configuration."""
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if self._level.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {self._level}. Must be one of {valid_levels}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "level": self._level,
            "logger_type": str(type(self._logger).__name__)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueLoggingConfig':
        """Create instance from dictionary."""
        return cls(
            logger=None,  # Will use default logger
            level=data.get('level', 'INFO')
        )
