import asyncio
import aiohttp
import aioredis
import asyncpg
import os
import subprocess
import time
import json
import socket
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from . import healthchecks

# Config with environment variable overrides and defaults
MAX_FAILURES = int(os.getenv("MAX_FAILURES", "3"))  # How many failures allowed before restart
FAILURE_RESET_TIME = int(os.getenv("FAILURE_RESET_TIME", "600"))  # Reset failure streak after N seconds
SLACK_ALERT_URL = os.getenv("SLACK_ALERT_WEBHOOK")  # Optional alert webhook
TEAMS_ALERT_URL = os.getenv("TEAMS_ALERT_WEBHOOK")  # Optional Microsoft Teams webhook
EMAIL_ALERT = os.getenv("EMAIL_ALERT_RECIPIENT")  # Optional email alert recipient
ALERT_INTERVAL = int(os.getenv("ALERT_INTERVAL", "1800"))  # Min seconds between alerts (default 30 mins)
MAX_RESTART_ATTEMPTS = int(os.getenv("MAX_RESTART_ATTEMPTS", "3"))  # Max service restart attempts
RESTART_BACKOFF_FACTOR = float(os.getenv("RESTART_BACKOFF_FACTOR", "1.5"))  # Exponential backoff factor
CHECK_INTERVAL = int(os.getenv("HEALTHCHECK_INTERVAL", "300"))  # Seconds between checks (default 5 mins)

# Internal State
failure_streak = 0
last_failure_time = None
last_alert_time = None
restart_attempts = 0
last_restart_time = None
RECOVERY_TRACKER = {}  # service_name -> was_failure: bool
SERVICE_STATS = {}  # service_name -> {failures: int, last_failure: timestamp, recoveries: int}

# ------------------------------
# Core alert functions
# ------------------------------

async def send_slack_alert(message: str, alert_url: str = None):
    """
    Send an alert to Slack.
    
    Args:
        message: The message to send
        alert_url: The Slack webhook URL
    """
    if not alert_url:
        return  # Alerting not configured
        
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "text": message,
            "username": f"Healthcheck ({socket.gethostname()})",
            "icon_emoji": ":warning:"
        }
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(3):  # Retry up to 3 times
                try:
                    async with session.post(
                        alert_url, 
                        json=payload,
                        headers=headers,
                        timeout=10
                    ) as resp:
                        if resp.status == 200:
                            return
                        else:
                            print(f"⚠️ Alert API responded with status {resp.status}")
                except Exception as e:
                    print(f"⚠️ Alert attempt {attempt+1} failed: {e}")
                    if attempt < 2:  # Don't sleep after last attempt
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
    except Exception as e:
        print(f"⚠️ Failed to send alert: {e}")

async def send_teams_alert(message: str, alert_url: str = None):
    """
    Send an alert to Microsoft Teams.
    
    Args:
        message: The message to send
        alert_url: The Teams webhook URL
    """
    if not alert_url:
        return  # Alerting not configured
        
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "text": message,
            "title": f"Healthcheck Alert ({socket.gethostname()})",
        }
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(3):  # Retry up to 3 times
                try:
                    async with session.post(
                        alert_url, 
                        json=payload,
                        headers=headers,
                        timeout=10
                    ) as resp:
                        if resp.status == 200:
                            return
                        else:
                            print(f"⚠️ Teams alert API responded with status {resp.status}")
                except Exception as e:
                    print(f"⚠️ Teams alert attempt {attempt+1} failed: {e}")
                    if attempt < 2:  # Don't sleep after last attempt
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
    except Exception as e:
        print(f"⚠️ Failed to send Teams alert: {e}")

async def send_email_alert(message: str, recipient: str = None):
    """
    Send an alert via email.
    
    Args:
        message: The message to send
        recipient: The email recipient
    """
    if not recipient:
        return  # Alerting not configured
        
    try:
        from ..emailing import send_email
        
        subject = f"Healthcheck Alert - {socket.gethostname()}"
        
        # Use the emailing module to send the email
        send_email(
            subject=subject,
            recipients=[recipient],
            text=message
        )
    except Exception as e:
        print(f"⚠️ Failed to send email alert: {e}")

