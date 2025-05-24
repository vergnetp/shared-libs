# Improved Logging System (python/log/logging.py)
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
from .config.logger_config import LoggerConfig, LogLevel


class Logger:
    """
    Thread-safe logger with Redis integration using Queue module.
    Uses a singleton pattern for global access.
    """
    _instance = None
    _instance_lock = threading.Lock()
    
    def __init__(self, config: Optional[LoggerConfig] = None, **kwargs):
        """
        Initialize the logger with a LogConfig object or keyword arguments.
        
        Args:
            config: LogConfig instance (overrides any keyword arguments)
            **kwargs: Configuration options passed directly if no config object
        """      
        # If no config object provided, create one from kwargs
        self.config = config if config is not None else LoggerConfig(**kwargs)

        # Thread synchronization
        self._file_lock = threading.RLock()
        
        # Initialize QueueConfig if Redis is enabled and defined
        if self.config.use_redis and self.config.redis_url:
            try:
                self.queue_config = QueueConfig(
                    redis_url=self.config.redis_url,
                    queue_prefix="log:",
                    logger=self._create_simple_logger()
                )
                
                # Initialize QueueManager
                self.queue_manager = QueueManager(config=self.queue_config)
            except Exception as e:
                if not self.config.quiet_init:
                    print(f"Failed to initialize Redis: {e}. Falling back to local logging only.")
                self.config.use_redis = False
        else:
            if self.config.use_redis and not self.config.redis_url:
                if not self.config.quiet_init:
                    print("Warning: use_redis is True but redis_url is not provided. Disabling Redis logging.")
                self.config._use_redis = False

        # Ensure log directory exists if not using default path
        if self.config.log_dir is not None:
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
        if not self.config.quiet_init:
            print(f"Logger initialized: redis={self.config.use_redis}, path={self._get_log_file_path()}, service={self.config.service_name}", flush=True)
    
    def _create_simple_logger(self):
        """Create a simple logger for the QueueConfig or unit tests"""
        class SimpleLogger:
            def __init__(self, quiet_init=False):
                self.quiet_init = quiet_init
                
            def error(self, msg, **kwargs): 
                if not self.quiet_init:
                    print(f"ERROR: {msg}")
            def warning(self, msg, **kwargs): 
                if not self.quiet_init:
                    print(f"WARNING: {msg}")
            def debug(self, msg, **kwargs): 
                if not self.quiet_init:
                    print(f"DEBUG: {msg}")
            def info(self, msg, **kwargs): 
                if not self.quiet_init:
                    print(f"INFO: {msg}")
            def critical(self, msg, **kwargs): 
                if not self.quiet_init:
                    print(f"CRITICAL: {msg}")
                    
        return SimpleLogger(quiet_init=self.config.quiet_init)
    
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
            if not os.path.exists(self.config.log_dir):
                try:
                    os.makedirs(self.config.log_dir, exist_ok=True)
                except (OSError, PermissionError) as e:
                    # Print instead of logging to avoid recursion
                    print(f"Failed to create log directory: {e}", file=sys.stderr)
                    # Try to find a writable directory as fallback
                    try:
                        self.config.log_dir = os.path.join(os.path.expanduser("~"), ".logs")
                        os.makedirs(self.config.log_dir, exist_ok=True)
                        print(f"Using fallback log directory: {self.config.log_dir}", file=sys.stderr)
                    except Exception:
                        # Last resort is to use current directory
                        self.config.log_dir = os.getcwd()
                        print(f"Using current directory for logs: {self.config.log_dir}", file=sys.stderr)
    
    @classmethod
    def get_instance(cls, **kwargs) -> "Logger":
        """
        Get or create the singleton logger instance.
        
        Args:
            **kwargs: Configuration options passed to __init__ if creating instance.
                      
        Returns:
            Logger: The singleton logger instance
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    # Set quiet_init for tests if testing mode is detected
                    if 'pytest' in sys.modules or os.getenv('PYTEST_CURRENT_TEST'):
                        kwargs.setdefault('quiet_init', True)
                    
                    cls._instance = Logger(**kwargs)
        return cls._instance
    
    def log(self, 
            level: LogLevel, 
            message: str, 
            indent: int = 0, 
            truncate: bool = True,
            context: Dict[str, Any] = None,
            prefix: str = None,
            **fields):
        """
        Log a message - handles local logging and Redis queueing if enabled.
        
        Args:
            level: Log level
            message: Log message
            indent: Indentation level (for local log formatting)
            truncate: Whether to truncate long messages
            context: Additional contextual data to include in structured log
            prefix: Optional prefix for the message (like [DEBUG], [INFO], etc.)
            **fields: Additional structured fields to include in the log
        """
        # Skip logs below minimum level immediately
        if level.value < self.config.min_level.value:
            return

        # Merge global context, context parameter, and fields
        combined_context = self.config.global_context.copy()
        if context:
            combined_context.update(context)
        combined_context.update(fields)
        
        # Remove excluded fields
        for field in self.config.excluded_fields:
            combined_context.pop(field, None)
        
        # Add caller info if enabled
        if self.config.add_caller_info and 'component' not in combined_context:
            component, subcomponent = utils.get_caller_info(frames_back=2)
            combined_context['component'] = component
            combined_context['subcomponent'] = subcomponent

        # Truncate long messages if requested
        if truncate and len(message) > self.config.MAX_MESSAGE_SIZE:
            message = message[:self.config.MAX_MESSAGE_SIZE] + "... [truncated]"
        
        # Create timestamp once for consistency
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Add request_id if available and not already present
        """if 'request_id' not in combined_context:
            from ..framework.context import request_id_var
            request_id = request_id_var.get()
            if request_id:
                combined_context['request_id'] = request_id """
        
        # Add standard fields to context if not already present
        if 'timestamp' not in combined_context:
            combined_context['timestamp'] = timestamp

        if 'service_name' not in combined_context:
            combined_context['service_name'] = self.config.service_name

        if 'environment' not in combined_context:
            combined_context['environment'] = self.config.environment
        
        # Format indentation
        indent_str = '    ' * indent
        
        # Store original message for Redis/OpenSearch
        original_message = message
        
        # Add prefix for console/file logs if provided
        if prefix:
            message = f"{prefix} {message}"
        
        # Format structured fields for text output
        field_str = self._format_field_string(combined_context)
        
        # Create consistent formatted output for console and file
        formatted_output = f"{timestamp} {indent_str}{message}{field_str}"
        
        # Handle console output
        self._output_to_console(level, formatted_output)
        
        # Handle file output
        self._output_to_file(level, timestamp, indent_str, message, field_str)
        
        # Handle Redis output if enabled
        if self.config.use_redis:
            self._output_to_redis(level, timestamp, original_message, indent, combined_context)

    def _format_field_string(self, context: Dict[str, Any]) -> str:
        """Format context fields as a string for text output."""
        if not context:
            return ""
            
        field_parts = []
        for key, value in context.items():
            if key != 'timestamp':  # Skip timestamp in fields as it's already in the log prefix
                # Convert value to string and truncate if needed
                value_str = str(value)
                if len(value_str) > 50:  # Truncate long values
                    value_str = value_str[:47] + "..."
                field_parts.append(f"{key}={value_str}")
        
        if not field_parts:
            return ""
            
        field_str = " | " + " ".join(field_parts)
        # Truncate entire field string if too long
        if len(field_str) > 500:
            field_str = field_str[:497] + "..."
            
        return field_str
        
    def _output_to_console(self, level: LogLevel, formatted_output: str):
        """Output log message to console based on level."""
        if level in (LogLevel.ERROR, LogLevel.CRITICAL):
            print(formatted_output, file=sys.stderr, flush=True)
        elif level != LogLevel.DEBUG or self.config.log_debug_to_file:
            # For non-debug messages, or debug if enabled
            print(formatted_output, flush=True)
            
    def _output_to_file(self, level: LogLevel, timestamp: str, indent_str: str, message: str, field_str: str):
        """Output log message to file."""
        if level != LogLevel.DEBUG or self.config.log_debug_to_file:
            try:
                # Try to rotate logs if needed, but don't let it stop us
                try:
                    self._rotate_logs_if_needed()
                except Exception as e:
                    if not self.config.quiet_init:
                        print(f"Failed to rotate logs: {e}", file=sys.stderr)
                        
                log_path = self._get_log_file_path()
                
                with self._file_lock:
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(log_path), exist_ok=True)
                    
                    # Add level name in brackets for file logs
                    formatted_file = f"{timestamp} [{level.name}] {indent_str}{message}{field_str}"
                    
                    # Using a buffer for file writing can improve performance
                    if not hasattr(self, '_file_buffer'):
                        self._file_buffer = []
                        self._last_flush = time.time()
                    
                    # Add to buffer
                    self._file_buffer.append(formatted_file + "\n")
                    
                    # Flush if buffer is large or critical message or time threshold exceeded
                    should_flush = (
                        level == LogLevel.CRITICAL or
                        len(self._file_buffer) >= 100 or
                        time.time() - self._last_flush > self.config.flush_interval or
                        'pytest' in sys.modules  # Force flush in test environment
                    )
                    
                    if should_flush:
                        with open(log_path, 'a') as log_file:
                            log_file.writelines(self._file_buffer)
                            log_file.flush()  # Ensure file is flushed to disk
                            os.fsync(log_file.fileno())  # Force OS to write to disk
                        
                        # Clear buffer and update last flush time
                        self._file_buffer = []
                        self._last_flush = time.time()
                        
            except Exception as e:
                if not self.config.quiet_init:
                    print(f"Failed to write log to file: {e}", file=sys.stderr)
                    # If file writing fails, try to write to console as fallback
                    print(formatted_file, file=sys.stderr)
                    
    def _output_to_redis(self, level: LogLevel, timestamp: str, message: str, indent: int, context: Dict[str, Any]):
        """Queue log message to Redis."""
        try:
            # Create the log record
            log_record = {
                'timestamp': timestamp,
                'level': level.name,
                'message': message,
                'indent': indent,
                'service': self.config.service_name,
                'pid': os.getpid(),
                'thread': threading.get_ident(),
            }
            
            # Add all fields from context
            for key, value in context.items():
                if key != 'timestamp' and key not in log_record:
                    log_record[key] = value
            
            # Use queue manager with a timeout for the operation
            retry_config = QueueRetryConfig(max_attempts=3, delays=[1, 5, 15], timeout=30)        
            
            self.queue_manager.enqueue(
                entity=log_record,
                processor=self.config.log_processor,
                priority="high" if level in (LogLevel.ERROR, LogLevel.CRITICAL) else "normal",
                retry_config=retry_config

            )
        except Exception as e:
            if not self.config.quiet_init:
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
        if self.config.log_dir is None:
            # If no log_dir specified, use default path 3 directories up
            return utils.build_path(utils.get_root(), 'logs', f'{date}.log')
        else:
            # Otherwise use the specified log directory
            return os.path.join(self.config.log_dir, f"{date}.log")
    
    def _rotate_logs_if_needed(self):
        """Check if logs need rotation and rotate if needed."""
        # Skip rotation in testing environments
        if 'pytest' in sys.modules or os.getenv('PYTEST_CURRENT_TEST'):
            return
            
        # This is a simple date-based rotation
        current_date = datetime.now().strftime("%Y_%m_%d")
        current_path = self._get_log_file_path(current_date)
        
        # Check if current log file is too large (optional)
        if os.path.exists(current_path):
            size_mb = os.path.getsize(current_path) / (1024 * 1024)
            if size_mb > 100:  # Rotate at 100MB
                # Create an additional rotation with timestamp
                timestamp = datetime.now().strftime("%H%M%S")
                rotation_path = f"{current_path}.{timestamp}"
                try:
                    with self._file_lock:
                        # Rename current file to rotation path
                        os.rename(current_path, rotation_path)
                except Exception as e:
                    print(f"Failed to rotate log file: {e}", file=sys.stderr)

    def set_log_level(self, level: Union[LogLevel, str]):
        """
        Dynamically change the minimum log level.
        
        Args:
            level: New minimum log level (enum or string)
        """
        if isinstance(level, str):
            self.config.min_level = LogLevel.from_string(level)
        else:
            self.config.min_level = level
            
        if not self.config.quiet_init:
            self.log(
                LogLevel.INFO,
                f"Log level changed to {self.config.min_level.name}"
            )
    
    def register_log_processor(self, processor_func, processor_name=None):
        """
        Register a custom log processor function.
        
        Args:
            processor_func: The processor function for handling logs
            processor_name: Optional name for the processor (defaults to function name)
        """
        if not self.config.use_redis:
            return
            
        if processor_name is None:
            processor_name = processor_func.__name__
            
        self.queue_config.operations_registry[processor_name] = processor_func
        
        if not self.config.quiet_init:
            print(f"Registered log processor: {processor_name}")
            
    def shutdown(self):
        """
        Gracefully shut down the logger, flushing any pending operations.
        """
        if self._shutdown:
            return
            
        self._shutdown = True
        
        # Flush any remaining buffer to file
        if hasattr(self, '_file_buffer') and self._file_buffer:
            try:
                log_path = self._get_log_file_path()
                with open(log_path, 'a') as log_file:
                    log_file.writelines(self._file_buffer)
            except Exception as e:
                print(f"Failed to flush log buffer during shutdown: {e}", file=sys.stderr)
        
        # Log that we're shutting down, but only if not quiet
        if not self.config.quiet_init:
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
    # Get logger instance
    logger = Logger.get_instance()
    
    # Remove 'self' from fields if present to avoid conflict with the logger instance
    fields_copy = fields.copy() if fields else {}
    if 'self' in fields_copy:
        del fields_copy['self']
    
    # Now call log with the cleaned fields
    logger.log(level, message, indent=indent, context=context, prefix=prefix, **fields_copy)

def debug(message: str, indent: int = 0, context: Dict[str, Any] = None, frames_back: bool=1, **fields):
    """Log a debug message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back)
    if 'component' not in fields:
        fields['component'] = component
    if 'subcomponent' not in fields:
        fields['subcomponent'] = subcomponent 
    _log(LogLevel.DEBUG, f"[DEBUG] {fields['component']} - {fields['subcomponent']} - ", message, indent, context, **fields)

