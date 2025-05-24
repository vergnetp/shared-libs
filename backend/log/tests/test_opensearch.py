# tests/test_opensearch.py

import pytest
import time
from datetime import datetime
from typing import Dict, Any, List

from opensearchpy import OpenSearch, RequestsHttpConnection

from ..log_storage import LogStorageInterface
from ..opensearch_storage import OpenSearchLogStorage

class TestOpenSearchStorage:
    @pytest.fixture(scope="class")
    def opensearch_client(self):
        """Create a synchronous OpenSearch client for testing"""
        # Connect to the Docker container defined in docker-compose.yml
        client = OpenSearch(
            hosts=[{'host': 'localhost', 'port': 9200}],
            http_auth=None,
            use_ssl=False,
            verify_certs=False,
            connection_class=RequestsHttpConnection,
            timeout=30
        )
        
        # Wait for OpenSearch to be ready
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                info = client.info()
                print(f"Connected to OpenSearch: {info['version']['number']}")
                break
            except Exception as e:
                retry_count += 1
                print(f"Waiting for OpenSearch to be ready... ({retry_count}/{max_retries})")
                if retry_count >= max_retries:
                    pytest.fail(f"Could not connect to OpenSearch: {e}")
                time.sleep(2)  # Wait before retry
        
        # Delete test indices to start clean
        try:
            client.indices.delete(index="test-logs-*")
            print("Cleaned up existing test indices")
        except Exception:
            # Ignore if indices don't exist
            pass
            
        return client
    
    @pytest.fixture(scope="class")
    def storage(self, opensearch_client):
        """Create storage instance with direct configuration"""
        storage = OpenSearchLogStorage(
            host="localhost",
            port=9200,
            use_ssl=False,
            index_prefix="test-logs",
            verify_certs=False
        )
        
        # Override the client to ensure we're using the same one
        storage._client = opensearch_client
        
        # Create explicit mappings for the test indices
        self._create_test_index(opensearch_client)
        
        return storage
    
    def _create_test_index(self, client):
        """Create test index with explicit mappings"""
        index_name = f"test-logs-{datetime.now().strftime('%Y.%m.%d')}"
        
        # Check if index exists
        if not client.indices.exists(index=index_name):
            # Define mappings with proper timestamp format
            mappings = {
                "mappings": {
                    "properties": {
                        "timestamp": {
                            "type": "date", 
                            "format": "yyyy-MM-dd HH:mm:ss.SSS||yyyy-MM-dd||epoch_millis"
                        },
                        "level": {"type": "keyword"},
                        "message": {"type": "text"},
                        "service": {"type": "keyword"},
                        "component": {"type": "keyword"},
                        "subcomponent": {"type": "keyword"},
                        "context": {"type": "object", "dynamic": True}
                    }
                }
            }
            
            # Create index with proper mappings
            client.indices.create(index=index_name, body=mappings)
            print(f"Created index {index_name} with explicit mappings")
    
    def test_store_log(self, storage, opensearch_client):
        """Test storing a single log record"""
        # Create a test log record
        log_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "level": "INFO",
            "message": "Test log message",
            "service": "test-service",
            "component": "TestComponent",
            "subcomponent": "test_method"
        }
        
        # Store the log using refresh=true to make it searchable immediately
        result = opensearch_client.index(
            index=f"test-logs-{datetime.now().strftime('%Y.%m.%d')}",
            body=log_record,
            refresh=True
        )
        
        # Verify result directly
        assert result["result"] == "created"
        
        # Verify the log was stored correctly
        response = opensearch_client.search(
            index=f"test-logs-{datetime.now().strftime('%Y.%m.%d')}",
            body={
                "query": {
                    "match": {
                        "message": "Test log message"
                    }
                }
            }
        )
        
        # Check results
        assert response["hits"]["total"]["value"] == 1
        stored_log = response["hits"]["hits"][0]["_source"]
        assert stored_log["message"] == log_record["message"]
        assert stored_log["component"] == log_record["component"]
        assert stored_log["subcomponent"] == log_record["subcomponent"]
    
    def test_store_batch(self, storage, opensearch_client):
        """Test storing a batch of log records"""
        # Create test log records
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_records = [
            {
                "timestamp": timestamp,
                "level": "INFO",
                "message": f"Test batch message {i}",
                "service": "test-service",
                "component": "TestComponent",
                "subcomponent": "test_batch"
            }
            for i in range(5)
        ]
        
        # Create bulk request
        bulk_body = []
        for record in log_records:
            bulk_body.append({"index": {"_index": f"test-logs-{datetime.now().strftime('%Y.%m.%d')}"} })
            bulk_body.append(record)
        
        # Send bulk request directly
        result = opensearch_client.bulk(body=bulk_body, refresh=True)
        
        # Check that there are no errors
        assert not result.get("errors", False)
        
        # Verify the logs were stored correctly
        response = opensearch_client.search(
            index=f"test-logs-{datetime.now().strftime('%Y.%m.%d')}",
            body={
                "query": {
                    "match_phrase_prefix": {
                        "message": "Test batch message"
                    }
                },
                "size": 10
            }
        )
        
        # Check results
        assert response["hits"]["total"]["value"] == 5
    
    def test_structured_fields(self, storage, opensearch_client):
        """Test storing and querying structured fields"""
        # Create a log record with structured fields
        log_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "level": "INFO",
            "message": "Structured field test",
            "service": "test-service",
            "component": "TestComponent",
            "subcomponent": "test_structured",
            "context": {
                "user_id": "user123",
                "transaction_id": "tx-abc-123",
                "duration_ms": 150,
                "status_code": 200
            }
        }
        
        # Store directly
        opensearch_client.index(
            index=f"test-logs-{datetime.now().strftime('%Y.%m.%d')}",
            body=log_record,
            refresh=True
        )
        
        # Query by context field
        response = opensearch_client.search(
            index=f"test-logs-{datetime.now().strftime('%Y.%m.%d')}",
            body={
                "query": {
                    "term": {
                        "context.user_id": "user123"
                    }
                }
            }
        )
        
        # Check results
        assert response["hits"]["total"]["value"] == 1
        stored_log = response["hits"]["hits"][0]["_source"]
        assert stored_log["context"]["transaction_id"] == "tx-abc-123"
        assert stored_log["context"]["duration_ms"] == 150
    
    def test_component_subcomponent_queries(self, storage, opensearch_client):
        """Test querying by component and subcomponent"""
        # Create multiple log records with different components/subcomponents
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Create logs with different component/subcomponent combinations
        components = ["PoolManager", "AuthService", "ApiHandler"]
        subcomponents = ["LeakDetection", "Authentication", "RequestProcessing"]
        
        # Create bulk request
        bulk_body = []
        for component in components:
            for subcomponent in subcomponents:
                bulk_body.append({"index": {"_index": f"test-logs-{datetime.now().strftime('%Y.%m.%d')}"} })
                bulk_body.append({
                    "timestamp": timestamp,
                    "level": "INFO",
                    "message": f"Log from {component}.{subcomponent}",
                    "service": "test-service",
                    "component": component,
                    "subcomponent": subcomponent
                })
        
        # Send bulk request directly
        result = opensearch_client.bulk(body=bulk_body, refresh=True)
        
        # Check that there are no errors
        assert not result.get("errors", False)
        
        # Test 1: Query by component
        response = opensearch_client.search(
            index=f"test-logs-{datetime.now().strftime('%Y.%m.%d')}",
            body={
                "query": {
                    "match": {
                        "component": "PoolManager"
                    }
                },
                "size": 10
            }
        )
        
        # Should find 3 logs from PoolManager (one for each subcomponent)
        assert response["hits"]["total"]["value"] == 3
        
        # Test 2: Query by subcomponent
        response = opensearch_client.search(
            index=f"test-logs-{datetime.now().strftime('%Y.%m.%d')}",
            body={
                "query": {
                    "match": {
                        "subcomponent": "LeakDetection"
                    }
                },
                "size": 10
            }
        )
        
        # Should find 3 logs with LeakDetection subcomponent (one for each component)
        assert response["hits"]["total"]["value"] == 3
        
        # Test 3: Query by both component and subcomponent
        response = opensearch_client.search(
            index=f"test-logs-{datetime.now().strftime('%Y.%m.%d')}",
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"component": "PoolManager"}},
                            {"match": {"subcomponent": "LeakDetection"}}
                        ]
                    }
                }
            }
        )
        
        # Should find exactly 1 log matching both criteria
        assert response["hits"]["total"]["value"] == 1
        assert response["hits"]["hits"][0]["_source"]["component"] == "PoolManager"
        assert response["hits"]["hits"][0]["_source"]["subcomponent"] == "LeakDetection"
    
    @pytest.fixture(scope="class", autouse=True)
    def cleanup_indices(self, opensearch_client):
        """Clean up test indices after all tests in the class have run"""
        # Setup code (if needed)
        yield
        # Cleanup code after all tests
        try:
            opensearch_client.indices.delete(index="test-logs-*")
            print("Cleaned up test indices after tests")
        except Exception as e:
            print(f"Cleanup error: {e}")