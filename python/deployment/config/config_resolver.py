from typing import Dict, Any, List
from .deployment_config import DeploymentConfig


class ConfigurationResolver:
    """
    Responsible for resolving configuration values from injection configs.
    Separate from Docker concerns.
    """
    
    def __init__(self, deployment_config: DeploymentConfig):
        self.config = deployment_config
    
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
            else:
                raise ValueError(f"Property '{prop}' not found on {type(current_obj).__name__}")
        
        return current_obj
    
    def resolve_all_config_values(self, mask_sensitive: bool = True) -> Dict[str, str]:
        """
        Resolve all configured config mappings to their values.
        
        Returns:
            Dictionary of resolved configuration values
        """
        resolved = {}
        
        # Start with static build args
        resolved.update(self.config.build_args)
        
        # Add resolved configuration values
        for build_arg_name, config_path in self.config.config_mapping.items():
            try:
                value = self.resolve_config_value(config_path)
                
                # Convert to string for build args
                if value is None:
                    resolved[build_arg_name] = ""
                elif isinstance(value, bool):
                    resolved[build_arg_name] = "true" if value else "false"
                else:
                    resolved[build_arg_name] = str(value)
                    
            except ValueError as e:
                print(f"Warning: Could not resolve config path '{config_path}': {e}")
                resolved[build_arg_name] = ""
        
        # Mask sensitive values if requested
        if mask_sensitive:
            for arg_name, config_path in self.config.config_mapping.items():
                if config_path in self.config._sensitive_configs:
                    if arg_name in resolved:
                        resolved[arg_name] = "***MASKED***"
        
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