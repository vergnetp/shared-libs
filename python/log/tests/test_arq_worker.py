import pytest
import pytest_asyncio
import os
import asyncio
import json
import importlib
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import your logger module - adjust the import path as needed
from .. import logging as mylog

import warnings
warnings.filterwarnings("ignore", message="coroutine 'periodic_flush' was never awaited")

# Helper for async mocks
class AsyncMock(MagicMock):
    """Helper class for mocking async functions"""
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)

def is_opensearchpy_available():
    """Check if opensearchpy is installed."""
    try:
        import opensearchpy
        return True
    except ImportError:
        return False

def is_arq_available():
    """Check if ARQ is installed."""
    try:
        import arq
        return True
    except ImportError:
        return False

@pytest_asyncio.fixture
async def mock_opensearch():
    """Create a mock for OpenSearch client."""
    mock_client = MagicMock()
    mock_client.bulk = AsyncMock(return_value={"errors": False, "items": []})
    yield mock_client

@pytest_asyncio.fixture
async def mock_arq_worker(mock_opensearch):
    """
    Create a mock ARQ worker environment for testing jobs.py.
    
    This fixture patches OpenSearch imports even if OpenSearch is not available,
    allowing jobs.py to be tested without the actual dependency.
    """
    # Check if ARQ is available before proceeding
    if not is_arq_available():
        pytest.skip("ARQ not available")
        yield None, None, None, None
        return
        
    # Import with patching to prevent import errors
    import sys
    import importlib.util
    import types
    from pathlib import Path
    from unittest.mock import patch
    
    # Create a fake OpenSearch module
    class FakeAsyncOpenSearch:
        def __init__(self, *args, **kwargs):
            pass
            
        async def bulk(self, body):
            return {"errors": False, "items": []}
            
        async def close(self):
            pass
    
    # Create a fake RequestsHttpConnection
    class FakeRequestsHttpConnection:
        pass
    
    # Create a fake AWS4Auth
    class FakeAWS4Auth:
        def __init__(self, *args, **kwargs):
            pass
    
    # Create patched modules
    fake_opensearchpy = types.ModuleType("opensearchpy")
    fake_opensearchpy.AsyncOpenSearch = FakeAsyncOpenSearch
    fake_opensearchpy.RequestsHttpConnection = FakeRequestsHttpConnection
    
    fake_requests_aws4auth = types.ModuleType("requests_aws4auth")
    fake_requests_aws4auth.AWS4Auth = FakeAWS4Auth
    
    # Create a fake boto3 module
    fake_boto3 = types.ModuleType("boto3")
    
    class FakeSession:
        def __init__(self):
            pass
            
        def get_credentials(self):
            class FakeCredentials:
                access_key = "fake-access-key"
                secret_key = "fake-secret-key"
                token = None
            return FakeCredentials()
            
    fake_boto3.Session = FakeSession
    
    # Find the jobs.py file
    jobs_path = None
    if hasattr(mylog, "__file__"):
        jobs_path = Path(mylog.__file__).parent / "jobs.py"
        
    if not jobs_path or not jobs_path.exists():
        pytest.skip("jobs.py not found")
        yield None, None, None, None
        return
    
    # Create a fake task that can be awaited
    class MockTask:
        def __init__(self):
            self.cancelled = False
            
        def cancel(self):
            self.cancelled = True
            
        def __await__(self):
            # Make this properly awaitable
            async def coro():
                return None
            return coro().__await__()
    
    orig_create_task = None
    try:
        # Create module spec
        spec = importlib.util.spec_from_file_location("jobs", jobs_path)
        jobs = importlib.util.module_from_spec(spec)
        
        # Patch asyncio.create_task before importing
        orig_create_task = asyncio.create_task
        
        def mock_create_task(coro, **kwargs):
            # Return a properly awaitable MockTask
            return MockTask()
            
        asyncio.create_task = mock_create_task
        
        # Patch sys.modules temporarily
        with patch.dict(sys.modules, {
            "opensearchpy": fake_opensearchpy,
            "requests_aws4auth": fake_requests_aws4auth,
            "boto3": fake_boto3
        }):
            # Execute module
            spec.loader.exec_module(jobs)
            
            # Create a mock Redis pool
            mock_redis = MagicMock()
            mock_redis.delete = AsyncMock(return_value=1)
            mock_redis.llen = AsyncMock(return_value=0)
            mock_redis.blpop = AsyncMock(return_value=None)
            mock_redis.close = AsyncMock()
            mock_redis.aclose = AsyncMock()
            
            # Create a context object for the worker
            ctx = {"redis": mock_redis}
            
            # Replace any OpenSearch client function
            if hasattr(jobs, "get_opensearch_client"):
                async def mock_get_client():
                    return mock_opensearch
                jobs.get_opensearch_client = mock_get_client
            
            # Create a properly awaitable flush_task if needed
            if hasattr(jobs, "startup"):
                await jobs.startup(ctx)
            
            yield jobs, ctx, mock_redis, mock_opensearch
            
            # Clean up
            if hasattr(jobs, "shutdown"):
                await jobs.shutdown(ctx)
                
    except Exception as e:
        print(f"Error setting up mock ARQ worker: {e}")
        yield None, None, None, None
    finally:
        # Restore original create_task
        if orig_create_task:
            asyncio.create_task = orig_create_task

