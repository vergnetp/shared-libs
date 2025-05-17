import threading
import importlib
from typing import Dict, Optional, Callable


class QueueCallableConfig:
    """
    Configuration for managing callable functions within the queue system.
    
    Provides a unified registry for processor functions and callbacks,
    with automated lookup by name and module.
    """
    def __init__(self, logger=None):
        """
        Initialize the callable registry.
        
        Args:
            logger: Optional logger for error reporting
        """
        self.registry = {}
        self._registry_lock = threading.RLock()
        self.logger = logger
        
    def register(self, callable_func: Callable) -> str:
        """
        Register a callable function for later use.
        
        Args:
            callable_func: The callable function to register
            
        Returns:
            Key used for the registry
        """
        with self._registry_lock:
            key = f"{callable_func.__module__}.{callable_func.__name__}"
            self.registry[key] = callable_func
            return key

    def get(self, name: str, module: str) -> Optional[Callable]:
        """
        Get a callable by name and module, attempting to import it if not found.
        
        Args:
            name: Name of the callable
            module: Module name
            
        Returns:
            Callable function or None if not found or import fails
        """
        with self._registry_lock:
            key = f"{module}.{name}"
            
            # Return cached callable if available
            if key in self.registry:
                if self.logger:
                    self.logger.debug(f"Found callable in registry: {key}")
                return self.registry[key]
            
            # Not found in registry, try dynamic import
            try:
                if self.logger:
                    self.logger.debug(f"Importing callable from module: {module}")
                mod = importlib.import_module(module)
                callable_func = getattr(mod, name)
                
                # Register for future use
                if callable(callable_func):
                    self.registry[key] = callable_func
                    if self.logger:
                        self.logger.debug(f"Successfully imported and registered callable: {key}")
                    return callable_func
            except (ImportError, AttributeError) as e:
                if self.logger:
                    self.logger.warning(
                        f"Error importing callable", 
                        module=module, 
                        name=name, 
                        error=str(e)
                    )
                    
                # Try with shorter module paths (for test modules)
                if '.' in module:
                    parts = module.split('.')
                    for i in range(1, len(parts)):
                        try_module = '.'.join(parts[:i])
                        try:
                            if self.logger:
                                self.logger.debug(f"Trying shorter module path: {try_module}")
                            mod = importlib.import_module(try_module)
                            if hasattr(mod, name):
                                callable_func = getattr(mod, name)
                                if callable(callable_func):
                                    shorter_key = f"{try_module}.{name}"
                                    self.registry[shorter_key] = callable_func
                                    # Also register with original key for future lookups
                                    self.registry[key] = callable_func
                                    if self.logger:
                                        self.logger.debug(f"Found callable in parent module: {try_module}")
                                    return callable_func
                        except ImportError:
                            continue
            
            if self.logger:
                self.logger.warning(f"Callable not found: {key}")
            return None

    def to_dict(self) -> Dict[str, Dict[str, str]]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the registered callables
        """
        with self._registry_lock:
            return {
                key: {
                    "name": key.split(".")[-1],
                    "module": ".".join(key.split(".")[:-1]),
                }
                for key in self.registry
            }