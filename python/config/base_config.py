import hashlib
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Set


class ConfigInterface(ABC):
    """
    Abstract interface defining the contract for all configuration classes.
    Ensures consistent behavior across all configuration types.
    """
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration
        """
        pass
    
    @abstractmethod
    def hash(self) -> str:
        """
        Generate a stable hash for the configuration.
        
        Returns:
            Hash string for the configuration
        """
        pass
    
    @abstractmethod
    def _get_hash_data(self) -> Dict[str, Any]:
        """
        Get the data to be used for hash generation.
        Should exclude sensitive fields like passwords.
        
        Returns:
            Dictionary of data for hash generation
        """
        pass
    
    @abstractmethod
    def _validate_config(self) -> None:
        """
        Validate configuration parameters.
        
        Raises:
            ValueError: If configuration is invalid
        """
        pass


class BaseConfig(ConfigInterface):
    """
    Base configuration class providing common functionality.
    
    Implements consistent hash generation, update methods, and validation
    patterns that can be inherited by all configuration classes.
    """
    
    # Set of sensitive field names that should be excluded from hashing
    SENSITIVE_FIELDS: Set[str] = {'password', 'redis_url', 'url'}
    
    def __init__(self):
        """Initialize base configuration."""
        # Call validation after initialization in subclasses
        pass
    
    def hash(self) -> str:
        """
        Generate a stable hash for the configuration.
        Excludes sensitive fields for security.
        
        Returns:
            16-character hash string
        """
        hash_data = self._get_hash_data()
        config_str = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]
    
    def _get_hash_data(self) -> Dict[str, Any]:
        """
        Default implementation that excludes sensitive fields.
        Can be overridden by subclasses for custom behavior.
        
        Returns:
            Dictionary of data for hash generation
        """
        data = self.to_dict().copy()
        
        # Remove sensitive fields
        for field in self.SENSITIVE_FIELDS:
            data.pop(field, None)
        
        # Mask URLs that might contain passwords
        for key, value in data.items():
            if isinstance(value, str) and ('://' in value and '@' in value):
                data[key] = self._mask_url(value)
        
        return data
    
    def _mask_url(self, url: str) -> str:
        """
        Mask password in URL for security.
        
        Args:
            url: URL potentially containing credentials
            
        Returns:
            URL with password masked
        """
        if not url or '://' not in url:
            return url
        
        try:
            parts = url.split('://', 1)
            protocol = parts[0]
            rest = parts[1]
            
            if '@' in rest:
                auth_host_parts = rest.split('@', 1)
                auth_part = auth_host_parts[0]
                host_part = auth_host_parts[1]
                
                if ':' in auth_part:
                    user_pass = auth_part.split(':', 1)
                    user = user_pass[0]
                    return f"{protocol}://{user}:****@{host_part}"
                else:
                    return f"{protocol}://{auth_part}@{host_part}"
            
            return url
        except Exception:
            return f"{protocol}://****"
    
    def update(self, **kwargs) -> 'BaseConfig':
        """
        Update configuration values at runtime.
        
        Args:
            **kwargs: Configuration values to update
            
        Returns:
            Self for method chaining
            
        Raises:
            ValueError: If unknown parameter provided
        """
        for key, value in kwargs.items():
            # Look for private attributes first (e.g., _field_name)
            private_attr = f'_{key}'
            if hasattr(self, private_attr):
                setattr(self, private_attr, value)
            # Then check for public attributes
            elif hasattr(self, key):
                setattr(self, key, value)
            else:
                raise ValueError(f"Unknown configuration parameter: {key}")
        
        # Re-validate after updates
        self._validate_config()
        return self
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseConfig':
        """
        Create configuration instance from dictionary.
        Default implementation - should be overridden by subclasses.
        
        Args:
            data: Configuration dictionary
            
        Returns:
            Configuration instance
        """
        raise NotImplementedError("Subclasses must implement from_dict method")
    
    def _validate_config(self) -> None:
        """
        Default validation - can be overridden by subclasses.
        """
        pass
    
    def __repr__(self) -> str:
        """String representation with sensitive fields masked."""
        class_name = self.__class__.__name__
        config_dict = self.to_dict()
        
        # Mask sensitive information
        for field in self.SENSITIVE_FIELDS:
            if field in config_dict:
                config_dict[field] = '****'
        
        # Create a concise representation
        key_items = []
        for key, value in config_dict.items():
            if isinstance(value, dict):
                key_items.append(f"{key}={{...}}")
            else:
                key_items.append(f"{key}={value}")
        
        return f"{class_name}({', '.join(key_items[:3])}{'...' if len(key_items) > 3 else ''})"