from arq.worker import Worker
from jobs import log_message, startup, shutdown
import asyncio
import aioredis

REDIS_URL = "redis://your-redis-host:6379"

async def wait_for_redis(redis_url, retries=10, delay=3):
    for attempt in range(retries):
        try:
            redis = await aioredis.from_url(redis_url)
            await redis.ping()
            await redis.close()
            print(f"Connected to Redis at {redis_url}")
            return
        except Exception as e:
            print(f"Redis not ready (attempt {attempt + 1}/{retries}): {e}")
            await asyncio.sleep(delay)
    raise Exception("Failed to connect to Redis after several attempts")

async def main():
    await wait_for_redis(REDIS_URL)

    worker = Worker(
        functions=[log_message],
        redis_url=REDIS_URL,
        on_startup=startup,
        on_shutdown=shutdown,
        handle_signals=True
    )

    while True:
        try:
            await worker.run()
        except Exception as e:
            print(f"Worker crashed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
