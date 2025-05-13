from datetime import datetime
from typing import Dict, Any, Optional, List

import asyncio
from .log_storage import LogStorageInterface

# OpenSearch imports
from opensearchpy import AsyncOpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import boto3

class OpenSearchLogStorage(LogStorageInterface):
    """Implementation of LogStorageInterface for OpenSearch"""
    
    def __init__(self, 
                 host: str = 'localhost',
                 port: int = 9200, 
                 use_ssl: bool = False,
                 index_prefix: str = 'logs',
                 auth_type: str = 'none',  # none, basic, aws
                 region: str = 'us-east-1',
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 verify_certs: bool = False,
                 timeout: int = 30):
        """
        Initialize OpenSearch log storage.
        
        Args:
            host: OpenSearch host
            port: OpenSearch port
            use_ssl: Whether to use SSL for connection
            index_prefix: Prefix for index names
            auth_type: Authentication type ('none', 'basic', or 'aws')
            region: AWS region if using aws auth
            username: Username for basic auth
            password: Password for basic auth
            verify_certs: Whether to verify SSL certificates
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.index_prefix = index_prefix
        self.auth_type = auth_type
        self.region = region
        self.username = username
        self.password = password
        self.verify_certs = verify_certs
        self.timeout = timeout
        
        # Will be initialized on first use
        self._client = None
        self._client_lock = asyncio.Lock()
        
    async def get_client(self):
        """Get or create an OpenSearch client."""
        if self._client is not None:
            return self._client
        
        # Use a lock to prevent multiple initializations
        async with self._client_lock:
            if self._client is not None:
                return self._client
                
            # Configure authentication
            auth = None
            if self.auth_type == 'aws':
                session = boto3.Session()
                credentials = session.get_credentials()
                auth = AWS4Auth(
                    credentials.access_key,
                    credentials.secret_key,
                    self.region,
                    'es',
                    session_token=credentials.token
                )
            elif self.auth_type == 'basic':
                # Basic auth with username/password
                if self.username and self.password:
                    auth = (self.username, self.password)
            
            # Create client
            self._client = AsyncOpenSearch(
                hosts=[{'host': self.host, 'port': self.port}],
                http_auth=auth,
                use_ssl=self.use_ssl,
                verify_certs=self.verify_certs,
                connection_class=RequestsHttpConnection,
                timeout=self.timeout
            )
            
            return self._client
    
    def _get_index_name(self, timestamp: Optional[str] = None) -> str:
        """
        Get index name based on date in timestamp.
        
        Args:
            timestamp: Timestamp string containing a date
            
        Returns:
            Index name with date
        """
        if timestamp:
            try:
                # Parse timestamp and format index date
                date_part = timestamp.split()[0]  # Get date part of timestamp
                return f"{self.index_prefix}-{date_part.replace('-', '.')}"
            except Exception:
                # Default to today's date if parsing fails
                return f"{self.index_prefix}-{datetime.now().strftime('%Y.%m.%d')}"
        else:
            # Use today's date if no timestamp in log
            return f"{self.index_prefix}-{datetime.now().strftime('%Y.%m.%d')}"
    
    async def store_log(self, log_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store a single log record in OpenSearch.
        
        Args:
            log_record: The log record to store
            
        Returns:
            Dict with storage status
        """
        # Add timestamp if not present
        if 'timestamp' not in log_record:
            log_record['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Get OpenSearch client
        client = await self.get_client()
        
        # Determine index name based on date
        index_name = self._get_index_name(log_record.get('timestamp'))
        
        # Send to OpenSearch
        try:
            response = await client.index(
                index=index_name,
                body=log_record,
                refresh=False  # Don't wait for refresh to improve performance
            )
            return {"status": "indexed", "id": response.get("_id")}
        except Exception as e:
            # Log error and return error status
            print(f"Error indexing log record: {e}")
            return {"status": "error", "error": str(e)}
    
    async def store_batch(self, log_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Store a batch of log records in OpenSearch.
        
        Args:
            log_records: List of log records to store
            
        Returns:
            Dict with storage status
        """
        if not log_records:
            return {"status": "empty", "count": 0}
        
        client = await self.get_client()
        
        # Group records by index
        records_by_index = {}
        for record in log_records:
            # Add timestamp if not present
            if 'timestamp' not in record:
                record['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
            # Determine index name
            index_name = self._get_index_name(record.get('timestamp'))
                
            # Add to group
            if index_name not in records_by_index:
                records_by_index[index_name] = []
            records_by_index[index_name].append(record)
        
        # Prepare bulk request for each index
        bulk_body = []
        for index_name, records in records_by_index.items():
            for record in records:
                # Add index action and document
                bulk_body.append({"index": {"_index": index_name}})
                bulk_body.append(record)
        
        # Execute bulk request
        try:
            if bulk_body:
                response = await client.bulk(body=bulk_body)
                errors = [item["index"]["error"] for item in response.get("items", []) 
                         if "error" in item.get("index", {})]
                
                if errors:
                    return {
                        "status": "partial",
                        "success_count": len(response.get("items", [])) - len(errors),
                        "error_count": len(errors),
                        "first_error": str(errors[0]) if errors else None
                    }
                else:
                    return {
                        "status": "success",
                        "count": len(log_records),
                        "took_ms": response.get("took")
                    }
            else:
                return {"status": "empty", "count": 0}
        except Exception as e:
            # Log failure and return error
            print(f"Bulk indexing failed: {e}")
            return {"status": "error", "error": str(e), "count": len(log_records)}