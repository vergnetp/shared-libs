"""
Example of how to integrate the new configuration system with the existing code.
"""
from typing import Dict, Any
import os


# Import the new config system
from ..utils import Config


# For database initialization
from databases import DatabaseFactory
from log import init_logger, info, error, critical
from.config import AppConfig

def initialize_app():
    """
    Initialize the application with the new configuration system.
    
    This function:
    1. Loads and validates configuration
    2. Sets up logging
    3. Initializes database connections
    4. Configures other components based on settings
    """
    # Initialize configuration with environment variables and config files
    config_file = os.getenv("CONFIG_FILE", "config.yml")
    
    try:
        Config.initialize(
            config_file=config_file if os.path.exists(config_file) else None,
            env_prefix="APP_",
            default_config={
                "app": {
                    "name": "default-service",
                    "environment": "development",
                    "debug": False,
                    "port": 8000
                },
                "database": {
                    "type": "sqlite",
                    "database": "app.db"
                },
                "logging": {
                    "level": "INFO",
                    "use_redis": False
                }
            }
        )
        
        # Validate configuration
        full_config = Config.to_dict()
        try:
            db_config = AppConfig(**full_config)
        except Exception as e:
            print(f"Invalid database configuration: {e}")
                
        # Set up logging first
        logging_config = Config.get_section("logging")
        init_logger(
            service_name=Config.get("app.name", "default-service"),
            redis_url=Config.get("redis.url") if Config.get_bool("logging.use_redis", False) else None,
            min_level=logging_config.get("level", "INFO"),
            log_debug_to_file=logging_config.get("log_debug_to_file", False)
        )
        
        # Log successful configuration
        info(f"Application {Config.get('app.name')} configured for {Config.get('app.environment')} environment")
        
        # Initialize database
        db_config = Config.get_section("database")
        db = DatabaseFactory(
            db_type=db_config.get("type", "sqlite"),
            database=db_config.get("database"),
            host=db_config.get("host"),
            port=db_config.get("port"),
            user=db_config.get("user"),
            password=db_config.get("password"),
            alias=Config.get("app.name")
        )
        
        # Set up Redis connection if configured
        redis_conn = None
        if Config.get_bool("redis.enabled", False):
            try:
                import aioredis
                redis_config = Config.get_section("redis")
                
                # Format Redis URL from config
                redis_url = f"redis://{redis_config.get('host', 'localhost')}:{redis_config.get('port', 6379)}"
                
                # Async function to create the connection
                async def create_redis():
                    return await aioredis.from_url(redis_url)
                
                # We'll use this in the startup event of FastAPI
                redis_conn = {
                    "url": redis_url,
                    "creator": create_redis
                }
                
                info(f"Redis configured at {redis_url}")
            except ImportError:
                error("Redis is enabled but aioredis is not installed")
        
        # Set up health checks if enabled
        if Config.get_bool("healthcheck.enabled", False):
            from framework.healthchecks import launch_healthchecks
            
            # Get healthcheck targets
            targets = []
            
            # Add API healthcheck if configured
            if Config.get("healthcheck.api_url"):
                targets.append({
                    "type": "http",
                    "name": "API",
                    "url": Config.get("healthcheck.api_url"),
                    "expect_status": Config.get_int("healthcheck.api_status", 200)
                })
                
            # Add database healthcheck if configured
            if Config.get_bool("healthcheck.monitor_database", True):
                if db_config.get("type") == "postgres":
                    targets.append({
                        "type": "postgres",
                        "name": "Database",
                        "url": f"postgresql://{db_config.get('user')}:{db_config.get('password')}@{db_config.get('host', 'localhost')}:{db_config.get('port', 5432)}/{db_config.get('database')}",
                    })
                elif db_config.get("type") == "mysql":
                    targets.append({
                        "type": "mysql",
                        "name": "Database",
                        "url": f"mysql://{db_config.get('user')}:{db_config.get('password')}@{db_config.get('host', 'localhost')}:{db_config.get('port', 3306)}/{db_config.get('database')}",
                    })
                    
            # Add Redis healthcheck if configured
            if Config.get_bool("redis.enabled", False) and Config.get_bool("healthcheck.monitor_redis", True):
                targets.append({
                    "type": "redis",
                    "name": "Redis",
                    "url": redis_url,
                })
                
            # Launch healthchecks if any targets are configured
            if targets:
                # Start in a separate thread to not block
                import threading
                healthcheck_thread = threading.Thread(
                    target=launch_healthchecks,
                    args=(targets,),
                    kwargs={
                        "interval": Config.get_int("healthcheck.interval", 300),
                        "alert_url": Config.get("healthcheck.alert_url"),
                        "max_failures": Config.get_int("healthcheck.max_failures", 3)
                    },
                    daemon=True
                )
                healthcheck_thread.start()
                info(f"Health checks started with {len(targets)} targets")
        
        # Return initialized components
        return {
            "db": db,
            "redis": redis_conn,
            "config": Config
        }
    
    except Exception as e:
        critical(f"Failed to initialize application: {e}")
        raise
        
if __name__ == "__main__":
    # Example usage
    try:
        components = initialize_app()
        print(f"Application initialized with database: {components['db'].type()}")
    except Exception as e:
        print(f"Initialization failed: {e}")