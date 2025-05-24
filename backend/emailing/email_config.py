from typing import Dict, List, Optional, Union, Any

class EmailConfig:
    """
    Configuration for email operations.
    
    This class provides configuration options for email sending,
    including provider settings, default values, and system-wide
    behavior for email operations.
    """
    
    def __init__(
        self,
        provider: str = "smtp",
        from_address: Optional[str] = None,
        reply_to: Optional[str] = None,
        default_subject_prefix: str = "",
        max_file_size_mb: int = 25,
        **provider_settings
    ):
        """
        Initialize email configuration.
        
        Args:
            provider: Email provider to use ("smtp", "aws_ses", "sendgrid")
            from_address: Default sender email address
            reply_to: Default reply-to address
            default_subject_prefix: Prefix added to all email subjects 
            max_file_size_mb: Maximum attachment size in MB
            **provider_settings: Provider-specific configuration options
        """
        self.provider = provider
        self.from_address = from_address
        self.reply_to = reply_to
        self.default_subject_prefix = default_subject_prefix
        self.max_file_size_mb = max_file_size_mb
        
        # Provider-specific settings
        self.provider_settings = provider_settings
        
        # Validate the configuration
        self._validate_config()
        
    def _validate_config(self):
        """Validate configuration values and adjust if necessary."""
        valid_providers = ["smtp", "aws_ses", "sendgrid"]
        if self.provider not in valid_providers:
            raise ValueError(f"Invalid provider: {self.provider}. Must be one of {valid_providers}")
            
        if self.max_file_size_mb <= 0:
            raise ValueError(f"max_file_size_mb must be positive, got {self.max_file_size_mb}")
                
    def with_overrides(self, **overrides):
        """
        Create a new configuration with specific overrides.
        
        Args:
            **overrides: Configuration parameters to override
            
        Returns:
            A new EmailConfig instance with overridden values
        """
        # Start with current config
        config_dict = self.to_dict()
        
        # Update with overrides
        config_dict.update(overrides)
        
        # Create new instance
        return EmailConfig(**config_dict)
        
    def get_provider_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a provider-specific setting.
        
        Args:
            key: Setting name
            default: Default value if setting not found
            
        Returns:
            Setting value or default if not found
        """
        return self.provider_settings.get(key, default)
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration
        """
        config_dict = {
            "provider": self.provider,
            "from_address": self.from_address,
            "reply_to": self.reply_to,
            "default_subject_prefix": self.default_subject_prefix,
            "max_file_size_mb": self.max_file_size_mb,
        }
        
        # Add provider settings
        config_dict.update(self.provider_settings)
        
        return config_dict