import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List, Union, Type

from ..queue import QueueConfig, QueueManager, QueueWorker, QueueRetryConfig
from .log_storage import LogStorageInterface
from .opensearch_storage import OpenSearchLogStorage

# Simple logger for our queue system
class SimpleLogger:
    @staticmethod
    def error(msg): print(f"ERROR: {msg}")
    @staticmethod
    def warning(msg): print(f"WARNING: {msg}")
    @staticmethod
    def debug(msg): print(f"DEBUG: {msg}")
    @staticmethod
    def info(msg): print(f"INFO: {msg}")
    @staticmethod
    def critical(msg): print(f"CRITICAL: {msg}")

# This processor handles a single log record
def process_log_record(log_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single log record.
    
    Args:
        log_record: The log record to process
        
    Returns:
        Dict with processing status
    """
    # Get the storage backend instance
    storage = get_storage_instance()
    
    # Store the log
    result = storage.store_log(log_record)
    return result

# This processor handles a batch of log records
def process_log_batch(log_batch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a batch of log records.
    
    Args:
        log_batch: Dictionary containing a 'log_records' key with a list of log records
        
    Returns:
        Dict with processing status
    """
    log_records = log_batch.get('log_records', [])
    if not log_records:
        return {"status": "empty", "count": 0}
    
    # Get the storage backend instance
    storage = get_storage_instance()
    
    # Store the batch
    result = storage.store_batch(log_records)
    return result

# Singleton storage instance
_storage_instance = None

def initialize_storage(storage_class: Type[LogStorageInterface] = OpenSearchLogStorage, **storage_config) -> LogStorageInterface:
    """
    Initialize and set the log storage backend.
    
    Args:
        storage_class: LogStorageInterface implementation class
        **storage_config: Configuration parameters for the storage class
        
    Returns:
        The configured storage instance
    """
    global _storage_instance
    _storage_instance = storage_class(**storage_config)
    return _storage_instance

def get_storage_instance() -> LogStorageInterface:
    """
    Get the current log storage instance.
    
    Returns:
        The configured storage instance, or OpenSearchLogStorage with defaults if not initialized
    """
    global _storage_instance
    if _storage_instance is None:
        # Create a default OpenSearch instance if none exists
        _storage_instance = OpenSearchLogStorage()
    return _storage_instance

# For tracking our queue components
_queue_config = None
_queue_manager = None
_queue_worker = None

def initialize_log_processing(redis_url: Optional[str] = None, 
                              storage_class: Type[LogStorageInterface] = OpenSearchLogStorage,
                              storage_config: Optional[Dict[str, Any]] = None,
                              worker_count: int = 3,
                              work_timeout: float = 30.0) -> Dict[str, Any]:
    """
    Initialize the log processing system with specified configuration.
    
    Args:
        redis_url: Redis connection URL
        storage_class: Class for log storage
        storage_config: Configuration for storage backend
        worker_count: Number of worker tasks to use
        work_timeout: Timeout for each worker task in seconds
        
    Returns:
        Dictionary with initialized components
    """
    global _queue_config, _queue_manager, _queue_worker, _storage_instance
    
    # Initialize storage backend
    if storage_config is None:
        storage_config = {}
    _storage_instance = storage_class(**storage_config)
    
    # Initialize QueueConfig
    _queue_config = QueueConfig(
        redis_url=redis_url,
        queue_prefix="log:",
        logger=SimpleLogger()
    )
    
    # Create QueueManager for job submission
    _queue_manager = QueueManager(config=_queue_config)
    
    # Register processor functions
    _queue_config.operations_registry["log_message"] = process_log_record
    _queue_config.operations_registry["log_batch"] = process_log_batch
    
    # Create QueueWorker for processing
    _queue_worker = QueueWorker(
        config=_queue_config,
        max_workers=worker_count,
        work_timeout=work_timeout
    )
    
    print(f"Log processing system initialized with {storage_class.__name__}")
    
    return {
        "config": _queue_config,
        "manager": _queue_manager,
        "worker": _queue_worker,
        "storage": _storage_instance
    }

def get_queue_manager() -> QueueManager:
    """
    Get the initialized queue manager or initialize with defaults if needed.
    
    Returns:
        QueueManager instance
    """
    global _queue_manager
    if _queue_manager is None:
        initialize_log_processing()
    return _queue_manager

def get_queue_worker() -> QueueWorker:
    """
    Get the initialized queue worker or initialize with defaults if needed.
    
    Returns:
        QueueWorker instance
    """
    global _queue_worker
    if _queue_worker is None:
        initialize_log_processing()
    return _queue_worker

# Functions to submit logs to the system - can be used by external code
async def submit_log(log_record: Dict[str, Any], priority: str = "normal") -> Dict[str, Any]:
    """
    Submit a single log record to the processing system.
    
    Args:
        log_record: Log record to process
        priority: Queue priority ("high", "normal", "low")
    
    Returns:
        Result from the enqueue operation
    """
    manager = get_queue_manager()
    
    # Configure retry settings
    retry_config = QueueRetryConfig(max_attempts=3, delays=[1, 5, 10])
    
    # Submit to queue
    result = await manager.enqueue(
        entity=log_record,
        processor="log_message",
        priority=priority,
        retry_config=retry_config
    )
    
    return result

async def submit_log_batch(log_records: List[Dict[str, Any]], priority: str = "normal") -> Dict[str, Any]:
    """
    Submit a batch of log records to the processing system.
    
    Args:
        log_records: List of log records to process
        priority: Queue priority ("high", "normal", "low")
    
    Returns:
        Result from the enqueue operation
    """
    manager = get_queue_manager()
    
    # Configure retry settings
    retry_config = QueueRetryConfig(max_attempts=3, delays=[1, 5, 10])
    
    # Submit to queue
    result = await manager.enqueue(
        entity={"log_records": log_records},
        processor="log_batch",
        priority=priority,
        retry_config=retry_config
    )
    
    return result

async def start_worker() -> QueueWorker:
    """
    Start the log processing worker.
    
    Returns:
        The running QueueWorker instance
    """
    worker = get_queue_worker()
    await worker.start()
    print("Log processing worker started")
    return worker

async def stop_worker():
    """
    Stop the log processing worker if running.
    """
    global _queue_worker
    if _queue_worker:
        await _queue_worker.stop()
        print("Log processing worker stopped")

# Main function to run the worker independently 
async def run_worker():
    """
    Run a standalone log processing worker.
    
    This creates and runs a QueueWorker that will process
    queued log messages from Redis.
    """
    # Start the worker
    worker = await start_worker()
    
    try:
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down worker...")
    finally:
        # Shut down worker gracefully
        await stop_worker()
        print("Worker shutdown complete")

# Entry point for standalone execution
if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("\nWorker stopped by user")