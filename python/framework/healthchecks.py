import asyncio
import aiohttp
import aioredis
import asyncpg
import os
import subprocess
import time
from . import healthchecks

# Config
MAX_FAILURES = int(os.getenv("MAX_FAILURES", 3))  # How many failures allowed before restart
FAILURE_RESET_TIME = int(os.getenv("FAILURE_RESET_TIME", 600))  # Reset failure streak after N seconds
SLACK_ALERT_URL = os.getenv("SLACK_ALERT_WEBHOOK")  # Optional alert webhook

# Internal State
failure_streak = 0
last_failure_time = None
RECOVERY_TRACKER = {}  # service_name -> was_failure: bool

# ------------------------------
# Core alert function
# ------------------------------

async def send_alert(message: str, alert_url: str = None):
    if not alert_url:
        return  # Alerting not configured
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(alert_url, json={"text": message})
    except Exception as e:
        print(f"⚠️ Failed to send alert: {e}")

# ------------------------------
# Checkers
# ------------------------------

async def check_http_target(name: str, url: str, expect_status: int = 200, failures: list = None, recoveries: list = None):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status == expect_status:
                    print(f"✅ {name} OK (HTTP {resp.status})")
                    if RECOVERY_TRACKER.get(name):
                        if recoveries is not None:
                            recoveries.append(f"✅ {name} recovered (HTTP {resp.status})")
                    RECOVERY_TRACKER[name] = False
                else:
                    msg = f"❌ {name} unhealthy (HTTP {resp.status})"
                    print(msg)
                    if failures is not None:
                        failures.append(msg)
                    RECOVERY_TRACKER[name] = True
    except Exception as e:
        msg = f"❌ {name} HTTP check failed: {e}"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True

async def check_redis_target(name: str, url: str, failures: list = None, recoveries: list = None):
    try:
        redis = await aioredis.from_url(url)
        pong = await redis.ping()
        if pong:
            print(f"✅ {name} OK (Redis PING)")
            if RECOVERY_TRACKER.get(name):
                if recoveries is not None:
                    recoveries.append(f"✅ {name} recovered (Redis PING)")
            RECOVERY_TRACKER[name] = False
        await redis.close()
    except Exception as e:
        msg = f"❌ {name} Redis check failed: {e}"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True

async def check_postgres_target(name: str, url: str, failures: list = None, recoveries: list = None):
    try:
        conn = await asyncpg.connect(url)
        await conn.execute("SELECT 1;")
        print(f"✅ {name} OK (Postgres SELECT 1)")
        if RECOVERY_TRACKER.get(name):
            if recoveries is not None:
                recoveries.append(f"✅ {name} recovered (Postgres SELECT 1)")
        RECOVERY_TRACKER[name] = False
        await conn.close()
    except Exception as e:
        msg = f"❌ {name} Postgres check failed: {e}"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True

# ------------------------------
# Healthcheck runner
# ------------------------------

async def run_checks(targets: list[dict], interval: int = 300, alert_url: str = None):
    global failure_streak, last_failure_time

    while True:
        print("\n🔎 Running health checks...")
        failures = []
        recoveries = []

        tasks = []
        for target in targets:
            type_ = target.get("type", "http")
            name = target.get("name", "Unknown")
            url = target.get("url")
            if type_ == "http":
                tasks.append(check_http_target(name, url, target.get("expect_status", 200), failures, recoveries))
            elif type_ == "redis":
                tasks.append(check_redis_target(name, url, failures, recoveries))
            elif type_ == "postgres":
                tasks.append(check_postgres_target(name, url, failures, recoveries))
            else:
                print(f"⚠️ Unknown check type '{type_}' for target {name}")

        await asyncio.gather(*tasks)

        # If failures detected
        if failures:
            if alert_url:
                combined_message = "🚨 Healthcheck Failures:\n" + "\n".join(failures)
                await send_alert(combined_message, alert_url)
                healthchecks.set_health_message(combined_message)

            failure_streak += 1
            last_failure_time = time.time()

            print(f"⚠️ Failure streak count: {failure_streak}")

            if failure_streak >= MAX_FAILURES:
                print(f"🚨 Too many consecutive failures. Restarting services...")
                try:
                    subprocess.run(["docker-compose", "restart", "api", "worker"], check=True)
                    failure_streak = 0
                except Exception as e:
                    print(f"❌ Failed to restart services: {e}")
        else:
            # No failures detected
            if last_failure_time and (time.time() - last_failure_time > FAILURE_RESET_TIME):
                print("✅ Resetting failure streak (system stable).")
                failure_streak = 0
                last_failure_time = None
                healthchecks.set_health_message("All systems operational")

        # If recoveries detected
        if recoveries and alert_url:
            combined_message = "✅ Recoveries:\n" + "\n".join(recoveries)
            await send_alert(combined_message, alert_url)
            healthchecks.set_health_message(combined_message)

        await asyncio.sleep(interval)

# ------------------------------
# Public API
# ------------------------------

def launch_healthchecks(targets: list[dict], interval: int = 300, alert_url: str = None):
    """
    Launch healthchecks asynchronously.

    Example:
        launch_healthchecks([
            {"type": "http", "name": "API", "url": "http://localhost:8000/healthz"},
            {"type": "redis", "name": "Redis", "url": "redis://localhost:6379"},
            {"type": "postgres", "name": "Postgres", "url": "postgresql://user:pass@localhost:5432/db"},
        ])
    """
    asyncio.run(run_checks(targets, interval, alert_url or SLACK_ALERT_URL))
