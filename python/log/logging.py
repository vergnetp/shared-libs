# Fixed Logging System (python/log/logging.py)
# Focus on improving thread safety, buffer handling, and error recovery

import queue
import threading
import traceback
import asyncio
import os
import sys
import json
import pathlib
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Union, List
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
DEFAULT_FLUSH_INTERVAL = 5  # seconds
DEFAULT_RETRY_INTERVAL = 30  # seconds
DEFAULT_RETRY_COUNT = 3
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
                 flush_interval: int = DEFAULT_FLUSH_INTERVAL,
                 retry_interval: int = DEFAULT_RETRY_INTERVAL,
                 retry_count: int = DEFAULT_RETRY_COUNT,
                 quiet_init: bool = False):
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
            retry_interval: How long to wait between Redis reconnection attempts
            retry_count: How many times to retry Redis connection
            quiet_init: If True, suppresses printing the initialization message
        """
        # Core settings
        self.queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self.worker_thread = threading.Thread(
            target=self._process_queue,
            daemon=True,
            name="AsyncLoggerWorker"
        )
        self.use_redis = use_redis and REDIS_AVAILABLE
        self.log_dir = log_dir  # Can be None to use default path
        self.service_name = service_name or f"service-{os.getpid()}"
        self.log_debug_to_file = log_debug_to_file
        self.quiet_init = quiet_init  # Store quiet_init setting
        self.flush_interval = flush_interval
        self.retry_interval = retry_interval
        self.retry_count = retry_count
        
        # Thread synchronization
        self._queue_lock = threading.RLock()
        self._redis_lock = threading.RLock()
        self._file_lock = threading.RLock()
        
        # Set minimum log level
        if isinstance(min_level, str):
            self.min_level = LogLevel.from_string(min_level)
        else:
            self.min_level = min_level
        
        # Redis settings
        self.redis_url = redis_url
        self.redis_pool: Optional[ArqRedis] = None
        self._redis_healthy = False
        self._last_redis_attempt = 0
        
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
        self._last_flush_time = time.time()
        
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
    
    async def _init_redis(self):
        """
        Initialize Redis connection pool with retry logic
        """
        if not REDIS_AVAILABLE:
            if not self.quiet_init:
                self._direct_log(LogLevel.ERROR, "Required Redis libraries not available")
            return
            
        with self._redis_lock:
            self._last_redis_attempt = time.time()
            
            for attempt in range(self.retry_count):
                try:
                    if self.redis_url:
                        self.redis_pool = await create_pool(self.redis_url)
                    else:
                        self.redis_pool = await create_pool()
                        
                    # Test the connection
                    ping_result = await self.redis_pool.ping()
                    if not ping_result:
                        raise Exception("Redis ping failed")
                        
                    self._redis_healthy = True
                    if not self.quiet_init:
                        self._direct_log(LogLevel.INFO, f"Redis connection established (attempt {attempt+1})")
                    return
                except Exception as e:
                    if not self.quiet_init:
                        self._direct_log(
                            LogLevel.WARN, 
                            f"Redis connection attempt {attempt+1} failed: {e}"
                        )
                    if self.redis_pool:
                        try:
                            self.redis_pool.close()
                            await self.redis_pool.wait_closed()
                        except Exception:
                            pass
                        self.redis_pool = None
                    
                    if attempt < self.retry_count - 1:
                        await asyncio.sleep(self.retry_interval / (attempt + 1))
            
            # All retries failed
            self._redis_healthy = False
            self.use_redis = False  # Disable Redis for now
            if not self.quiet_init:
                self._direct_log(
                    LogLevel.ERROR, 
                    f"Failed to initialize Redis after {self.retry_count} attempts. Falling back to local logging."
                )
    
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
            "quiet_init": False,  # Default to showing init message
            "flush_interval": DEFAULT_FLUSH_INTERVAL,
            "retry_interval": DEFAULT_RETRY_INTERVAL,
            "retry_count": DEFAULT_RETRY_COUNT,
        }
        
        # Try to load from config file if it exists
        config_paths = [
            os.getenv("CONFIG_FILE"),
            "config.yml",
            "config.yaml",
            "config.json",
            os.path.join(utils.get_config_folder(), "logging.yml"),
            os.path.join(utils.get_config_folder(), "logging.yaml"),
            os.path.join(utils.get_config_folder(), "logging.json"),
        ]
        
        for config_file in [p for p in config_paths if p]:
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r') as f:
                        if config_file.endswith(('.yml', '.yaml')) and YAML_AVAILABLE:
                            file_config = yaml.safe_load(f)
                        else:
                            file_config = json.load(f)
                            
                        if file_config:
                            # Look for logging section or use whole file
                            if "logging" in file_config:
                                config.update(file_config["logging"])
                            else:
                                config.update(file_config)
                        break  # Use first valid config file found
                except Exception as e:
                    print(f"Error loading config file {config_file}: {e}", file=sys.stderr)
        
        # Environment variables override config file
        env_mappings = {
            "LOG_DIR": "log_dir",
            "LOGGING_USE_REDIS": "use_redis",
            "LOG_LEVEL": "min_level",
            "REDIS_URL": "redis_url",
            "SERVICE_NAME": "service_name",
            "LOG_DEBUG_TO_FILE": "log_debug_to_file",
            "QUIET_LOGGER_INIT": "quiet_init",
            "LOG_FLUSH_INTERVAL": "flush_interval",
            "REDIS_RETRY_INTERVAL": "retry_interval",
            "REDIS_RETRY_COUNT": "retry_count"
        }
        
        for env_var, config_key in env_mappings.items():
            if os.getenv(env_var):
                if config_key in ("use_redis", "log_debug_to_file", "quiet_init"):
                    config[config_key] = os.getenv(env_var).lower() in ("true", "1", "yes", "y")
                elif config_key in ("flush_interval", "retry_interval", "retry_count"):
                    try:
                        config[config_key] = int(os.getenv(env_var))
                    except ValueError:
                        # Keep default if can't convert to int
                        pass
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
                    if 'pytest' in sys.modules or os.getenv('PYTEST_CURRENT_TEST'):
                        kwargs.setdefault('quiet_init', True)
                    
                    # Load config from file and environment
                    config = cls._load_config()
                    
                    # kwargs override config
                    config.update(kwargs)
                    
                    cls._instance = AsyncLogger(**config)
        return cls._instance
    
    def _check_redis_retry(self):
        """Check if we should retry Redis connection"""
        if not self.use_redis or self._redis_healthy:
            return False
            
        now = time.time()
        if now - self._last_redis_attempt > self.retry_interval:
            return True
        return False
        
    def _process_queue(self):
        """Worker thread that processes the log queue"""
        batch = []
        last_flush = time.time()
        
        while not self._shutdown:
            try:
                # Check if we need to retry Redis connection
                if self._check_redis_retry():
                    asyncio.run(self._init_redis())
                
                # Try to get a message with timeout
                try:
                    record = self.queue.get(timeout=0.1)
                    if record is None:  # Sentinel for shutdown
                        break
                        
                    # Process record
                    batch.append(record)
                    self.queue.task_done()
                except queue.Empty:
                    # No messages, check if we need to flush batch
                    pass
                    
                # Check if we should flush due to batch size or time
                now = time.time()
                if (len(batch) >= 20 or  # Flush on batch size
                    (batch and now - last_flush >= self.flush_interval)):  # Flush on interval
                    self._flush_batch(batch)
                    batch = []
                    last_flush = now
                    
            except Exception:
                # Log the exception but keep the thread running
                traceback_msg = traceback.format_exc()
                # Use print instead of logging to avoid potential recursion
                if not self.quiet_init:
                    print(f"Logger thread error: {traceback_msg}", file=sys.stderr)
                
                # Sleep briefly to avoid tight error loop
                time.sleep(0.5)
                
        # Final flush of remaining messages on shutdown
        if batch:
            self._flush_batch(batch)
    
    def _flush_batch(self, batch: List[Dict[str, Any]]):
        """
        Process a batch of log records
        
        Args:
            batch: List of log records to process
        """
        if not batch:
            return
            
        # Copy batch to prevent race conditions
        batch_copy = batch.copy()
        
        # Run async flush for Redis
        if self.use_redis and self._redis_healthy and self.redis_pool:
            try:
                asyncio.run(self._flush_batch_redis(batch_copy))
            except Exception as e:
                # Redis failed, fall back to local logging
                if not self.quiet_init:
                    print(f"Redis batch flush failed: {e}, falling back to local", file=sys.stderr)
                self._flush_batch_local(batch_copy)
        else:
            # Use local logging
            self._flush_batch_local(batch_copy)
    
    async def _flush_batch_redis(self, batch: List[Dict[str, Any]]):
        """
        Flush batch of records to Redis
        
        Args:
            batch: List of log records to process
        """
        if not self.redis_pool:
            raise Exception("Redis pool not initialized")
            
        with self._redis_lock:
            # Group critical records for local backup
            critical_records = [record for record in batch if record['level'] == LogLevel.CRITICAL]
            
            # Convert LogLevel enum to string for serialization
            redis_batch = []
            for record in batch:
                record_copy = record.copy()
                record_copy['level'] = record_copy['level'].name
                redis_batch.append(record_copy)
                
            # Enqueue batch job to Redis
            await self.redis_pool.enqueue_job(
                "log_batch",  # Worker needs to handle batched logs
                log_records=redis_batch
            )
            
            # For critical logs, ensure we have local backup too
            if critical_records:
                self._flush_batch_local(critical_records)
    
    def _flush_batch_local(self, batch: List[Dict[str, Any]]):
        """
        Flush batch of records to local storage
        
        Args:
            batch: List of log records to process
        """
        # Group by log level for processing
        debug_records = []
        file_records = []
        
        for record in batch:
            level = record['level']
            
            # Skip logs below minimum level
            if level.value < self.min_level.value:
                continue
                
            # For debug messages, handle according to configuration
            if level == LogLevel.DEBUG:
                debug_records.append(record)
                if self.log_debug_to_file:
                    file_records.append(record)
            else:
                # Write other levels to both stdout and file
                file_records.append(record)
                self._write_record_to_stdout(record)
                
        # Process debug records (stdout only by default)
        for record in debug_records:
            self._write_record_to_stdout(record)
            
        # Write file records in a single batch with lock
        if file_records:
            self._write_records_to_file(file_records)
    
    def _write_record_to_stdout(self, record: Dict[str, Any]):
        """
        Write a log record to stdout.
        
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
        
        # Print to console (stderr for errors and critical)
        if level in (LogLevel.ERROR, LogLevel.CRITICAL):
            print(formatted_msg, file=sys.stderr, flush=True)
        else:
            print(formatted_msg, flush=True)
    
    def _write_records_to_file(self, records: List[Dict[str, Any]]):
        """
        Write multiple log records to file with a single lock.
        
        Args:
            records: List of log records to write
        """
        if not records:
            return
            
        # Group records by date
        record_groups = {}
        for record in records:
            timestamp = record['timestamp']
            date_str = timestamp.split()[0].replace('-', '_')
            if date_str not in record_groups:
                record_groups[date_str] = []
            record_groups[date_str].append(record)
            
        # Write each group to its date file
        with self._file_lock:
            for date_str, group in record_groups.items():
                log_path = self._get_log_file_path(date_str)
                
                # Ensure directory exists
                try:
                    os.makedirs(os.path.dirname(log_path), exist_ok=True)
                except Exception as e:
                    if not self.quiet_init:
                        print(f"Failed to create log directory for {log_path}: {e}", file=sys.stderr)
                    continue
                    
                # Format all records for this date
                lines = []
                for record in group:
                    level = record['level']
                    message = record['message']
                    timestamp = record['timestamp']
                    indent_level = record.get('indent', 0)
                    indent = '    ' * indent_level
                    
                    formatted_msg = f"{timestamp} [{level.name}] {indent}{message}"
                    lines.append(formatted_msg + "\n")
                    
                # Write all lines to file
                try:
                    # First check if file is writable
                    if os.path.exists(log_path):
                        if not os.access(log_path, os.W_OK):
                            raise PermissionError(f"No write permission for {log_path}")
                            
                    with open(log_path, 'a') as log_file:
                        log_file.writelines(lines)
                        if any(r['level'] == LogLevel.CRITICAL for r in group):
                            log_file.flush()  # Force write immediately for critical logs
                except Exception as e:
                    if not self.quiet_init:
                        print(f"Failed to write to log file {log_path}: {e}", file=sys.stderr)
                        
                        # Try fallback to user home directory
                        try:
                            fallback_path = os.path.join(
                                os.path.expanduser('~'), 
                                '.logs', 
                                f"{date_str}.log"
                            )
                            os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
                            with open(fallback_path, 'a') as fallback_file:
                                fallback_file.writelines(lines)
                        except Exception as fallback_error:
                            print(f"Failed to write to fallback log file: {fallback_error}", file=sys.stderr)
    
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
            with self._file_lock:
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
        from ..framework.context import request_id_var
        request_id = request_id_var.get()
        if request_id:
            record['request_id'] = request_id
        # Add context if provided
        if context:
            record['context'] = context

        # Queue for processing (even critical logs go to queue for Redis if enabled)
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # If queue is full, log a warning but drop this message
            if not self.quiet_init:
                print(f"Log queue full ({self.queue.qsize()}/{MAX_QUEUE_SIZE}), dropping message: {message[:50]}...", file=sys.stderr)
    
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
def _log(level: LogLevel, prefix: str, message: str, indent: int = 0, context: Dict[str, Any] = None, force_flush: bool = False):
    """
    Internal helper to log a message.

    Args:
        level: LogLevel enum
        prefix: String prefix like [DEBUG], [INFO], etc.
        message: The actual message
        indent: Indentation level
        context: Additional contextual data
        force_flush: If True, immediately flush critical logs to file
    """
    from ..framework.context import request_id_var
    request_id = request_id_var.get()
    if request_id:
        print(f"{prefix} [request_id={request_id}] {message}")
    else: 
        print(f"{prefix} {message}")

    logger = AsyncLogger.get_instance()
    logger.enqueue_log(level, f"{prefix} {message}", indent=indent, context=context)

    if force_flush and level == LogLevel.CRITICAL:
        # Force immediate flush to file
        try:
            log_path = logger._get_log_file_path()
            with logger._file_lock:
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                indent_space = '    ' * indent
                with open(log_path, 'a') as log_file:
                    log_file.write(f"{timestamp} [{level.name}] {indent_space}{message}\n")
                    log_file.flush()
        except Exception as e:
            if not logger.quiet_init:
                print(f"Failed to force-flush critical log: {e}", file=sys.stderr)

def debug(message: str, indent: int = 0, context: Dict[str, Any] = None):
    _log(LogLevel.DEBUG, "[DEBUG]", message, indent, context)

def info(message: str, indent: int = 0, context: Dict[str, Any] = None):
    _log(LogLevel.INFO, "[INFO]", message, indent, context)

def warning(message: str, indent: int = 0, context: Dict[str, Any] = None):
    _log(LogLevel.WARN, "[WARN]", message, indent, context)

def error(message: str, indent: int = 0, context: Dict[str, Any] = None):
    _log(LogLevel.ERROR, "[ERROR]", message, indent, context)

def critical(message: str, context: Dict[str, Any] = None):
    _log(LogLevel.CRITICAL, "[CRITICAL]", message, indent=0, context=context, force_flush=True)

def profile(message: str, indent: int = 0, context: Dict[str, Any] = None):
    _log(LogLevel.DEBUG, "[PROFILER]", message, indent, context)

def get_log_file():
    """
    Returns the file path where logs should be saved.
    
    Args:
        date (str, optional): A date string in YYYY_MM_DD format. Defaults to today.
        
    Returns:
        str: Full path to the log file for the given date.
    """
    logger = AsyncLogger.get_instance()
    return logger._get_log_file_path()
