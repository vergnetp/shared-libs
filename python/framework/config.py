# shared_libs/framework/config.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal, Dict, Any

class DatabaseConfig(BaseModel):
    """Database configuration for the application."""
    type: Literal["postgres", "mysql", "sqlite"] = Field(..., description="Database type")
    host: Optional[str] = Field(None, description="Database host (not required for SQLite)")
    port: Optional[int] = Field(None, description="Database port")
    database: str = Field(..., description="Database name")
    user: Optional[str] = Field(None, description="Database user")
    password_env_var: str = Field("DB_PASSWORD", description="Environment variable name for password")

class RedisConfig(BaseModel):
    """Redis configuration."""
    enabled: bool = Field(True, description="Whether Redis is enabled")
    host: str = Field("localhost", description="Redis host")
    port: int = Field(6379, description="Redis port")
    password_env_var: Optional[str] = Field("REDIS_PASSWORD", description="Environment variable for password")

class OpenSearchConfig(BaseModel):
    """OpenSearch configuration."""
    enabled: bool = Field(False, description="Whether OpenSearch is enabled")
    host: str = Field("localhost", description="OpenSearch host")
    port: int = Field(9200, description="OpenSearch port")
    index_prefix: str = Field("logs", description="Index prefix for logs")

class DeploymentConfig(BaseModel):
    """Deployment configuration."""
    api_servers: List[str] = Field(["localhost"], description="List of servers to deploy API to")
    worker_servers: List[str] = Field(["localhost"], description="List of servers to deploy workers to")
    docker_registry: Optional[str] = Field(None, description="Docker registry URL")
    docker_username_env_var: Optional[str] = Field("DOCKER_USERNAME", description="Environment variable for Docker username")
    docker_password_env_var: Optional[str] = Field("DOCKER_PASSWORD", description="Environment variable for Docker password")

class AppConfig(BaseModel):
    """Main application configuration."""
    app_name: str = Field(..., description="Application name")
    environment: Literal["dev", "test", "staging", "prod"] = Field("dev", description="Environment")
    database: DatabaseConfig
    redis: Optional[RedisConfig] = Field(None, description="Redis configuration")
    opensearch: Optional[OpenSearchConfig] = Field(None, description="OpenSearch configuration")
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig, description="Deployment configuration")
