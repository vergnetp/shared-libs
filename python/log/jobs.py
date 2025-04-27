import json
import asyncio
import os
from datetime import datetime
from opensearchpy import AsyncOpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import boto3

# Configure OpenSearch connection - values from environment or defaults
OPENSEARCH_HOST = os.environ.get('OPENSEARCH_HOST', 'localhost')
OPENSEARCH_PORT = int(os.environ.get('OPENSEARCH_PORT', 9200))
OPENSEARCH_USE_SSL = os.environ.get('OPENSEARCH_USE_SSL', 'false').lower() == 'true'
OPENSEARCH_INDEX_PREFIX = os.environ.get('OPENSEARCH_INDEX_PREFIX', 'logs')
OPENSEARCH_AUTH_TYPE = os.environ.get('OPENSEARCH_AUTH_TYPE', 'none')  # none, basic, aws

# Get AWS region for authentication if needed
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Buffer for batch processing
log_buffer = []
buffer_size = int(os.environ.get('LOG_BUFFER_SIZE', 50))
buffer_lock = asyncio.Lock()
flush_interval = int(os.environ.get('LOG_FLUSH_INTERVAL', 10))  # seconds
last_flush_time = datetime.now()

# OpenSearch client instance
opensearch_client = None

async def get_opensearch_client():
    """Get or create an OpenSearch client."""
    global opensearch_client
    
    if opensearch_client is not None:
        return opensearch_client
    
    # Configure authentication
    auth = None
    if OPENSEARCH_AUTH_TYPE == 'aws':
        session = boto3.Session()
        credentials = session.get_credentials()
        auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            AWS_REGION,
            'es',
            session_token=credentials.token
        )
    elif OPENSEARCH_AUTH_TYPE == 'basic':
        # Basic auth with username/password
        username = os.environ.get('OPENSEARCH_USERNAME')
        password = os.environ.get('OPENSEARCH_PASSWORD')
        if username and password:
            auth = (username, password)
    
    # Create client
    opensearch_client = AsyncOpenSearch(
        hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
        http_auth=auth,
        use_ssl=OPENSEARCH_USE_SSL,
        verify_certs=False,  # Set to True in production with proper certs
        connection_class=RequestsHttpConnection,
        timeout=30
    )
    
    return opensearch_client

async def flush_logs():
    """Flush buffered logs to OpenSearch."""
    global log_buffer, last_flush_time
    
    async with buffer_lock:
        if not log_buffer:
            last_flush_time = datetime.now()
            return
            
        # Make a copy of the buffer and clear it
        logs_to_send = log_buffer.copy()
        log_buffer = []
    
    try:
        client = await get_opensearch_client()
        
        # Prepare bulk request
        bulk_actions = []
        for log in logs_to_send:
            # Determine index name based on date
            timestamp = log.get('timestamp')
            if timestamp:
                try:
                    # Parse timestamp and format index date
                    date_part = timestamp.split()[0]  # Get date part of timestamp
                    index_name = f"{OPENSEARCH_INDEX_PREFIX}-{date_part.replace('-', '.')}"
                except Exception:
                    # Default to today's date if parsing fails
                    index_name = f"{OPENSEARCH_INDEX_PREFIX}-{datetime.now().strftime('%Y.%m.%d')}"
            else:
                # Use today's date if no timestamp in log
                index_name = f"{OPENSEARCH_INDEX_PREFIX}-{datetime.now().strftime('%Y.%m.%d')}"
            
            # Add index action
            bulk_actions.append({"index": {"_index": index_name}})
            bulk_actions.append(log)
        
        if bulk_actions:
            # Convert to newline-delimited JSON
            bulk_body = "\n".join(json.dumps(action) for action in bulk_actions) + "\n"
            
            # Send to OpenSearch
            response = await client.bulk(body=bulk_body)
            
            # Handle errors if any
            if response.get("errors", False):
                errors = [item["index"]["error"] for item in response["items"] if "error" in item.get("index", {})]
                print(f"Error sending logs to OpenSearch: {errors}")
    
    except Exception as e:
        print(f"Failed to send logs to OpenSearch: {e}")
    
    last_flush_time = datetime.now()

async def periodic_flush():
    """Periodically flush logs to ensure timely delivery even with low volume."""
    while True:
        now = datetime.now()
        if (now - last_flush_time).total_seconds() >= flush_interval:
            await flush_logs()
        await asyncio.sleep(1)  # Check every second

async def startup(ctx):
    """Start the periodic flush task when the worker starts."""
    ctx['flush_task'] = asyncio.create_task(periodic_flush())
    print("Log worker started with OpenSearch integration")

async def shutdown(ctx):
    """Flush remaining logs and cancel the periodic task."""
    if 'flush_task' in ctx:
        ctx['flush_task'].cancel()
        try:
            await ctx['flush_task']
        except asyncio.CancelledError:
            pass
    
    # Final flush
    await flush_logs()
    print("Log worker shutdown complete")

async def log_message(ctx, *, log_record):
    """
    ARQ worker function to process logs sent via Redis.
    
    This writes logs to OpenSearch with buffering for efficiency.
    
    Args:
        ctx: ARQ context
        log_record: The log record dictionary
    """
    global log_buffer
    
    # Add timestamp if not present
    if 'timestamp' not in log_record:
        log_record['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    # Add to buffer
    async with buffer_lock:
        log_buffer.append(log_record)
        buffer_full = len(log_buffer) >= buffer_size
    
    # Flush if buffer is full
    if buffer_full:
        await flush_logs()
    
    return True  # Return success