async def send_alert(message: str, alert_urls: Dict[str, str] = None):
    """
    Send alerts to all configured channels.
    
    Args:
        message: The message to send
        alert_urls: Dictionary of alert URLs by type
    """
    global last_alert_time
    
    # Rate limit alerts
    current_time = time.time()
    if last_alert_time and (current_time - last_alert_time < ALERT_INTERVAL):
        print(f"🔇 Alert suppressed (rate limited): {message}")
        return
        
    last_alert_time = current_time
    
    # Format timestamp for alerts
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    
    # Prepare alert URLs
    if not alert_urls:
        alert_urls = {}
    
    # Send to all configured channels
    tasks = []
    
    # Slack
    slack_url = alert_urls.get("slack", SLACK_ALERT_URL)
    if slack_url:
        tasks.append(send_slack_alert(full_message, slack_url))
        
    # Teams
    teams_url = alert_urls.get("teams", TEAMS_ALERT_URL)
    if teams_url:
        tasks.append(send_teams_alert(full_message, teams_url))
        
    # Email
    email_recipient = alert_urls.get("email", EMAIL_ALERT)
    if email_recipient:
        tasks.append(send_email_alert(full_message, email_recipient))
        
    # Wait for all alerts to complete
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    else:
        print(f"ℹ️ No alert channels configured, message: {message}")

# ------------------------------
# Service control functions
# ------------------------------

