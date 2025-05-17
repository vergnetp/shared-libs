from typing import Any, Dict, List, Optional, Union, Callable, Type


class QueueLoggingConfig:
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
        self.logger = logger or self._create_default_logger()
        self.level = level
    
    def _create_default_logger(self):
        """
        Create a simple default logger that outputs to console.
        
        Returns:
            Simple logger instance
        """
        return type('SimpleLogger', (), {
            'error': lambda msg, **kwargs: print(f"ERROR: {msg}"),
            'warning': lambda msg, **kwargs: print(f"WARNING: {msg}"),
            'info': lambda msg, **kwargs: print(f"INFO: {msg}"),
            'debug': lambda msg, **kwargs: print(f"DEBUG: {msg}"),
            'critical': lambda msg, **kwargs: print(f"CRITICAL: {msg}")
        })()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration
        """
        return {
            "level": self.level,
        }