def info(message: str, indent: int = 0, context: Dict[str, Any] = None, frames_back: bool=1, **fields):
    """Log an info message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back)
    if 'component' not in fields:
        fields['component'] = component
    if 'subcomponent' not in fields:
        fields['subcomponent'] = subcomponent 
    _log(LogLevel.INFO, f"[INFO] {fields['component']} - {fields['subcomponent']} - ", message, indent, context, **fields)

def warning(message: str, indent: int = 0, context: Dict[str, Any] = None, frames_back: bool=1, **fields):
    """Log a warning message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back)
    if 'component' not in fields:
        fields['component'] = component
    if 'subcomponent' not in fields:
        fields['subcomponent'] = subcomponent 
    _log(LogLevel.WARN, f"[WARN] {fields['component']} - {fields['subcomponent']} - ", message, indent, context, **fields)

def error(message: str, indent: int = 0, context: Dict[str, Any] = None, frames_back: bool=1, **fields):
    """Log an error message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back)
    if 'component' not in fields:
        fields['component'] = component
    if 'subcomponent' not in fields:
        fields['subcomponent'] = subcomponent 
    _log(LogLevel.ERROR, f"[ERROR] {fields['component']} - {fields['subcomponent']} - ", message, indent, context, **fields)

def critical(message: str, context: Dict[str, Any] = None, frames_back: bool=1, **fields):
    """Log a critical message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back)
    if 'component' not in fields:
        fields['component'] = component
    if 'subcomponent' not in fields:
        fields['subcomponent'] = subcomponent 
    _log(LogLevel.CRITICAL, f"[CRITICAL] {fields['component']} - {fields['subcomponent']} - ", message, 0, context, **fields)

def profile(message: str, indent: int = 0, context: Dict[str, Any] = None, frames_back: bool=1, **fields):
    """Log a profiling message with structured fields."""
    component, subcomponent = utils.get_caller_info(frames_back)
    if 'component' not in fields:
        fields['component'] = component
    if 'subcomponent' not in fields:
        fields['subcomponent'] = subcomponent 
    _log(LogLevel.DEBUG, f"[PROFILER] {fields['component']} - {fields['subcomponent']} - ", message, indent, context, **fields)

def get_log_file():
    """
    Returns the file path where logs should be saved.
    
    Returns:
        str: Full path to the log file for today.
    """
    logger = Logger.get_instance()
    return logger._get_log_file_path()

def initialize_logger(**kwargs):
    """
    Initialize the logger with specified parameters.
    
    Args:
        **kwargs: Parameters for Logger initialization
        
    Returns:
       Logger: The configured logger instance
    """
    return Logger.get_instance(**kwargs)