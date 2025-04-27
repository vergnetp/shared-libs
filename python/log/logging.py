import queue
import threading
import traceback
import asyncio
import os
import sys
import json
import pathlib
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Union
import atexit
from .. import utils

# Optional Redis dependencies
try:
    from redis.asyncio import Redis
    from arq.connections import create_pool, ArqRedis
    REDIS_AVAILABLE = True
except ImportError:
    Redis = None
    ArqRedis = None
    REDIS_AVAILABLE = False

# Try to import yaml, but don't require it
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Configuration constants
MAX_QUEUE_SIZE = 10000
MAX_MESSAGE_SIZE = 5000
# Maximum verbosity level; any message with a level above this will be ignored
MAX_VERBOSE_LEVEL = 10

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
    Thread-safe asynchronous logger with Redis integration and local fallback.
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
                 quiet_init: bool = False):  # Added quiet_init parameter
        """
        Initialize the logger with configurable options.
        
        Args:
            use_redis: Whether to use Redis as primary logging destination
            redis_url: Redis connection URL
            log_dir: Directory for local log files
                     If None, uses ../../../logs/ (relative to logger module)
                     This matches the original logger's behavior
            service_name: Identifier for this service instance
            min_level: Minimum log level to process
            log_debug_to_file: If True, debug messages will be written to file
                              (default is False for backward compatibility)
            quiet_init: If True, suppresses printing the initialization message
                       (default is False)
            
        Note:
            All these parameters can also be configured via:
            1. Direct parameters to this constructor
            2. Environment variables (LOG_DIR, LOGGING_USE_REDIS, etc.)
            3. Config file (specified by CONFIG_FILE env var, defaults to config.yml)
            
            See get_instance() for more details on configuration precedence.
        """
        # Core settings
        self.queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.use_redis = use_redis and REDIS_AVAILABLE
        self.log_dir = log_dir  # Can be None to use default path
        self.service_name = service_name or f"service-{os.getpid()}"
        self.log_debug_to_file = log_debug_to_file
        self.quiet_init = quiet_init  # Store quiet_init setting
        
        # Set minimum log level
        if isinstance(min_level, str):
            self.min_level = LogLevel.from_string(min_level)
        else:
            self.min_level = min_level
        
        # Redis settings
        self.redis_url = redis_url
        self.redis_pool: Optional[ArqRedis] = None
        
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
        
        # Start worker thread
        self.worker_thread.start()
        
        # Initialize Redis if needed
        if self.use_redis:
            asyncio.run(self._init_redis())
        
        # Register cleanup on exit
        atexit.register(self._cleanup)
        
        # Initial startup log - only if not quiet
        if not self.quiet_init:
            self._direct_log(
                LogLevel.INFO, 
                f"Logger initialized: redis={self.use_redis}, path={self._get_log_file_path()}, service={self.service_name}"
            )
    
    def _cleanup(self):
        """Cleanup function for atexit that uses the current instance"""
        try:
            self.shutdown()
        except Exception:
            # Ignore exceptions during shutdown
            pass
        
    def _ensure_log_dir(self):
        """Ensure the log directory exists"""
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir, exist_ok=True)
            except Exception as e:
                # Print instead of logging to avoid recursion
                print(f"Failed to create log directory: {e}", file=sys.stderr)
    
    async def _init_redis(self):
        """Initialize Redis connection pool"""
        if not REDIS_AVAILABLE:
            if not self.quiet_init:
                self._direct_log(LogLevel.ERROR, "Required Redis libraries not available")
            return
            
        try:
            if self.redis_url:
                self.redis_pool = await create_pool(self.redis_url)
            else:
                self.redis_pool = await create_pool()
            if not self.quiet_init:
                self._direct_log(LogLevel.INFO, "Redis connection established")
        except Exception as e:
            if not self.quiet_init:
                self._direct_log(
                    LogLevel.ERROR, 
                    f"Failed to initialize Redis: {e}. Falling back to local logging."
                )
            self.use_redis = False
    
    @staticmethod
    def _load_config():
        """
        Load configuration from file and environment variables.
        
        Priority order (highest to lowest):
        1. Environment variables
        2. Config file
        3. Default values
        
        Config file location can be specified via CONFIG_FILE environment variable.
        Supports both JSON (default) and YAML (if PyYAML is installed) formats.
        
        Returns:
            dict: Configuration dictionary
        """
        # Start with defaults
        config = {
            "log_dir": None,  # None means use default relative path
            "use_redis": False,
            "min_level": "INFO",
            "redis_url": None,
            "service_name": f"service-{os.getpid()}",
            "log_debug_to_file": False,  # Default to not logging debug to file
            "quiet_init": False  # Default to showing init message
        }
        
        # Try to load from config file if it exists
        config_file = os.getenv("CONFIG_FILE", "config.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    if config_file.endswith(('.yml', '.yaml')) and YAML_AVAILABLE:
                        file_config = yaml.safe_load(f)
                    else:
                        file_config = json.load(f)
                        
                    if file_config and "logging" in file_config:
                        config.update(file_config["logging"])
            except Exception as e:
                print(f"Error loading config file: {e}", file=sys.stderr)
        
        # Environment variables override config file
        env_mappings = {
            "LOG_DIR": "log_dir",
            "LOGGING_USE_REDIS": "use_redis",
            "LOG_LEVEL": "min_level",
            "REDIS_URL": "redis_url",
            "SERVICE_NAME": "service_name",
            "LOG_DEBUG_TO_FILE": "log_debug_to_file",
            "QUIET_LOGGER_INIT": "quiet_init"
        }
        
        for env_var, config_key in env_mappings.items():
            if os.getenv(env_var):
                if config_key in ("use_redis", "log_debug_to_file", "quiet_init"):
                    config[config_key] = os.getenv(env_var).lower() == "true"
                else:
                    config[config_key] = os.getenv(env_var)
        
        return config  
    
    @classmethod
    def get_instance(cls, **kwargs) -> "AsyncLogger":
        """
        Get or create the singleton logger instance.
        
        Args:
            **kwargs: Configuration options passed to __init__ if creating instance.
                      These override any settings from config file or environment.
            
        Returns:
            AsyncLogger: The singleton logger instance
            
        Configuration is loaded from (in order of precedence):
        1. kwargs passed to this method
        2. Environment variables
        3. Config file (path in CONFIG_FILE env var, defaults to ./config.yml)
        4. Default values
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    # Set quiet_init for tests if testing mode is detected
                    if 'pytest' in sys.modules:
                        kwargs.setdefault('quiet_init', True)
                    
                    # Load config from file and environment
                    config = cls._load_config()
                    
                    # kwargs override config
                    config.update(kwargs)
                    
                    cls._instance = AsyncLogger(**config)
        return cls._instance
    
    def _process_queue(self):
        """Worker thread that processes the log queue"""
        while not self._shutdown:
            try:
                record = self.queue.get(timeout=0.1)
                if record is None:  # Sentinel for shutdown
                    break
                    
                asyncio.run(self._handle_log(record))
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                # Log the exception but keep the thread running
                traceback_msg = traceback.format_exc()
                # Use print instead of logging to avoid potential recursion
                if not self.quiet_init:
                    print(f"Logger thread error: {traceback_msg}", file=sys.stderr)
    
    async def _handle_log(self, record: Dict[str, Any]):
        """
        Process a log record, sending to Redis and/or writing locally.
        
        Args:
            record: Dictionary containing log metadata and message
        """
        level = record['level']
        
        # Skip logs below minimum level
        if level.value < self.min_level.value:
            return
            
        try:
            # Try Redis first if enabled
            if self.use_redis and self.redis_pool:
                try:
                    # Convert LogLevel enum to string for serialization
                    record_copy = record.copy()
                    record_copy['level'] = record_copy['level'].name
                    
                    await self.redis_pool.enqueue_job(
                        "log_message", 
                        log_record=record_copy
                    )
                    
                    # For critical logs, ensure we have local backup too
                    if level == LogLevel.CRITICAL:
                        self._write_to_local(record)
                        
                except Exception as e:
                    # Redis failed, log locally and include the Redis error
                    if not self.quiet_init:
                        print(f"Redis logging failed: {e}, falling back to local", file=sys.stderr)
                    # Only write non-debug logs to local file when Redis fails
                    # unless log_debug_to_file is enabled
                    if level != LogLevel.DEBUG or self.log_debug_to_file:
                        self._write_to_local(record)
            else:
                # Redis not enabled
                # For debug messages, handle according to configuration
                if level == LogLevel.DEBUG:
                    # Always write to stdout
                    self._write_to_stdout_only(record)
                    
                    # Optionally also write to file if configured
                    if self.log_debug_to_file:
                        self._write_to_file_only(record)
                else:
                    # Write other levels to both stdout and file
                    self._write_to_local(record)
                
        except Exception as e:
            # Last resort if all else fails - direct console output
            print(f"CRITICAL LOGGING FAILURE: {e}", file=sys.stderr)
            print(f"Original message: {record.get('message', 'unknown')}", file=sys.stderr)
    
    def _write_to_stdout_only(self, record: Dict[str, Any]):
        """
        Write a log record to stdout only.
        
        Args:
            record: Dictionary containing log metadata and message
        """
        level = record['level']
        message = record['message']
        timestamp = record['timestamp']
        indent_level = record.get('indent', 0)
        indent = '    ' * indent_level
        
        # Format the message for display
        formatted_msg = f"{timestamp} {indent}{message}"
        
        # Print to console
        print(formatted_msg, flush=True)
        
    def _write_to_file_only(self, record: Dict[str, Any]):
        """
        Write a log record to the file only, not stdout.
        
        Args:
            record: Dictionary containing log metadata and message
        """
        level = record['level']
        message = record['message']
        timestamp = record['timestamp']
        indent_level = record.get('indent', 0)
        indent = '    ' * indent_level
        
        # Format the message for file
        formatted_msg = f"{timestamp} [{level.name}] {indent}{message}"
            
        # Write to log file
        try:
            log_path = self._get_log_file_path()
            with open(log_path, 'a') as log_file:
                log_file.write(f"{formatted_msg}\n")
                if level == LogLevel.CRITICAL:
                    log_file.flush()  # Force write immediately for critical logs
        except Exception as e:
            if not self.quiet_init:
                print(f"Failed to write to log file: {e}", file=sys.stderr)
    
    def _get_log_file_path(self, date=None):
        """
        Returns the file path where logs should be saved.
        
        Args:
            date (str, optional): A date string in YYYY_MM_DD format. Defaults to today.
            
        Returns:
            str: Full path to the log file for the given date.
            
        The path is built using `build_path()` and follows the pattern:
        ../../../logs/YYYY_MM_DD.log (relative to logger module location)
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
    
    def _write_to_local(self, record: Dict[str, Any]):
        """
        Write a log record to the local file system and stdout.
        
        Args:
            record: Dictionary containing log metadata and message
        """
        level = record['level']
        message = record['message']
        timestamp = record['timestamp']
        indent_level = record.get('indent', 0)
        indent = '    ' * indent_level
        
        # Format the message for display and file
        formatted_msg_stdout = f"{timestamp} {indent}{message}"
        formatted_msg_file = f"{timestamp} [{level.name}] {indent}{message}"
        
        # Always print to console (stderr for errors and critical)
        if level in (LogLevel.ERROR, LogLevel.CRITICAL):
            print(formatted_msg_stdout, file=sys.stderr, flush=True)
        else:
            print(formatted_msg_stdout, flush=True)
            
        # Write to log file
        try:
            log_path = self._get_log_file_path()
            os.makedirs(os.path.dirname(log_path), exist_ok=True)  # Ensure directory exists
            with open(log_path, 'a') as log_file:
                log_file.write(f"{formatted_msg_file}\n")
                if level == LogLevel.CRITICAL:
                    log_file.flush()  # Force write immediately for critical logs
        except Exception as e:
            if not self.quiet_init:
                print(f"Failed to write to log file: {e}", file=sys.stderr)
    
    def _direct_log(self, level: LogLevel, message: str):
        """
        Write a log message directly, bypassing the queue.
        Used for logger internal messages and critical errors.
        
        Args:
            level: Log level
            message: Log message
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Format the message
        formatted_msg = f"{timestamp} [{level.name}] {message}"
        
        # Print to console based on level
        if level in (LogLevel.ERROR, LogLevel.CRITICAL):
            print(formatted_msg, file=sys.stderr, flush=True)
        else:
            print(formatted_msg, flush=True)
            
        # Write to file
        try:
            log_path = self._get_log_file_path()
            os.makedirs(os.path.dirname(log_path), exist_ok=True)  # Ensure directory exists
            with open(log_path, 'a') as log_file:
                log_file.write(f"{formatted_msg}\n")
                log_file.flush()  # Ensure it's written immediately
        except Exception as e:
            # Use print instead of logging to avoid recursion
            if not self.quiet_init:
                print(f"Failed to write direct log to file: {e}", file=sys.stderr)
    
    def enqueue_log(self, 
                   level: LogLevel, 
                   message: str, 
                   indent: int = 0, 
                   truncate: bool = True,
                   context: Dict[str, Any] = None):
        """
        Enqueue a log message for processing by the worker thread.
        
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
            
        # Create the log record
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        record = {
            'timestamp': timestamp,
            'level': level,
            'message': message,
            'indent': indent,
            'service': self.service_name,
            'pid': os.getpid(),
            'thread': threading.get_ident(),
        }
        
        # Add context if provided
        if context:
            record['context'] = context
            
        # For critical logs, process immediately
        if level == LogLevel.CRITICAL:
            # Direct output for critical messages
            formatted_msg = f"{message}"
            print(formatted_msg, file=sys.stderr, flush=True)
            
            # Write to file directly to ensure it's captured
            try:
                log_path = self._get_log_file_path()
                os.makedirs(os.path.dirname(log_path), exist_ok=True)  # Ensure directory exists
                with open(log_path, 'a') as log_file:
                    log_file.write(f"{timestamp} [CRITICAL] {indent * '    '}{message}\n")
                    log_file.flush()
            except Exception as e:
                if not self.quiet_init:
                    print(f"Failed to write critical log to file: {e}", file=sys.stderr)
            
            # Also enqueue for Redis if available
            if self.use_redis and self.redis_pool:
                try:
                    self.queue.put_nowait(record)
                except queue.Full:
                    pass  # Already logged directly, so Redis is just a bonus
            return
            
        # Queue normal logs
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # If queue is full, log a warning but drop this message
            if not self.quiet_init:
                print(f"Log queue full, dropping message: {message[:50]}...", file=sys.stderr)
    
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
            self.enqueue_log(
                LogLevel.INFO,
                f"Log level changed to {self.min_level.name}"
            )
            
    def shutdown(self):
        """
        Gracefully shut down the logger, flushing remaining messages.
        """
        if self._shutdown:
            return
            
        self._shutdown = True
        
        # Log that we're shutting down, but only if not quiet
        if not self.quiet_init:
            print("Logger shutting down, flushing messages...", file=sys.stderr)
        
        # Put sentinel to stop worker thread
        try:
            self.queue.put(None, timeout=1)
        except queue.Full:
            pass
            
        # Wait for queue to drain
        try:
            self.queue.join(timeout=5)
        except Exception:
            pass
            
        # Wait for worker thread to finish
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
            
        # Close Redis connection if active
        if self.use_redis and self.redis_pool:
            try:
                asyncio.run(self.redis_pool.aclose())
            except Exception as e:
                if not self.quiet_init:
                    print(f"Error closing Redis pool: {e}", file=sys.stderr)
                
        if not self.quiet_init:
            print("Logger shutdown complete", file=sys.stderr)


# Public API - Simple functions for common use
def debug(message: str, indent: int = 0, context: Dict[str, Any] = None):
    """
    Log a debug message to stdout only.
    
    Args:
        message: The debug message.
        indent: Optional indentation level.
        context: Additional contextual data
        
    These messages are printed to stdout only and not written to the file.
    """
    # Print directly to stdout first for immediate feedback and test compatibility
    print(f"[DEBUG] {message}")
    
    # Then also log through the async system
    AsyncLogger.get_instance().enqueue_log(
        LogLevel.DEBUG, f"[DEBUG] {message}", indent=indent, context=context
    )

def info(message: str, indent: int = 0, context: Dict[str, Any] = None):
    """Log an info message"""
    # Print directly to stdout first
    print(f"[INFO] {message}")
        
    # Then log through the async system
    AsyncLogger.get_instance().enqueue_log(
        LogLevel.INFO, f"[INFO] {message}", indent=indent, context=context
    )

def warn(message: str, indent: int = 0, context: Dict[str, Any] = None):
    """Log a warning message"""
    # Print directly to stdout first
    print(f"[WARN] {message}")
        
    # Then log through the async system
    AsyncLogger.get_instance().enqueue_log(
        LogLevel.WARN, f"[WARN] {message}", indent=indent, context=context
    )

def error(message: str, indent: int = 0, context: Dict[str, Any] = None):
    """Log an error message"""
    # Print directly to stderr first
    print(f"[ERROR] {message}", file=sys.stderr)
        
    # Then log through the async system
    AsyncLogger.get_instance().enqueue_log(
        LogLevel.ERROR, f"[ERROR] {message}", indent=indent, truncate=False, context=context
    )

def critical(message: str, context: Dict[str, Any] = None):
    """
    Log a critical message - processed immediately, guaranteed to be written
    """
    # Print directly to stdout with format matching the original logger for test compatibility
    print(f"[CRITICAL] {message}")
        
    # Then log through the async system (keeping the CRITICAL: prefix for the async logs)
    AsyncLogger.get_instance().enqueue_log(
        LogLevel.CRITICAL, f"[CRITICAL] {message}", truncate=False, context=context
    )

def profile(message: str, indent: int = 0):
    """
    Log a profiling message to stdout only.
    
    Args:
        message: The profiling detail.
        indent: Optional indentation level.
        
    Like debug(), this avoids file I/O and is helpful for inline performance traces.
    """
    # Print directly to stdout first
    print(f"[PROFILER] {message}")
        
    # Then log through the async system
    AsyncLogger.get_instance().enqueue_log(
        LogLevel.DEBUG, f"[PROFILER] {message}", indent=indent
    )

def set_log_level(level: Union[LogLevel, str]):
    """Change the minimum log level"""
    AsyncLogger.get_instance().set_log_level(level)

def shutdown():
    """Shutdown the logger, flushing all queued messages"""
    if AsyncLogger._instance is not None:
        AsyncLogger._instance.shutdown()

def get_log_file():
    """
    Returns the file path where current logs are being saved.
    
    This function exists for compatibility with the original logging module.
    
    Returns:
        str: Full path to the current log file
    """
    return AsyncLogger.get_instance()._get_log_file_path()


# Example ARQ worker configuration for handling log messages
# This would be in a separate worker process/service
'''
async def log_message(ctx, *, log_record):
    """
    ARQ worker function to process logs sent via Redis.
    
    This would typically write to Elasticsearch, a central file, 
    or other monitoring system.
    
    Args:
        ctx: ARQ context
        log_record: The log record dictionary
    """
    # Example: Convert to JSON format for storage
    log_json = json.dumps(log_record)
    
    # Here you would implement your centralized logging logic
    # For example:
    # - Write to Elasticsearch
    # - Send to a log aggregation service
    # - Store in a database
    # - Forward to monitoring systems
    
    # Example pseudo-code for Elasticsearch:
    # await es_client.index(
    #     index=f"logs-{datetime.now().strftime('%Y.%m.%d')}",
    #     body=log_record
    # )
    
    return True  # Return success
'''

# Example configuration file (config.json)
'''
{
  "logging": {
    "use_redis": true,
    "redis_url": "redis://localhost:6379/0",
    "min_level": "DEBUG",
    "service_name": "auth-service",
    "log_debug_to_file": true,
    "quiet_init": true
  }
}
'''