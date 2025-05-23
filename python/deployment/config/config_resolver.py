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
        
        # Add manual config mappings (for overrides or special cases)
        for build_arg_name, config_path in self.config.config_mapping.items():
            try:
                if '{' in config_path and '}' in config_path:
                    resolved_value = self._resolve_interpolated_string(config_path)
                else:
                    resolved_value = self.resolve_config_value(config_path)
                
                if resolved_value is None:
                    resolved[build_arg_name] = ""
                elif isinstance(resolved_value, bool):
                    resolved[build_arg_name] = "true" if resolved_value else "false"
                else:
                    resolved[build_arg_name] = str(resolved_value)
                    
            except ValueError as e:
                print(f"Warning: Could not resolve config path '{config_path}': {e}")
                resolved[build_arg_name] = ""
        
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

    def _resolve_interpolated_string(self, template: str) -> str:
        """
        Resolve a string with interpolated config values.
        Example: "redis://:{redis.password}@{redis.host}:{redis.port}/0"
        """
        import re
        
        # Find all {config.path} patterns
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, template)
        
        result = template
        for match in matches:
            try:
                value = self.resolve_config_value(match)
                result = result.replace(f'{{{match}}}', str(value))
            except ValueError as e:
                print(f"Warning: Could not resolve interpolated value '{match}': {e}")
                # Keep the placeholder if resolution fails
                pass
        
        return result
      
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