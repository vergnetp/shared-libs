"""
Framework module: expose a base web service app (FastAPI) that has some built in health checks, health status, metrics logging
"""
from fastapi import FastAPI
from .app_factory import AppFactory
from .config import AppConfig
from .context import *

def create_app(config: AppConfig) -> FastAPI:
    """
    Create and configure a new FastAPI application with all components.
    
    Args:
        config (shared_libs.framework.config.AppConfig): The application configuration
    
    Returns:
        FastAPI: The configured FastAPI application
    
    Example:
        from shared_libs.framework import create_app, AppConfig, DatabaseConfig, RedisConfig
        
        config = AppConfig(
            app_name="project1",
            environment="dev",  # Can be overridden by ENV env variable
            database=DatabaseConfig(
                type="postgres",
                host="localhost",
                port=5432,
                database="project1_db",
                user="postgres",
                password_env_var="PROJECT1_DB_PASSWORD"
            ),
            redis=RedisConfig(
                enabled=True,
                host="localhost"
            )
        )

        app = create_app(config)
        
        @app.get("/hello")
        async def hello():
            return {"message": "Hello World"}
    """
    factory = AppFactory(config)
    return factory.create_app()