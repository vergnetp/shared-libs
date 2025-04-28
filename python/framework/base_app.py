from fastapi import FastAPI, Request
import time
import os
import uuid

from ..log import info
from . import status as platform_status
from . import context

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")

def create_base_app() -> FastAPI:
    """
    Create a base FastAPI app with:
      - /status endpoint
      - Request timing middleware
    """
    app = FastAPI()

    @app.get("/status", tags=["Healthcheck"])
    async def status():
        return platform_status.get_status_info()

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()
        request_id = str(uuid.uuid4())
        context.request_id_var.set(request_id)
        try:
            response = await call_next(request)
        except Exception as e:
            info(f"[{SERVICE_NAME}] ❌ Exception during request: {e}")
            raise

        duration = time.time() - start_time

        ip = request.client.host if request.client else "unknown"
        path = request.url.path
        method = request.method
        status_code = response.status_code

        info(f"[{SERVICE_NAME}] [{method}] {path} - {status_code} - {duration:.3f}s - IP {ip}")
       

        return response

    return app



""" /project1/main.py
from shared_libs.utils import load_env_file
from shared_libs.logging import init_logger
from shared_libs.database import init_database
from shared_libs.framework.base_app import create_base_app

# Load env
load_env_file(".env")

# Initialize shared services
init_logger(service_name="project1-api")
init_database()

# Create base app
app = create_base_app()

# Define your own routes
from fastapi import APIRouter

router = APIRouter()

@router.get("/hello")
async def hello():
    return {"message": "Hello World"}

app.include_router(router) """