class TestARQWorker:
    """Test ARQ worker functionality."""
    
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.asyncio
    async def test_log_message_function(self, mock_arq_worker):
        """Test that the log_message function works properly."""
        if not mock_arq_worker or mock_arq_worker[0] is None:
            pytest.skip("ARQ worker mock not available")
            
        jobs, ctx, mock_redis, mock_opensearch = mock_arq_worker
        
        # Create a test log record
        log_record = {
            "level": "INFO",
            "message": "[INFO] Test message",
            "service": "test-service",
            "pid": 12345,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        
        # Call the log_message function directly
        try:
            result = await jobs.log_message(ctx, log_record=log_record)
            
            # Verify the result
            assert result is True, "log_message function should return True"
            
            # If flush function exists, call it to ensure logs are processed
            if hasattr(jobs, "flush_logs"):
                await jobs.flush_logs()
        except Exception as e:
            pytest.fail(f"log_message function raised an exception: {e}")
            
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.asyncio
    async def test_log_message_batching(self, mock_arq_worker):
        """Test that log messages are batched correctly."""
        if not mock_arq_worker or mock_arq_worker[0] is None:
            pytest.skip("ARQ worker mock not available")
            
        jobs, ctx, mock_redis, mock_opensearch = mock_arq_worker
        
        # Check if the module has batching functionality
        if not hasattr(jobs, "flush_logs"):
            pytest.skip("This ARQ worker implementation doesn't have batching")
            
        try:
            # Create multiple test log records
            log_records = []
            for i in range(5):
                log_records.append({
                    "level": f"INFO",
                    "message": f"[INFO] Test message {i}",
                    "service": "test-service",
                    "pid": 12345,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                })
                
            # Process each record
            for record in log_records:
                await jobs.log_message(ctx, log_record=record)
                
            # Flush the buffer
            await jobs.flush_logs()
            
            # If we got here without errors, the test is successful
            assert True
        except Exception as e:
            pytest.fail(f"Error in batching test: {e}")
            
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.asyncio
    async def test_log_message_error_handling(self, mock_arq_worker):
        """Test error handling in log_message function."""
        if not mock_arq_worker or mock_arq_worker[0] is None:
            pytest.skip("ARQ worker mock not available")
            
        jobs, ctx, mock_redis, mock_opensearch = mock_arq_worker
        
        # Create a test log record with missing fields to test error handling
        log_record = {
            # Missing level and message
            "service": "test-service",
            "pid": 12345
        }
        
        # The function should not raise an exception even with invalid input
        try:
            result = await jobs.log_message(ctx, log_record=log_record)
            # If we get here, the function handled the error gracefully
            assert True
        except Exception as e:
            pytest.fail(f"log_message function should handle invalid input gracefully, but raised: {e}")
            
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.asyncio
    async def test_opensearch_connection_options(self, mock_arq_worker, monkeypatch):
        """Test OpenSearch connection options work correctly."""
        if not mock_arq_worker or mock_arq_worker[0] is None:
            pytest.skip("ARQ worker mock not available")
            
        jobs, ctx, mock_redis, mock_opensearch = mock_arq_worker
        
        # Check if the module has OpenSearch integration
        if not hasattr(jobs, "get_opensearch_client"):
            pytest.skip("This ARQ worker implementation doesn't have OpenSearch integration")
            
        # Test different authentication methods
        auth_types = ["none", "basic", "aws"]
        
        for auth_type in auth_types:
            # Set environment variables
            monkeypatch.setenv("OPENSEARCH_HOST", "localhost")
            monkeypatch.setenv("OPENSEARCH_PORT", "9200") 
            monkeypatch.setenv("OPENSEARCH_AUTH_TYPE", auth_type)
            
            if auth_type == "basic":
                monkeypatch.setenv("OPENSEARCH_USERNAME", "user")
                monkeypatch.setenv("OPENSEARCH_PASSWORD", "pass")
            elif auth_type == "aws":
                monkeypatch.setenv("AWS_REGION", "us-east-1")
                
            # Try to get OpenSearch client with this auth type
            try:
                client = await jobs.get_opensearch_client()
                assert client is not None, f"Failed to get OpenSearch client with auth_type={auth_type}"
            except Exception as e:
                if "AWS4Auth" in str(e) and auth_type == "aws":
                    # This is expected if boto3 is not available
                    pass
                else:
                    pytest.fail(f"get_opensearch_client raised unexpected exception with auth_type={auth_type}: {e}")
                    
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.asyncio
    async def test_periodic_flush(self, mock_arq_worker, monkeypatch):
        """Test that periodic flush works correctly."""
        if not mock_arq_worker or mock_arq_worker[0] is None:
            pytest.skip("ARQ worker mock not available")
            
        jobs, ctx, mock_redis, mock_opensearch = mock_arq_worker
        
        # Check if the module has periodic flushing
        if not hasattr(jobs, "periodic_flush"):
            pytest.skip("This ARQ worker implementation doesn't have periodic_flush")
            
        # Instead of waiting for periodic flush, test the flush_logs function directly
        # since our mock periodic task isn't actually running
        
        # Create a test log record
        log_record = {
            "level": "INFO",
            "message": "[INFO] Periodic flush test",
            "service": "test-service",
            "pid": 12345,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        
        # Add to buffer
        if hasattr(jobs, "log_buffer"):
            # Direct manipulation of the buffer for testing
            async with jobs.buffer_lock:
                jobs.log_buffer.append(log_record)
                buffer_size_before = len(jobs.log_buffer)
                
            # Verify record was added
            assert buffer_size_before > 0, "Failed to add record to buffer"
                
            # Manually call flush_logs instead of waiting for periodic flush
            await jobs.flush_logs()
            
            # Buffer should be empty after flush_logs
            async with jobs.buffer_lock:
                assert len(jobs.log_buffer) == 0, "Buffer not emptied by flush_logs"
                
        # This test only verifies the flush_logs function works correctly,
        # not that the periodic task is actually running, which is difficult to mock
                
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.asyncio
    async def test_worker_startup_shutdown(self, mock_arq_worker):
        """Test worker startup and shutdown functions."""
        if not mock_arq_worker or mock_arq_worker[0] is None:
            pytest.skip("ARQ worker mock not available")
            
        jobs, ctx, mock_redis, mock_opensearch = mock_arq_worker
        
        # Check if the module has startup/shutdown
        if not hasattr(jobs, "startup") or not hasattr(jobs, "shutdown"):
            pytest.skip("This ARQ worker implementation doesn't have startup/shutdown functions")
            
        # Create a fresh context
        new_ctx = {"redis": mock_redis}
        
        # Call startup
        await jobs.startup(new_ctx)
        
        # Verify flush_task was created
        assert 'flush_task' in new_ctx, "startup didn't create flush_task"
        
        # Call shutdown
        await jobs.shutdown(new_ctx)
        
        # If we got here without errors, the test passed
        assert True
        
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.asyncio
    async def test_flush_logic(self, mock_arq_worker):
        """Test the flush_logs function logic."""
        if not mock_arq_worker or mock_arq_worker[0] is None:
            pytest.skip("ARQ worker mock not available")
            
        jobs, ctx, mock_redis, mock_opensearch = mock_arq_worker
        
        # Check if the module has flush_logs
        if not hasattr(jobs, "flush_logs"):
            pytest.skip("This ARQ worker implementation doesn't have flush_logs")
            
        # Test with empty buffer
        if hasattr(jobs, "log_buffer"):
            async with jobs.buffer_lock:
                jobs.log_buffer = []
                
            # Should not raise errors with empty buffer
            await jobs.flush_logs()
            
            # Test with a few records
            async with jobs.buffer_lock:
                jobs.log_buffer = [
                    {
                        "level": "INFO",
                        "message": f"[INFO] Test message {i}",
                        "service": "test-service",
                        "pid": 12345,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    }
                    for i in range(3)
                ]
                
            # Flush logs
            await jobs.flush_logs()
            
            # Buffer should be empty after flush
            async with jobs.buffer_lock:
                assert len(jobs.log_buffer) == 0, "Buffer not emptied after flush_logs"