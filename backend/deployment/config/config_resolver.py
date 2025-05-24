from typing import Dict, Any, List
from .deployment_config import DeploymentConfig


class ConfigurationResolver:
    """
    Responsible for resolving configuration values from injection configs.
    Separate from Docker concerns.
    """
    
    def __init__(self, deployment_config: DeploymentConfig):
        self.config = deployment_config
        # Initialize sensitive configs set
        self._sensitive_configs = getattr(deployment_config, '_sensitive_configs', set())
    
    def resolve_config_value(self, config_path: str) -> Any:
        """
        Resolve a configuration value by path.
        
        Args:
            config_path: Dot-separated path like "database.host"
            
        Returns:
            Resolved configuration value
        """
        parts = config_path.split('.')
        
        if len(parts) < 2:
            raise ValueError(f"Invalid config path: {config_path}")
        
        config_name = parts[0]
        property_path = parts[1:]
        
        if config_name not in self.config.config_injection:
            raise ValueError(f"Configuration object '{config_name}' not found")
        
        # Get the configuration object
        current_obj = self.config.config_injection[config_name]
        
        # Navigate through the property path
        for prop in property_path:
            if hasattr(current_obj, prop):
                attr = getattr(current_obj, prop)
                current_obj = attr() if callable(attr) else attr
            elif hasattr(current_obj, f'_{prop}'):  # Check for private attributes
                attr = getattr(current_obj, f'_{prop}')
                current_obj = attr() if callable(attr) else attr
            else:
                raise ValueError(f"Property '{prop}' not found on {type(current_obj).__name__}")
        
        return current_obj

    def resolve_all_config_values(self, mask_sensitive: bool = True) -> Dict[str, str]:
        """
        Resolve all configured config mappings to their values using reflection.
        
        Returns:
            Dictionary of resolved configuration values
        """
        resolved = {}
        
        # Start with static build args
        resolved.update(self.config.build_args)
        
        # Use reflection to automatically discover and inject config values
        resolved.update(self._resolve_by_reflection(mask_sensitive))        
 
        return resolved

    def _resolve_by_reflection(self, mask_sensitive: bool = True) -> Dict[str, str]:
        """Use reflection to automatically inject all config properties."""
        resolved = {}
        
        for config_name, config_obj in self.config.config_injection.items():
            # Get all public properties
            for attr_name in dir(config_obj):
                if attr_name.startswith('_') or callable(getattr(config_obj, attr_name, None)):
                    continue
                    
                try:
                    value = getattr(config_obj, attr_name)
                    
                    # Convert to string
                    if value is None:
                        str_value = ""
                    elif isinstance(value, bool):
                        str_value = "true" if value else "false"
                    else:
                        str_value = str(value)
                    
                    # Check for sensitive data
                    config_path = f"{config_name}.{attr_name}"
                    if mask_sensitive and config_path in self.config._sensitive_configs:
                        str_value = "***MASKED***"
                    
                    # Simple mapping: property name = build arg name
                    resolved[attr_name] = str_value
                    
                except Exception as e:
                    print(f"Warning: Could not resolve {config_name}.{attr_name}: {e}")
        
        return resolved
      
    def validate_config_mappings(self) -> List[str]:
        """
        Validate that all config mappings can be resolved.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        for build_arg_name, config_path in self.config.config_mapping.items():
            try:
                self.resolve_config_value(config_path)
            except Exception as e:
                errors.append(f"Config mapping '{build_arg_name}' -> '{config_path}': {e}")
        
        return errors