from pydantic import BaseSettings, BaseModel, Field, AnyUrl
from typing import Optional, Literal
import os


class SecretsConfig(BaseModel):
    database_password: str
    redis_password: Optional[str]

class RuntimeSettings(BaseModel):
    enable_beta_features: bool = False
    max_requests_per_minute: int = 1000

class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"] = "INFO"
    destination: Optional[Literal["stdout", "redis", "opensearch"]] = "stdout"
    redis_url: Optional[AnyUrl] = None
    opensearch_url: Optional[AnyUrl] = None
    opensearch_index: Optional[str] = None

class DestinationsConfig(BaseModel):
    opensearch_host: Optional[str] = None
    opensearch_port: Optional[int] = None
    postgres_host: Optional[str] = None
    postgres_db: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None

class AppConfig(BaseSettings):
    service_name: str = Field(..., description="Name of the service (used for logging etc.)")
    database_url: AnyUrl = Field(..., description="Database URL")
    redis_url: Optional[AnyUrl] = Field(None, description="Redis URL if using queue or caching")
    logging_config: Optional[LoggingConfig] = Field(default_factory=LoggingConfig, description="Logging configuration")
    destinations_config: Optional[DestinationsConfig] = Field(default_factory=DestinationsConfig, description="Destination services config")

    class Config:
        env_file = ".env"
        case_sensitive = True

class ConfigService:
    """
    Centralized ConfigService:
    - Loads environment settings (AppConfig)
    - Loads secrets securely (SecretsConfig)
    - Handles runtime feature flags (RuntimeSettings)
    """

    def __init__(self):
        self.app_config = self._load_app_config()
        self.secrets_config = self._load_secrets_config()
        self.runtime_settings = self._load_runtime_settings()

    def _load_app_config(self) -> AppConfig:
        return AppConfig()  # Auto-load from .env or passed manually

    def _load_secrets_config(self) -> SecretsConfig:
        # In future: Load from Vault etc. 
        database_password=os.environ.get("APP_DATABASE_PASSWORD", None) 
        if not database_password:
            raise RuntimeError("Missing required secret: APP_DATABASE_PASSWORD")     
        return SecretsConfig(
            database_password=database_password,
            redis_password=os.environ.get("APP_REDIS_PASSWORD", None),            
        )

    def _load_runtime_settings(self) -> RuntimeSettings:
        # Load from Redis, database, or a config API later
        return RuntimeSettings()

    def refresh_runtime_settings(self):
        """Refresh dynamic runtime config."""
        self.runtime_settings = self._load_runtime_settings()

    def refresh_secrets(self):
        """Optionally refresh secrets if your secret manager rotates them."""
        self.secrets_config = self._load_secrets_config()

"""
Example of .env:
SERVICE_NAME=project1-api
DATABASE_URL=postgresql://user:pass@localhost:5432/project1db
REDIS_URL=redis://localhost:6379

config = AppConfig() would load automatically
If fields are not valid (e.g. int instead of str), an error is raised upon config creation (before app start), thanks to pydantic
"""

