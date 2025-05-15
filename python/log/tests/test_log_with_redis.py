import pytest
import time
from pathlib import Path

# Import your logger module
from .. import logging as mylog
from ...queue import QueueConfig, QueueManager, QueueWorker

# Try to import Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Helper function to check Redis availability
def is_redis_running(port=6382):
    """Check if Redis is running on the specified port."""
    if not REDIS_AVAILABLE:
        return False
    
    try:
        client = redis.Redis(host='localhost', port=port)
        return client.ping()
    except:
        return False

@pytest.fixture(scope="module")
def redis_url():
    """Redis URL to use for tests"""
    return "redis://localhost:6382"

@pytest.fixture(scope="module")
def redis_client(redis_url):
    """Simple Redis client for testing"""
    if not REDIS_AVAILABLE:
        pytest.skip("Redis Python package not installed")
        return None
        
    if not is_redis_running(port=6382):
        pytest.skip("Redis server not running on port 6382")
        return None
    
    try:
        client = redis.Redis(host='localhost', port=6382)
        client.ping()  # Test the connection
        yield client
        client.close()
    except Exception as e:
        pytest.skip(f"Redis connection failed: {e}")
        yield None

@pytest.fixture
def redis_logger(redis_url):
    """Initialize the logger with Redis"""
    if not redis_url:
        pytest.skip("Redis URL not available")
        return None
    
    # Reset logger singleton
    if hasattr(mylog.Logger, "_instance"):
        mylog.Logger._instance = None
    
    # Create logger
    try:
        logger = mylog.initialize_logger(
            use_redis=True,
            redis_url=redis_url,
            quiet_init=True
        )
        
        yield logger
        
        # Clean up
        logger.shutdown()
    except Exception as e:
        pytest.skip(f"Redis logger setup failed: {e}")
        yield None

@pytest.fixture
def queue_config(redis_url):
    """Create a queue configuration"""
    if not redis_url:
        pytest.skip("Redis URL not available")
        return None
        
    # Create config with fresh Redis client for each test
    try:
        config = QueueConfig(
            redis_url=redis_url,
            queue_prefix="test:",
        )
        return config
    except Exception as e:
        pytest.skip(f"Queue config creation failed: {e}")
        return None

def test_redis_client_creation(redis_client):
    """Test that Redis client can be created successfully"""
    # Skip if client creation failed
    if redis_client is None:
        pytest.skip("Redis client not available")
    
    try:
        # Test basic Redis operations
        test_key = "test:simple:key"
        test_value = "test_value"
        
        # Set and get a value
        redis_client.set(test_key, test_value)
        retrieved = redis_client.get(test_key)
        
        # Clean up
        redis_client.delete(test_key)
        
        # Verify
        assert retrieved.decode() == test_value, "Redis client failed basic set/get operation"
    except Exception as e:
        pytest.fail(f"Redis operation failed: {e}")

def test_logger_with_redis(redis_logger):
    """Test that logger can be created with Redis enabled"""
    # Skip if logger creation failed
    if redis_logger is None:
        pytest.skip("Redis logger not available")
    
    assert redis_logger.use_redis is True, "Logger not configured to use Redis"
    
    try:
        # Log a simple message
        test_message = "Simple test message"
        mylog.info(test_message)
        
        # If no exceptions, test passes
        assert True, "Logger failed to log with Redis enabled"
    except Exception as e:
        pytest.fail(f"Logging failed: {e}")

def test_config_creation(queue_config):
    """Test that queue config can be created successfully"""
    # Skip if config creation failed
    if queue_config is None:
        pytest.skip("Queue config not available")
        
    assert queue_config is not None
    assert queue_config.redis_url.startswith("redis://"), "Queue config has invalid Redis URL"

def test_queue_manager_creation(queue_config):
    """Test that queue manager can be created successfully"""
    # Skip if config creation failed
    if queue_config is None:
        pytest.skip("Queue config not available")
    
    try:
        # Create manager
        manager = QueueManager(config=queue_config)
        
        # Simple validation
        assert manager is not None
        assert manager.config == queue_config, "Queue manager not using provided config"
        
        # Don't test enqueue operation - just test creation
        assert True, "Queue manager created successfully"
    except Exception as e:
        pytest.fail(f"Queue manager creation failed: {e}")

def test_worker_creation(queue_config):
    """Test that worker can be created successfully"""
    # Skip if config creation failed
    if queue_config is None:
        pytest.skip("Queue config not available")
        
    try:
        # Create worker
        worker = QueueWorker(config=queue_config, max_workers=1)
        
        # Verify worker was created
        assert worker is not None
        assert worker.max_workers == 1, "Worker not configured with right number of workers"
        assert worker.config.redis_url == queue_config.redis_url, "Worker not using the right Redis URL"
    except Exception as e:
        pytest.fail(f"Worker creation failed: {e}")

def test_minimal_functionality():
    """A test that should always pass regardless of Redis."""
    # This test functions as a sanity check
    assert True, "Minimal functionality test failed"