async def restart_service(service_name: str):
    """
    Restart a service with exponential backoff.
    
    Args:
        service_name: Name of the service to restart
    
    Returns:
        bool: True if restart succeeded, False otherwise
    """
    global restart_attempts, last_restart_time
    
    # Check if too many restart attempts
    current_time = time.time()
    if last_restart_time:
        # Reset counter if last restart was more than an hour ago
        if current_time - last_restart_time > 3600:
            restart_attempts = 0
        # Otherwise, check if we've hit the limit
        elif restart_attempts >= MAX_RESTART_ATTEMPTS:
            await send_alert(
                f"🚨 Service {service_name} needs restart but maximum attempts ({MAX_RESTART_ATTEMPTS}) reached. Manual intervention required."
            )
            return False
    
    # Calculate backoff delay
    delay = 0
    if restart_attempts > 0:
        delay = min(60, 5 * (RESTART_BACKOFF_FACTOR ** (restart_attempts - 1)))
        print(f"⏳ Waiting {delay:.1f} seconds before restart attempt...")
        await asyncio.sleep(delay)
    
    # Attempt restart
    restart_attempts += 1
    last_restart_time = current_time
    
    print(f"🔄 Restarting services (attempt {restart_attempts})...")
    
    try:
        # Try docker-compose restart first
        process = await asyncio.create_subprocess_exec(
            "docker-compose", "restart", "api", "worker",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            print(f"✅ Services restarted successfully")
            await send_alert(f"✅ Services restarted successfully after {restart_attempts} attempts")
            return True
        else:
            error = stderr.decode().strip() or "unknown error"
            print(f"❌ Failed to restart services via docker-compose: {error}")
            
            # Fallback to individual service restart
            service_list = ["api", "worker"]
            for svc in service_list:
                try:
                    fallback_process = await asyncio.create_subprocess_exec(
                        "docker", "restart", svc,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    f_stdout, f_stderr = await fallback_process.communicate()
                    
                    if fallback_process.returncode == 0:
                        print(f"✅ Service {svc} restarted successfully")
                    else:
                        f_error = f_stderr.decode().strip() or "unknown error"
                        print(f"❌ Failed to restart service {svc}: {f_error}")
                        return False
                except Exception as e:
                    print(f"❌ Error restarting service {svc}: {e}")
                    return False
            
            # If we got here, all individual restarts succeeded
            await send_alert(f"✅ Services restarted individually after docker-compose failure")
            return True
    except Exception as e:
        print(f"❌ Failed to restart services: {e}")
        return False

# ------------------------------
# Checkers
# ------------------------------

async def check_http_target(name: str, url: str, expect_status: int = 200, failures: list = None, recoveries: list = None, timeout: int = 5):
    """
    Check an HTTP target for health.
    
    Args:
        name: Name of the target
        url: URL to check
        expect_status: Expected HTTP status code
        failures: List to append failure messages to
        recoveries: List to append recovery messages to
        timeout: Timeout in seconds
    """
    # Initialize service stats if not exists
    if name not in SERVICE_STATS:
        SERVICE_STATS[name] = {"failures": 0, "last_failure": None, "recoveries": 0}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == expect_status:
                    print(f"✅ {name} OK (HTTP {resp.status})")
                    if RECOVERY_TRACKER.get(name):
                        if recoveries is not None:
                            recoveries.append(f"✅ {name} recovered (HTTP {resp.status})")
                        SERVICE_STATS[name]["recoveries"] += 1
                    RECOVERY_TRACKER[name] = False
                else:
                    msg = f"❌ {name} unhealthy (HTTP {resp.status})"
                    print(msg)
                    if failures is not None:
                        failures.append(msg)
                    RECOVERY_TRACKER[name] = True
                    SERVICE_STATS[name]["failures"] += 1
                    SERVICE_STATS[name]["last_failure"] = time.time()
    except asyncio.TimeoutError:
        msg = f"❌ {name} HTTP check timed out after {timeout} seconds"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True
        SERVICE_STATS[name]["failures"] += 1
        SERVICE_STATS[name]["last_failure"] = time.time()
    except Exception as e:
        msg = f"❌ {name} HTTP check failed: {e}"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True
        SERVICE_STATS[name]["failures"] += 1
        SERVICE_STATS[name]["last_failure"] = time.time()

async def check_redis_target(name: str, url: str, failures: list = None, recoveries: list = None, timeout: int = 5):
    """
    Check a Redis target for health.
    
    Args:
        name: Name of the target
        url: Redis URL to check
        failures: List to append failure messages to
        recoveries: List to append recovery messages to
        timeout: Timeout in seconds
    """
    # Initialize service stats if not exists
    if name not in SERVICE_STATS:
        SERVICE_STATS[name] = {"failures": 0, "last_failure": None, "recoveries": 0}
    
    try:
        redis = None
        try:
            redis = await aioredis.from_url(url, socket_timeout=timeout)
            pong = await redis.ping()
            if pong:
                print(f"✅ {name} OK (Redis PING)")
                if RECOVERY_TRACKER.get(name):
                    if recoveries is not None:
                        recoveries.append(f"✅ {name} recovered (Redis PING)")
                    SERVICE_STATS[name]["recoveries"] += 1
                RECOVERY_TRACKER[name] = False
        finally:
            if redis:
                await redis.close()
    except asyncio.TimeoutError:
        msg = f"❌ {name} Redis check timed out after {timeout} seconds"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True
        SERVICE_STATS[name]["failures"] += 1
        SERVICE_STATS[name]["last_failure"] = time.time()
    except Exception as e:
        msg = f"❌ {name} Redis check failed: {e}"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True
        SERVICE_STATS[name]["failures"] += 1
        SERVICE_STATS[name]["last_failure"] = time.time()

async def check_postgres_target(name: str, url: str, failures: list = None, recoveries: list = None, timeout: int = 5):
    """
    Check a PostgreSQL target for health.
    
    Args:
        name: Name of the target
        url: PostgreSQL URL to check
        failures: List to append failure messages to
        recoveries: List to append recovery messages to
        timeout: Timeout in seconds
    """
    # Initialize service stats if not exists
    if name not in SERVICE_STATS:
        SERVICE_STATS[name] = {"failures": 0, "last_failure": None, "recoveries": 0}
    
    try:
        conn = None
        try:
            conn = await asyncpg.connect(url, timeout=timeout)
            await conn.execute("SELECT 1;")
            print(f"✅ {name} OK (Postgres SELECT 1)")
            if RECOVERY_TRACKER.get(name):
                if recoveries is not None:
                    recoveries.append(f"✅ {name} recovered (Postgres SELECT 1)")
                SERVICE_STATS[name]["recoveries"] += 1
            RECOVERY_TRACKER[name] = False
        finally:
            if conn:
                await conn.close()
    except asyncio.TimeoutError:
        msg = f"❌ {name} Postgres check timed out after {timeout} seconds"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True
        SERVICE_STATS[name]["failures"] += 1
        SERVICE_STATS[name]["last_failure"] = time.time()
    except Exception as e:
        msg = f"❌ {name} Postgres check failed: {e}"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True
        SERVICE_STATS[name]["failures"] += 1
        SERVICE_STATS[name]["last_failure"] = time.time()

# ------------------------------
# Custom checks
# ------------------------------

async def check_custom_command(name: str, command: List[str], failures: list = None, recoveries: list = None, timeout: int = 30):
    """
    Run a custom command and check its exit code.
    
    Args:
        name: Name of the check
        command: Command to run as a list of arguments
        failures: List to append failure messages to
        recoveries: List to append recovery messages to
        timeout: Timeout in seconds
    """
    # Initialize service stats if not exists
    if name not in SERVICE_STATS:
        SERVICE_STATS[name] = {"failures": 0, "last_failure": None, "recoveries": 0}
    
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            
            if process.returncode == 0:
                print(f"✅ {name} OK (exit code 0)")
                if RECOVERY_TRACKER.get(name):
                    if recoveries is not None:
                        recoveries.append(f"✅ {name} recovered (exit code 0)")
                    SERVICE_STATS[name]["recoveries"] += 1
                RECOVERY_TRACKER[name] = False
            else:
                error = stderr.decode().strip() or "unknown error"
                msg = f"❌ {name} failed (exit code {process.returncode}): {error}"
                print(msg)
                if failures is not None:
                    failures.append(msg)
                RECOVERY_TRACKER[name] = True
                SERVICE_STATS[name]["failures"] += 1
                SERVICE_STATS[name]["last_failure"] = time.time()
        except asyncio.TimeoutError:
            # Kill the process if it times out
            process.kill()
            msg = f"❌ {name} command timed out after {timeout} seconds"
            print(msg)
            if failures is not None:
                failures.append(msg)
            RECOVERY_TRACKER[name] = True
            SERVICE_STATS[name]["failures"] += 1
            SERVICE_STATS[name]["last_failure"] = time.time()
    except Exception as e:
        msg = f"❌ {name} command failed: {e}"
        print(msg)
        if failures is not None:
            failures.append(msg)
        RECOVERY_TRACKER[name] = True
        SERVICE_STATS[name]["failures"] += 1
        SERVICE_STATS[name]["last_failure"] = time.time()

# ------------------------------
# Health reporting
# ------------------------------

def get_health_status():
    """
    Get the current health status of all services.
    
    Returns:
        dict: Health status information
    """
    healthy = True
    services = []
    
    for name, stats in SERVICE_STATS.items():
        service_info = {
            "name": name,
            "healthy": not RECOVERY_TRACKER.get(name, False),
            "failures": stats["failures"],
            "recoveries": stats["recoveries"],
        }
        
        if stats["last_failure"]:
            service_info["last_failure"] = datetime.fromtimestamp(stats["last_failure"]).isoformat()
            
        if not service_info["healthy"]:
            healthy = False
            
        services.append(service_info)
        
    return {
        "healthy": healthy,
        "failure_streak": failure_streak,
        "services": services,
        "last_check": datetime.now().isoformat(),
        "host": socket.gethostname(),
    }

# ------------------------------
# Healthcheck runner
# ------------------------------

async def run_checks(targets: List[Dict[str, Any]], interval: int = CHECK_INTERVAL, alert_url: str = None, max_failures: int = MAX_FAILURES):
    """
    Run health checks periodically.
    
    Args:
        targets: List of targets to check
        interval: Interval between checks in seconds
        alert_url: URL to send alerts to
        max_failures: Maximum number of consecutive failures before restarting
    """
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
            timeout = target.get("timeout", 5)
            
            if type_ == "http":
                tasks.append(check_http_target(
                    name, url, target.get("expect_status", 200), 
                    failures, recoveries, timeout
                ))
            elif type_ == "redis":
                tasks.append(check_redis_target(
                    name, url, failures, recoveries, timeout
                ))
            elif type_ == "postgres":
                tasks.append(check_postgres_target(
                    name, url, failures, recoveries, timeout
                ))
            elif type_ == "command":
                command = target.get("command", [])
                if command:
                    tasks.append(check_custom_command(
                        name, command, failures, recoveries, timeout
                    ))
                else:
                    print(f"⚠️ Missing command for custom check: {name}")
            else:
                print(f"⚠️ Unknown check type '{type_}' for target {name}")

        await asyncio.gather(*tasks)

        # If failures detected
        if failures:
            # Prepare alert information
            alert_urls = {}
            if alert_url:
                alert_urls["slack"] = alert_url
            if TEAMS_ALERT_URL:
                alert_urls["teams"] = TEAMS_ALERT_URL
            if EMAIL_ALERT:
                alert_urls["email"] = EMAIL_ALERT
                
            combined_message = "🚨 Healthcheck Failures:\n" + "\n".join(failures)
            await send_alert(combined_message, alert_urls)
            healthchecks.set_health_message(combined_message)

            failure_streak += 1
            last_failure_time = time.time()

            print(f"⚠️ Failure streak count: {failure_streak}")

            # If too many failures, try to restart services
            if failure_streak >= MAX_FAILURES:
                print(f"🚨 Too many consecutive failures ({failure_streak}). Attempting to restart services...")
                restart_success = await restart_service("api_and_worker")
                
                if restart_success:
                    # Reset failure counter after successful restart
                    failure_streak = 0
                    print("✅ Services restarted successfully.")
                else:
                    # If restart failed, send critical alert
                    critical_message = f"🔥 CRITICAL: Failed to restart services after {failure_streak} consecutive check failures. Manual intervention required!"
                    await send_alert(critical_message, alert_urls)
        else:
            # No failures detected
            if last_failure_time and (time.time() - last_failure_time > FAILURE_RESET_TIME):
                print("✅ Resetting failure streak (system stable).")
                failure_streak = 0
                last_failure_time = None
                restart_attempts = 0  # Reset restart attempts as well
                healthchecks.set_health_message("All systems operational")

        # If recoveries detected
        if recoveries:
            combined_message = "✅ Recoveries:\n" + "\n".join(recoveries)
            await send_alert(combined_message)
            healthchecks.set_health_message(combined_message)

        # Update health status
        healthchecks.status_info = get_health_status()

        await asyncio.sleep(interval)

# ------------------------------
# Public API
# ------------------------------

def launch_healthchecks(targets: List[Dict[str, Any]], interval: int = CHECK_INTERVAL, alert_url: str = None, max_failures: int = MAX_FAILURES):
    """
    Launch healthchecks asynchronously.

    Example:
        launch_healthchecks([
            {"type": "http", "name": "API", "url": "http://localhost:8000/healthz"},
            {"type": "redis", "name": "Redis", "url": "redis://localhost:6379"},
            {"type": "postgres", "name": "Postgres", "url": "postgresql://user:pass@localhost:5432/db"},
            {"type": "command", "name": "Disk Space", "command": ["df", "-h", "/"]},
        ])
        
    Args:
        targets: List of targets to check
        interval: Interval between checks in seconds
        alert_url: URL to send alerts to (Slack webhook)
        max_failures: Maximum number of consecutive failures before restarting
    """
    asyncio.run(run_checks(targets, interval, alert_url, max_failures))