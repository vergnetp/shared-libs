# Fixed Logging System (python/log/logging.py)
# Fully synchronous implementation using Queue module

import threading
import sys
import os
import pathlib
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Union, List
import atexit
from .. import utils
from ..queue import QueueConfig, QueueManager, QueueRetryConfig

# Configuration constants
MAX_MESSAGE_SIZE = 5000
DEFAULT_FLUSH_INTERVAL = 5  # seconds

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

class AsyncLogger:
    """
    Thread-safe logger with Redis integration using Queue module.
    Uses a singleton pattern for global access.
    """
    _instance = None
    _instance_lock = threading.Lock()
    
    def __init__(self, 
                 use_redis: bool = False, 
                 redis_url: str = None,
                 log_dir: str = None,
                 service_name: str = None,
                 min_level: Union[LogLevel, str] = LogLevel.INFO,
                 log_debug_to_file: bool = False,
                 flush_interval: int = DEFAULT_FLUSH_INTERVAL,
                 quiet_init: bool = False,
                 log_processor: str = "log_message",
                 log_batch_processor: str = "log_batch"):
        """
        Initialize the logger with configurable options.
        
        Args:
            use_redis: Whether to use Redis as primary logging destination
            redis_url: Redis connection URL
            log_dir: Directory for local log files
                     If None, uses ../../../logs/ (relative to logger module)
            service_name: Identifier for this service instance
            min_level: Minimum log level to process
            log_debug_to_file: If True, debug messages will be written to file
                              (default is False for backward compatibility)
            flush_interval: How often to flush logs to disk/Redis (seconds)
            quiet_init: If True, suppresses printing the initialization message
            log_processor: Name of the processor function for single logs
            log_batch_processor: Name of the processor function for log batches
        """
        # Core settings
        self.log_dir = log_dir  # Can be None to use default path
        self.service_name = service_name or f"service-{os.getpid()}"
        self.log_debug_to_file = log_debug_to_file
        self.quiet_init = quiet_init  # Store quiet_init setting
        self.flush_interval = flush_interval
        
        # Set minimum log level
        if isinstance(min_level, str):
            self.min_level = LogLevel.from_string(min_level)
        else:
            self.min_level = min_level
        
        # Redis settings
        self.redis_url = redis_url
        self.use_redis = use_redis
        
        # Processor names
        self.log_processor = log_processor
        self.log_batch_processor = log_batch_processor
        
        # Thread synchronization
        self._file_lock = threading.RLock()
        
        # Initialize QueueConfig if Redis is enabled
        if self.use_redis:
            try:
                self.queue_config = QueueConfig(
                    redis_url=self.redis_url,
                    queue_prefix="log:",
                    logger=self._create_simple_logger()
                )
                
                # Initialize QueueManager
                self.queue_manager = QueueManager(config=self.queue_config)
            except Exception as e:
                if not self.quiet_init:
                    print(f"Failed to initialize Redis: {e}. Falling back to local logging only.")
                self.use_redis = False
        
        # Ensure log directory exists if not using default path
        if self.log_dir is not None:
            self._ensure_log_dir()
        else:
            # For default path, ensure the logs directory exists
            try:
                log_path = pathlib.Path(utils.get_root()) / 'logs'
                log_path.mkdir(exist_ok=True, parents=True)
            except Exception:
                # Ignore path errors during init, will be handled during actual logging
                pass
        
        # Worker state
        self._shutdown = False
        
        # Register cleanup on exit
        atexit.register(self._cleanup)
        
        # Initial startup log - only if not quiet
        if not self.quiet_init:
            print(f"Logger initialized: redis={self.use_redis}, path={self._get_log_file_path()}, service={self.service_name}", flush=True)
    
    def _create_simple_logger(self):
        """Create a simple logger for the QueueConfig"""
        class SimpleLogger:
            def __init__(self, quiet_init=False):
                self.quiet_init = quiet_init
                
            def error(self, msg): 
                if not self.quiet_init:
                    print(f"ERROR: {msg}")
            def warning(self, msg): 
                if not self.quiet_init:
                    print(f"WARNING: {msg}")
            def debug(self, msg): 
                if not self.quiet_init:
                    print(f"DEBUG: {msg}")
            def info(self, msg): 
                if not self.quiet_init:
                    print(f"INFO: {msg}")
            def critical(self, msg): 
                if not self.quiet_init:
                    print(f"CRITICAL: {msg}")
                    
        return SimpleLogger(quiet_init=self.quiet_init)
    
    def _cleanup(self):
        """Cleanup function for atexit that uses the current instance"""
        try:
            self.shutdown()
        except Exception:
            # Ignore exceptions during shutdown
            pass
        
    def _ensure_log_dir(self):
        """Ensure the log directory exists"""
        with self._file_lock:
            if not os.path.exists(self.log_dir):
                try:
                    os.makedirs(self.log_dir, exist_ok=True)
                except (OSError, PermissionError) as e:
                    # Print instead of logging to avoid recursion
                    print(f"Failed to create log directory: {e}", file=sys.stderr)
                    # Try to find a writable directory as fallback
                    try:
                        self.log_dir = os.path.join(os.path.expanduser("~"), ".logs")
                        os.makedirs(self.log_dir, exist_ok=True)
                        print(f"Using fallback log directory: {self.log_dir}", file=sys.stderr)
                    except Exception:
                        # Last resort is to use current directory
                        self.log_dir = os.getcwd()
                        print(f"Using current directory for logs: {self.log_dir}", file=sys.stderr)
    
    @classmethod
    def get_instance(cls, **kwargs) -> "AsyncLogger":
        """
        Get or create the singleton logger instance.
        
        Args:
            **kwargs: Configuration options passed to __init__ if creating instance.
                      
        Returns:
            AsyncLogger: The singleton logger instance
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    # Set quiet_init for tests if testing mode is detected
                    if 'pytest' in sys.modules or os.getenv('PYTEST_CURRENT_TEST'):
                        kwargs.setdefault('quiet_init', True)
                    
                    cls._instance = AsyncLogger(**kwargs)
        return cls._instance
    
    def log(self, 
           level: LogLevel, 
           message: str, 
           indent: int = 0, 
           truncate: bool = True,
           context: Dict[str, Any] = None):
        """
        Log a message - handles local logging and Redis queueing if enabled.
        
        Args:
            level: Log level
            message: Log message
            indent: Indentation level (for local log formatting)
            truncate: Whether to truncate long messages
            context: Additional contextual data to include in structured log
        """
        # Skip logs below minimum level immediately
        if level.value < self.min_level.value:
            return
            
        # Truncate long messages if requested
        if truncate and len(message) > MAX_MESSAGE_SIZE:
            message = message[:MAX_MESSAGE_SIZE] + "... [truncated]"
            
        # Handle local logging first
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        indent_str = '    ' * indent
        
        # Print to console based on level
        formatted_console = f"{timestamp} {indent_str}{message}"
        if level in (LogLevel.ERROR, LogLevel.CRITICAL):
            print(formatted_console, file=sys.stderr, flush=True)
        else:
            # For debug messages, only print if debug to file is enabled
            if level != LogLevel.DEBUG or self.log_debug_to_file:
                print(formatted_console, flush=True)
        
        # Write to file
        if level != LogLevel.DEBUG or self.log_debug_to_file:
            try:
                log_path = self._get_log_file_path()
                with self._file_lock:
                    os.makedirs(os.path.dirname(log_path), exist_ok=True)
                    formatted_file = f"{timestamp} [{level.name}] {indent_str}{message}"
                    with open(log_path, 'a') as log_file:
                        log_file.write(f"{formatted_file}\n")
                        if level == LogLevel.CRITICAL:
                            log_file.flush()
            except Exception as e:
                if not self.quiet_init:
                    print(f"Failed to write log to file: {e}", file=sys.stderr)
        
        # Only queue to Redis if Redis is enabled
        if self.use_redis:
            # Create the log record
            log_record = {
                'timestamp': timestamp,
                'level': level.name,  # Use name instead of enum for serialization
                'message': message,
                'indent': indent,
                'service': self.service_name,
                'pid': os.getpid(),
                'thread': threading.get_ident(),
            }
            
            # Add request_id if available
            from ..framework.context import request_id_var
            request_id = request_id_var.get()
            if request_id:
                log_record['request_id'] = request_id
                
            # Add context if provided
            if context:
                log_record['context'] = context
            
            try:
                # Use queue manager to enqueue the log
                retry_config = QueueRetryConfig(max_attempts=3, delays=[1, 5, 15])
                
                # This is now synchronous
                self.queue_manager.enqueue(
                    entity=log_record,
                    processor=self.log_processor,  # Use configured processor name
                    priority="high" if level in (LogLevel.ERROR, LogLevel.CRITICAL) else "normal",
                    retry_config=retry_config
                )
            except Exception as e:
                # If Redis queueing fails, just log locally and continue
                if not self.quiet_init:
                    print(f"Failed to queue log to Redis: {e}", file=sys.stderr)
    
    def _get_log_file_path(self, date=None):
        """
        Returns the file path where logs should be saved.
        
        Args:
            date (str, optional): A date string in YYYY_MM_DD format. Defaults to today.
            
        Returns:
            str: Full path to the log file for the given date.
        """
        if date is None:
            date = datetime.now().strftime("%Y_%m_%d")
            
        # Use the custom path builder to maintain compatibility with original logger
        if self.log_dir is None:
            # If no log_dir specified, use default path 3 directories up
            return utils.build_path(utils.get_root(), 'logs', f'{date}.log')
        else:
            # Otherwise use the specified log directory
            return os.path.join(self.log_dir, f"{date}.log")
    
    def set_log_level(self, level: Union[LogLevel, str]):
        """
        Dynamically change the minimum log level.
        
        Args:
            level: New minimum log level (enum or string)
        """
        if isinstance(level, str):
            self.min_level = LogLevel.from_string(level)
        else:
            self.min_level = level
            
        if not self.quiet_init:
            self.log(
                LogLevel.INFO,
                f"Log level changed to {self.min_level.name}"
            )
    
    def register_log_processor(self, processor_func, processor_name=None):
        """
        Register a custom log processor function.
        
        Args:
            processor_func: The processor function for handling logs
            processor_name: Optional name for the processor (defaults to function name)
        """
        if not self.use_redis:
            return
            
        if processor_name is None:
            processor_name = processor_func.__name__
            
        self.queue_config.operations_registry[processor_name] = processor_func
        
        if not self.quiet_init:
            print(f"Registered log processor: {processor_name}")
            
    def shutdown(self):
        """
        Gracefully shut down the logger, flushing any pending operations.
        """
        if self._shutdown:
            return
            
        self._shutdown = True
        
        # Log that we're shutting down, but only if not quiet
        if not self.quiet_init:
            print("Logger shutdown complete", file=sys.stderr)


# Public API - Simple functions for common use
def _log(level: LogLevel, prefix: str, message: str, indent: int = 0, context: Dict[str, Any] = None, **fields):
    """
    Log a message using the logger instance.
    
    Args:
        level: LogLevel enum
        prefix: String prefix like [DEBUG], [INFO], etc.
        message: The message to log
        indent: Indentation level
        context: Additional context data
        **fields: Additional structured fields to include in the log
    """
    # Print to console with prefix
    from ..framework.context import request_id_var
    request_id = request_id_var.get()
    if request_id:
        print(f"{prefix} [request_id={request_id}] {message}")
    else: 
        print(f"{prefix} {message}")
    
    # Merge context and fields if needed
    combined_context = context.copy() if context else {}
    if fields:
        combined_context.update(fields)
    
    # Log through the logger
    logger = AsyncLogger.get_instance()
    logger.log(level, message, indent=indent, context=combined_context)

def debug(message: str, indent: int = 0, context: Dict[str, Any] = None, **fields):
    """Log a debug message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back=1)
    if 'component' not in fields or 'subcomponent' not in fields:        
        if 'component' not in fields:
            fields['component'] = component
        if 'subcomponent' not in fields:
            fields['subcomponent'] = subcomponent 
    _log(LogLevel.DEBUG, f"[DEBUG] {component} - {subcomponent} - ", message, indent, context, **fields)

