import asyncio
import datetime
import json
import uuid
import threading
from typing import Dict, Any, Optional

from .... import log as logger


class EntityUtilsMixin:
    """
    Shared utility methods for entity operations.
    
    This mixin class provides common functionality needed by both database-level
    and connection-level entity operations, including serialization/deserialization,
    type handling, and entity preparation.  
    """
    
    # Class-level lock registry
    _locks = {}
    _locks_lock = threading.RLock()
    
    # Default serializers and deserializers
    _default_serializers = {
        'dict': lambda v: json.dumps(v) if v is not None else None,
        'list': lambda v: json.dumps(v) if v is not None else None,
        'set': lambda v: json.dumps(list(v)) if v is not None else None,
        'tuple': lambda v: json.dumps(list(v)) if v is not None else None,
        'datetime': lambda v: v.isoformat() if v is not None else None,
        'date': lambda v: v.isoformat() if v is not None else None,
        'time': lambda v: v.isoformat() if v is not None else None,
        'bytes': lambda v: v.hex() if v is not None else None,
        'bool': lambda v: str(v).lower() if v is not None else None,
        'int': lambda v: str(v) if v is not None else None,
        'float': lambda v: str(v) if v is not None else None,
    }
    
    _default_deserializers = {
        'dict': lambda v: json.loads(v) if v else {},
        'list': lambda v: json.loads(v) if v else [],
        'set': lambda v: set(json.loads(v)) if v else set(),
        'tuple': lambda v: tuple(json.loads(v)) if v else (),
        'datetime': lambda v: datetime.datetime.fromisoformat(v) if v else None,
        'date': lambda v: datetime.date.fromisoformat(v) if v else None,
        'time': lambda v: datetime.time.fromisoformat(v) if v else None,
        'bytes': lambda v: bytes.fromhex(v) if v else None,
        'int': lambda v: int(v) if v and v.strip() else 0,
        'float': lambda v: float(v) if v and v.strip() else 0.0,
        'bool': lambda v: v.lower() in ('true', '1', 'yes', 'y', 't') if v else False,
    }
    
    def _get_instance_lock(self):
        """Get a lock unique to this instance."""
        instance_id = id(self)
        
        with self._locks_lock:
            if instance_id not in self._locks:
                self._locks[instance_id] = threading.RLock()
            return self._locks[instance_id]
    
    @property
    def _serializers(self):
        """Lazily initialize and return serializers dictionary."""
        if not hasattr(self, '_serializers_dict'):
            with self._get_instance_lock():
                if not hasattr(self, '_serializers_dict'):
                    self._serializers_dict = self._default_serializers.copy()
        return self._serializers_dict
    
    @property
    def _deserializers(self):
        """Lazily initialize and return deserializers dictionary."""
        if not hasattr(self, '_deserializers_dict'):
            with self._get_instance_lock():
                if not hasattr(self, '_deserializers_dict'):
                    self._deserializers_dict = self._default_deserializers.copy()
        return self._deserializers_dict
    
    @property
    def _custom_serializers(self):
        """Lazily initialize and return custom serializers dictionary."""
        if not hasattr(self, '_custom_serializers_dict'):
            with self._get_instance_lock():
                if not hasattr(self, '_custom_serializers_dict'):
                    self._custom_serializers_dict = {}
        return self._custom_serializers_dict
    
    @property
    def _custom_deserializers(self):
        """Lazily initialize and return custom deserializers dictionary."""
        if not hasattr(self, '_custom_deserializers_dict'):
            with self._get_instance_lock():
                if not hasattr(self, '_custom_deserializers_dict'):
                    self._custom_deserializers_dict = {}
        return self._custom_deserializers_dict
    
    def register_serializer(self, type_name: str, serializer_func, deserializer_func):
        """
        Register custom serialization functions for handling non-standard types.
        
        Args:
            type_name: String identifier for the type
            serializer_func: Function that converts the type to a string
            deserializer_func: Function that converts a string back to the type
        """
        self._custom_serializers[type_name] = serializer_func
        self._custom_deserializers[type_name] = deserializer_func
    
    def _infer_type(self, value: Any) -> str:
        """
        Infer the type of a value as a string.
        
        Args:
            value: Any Python value
            
        Returns:
            String identifier for the type
        """
        if value is None:
            return 'str'  # Default to string for None values
        
        python_type = type(value).__name__
        
        # Check for custom type
        for type_name, serializer in self._custom_serializers.items():
            try:
                if isinstance(value, eval(type_name)):
                    return type_name
            except (NameError, TypeError):
                # Type might not be importable here - try duck typing
                try:
                    # Try to apply serializer as a test
                    serializer(value)
                    return type_name
                except Exception:
                    pass
        
        # Map Python types to our type system
        type_map = {
            'dict': 'dict',
            'list': 'list',
            'tuple': 'tuple',
            'set': 'set',
            'int': 'int',
            'float': 'float',
            'bool': 'bool',
            'str': 'str',
            'bytes': 'bytes',
            'datetime': 'datetime',
            'date': 'date',
            'time': 'time',
        }
        
        return type_map.get(python_type, 'str')
    
    def _serialize_value(self, value: Any, value_type: Optional[str] = None) -> str:
        """
        Serialize a value based on its type.
        
        Args:
            value: Value to serialize
            value_type: Optional explicit type, if None will be inferred
            
        Returns:
            String representation of the value
        """
        if value is None:
            return None
        
        # Determine type if not provided
        if value_type is None:
            value_type = self._infer_type(value)
        
        # Check for custom serializer first
        if value_type in self._custom_serializers:
            try:
                return self._custom_serializers[value_type](value)
            except Exception as e:
                logger.warning(f"Custom serializer for {value_type} failed: {e}")
                # Fall back to string conversion
        
        # Use standard serializer if available
        serializer = self._serializers.get(value_type)
        if serializer:
            try:
                return serializer(value)
            except Exception as e:
                logger.warning(f"Standard serializer for {value_type} failed: {e}")
                # Fall back to string conversion
        
        # Default fallback
        return str(value)
    
    def _deserialize_value(self, value: Optional[str], value_type: str) -> Any:
        """
        Deserialize a value based on its type.
        
        Args:
            value: String representation of a value
            value_type: Type of the value
            
        Returns:
            Python object of the appropriate type
        """
        if value is None:
            return None
        
        # Check for custom deserializer first
        if value_type in self._custom_deserializers:
            try:
                return self._custom_deserializers[value_type](value)
            except Exception as e:
                logger.warning(f"Custom deserializer for {value_type} failed: {e}")
                # Fall back to returning the raw value
        
        # Use standard deserializer if available
        deserializer = self._deserializers.get(value_type)
        if deserializer:
            try:
                return deserializer(value)
            except Exception as e:
                logger.warning(f"Standard deserializer for {value_type} failed: {e}")
                # Fall back to returning the raw value
        
        # Default fallback
        return value
    
    def _serialize_entity(self, entity: Dict[str, Any], meta: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
        """
        Serialize all values in an entity to strings.
        
        Args:
            entity: Dictionary with entity data
            meta: Optional metadata with field types
            
        Returns:
            Dictionary with all values serialized to strings
        """
        result = {}
        
        for key, value in entity.items():
            value_type = meta.get(key, None) if meta else None
            
            try:
                result[key] = self._serialize_value(value, value_type)
            except Exception as e:
                logger.error(f"Error serializing field '{key}': {e}")
                # Use string representation as fallback
                result[key] = str(value) if value is not None else None
        
        return result
    
    def _deserialize_entity(self, entity_name: str, entity: Dict[str, Optional[str]], meta: Dict[str, str]) -> Dict[str, Any]:
        """
        Deserialize entity values based on metadata.
        
        Args:
            entity_name: Name of the entity for metadata lookup
            entity: Dictionary with string values
            meta: Dictionary of field name/field type(as string)
            
        Returns:
            Dictionary with values converted to appropriate Python types
        """
        result = {}   
        
        for key, value in entity.items():
            value_type = meta.get(key, 'str')
            
            try:
                result[key] = self._deserialize_value(value, value_type)
            except Exception as e:
                logger.error(f"Error deserializing field '{key}' as {value_type}: {e}")
                # Use the raw value as a fallback
                result[key] = value
        
        return result
    
    def _prepare_entity(self, entity_name: str, entity: Dict[str, Any], 
                       user_id: Optional[str] = None, comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Prepare an entity for storage by adding required fields.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity data
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            
        Returns:
            Entity with added/updated system fields
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        result = entity.copy()
        
        # Add ID if missing
        if 'id' not in result or not result['id']:
            result['id'] = str(uuid.uuid4())
        
        # Add timestamps
        if 'created_at' not in result:
            result['created_at'] = now
        
        result['updated_at'] = now
        
        # Add user_id if provided
        if user_id is not None:
            result['updated_by'] = user_id
            
            if 'created_by' not in result:
                result['created_by'] = user_id
        
        # Add comment if provided
        if comment is not None:
            result['update_comment'] = comment
        
        return result
    
    def _to_json(self, entity: Dict[str, Any]) -> str:
        """
        Convert an entity to a JSON string.
        
        Args:
            entity: Entity dictionary
            
        Returns:
            JSON string representation
        """
        return json.dumps(entity, default=str)
    
    def _from_json(self, json_str: str) -> Dict[str, Any]:
        """
        Convert a JSON string to an entity dictionary.
        
        Args:
            json_str: JSON string
            
        Returns:
            Entity dictionary
        """
        return json.loads(json_str)
    
    async def _internal_operation(self, is_async: bool, func_sync, func_async, *args, **kwargs):
        """
        Execute an operation in either sync or async mode.
        
        This internal helper method allows implementing a function once and then
        exposing it as both sync and async methods.
        
        Args:
            is_async: Whether to execute in async mode
            func_sync: Synchronous function to call
            func_async: Asynchronous function to call
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Result of the function call
        """
        if is_async:
            return await func_async(*args, **kwargs)
        else:
            return func_sync(*args, **kwargs)
    
    def _create_sync_method(self, internal_method, *args, **kwargs):
        """
        Create a synchronous wrapper for an internal method.
        
        Args:
            internal_method: Coroutine that implements the operation
            *args, **kwargs: Default arguments to pass to the method
            
        Returns:
            Synchronous function that executes the internal method
        """
        def sync_method(*method_args, **method_kwargs):
            combined_args = args + method_args
            combined_kwargs = {**kwargs, **method_kwargs}
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop in this thread, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(
                internal_method(is_async=False, *combined_args, **combined_kwargs)
            )
        
        return sync_method
    
    def _create_async_method(self, internal_method, *args, **kwargs):
        """
        Create an asynchronous wrapper for an internal method.
        
        Args:
            internal_method: Coroutine that implements the operation
            *args, **kwargs: Default arguments to pass to the method
            
        Returns:
            Asynchronous function that executes the internal method
        """
        async def async_method(*method_args, **method_kwargs):
            combined_args = args + method_args
            combined_kwargs = {**kwargs, **method_kwargs}
            return await internal_method(is_async=True, *combined_args, **combined_kwargs)
        
        return async_method
    
    def __del__(self):
        """Clean up the lock when this instance is garbage collected."""
        instance_id = id(self)
        with self._locks_lock:
            if instance_id in self._locks:
                del self._locks[instance_id]