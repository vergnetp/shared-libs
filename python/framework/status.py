import time
import os

start_time = time.time()
last_health_message = "All systems operational"

def set_health_message(message: str):
    global last_health_message
    last_health_message = message

def get_status_info():
    uptime_seconds = int(time.time() - start_time)
    return {
        "ok": True,
        "service_name": os.getenv("SERVICE_NAME", "unknown-service"),
        "uptime_seconds": uptime_seconds,
        "last_health_message": last_health_message,
    }