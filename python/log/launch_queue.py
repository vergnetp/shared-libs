import asyncio
import os
from ..utils.processing import ProcessingWorker, configure as configure_processing

# Define Redis URL from environment for flexibility
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

async def wait_for_redis(redis_url, retries=10, delay=3):
    """Wait for Redis to be available before starting worker."""
    for attempt in range(retries):
        try:
            # Use the utils.processing system to check Redis
            manager = configure_processing(redis_url=redis_url)
            redis = await manager._ensure_redis()
            await redis.ping()
            print(f"Connected to Redis at {redis_url}")
            return manager
        except Exception as e:
            print(f"Redis not ready (attempt {attempt + 1}/{retries}): {e}")
            await asyncio.sleep(delay)
    raise Exception("Failed to connect to Redis after several attempts")

async def main():
    """Main entry point for the log worker."""
    # Wait for Redis to be ready and get the configured processing manager
    manager = await wait_for_redis(REDIS_URL)
    
    # Import the log processors and register them
    from jobs import startup_processing
    await startup_processing(REDIS_URL)
    
    # Create the worker with appropriate settings
    worker = ProcessingWorker(
        manager,
        max_workers=3,  # Number of concurrent workers
        work_timeout=30.0  # Timeout for each work item in seconds
    )
    
    # Start worker and keep it running with automatic recovery
    print("Starting log processing worker...")
    while True:
        try:
            # Start the worker
            await worker.start()
            
            # Keep running until a keyboard interrupt or other exception
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            # Handle graceful shutdown on Ctrl+C
            print("\nShutting down worker...")
            await worker.stop()
            return
            
        except Exception as e:
            # Handle errors by restarting the worker
            print(f"Worker crashed: {e}. Retrying in 5 seconds...")
            
            # Try to stop gracefully if it's still running
            try:
                await worker.stop()
            except Exception:
                pass
                
            # Wait before restarting
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nWorker stopped by user")