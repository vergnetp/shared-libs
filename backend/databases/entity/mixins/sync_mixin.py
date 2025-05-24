from .utils_mixin import EntityUtilsMixin
from .async_mixin import EntityAsyncMixin
from ...connections import ConnectionInterface


class EntitySyncMixin(EntityUtilsMixin, ConnectionInterface):    
    """
    Mixin that adds entity operations to sync connections.
    
    This mixin provides sync methods for entity operations by wrapping
    the async versions from EntityAsyncMixin using the _create_sync_method utility.
    """
    
    # Meta cache to optimize metadata lookups (shared with async mixin)
    _meta_cache = {}
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_sync_methods()
    
    def _create_sync_methods(self):
        """
        Create sync versions of all entity operations by wrapping the async methods.
        """
        # Create sync versions of all entity methods from EntityAsyncMixin
        method_names = [
            # CRUD operations
            'get_entity',
            'save_entity',
            'save_entities',
            'delete_entity',
            'restore_entity',
            
            # Query operations
            'find_entities',
            'count_entities',
            
            # History operations
            'get_entity_history',
            'get_entity_by_version',
            
            # Schema operations
            '_ensure_entity_schema',
            '_update_entity_metadata',
            
            # Utility methods
            '_get_entity_metadata',
            '_add_to_history',        
        ]
        
        # Get the async mixin methods from a temporary EntityAsyncMixin instance
        async_mixin = EntityAsyncMixin()
        
        # Create sync versions of all methods
        for method_name in method_names:
            if hasattr(async_mixin, method_name) and callable(getattr(async_mixin, method_name)):
                async_method = getattr(async_mixin, method_name)
                sync_method = self._create_sync_method(async_method)
                setattr(self, method_name, sync_method)
