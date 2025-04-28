"""
Central configuration module for managing application settings.

This module provides a unified way to access configuration from various sources
with a clear precedence:
1. Environment variables (highest priority)
2. Configuration files (.env, .yaml, .json)
3. Default values (lowest priority)

Example:
    from config import Config
    
    # Get a single config value
    db_host = Config.get('database.host', 'localhost')
    
    # Get a config section as a dictionary
    db_config = Config.get_section('database')
    
    # Get a typed config value
    port = Config.get_int('database.port', 5432)
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Set, TypeVar, Callable, cast

# Try to import optional dependencies
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    import dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# Type variable for generic functions
T = TypeVar('T')

class ConfigError(Exception):
    """Exception raised for configuration errors."""
    pass

class Config:
    """
    Central configuration management.
    
    This class provides static methods for accessing configuration values
    from various sources with proper precedence.
    """
    
    # Cache of loaded configuration
    _config: Dict[str, Any] = {}
    
    # Set of fully loaded config files
    _loaded_files: Set[str] = set()
    
    # Environment variable overrides
    _env_prefix = ""
    
    # Default paths to look for config files
    _default_paths = [
        "./config.yml",
        "./config.yaml",
        "./config.json",
        "./config/.env",
        "./.env",
    ]
    
    # Lock to prevent reloading config during an active get operation
    _loading = False
    
    @classmethod
    def initialize(cls, config_file: Optional[str] = None, env_prefix: str = "", default_config: Dict[str, Any] = None) -> None:
        """
        Initialize the configuration system.
        
        Args:
            config_file: Path to the main configuration file (optional)
            env_prefix: Prefix for environment variables (e.g., "APP_")
            default_config: Default configuration values
            
        This method will:
        1. Set the environment variable prefix
        2. Load specified config file if provided
        3. Set default values from default_config
        """
        # Reset state
        cls._config = {}
        cls._loaded_files = set()
        cls._env_prefix = env_prefix
        
        # Add default config if provided
        if default_config:
            cls._config = default_config.copy()
            
        # Load specified config file if provided
        if config_file:
            cls.load_file(config_file)
        else:
            # Try to load from default locations
            for path in cls._default_paths:
                if os.path.exists(path):
                    cls.load_file(path)
                    break
        
        # Load environment variables
        if DOTENV_AVAILABLE:
            # Try to load .env file
            for env_path in ["./.env", "./config/.env"]:
                if os.path.exists(env_path) and env_path not in cls._loaded_files:
                    dotenv.load_dotenv(env_path)
                    cls._loaded_files.add(env_path)
        
        # Apply environment variable overrides
        cls._load_from_env()
    
    @classmethod
    def load_file(cls, file_path: str) -> None:
        """
        Load configuration from a file.
        
        Args:
            file_path: Path to the configuration file
            
        Raises:
            ConfigError: If the file can't be loaded
        """
        if not os.path.exists(file_path):
            raise ConfigError(f"Configuration file not found: {file_path}")
        
        # Skip if already loaded
        if file_path in cls._loaded_files:
            return
            
        try:
            extension = os.path.splitext(file_path)[1].lower()
            
            if extension in ('.yml', '.yaml'):
                if not YAML_AVAILABLE:
                    raise ConfigError("YAML configuration requires PyYAML library")
                with open(file_path, 'r') as f:
                    yaml_config = yaml.safe_load(f)
                    if yaml_config:
                        cls._deep_update(cls._config, yaml_config)
                        
            elif extension == '.json':
                with open(file_path, 'r') as f:
                    json_config = json.load(f)
                    if json_config:
                        cls._deep_update(cls._config, json_config)
                        
            elif extension == '.env':
                if DOTENV_AVAILABLE:
                    dotenv.load_dotenv(file_path)
                else:
                    raise ConfigError("Loading .env files requires python-dotenv library")
            else:
                raise ConfigError(f"Unsupported configuration file format: {extension}")
                
            cls._loaded_files.add(file_path)
            
        except Exception as e:
            raise ConfigError(f"Failed to load configuration from {file_path}: {e}")
    
    @classmethod
    def _load_from_env(cls) -> None:
        """
        Load configuration from environment variables.
        
        Environment variables like APP_DATABASE_HOST will be converted to
        nested dictionary keys like {"database": {"host": value}}.
        """
        prefix = cls._env_prefix.upper()
        prefix_len = len(prefix)
        
        for key, value in os.environ.items():
            # Skip if not using our prefix
            if prefix and not key.startswith(prefix):
                continue
                
            # Remove prefix
            if prefix:
                env_key = key[prefix_len:]
            else:
                env_key = key
                
            # Skip if empty
            if not env_key:
                continue
                
            # Convert to lowercase for consistency
            env_key = env_key.lower()
            
            # Replace double underscores with dots for section separation
            # e.g. DATABASE__HOST -> database.host
            env_key = env_key.replace('__', '.')
            
            # Replace single underscores with dots for nested keys
            # e.g. DATABASE_HOST -> database.host
            env_key = env_key.replace('_', '.')
            
            # Set in config
            cls._set_nested(cls._config, env_key, value)
    
    @classmethod
    def _deep_update(cls, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """
        Recursively update a dictionary with another dictionary.
        
        Args:
            target: Dictionary to update
            source: Dictionary with updates
        """
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                # Recursively update nested dictionaries
                cls._deep_update(target[key], value)
            else:
                # Replace or add values
                target[key] = value
    
    @classmethod
    def _set_nested(cls, config: Dict[str, Any], key_path: str, value: Any) -> None:
        """
        Set a value in a nested dictionary using a dot-separated key path.
        
        Args:
            config: Dictionary to update
            key_path: Dot-separated path to the key
            value: Value to set
        """
        keys = key_path.split('.')
        current = config
        
        # Navigate to the last parent
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
            
        # Set the value
        current[keys[-1]] = cls._parse_env_value(value)
    
    @classmethod
    def _parse_env_value(cls, value: str) -> Any:
        """
        Parse an environment variable value to the appropriate type.
        
        Args:
            value: String value from environment variable
            
        Returns:
            The value converted to the appropriate type
        """
        if value.lower() in ('true', 'yes', 'y', '1'):
            return True
        elif value.lower() in ('false', 'no', 'n', '0'):
            return False
        elif value.lower() in ('none', 'null'):
            return None
        elif value.isdigit():
            return int(value)
        elif re.match(r'^-?\d+(\.\d+)?$', value):
            return float(value)
        else:
            return value
    
    @classmethod
    def _get_nested(cls, key_path: str, default: Any = None) -> Any:
        """
        Get a value from the configuration using a dot-separated key path.
        
        Args:
            key_path: Dot-separated path to the key
            default: Default value if key not found
            
        Returns:
            The configuration value or default
        """
        if not key_path:
            return cls._config
            
        keys = key_path.split('.')
        current = cls._config
        
        # Navigate through the keys
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
            
        return current
    
    @classmethod
    def get(cls, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key_path: Dot-separated path to the key
            default: Default value if key not found
            
        Returns:
            The configuration value or default
            
        Example:
            host = Config.get('database.host', 'localhost')
        """
        return cls._get_nested(key_path, default)
    
    @classmethod
    def get_typed(cls, key_path: str, default: T, type_converter: Callable[[Any], T]) -> T:
        """
        Get a configuration value and convert it to a specific type.
        
        Args:
            key_path: Dot-separated path to the key
            default: Default value if key not found
            type_converter: Function to convert the value to the desired type
            
        Returns:
            The configuration value converted to the specified type
            
        Example:
            port = Config.get_typed('database.port', 5432, int)
        """
        value = cls._get_nested(key_path, default)
        try:
            return type_converter(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    @classmethod
    def get_int(cls, key_path: str, default: int = 0) -> int:
        """
        Get an integer configuration value.
        
        Args:
            key_path: Dot-separated path to the key
            default: Default value if key not found
            
        Returns:
            The configuration value as an integer
            
        Example:
            port = Config.get_int('database.port', 5432)
        """
        return cls.get_typed(key_path, default, int)
    
    @classmethod
    def get_float(cls, key_path: str, default: float = 0.0) -> float:
        """
        Get a float configuration value.
        
        Args:
            key_path: Dot-separated path to the key
            default: Default value if key not found
            
        Returns:
            The configuration value as a float
            
        Example:
            timeout = Config.get_float('api.timeout', 30.0)
        """
        return cls.get_typed(key_path, default, float)
    
    @classmethod
    def get_bool(cls, key_path: str, default: bool = False) -> bool:
        """
        Get a boolean configuration value.
        
        Args:
            key_path: Dot-separated path to the key
            default: Default value if key not found
            
        Returns:
            The configuration value as a boolean
            
        Example:
            debug = Config.get_bool('app.debug', False)
        """
        value = cls._get_nested(key_path, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', 'y', '1')
        return bool(value)
    
    @classmethod
    def get_list(cls, key_path: str, default: List[Any] = None) -> List[Any]:
        """
        Get a list configuration value.
        
        Args:
            key_path: Dot-separated path to the key
            default: Default value if key not found
            
        Returns:
            The configuration value as a list
            
        Example:
            hosts = Config.get_list('redis.hosts', ['localhost'])
        """
        if default is None:
            default = []
            
        value = cls._get_nested(key_path, default)
        
        if isinstance(value, str):
            # Try to parse comma-separated values
            return [v.strip() for v in value.split(',')]
        elif isinstance(value, list):
            return value
        elif value is None:
            return default
        else:
            # Convert single value to a list
            return [value]
    
    @classmethod
    def get_dict(cls, key_path: str, default: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get a dictionary configuration value.
        
        Args:
            key_path: Dot-separated path to the key
            default: Default value if key not found
            
        Returns:
            The configuration value as a dictionary
            
        Example:
            db_config = Config.get_dict('database', {'host': 'localhost'})
        """
        if default is None:
            default = {}
            
        value = cls._get_nested(key_path, default)
        
        if isinstance(value, dict):
            return value
        else:
            return default
    
    @classmethod
    def get_section(cls, section: str) -> Dict[str, Any]:
        """
        Get an entire configuration section.
        
        Args:
            section: Name of the configuration section
            
        Returns:
            Dictionary containing the section configuration
            
        Example:
            db_config = Config.get_section('database')
        """
        return cls.get_dict(section, {})
    
    @classmethod
    def set(cls, key_path: str, value: Any) -> None:
        """
        Set a configuration value.
        
        Args:
            key_path: Dot-separated path to the key
            value: Value to set
            
        Example:
            Config.set('database.host', 'localhost')
        """
        cls._set_nested(cls._config, key_path, value)
    
    @classmethod
    def reload(cls) -> None:
        """
        Reload configuration from all previously loaded files.
        
        This will reset the configuration to defaults and reload all files
        that were previously loaded.
        """
        # Remember loaded files
        loaded_files = list(cls._loaded_files)
        
        # Reset state but keep env prefix
        env_prefix = cls._env_prefix
        cls._config = {}
        cls._loaded_files = set()
        
        # Reload files
        for file_path in loaded_files:
            cls.load_file(file_path)
            
        # Reload environment variables
        cls._load_from_env()
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """
        Get the entire configuration as a dictionary.
        
        Returns:
            Dictionary containing all configuration values
            
        Example:
            config_dict = Config.to_dict()
        """
        return cls._config.copy()

# Initialize configuration on module import
Config.initialize()