def info(message: str, indent: int = 0, context: Dict[str, Any] = None, **fields):
    """Log a debug message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back=1)
    if 'component' not in fields or 'subcomponent' not in fields:
        if 'component' not in fields:
            fields['component'] = component
        if 'subcomponent' not in fields:
            fields['subcomponent'] = subcomponent 
    _log(LogLevel.INFO, "[INFO] {component} - {subcomponent} - ", message, indent, context, **fields)

def warning(message: str, indent: int = 0, context: Dict[str, Any] = None, **fields):
    """Log an info message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back=1)
    if 'component' not in fields or 'subcomponent' not in fields:
        if 'component' not in fields:
            fields['component'] = component
        if 'subcomponent' not in fields:
            fields['subcomponent'] = subcomponent 
    _log(LogLevel.WARN, "[WARN] {component} - {subcomponent} - ", message, indent, context, **fields)

def error(message: str, indent: int = 0, context: Dict[str, Any] = None, **fields):
    """Log an error message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back=1)
    if 'component' not in fields or 'subcomponent' not in fields:
        if 'component' not in fields:
            fields['component'] = component
        if 'subcomponent' not in fields:
            fields['subcomponent'] = subcomponent 
    _log(LogLevel.ERROR, "[ERROR] {component} - {subcomponent} - ", message, indent, context, **fields)

def critical(message: str, context: Dict[str, Any] = None, **fields):
    """Log a critical message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back=1)
    if 'component' not in fields or 'subcomponent' not in fields: 
        if 'component' not in fields:
            fields['component'] = component
        if 'subcomponent' not in fields:
            fields['subcomponent'] = subcomponent 
    _log(LogLevel.CRITICAL, "[CRITICAL] {component} - {subcomponent} - ", message, 0, context, **fields)

def profile(message: str, indent: int = 0, context: Dict[str, Any] = None, **fields):
    """Log a prfofiling message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back=1)
    if 'component' not in fields or 'subcomponent' not in fields:
        if 'component' not in fields:
            fields['component'] = component
        if 'subcomponent' not in fields:
            fields['subcomponent'] = subcomponent 
    _log(LogLevel.DEBUG, "[PROFILER] {component} - {subcomponent} - ", message, indent, context, **fields)

def get_log_file():
    """
    Returns the file path where logs should be saved.
    
    Returns:
        str: Full path to the log file for today.
    """
    logger = AsyncLogger.get_instance()
    return logger._get_log_file_path()

def initialize_logger(**kwargs):
    """
    Initialize the logger with specified parameters.
    
    Args:
        **kwargs: Parameters for AsyncLogger initialization
        
    Returns:
        AsyncLogger: The configured logger instance
    """
    return AsyncLogger.get_instance(**kwargs)