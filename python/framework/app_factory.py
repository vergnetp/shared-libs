# shared_libs/framework/app_factory.py
from fastapi import FastAPI
import os
from pathlib import Path
import secrets

from ..log import init_logger, info
from ..databases import DatabaseFactory
from .deployment.docker import generate_docker_compose
from .deployment.deployment import generate_deployment_scripts

class AppFactory:
    """
    Factory for creating and configuring FastAPI applications with
    all necessary components.
    """
    
    def __init__(self, config, setup_infrastructure=True):
        """
        Initialize the AppFactory with configuration.
        
        Args:
            config: The application configuration object
            setup_infrastructure: Whether to generate infrastructure files
        """
        self.config = config
        
        # Override environment from ENV if specified
        env_override = os.getenv("ENV")
        if env_override:
            if env_override in ("dev", "test", "staging", "prod"):
                self.config.environment = env_override
        
        # Initialize logging
        init_logger(
            service_name=self.config.app_name,
            min_level=os.getenv("LOG_LEVEL", "INFO")
        )
        
        info(f"Initializing application: {self.config.app_name} ({self.config.environment})")
        
        # Generate infrastructure files if requested
        if setup_infrastructure:
            self._setup_infrastructure()
    
    def _setup_infrastructure(self):
        """Generate infrastructure files based on configuration."""
        # Get current directory (project root)
        project_dir = os.getcwd()
        
        # Check if docker-compose.yml exists
        docker_compose_path = os.path.join(project_dir, "docker-compose.yml")
        if not os.path.exists(docker_compose_path):
            info("Generating docker-compose.yml...")
            generate_docker_compose(self.config, docker_compose_path)
        
        # Check if deployment scripts exist
        deployment_dir = os.path.join(project_dir, "deployment")
        if not os.path.exists(os.path.join(deployment_dir, "deploy.sh")):
            info("Generating deployment scripts...")
            generate_deployment_scripts(self.config, deployment_dir)
    
    def create_app(self) -> FastAPI:
        """
        Create and configure a FastAPI application with all components.
        
        Returns:
            FastAPI: The configured FastAPI application
        """
        from .base_app import create_base_app
        
        # Create the base app
        app = create_base_app()
        
        # Add startup and shutdown events
        @app.on_event("startup")
        async def startup_event():
            await self._initialize_services(app)
        
        @app.on_event("shutdown")
        async def shutdown_event():
            await self._cleanup_services(app)
        
        return app
    
    async def _initialize_services(self, app: FastAPI):
        """Initialize services based on configuration."""
        info(f"Initializing services for {self.config.app_name}...")
        
        # Initialize database if configured
        if self.config.database:
            # Get password from environment variable
            db_password = os.getenv(self.config.database.password_env_var)
            
            try:
                db = DatabaseFactory(
                    self.config.database.type,
                    database=self.config.database.database,
                    host=self.config.database.host,
                    port=self.config.database.port,
                    user=self.config.database.user,
                    password=db_password,
                    alias=self.config.app_name
                )
                app.state.db = db
                info(f"Database connection established: {self.config.database.type}")
            except Exception as e:
                info(f"Failed to connect to database: {e}")
        
        # Initialize Redis if configured
        if self.config.redis and self.config.redis.enabled:
            try:
                import aioredis
                
                # Get password from environment variable if specified
                redis_password = None
                if self.config.redis.password_env_var:
                    redis_password = os.getenv(self.config.redis.password_env_var)
                
                redis = await aioredis.from_url(
                    f"redis://{self.config.redis.host}:{self.config.redis.port}",
                    password=redis_password,
                    encoding="utf-8",
                    decode_responses=True
                )
                app.state.redis = redis
                info("Redis connection established")
            except ImportError:
                info("aioredis package not available. Redis functionality disabled.")
            except Exception as e:
                info(f"Failed to connect to Redis: {e}")
    
    async def _cleanup_services(self, app: FastAPI):
        """Clean up services during shutdown."""
        info(f"Cleaning up services for {self.config.app_name}...")
        
        # Close database connection
        if hasattr(app.state, "db"):
            try:
                await app.state.db.close_async()
                info("Database connection closed")
            except Exception as e:
                info(f"Error closing database connection: {e}")
        
        # Close Redis connection
        if hasattr(app.state, "redis"):
            try:
                await app.state.redis.close()
                info("Redis connection closed")
            except Exception as e:
                info(f"Error closing Redis connection: {e}")