
import asyncio
import datetime
from typing import Dict, Tuple, List, Any, Optional

from ....utils import async_method
from .... import log as logger
from ....resilience import with_timeout

from .utils_mixin import EntityUtilsMixin
from ...utils.decorators import auto_transaction
from ...connections.connection import  ConnectionInterface

  
class EntityAsyncMixin(EntityUtilsMixin, ConnectionInterface):
    """
    Mixin that adds entity operations to async connections.
    
    This mixin provides async methods for entity CRUD operations,
    leveraging the EntityUtils serialization/deserialization
    and the AsyncConnection database operations.
    """
    
    # Meta cache to optimize metadata lookups
    _meta_cache = {}
    
    @async_method
    async def _get_field_names(self, entity_name: str, is_history: bool = False) -> List[str]:
        """
        Get field names for an entity table.
        
        This method tries multiple approaches to get field names:
        1. Use metadata cache if available
        2. Query database schema as fallback
        
        Args:
            entity_name: Name of the entity type
            is_history: Whether to get field names for the history table
            
        Returns:
            List of field names
        """
        table_name = f"{entity_name}_history" if is_history else entity_name
        
        # Try to get from schema directly - more reliable way to get columns in order
        schema_sql, schema_params = self.sql_generator.get_list_columns_sql(table_name)
        schema_result = await self.execute(schema_sql, schema_params)
        if schema_result:
            # Check if this is SQLite's PRAGMA table_info() result
            # SQLite PRAGMA returns rows in format (cid, name, type, notnull, dflt_value, pk)
            if isinstance(schema_result[0][0], int) and len(schema_result[0]) >= 3 and isinstance(schema_result[0][1], str):
                # For SQLite, column name is at index 1
                field_names = [row[1] for row in schema_result]
            else:
                # For other databases, column name is at index 0
                field_names = [row[0] for row in schema_result]
            logger.info(f"Got field names for {table_name} from schema: {field_names}")
            return field_names
        
        # Only fall back to metadata if schema query failed
        if not is_history:
            meta = await self._get_entity_metadata(entity_name)
            if meta:
                field_names = list(meta.keys())
                logger.info(f"Got field names for {table_name} from metadata: {field_names}")
                if is_history:
                    # Add history-specific fields
                    history_fields = ["version", "history_timestamp", "history_user_id", "history_comment"]
                    for field in history_fields:
                        if field not in field_names:
                            field_names.append(field)
                return field_names
        
        # Last resort for history tables - use base entity + history fields
        if is_history:
            meta = await self._get_entity_metadata(entity_name)
            field_names = list(meta.keys())
            # Add history-specific fields
            history_fields = ["version", "history_timestamp", "history_user_id", "history_comment"]
            for field in history_fields:
                if field not in field_names:
                    field_names.append(field)
            logger.info(f"Constructed field names for history table {table_name}: {field_names}")
            return field_names
        
        # If all else fails, return an empty list
        return []

    # Core CRUD operations
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def get_entity(self, entity_name: str, entity_id: str, 
                         include_deleted: bool = False, 
                         deserialize: bool = False) -> Optional[Dict[str, Any]]:
        """
        Fetch an entity by ID.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to fetch
            include_deleted: Whether to include soft-deleted entities
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            Entity dictionary or None if not found
        """
        # Generate the SQL
        sql = self.sql_generator.get_entity_by_id_sql(entity_name, include_deleted)
        
        # Execute the query
        result = await self.execute(sql, (entity_id,))
        
        # Return None if no entity found
        if not result or len(result) == 0:
            return None
        
        # Get schema information from metadata cache or retrieve it
        field_names = await self._get_field_names(entity_name)
        
        # Convert the first row to a dictionary
        entity_dict = dict(zip(field_names[:len(result[0])], result[0]))
        
        # Deserialize if requested
        if deserialize:
            meta = await self._get_entity_metadata(entity_name)
            return self._deserialize_entity(entity_name, entity_dict, meta)
        
        return entity_dict
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def save_entity(self, entity_name: str, entity: Dict[str, Any], 
                        user_id: Optional[str] = None, 
                        comment: Optional[str] = None,
                        timeout: Optional[float] = 60) -> Dict[str, Any]:
        """
        Save an entity (create or update).
        
        Args:
            entity_name: Name of the entity type
            entity: Entity data dictionary
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            timeout: Optional timeout in seconds for the operation (defaults to 60)
            
        Returns:
            The saved entity with updated fields
        """
        async def perform_save():
            # Prepare entity with timestamps, IDs, etc.
            prepared_entity = self._prepare_entity(entity_name, entity, user_id, comment)
            
            # Ensure schema exists (will be a no-op if already exists)
            await self._ensure_entity_schema(entity_name, prepared_entity)
            
            # Update metadata based on entity fields
            await self._update_entity_metadata(entity_name, prepared_entity)
            
            # Serialize the entity to string values
            meta = await self._get_entity_metadata(entity_name)
            serialized = self._serialize_entity(prepared_entity, meta)
            
            # Always use targeted upsert with exactly the fields provided
            # (plus system fields added by _prepare_entity)
            fields = list(serialized.keys())
            sql = self.sql_generator.get_upsert_sql(entity_name, fields)
            
            # Execute the upsert
            params = tuple(serialized[field] for field in fields)
            await self.execute(sql, params)
            
            # Add to history
            await self._add_to_history(entity_name, serialized, user_id, comment)
            
            # Return the prepared entity
            return prepared_entity        

        try:
            return await asyncio.wait_for(perform_save(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"save_entity operation for {entity_name} timed out after {timeout:.1f}s")
        
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def save_entities(self, entity_name: str, entities: List[Dict[str, Any]],
                        user_id: Optional[str] = None,
                        comment: Optional[str] = None,
                        timeout: Optional[float] = 60) -> List[Dict[str, Any]]:
        """
        Save multiple entities in a single transaction with batch operations.
        
        Args:
            entity_name: Name of the entity type
            entities: List of entity data dictionaries
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
            timeout: Optional timeout in seconds for the entire operation (defaults to 60)
            
        Returns:
            List of saved entities with their IDs
        """
        if not entities:
            return []
        
        async def perform_batch_save():
            # Prepare all entities and collect fields
            prepared_entities = []
            all_fields = set()
            
            for entity in entities:
                prepared = self._prepare_entity(entity_name, entity, user_id, comment)
                prepared_entities.append(prepared)
                all_fields.update(prepared.keys())
            
            # Ensure schema exists and can accommodate all fields
            await self._ensure_entity_schema(entity_name, {field: None for field in all_fields})
            
            # Update metadata for all fields at once
            meta = {}
            for entity in prepared_entities:
                for field_name, value in entity.items():
                    if field_name not in meta:
                        meta[field_name] = self._infer_type(value)
            
            # Batch update the metadata
            meta_params = [(field_name, field_type) for field_name, field_type in meta.items()]
            if meta_params:
                sql = self.sql_generator.get_meta_upsert_sql(entity_name)
                await self.executemany(sql, meta_params)
            
            # Add all entities to the database with batch upsert
            fields = list(all_fields)
            sql = self.sql_generator.get_upsert_sql(entity_name, fields)
            
            # Prepare parameters for batch upsert
            batch_params = []
            for entity in prepared_entities:
                params = tuple(entity.get(field, None) for field in fields)
                batch_params.append(params)
            
            # Execute batch upsert
            await self.executemany(sql, batch_params)
            
            # Get all entity IDs for history lookup
            entity_ids = [entity['id'] for entity in prepared_entities]
            
            # Single query to get all existing versions
            versions = {}
            if entity_ids:
                placeholders = ','.join(['?'] * len(entity_ids))
                version_sql = f"SELECT [id], MAX([version]) as max_version FROM [{entity_name}_history] WHERE [id] IN ({placeholders}) GROUP BY [id]"
                version_results = await self.execute(version_sql, tuple(entity_ids))
                
                # Create a dictionary of id -> current max version
                versions = {row[0]: row[1] for row in version_results if row[1] is not None}
            
            # Prepare history entries
            now = datetime.datetime.utcnow().isoformat()
            history_fields = list(all_fields) + ['version', 'history_timestamp', 'history_user_id', 'history_comment']
            history_sql = f"INSERT INTO [{entity_name}_history] ({', '.join(['['+f+']' for f in history_fields])}) VALUES ({', '.join(['?'] * len(history_fields))})"
            
            history_params = []
            for entity in prepared_entities:
                history_entry = entity.copy()
                entity_id = entity['id']
                
                # Get next version (default to 1 if no previous versions exist)
                next_version = (versions.get(entity_id, 0) or 0) + 1
                
                history_entry['version'] = next_version
                history_entry['history_timestamp'] = now
                history_entry['history_user_id'] = user_id
                history_entry['history_comment'] = comment
                
                # Create params tuple with all fields in the correct order
                params = tuple(history_entry.get(field, None) for field in history_fields)
                history_params.append(params)
            
            # Execute batch history insert
            await self.executemany(history_sql, history_params)
            
            return prepared_entities
        
        try:
            return await asyncio.wait_for(perform_batch_save(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"save_entities operation timed out after {timeout:.1f}s")

    
    @async_method
    @with_timeout()
    @auto_transaction
    async def delete_entity(self, entity_name: str, entity_id: str, 
                           user_id: Optional[str] = None, 
                           permanent: bool = False) -> bool:
        """
        Delete an entity by ID.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to delete
            user_id: Optional ID of the user making the change
            permanent: Whether to permanently delete (true) or soft delete (false)
            
        Returns:
            True if deletion was successful
        """
        # Get current entity state for history
        current_entity = None
        if not permanent:
            current_entity = await self.get_entity(entity_name, entity_id, include_deleted=True)
            if not current_entity:
                return False
        
        # For permanent deletion, use a direct DELETE
        if permanent:
            sql = f"DELETE FROM [{entity_name}] WHERE [id] = ?"
            result = await self.execute(sql, (entity_id,))
            # For DELETE we expect an empty result if successful, but some drivers might
            # return a tuple with count
            if result and len(result) > 0 and isinstance(result[0], tuple) and len(result[0]) > 0:
                return result[0][0] > 0
            # Otherwise consider it successful if the query didn't raise an exception
            return True

        # For soft deletion, use an UPDATE
        now = datetime.datetime.utcnow().isoformat()
        sql = self.sql_generator.get_soft_delete_sql(entity_name)
        result = await self.execute(sql, (now, now, user_id, entity_id))
        
        # Add to history if soft-deleted
        if current_entity:
            # Update the entity with deletion info
            current_entity['deleted_at'] = now
            current_entity['updated_at'] = now
            if user_id:
                current_entity['updated_by'] = user_id
                
            # Serialize and add to history
            meta = await self._get_entity_metadata(entity_name)
            serialized = self._serialize_entity(current_entity, meta)
            await self._add_to_history(entity_name, serialized, user_id, "Soft deleted")
                
        return True
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def restore_entity(self, entity_name: str, entity_id: str, 
                            user_id: Optional[str] = None) -> bool:
        """
        Restore a soft-deleted entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity to restore
            user_id: Optional ID of the user making the change
            
        Returns:
            True if restoration was successful
        """
        # Check if entity exists and is deleted
        current_entity = await self.get_entity(entity_name, entity_id, include_deleted=True)
        if not current_entity or current_entity.get('deleted_at') is None:
            return False
            
        # Update timestamps
        now = datetime.datetime.utcnow().isoformat()
        
        # Generate restore SQL
        sql = self.sql_generator.get_restore_entity_sql(entity_name)
        result = await self.execute(sql, (now, user_id, entity_id))
        
        # Add to history if restored

        # Update the entity with restoration info
        current_entity['deleted_at'] = None
        current_entity['updated_at'] = now
        if user_id:
            current_entity['updated_by'] = user_id
            
        # Serialize and add to history
        meta = await self._get_entity_metadata(entity_name)
        serialized = self._serialize_entity(current_entity, meta)
        await self._add_to_history(entity_name, serialized, user_id, "Restored")
                
        return True
    
    # Query operations
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def find_entities(self, entity_name: str, where_clause: Optional[str] = None,
                          params: Optional[Tuple] = None, order_by: Optional[str] = None,
                          limit: Optional[int] = None, offset: Optional[int] = None,
                          include_deleted: bool = False, deserialize: bool = False) -> List[Dict[str, Any]]:
        """
        Query entities with flexible filtering.
        
        Args:
            entity_name: Name of the entity type
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            params: Parameters for the WHERE clause
            order_by: Optional ORDER BY clause (without the 'ORDER BY' keyword)
            limit: Optional LIMIT value
            offset: Optional OFFSET value
            include_deleted: Whether to include soft-deleted entities
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            List of entity dictionaries
        """
        # Generate query SQL
        sql = self.sql_generator.get_query_builder_sql(
            entity_name, where_clause, order_by, limit, offset, include_deleted
        )
        
        # Execute the query
        result = await self.execute(sql, params or ())
        
        # If no results, return empty list
        if not result:
            return []
            
        # Get field names from result description
        field_names = await self._get_field_names(entity_name)
        
        if deserialize:
            meta = await self._get_entity_metadata(entity_name)

        # Convert rows to dictionaries
        entities = []
        for row in result:
            entity_dict = dict(zip(field_names, row))
            
            # Deserialize if requested
            if deserialize:
                entity_dict = self._deserialize_entity(entity_name, entity_dict, meta)
                
            entities.append(entity_dict)
            
        return entities
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def count_entities(self, entity_name: str, where_clause: Optional[str] = None,
                           params: Optional[Tuple] = None, 
                           include_deleted: bool = False) -> int:
        """
        Count entities matching criteria.
        
        Args:
            entity_name: Name of the entity type
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            params: Parameters for the WHERE clause
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Count of matching entities
        """
        # Generate count SQL
        sql = self.sql_generator.get_count_entities_sql(
            entity_name, where_clause, include_deleted
        )
        
        # Execute the query
        result = await self.execute(sql, params or ())
        
        # Return the count
        if result and len(result) > 0:
            return result[0][0]
        return 0
    
    # History operations
    
    @async_method
    @with_timeout()
    @auto_transaction
    async def get_entity_history(self, entity_name: str, entity_id: str, 
                                deserialize: bool = False) -> List[Dict[str, Any]]:
        """
        Get the history of an entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            List of historical versions
        """
        # Generate SQL
        sql, params = self.sql_generator.get_entity_history_sql(entity_name, entity_id)
        
        # Execute the query
        result = await self.execute(sql, params)
        
        # If no results, return empty list
        if not result:
            return []
            
        # Get field names from result description
        field_names = await self._get_field_names(entity_name)
        
        if deserialize:
            meta = await self._get_entity_metadata(entity_name)

        # Convert rows to dictionaries
        history_entries = []
        for row in result:
            entity_dict = dict(zip(field_names, row))
            
            # Deserialize if requested
            if deserialize:
                entity_dict = self._deserialize_entity(entity_name, entity_dict, meta)
                
            history_entries.append(entity_dict)
            
        return history_entries

    @async_method
    @with_timeout()
    @auto_transaction
    async def get_entity_by_version(self, entity_name: str, entity_id: str, 
                            version: int, deserialize: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get a specific version of an entity.
        
        Args:
            entity_name: Name of the entity type
            entity_id: ID of the entity
            version: Version number to retrieve
            deserialize: Whether to deserialize values based on metadata
            
        Returns:
            Entity version or None if not found
        """
        # Get all field names for complete entity comparison
        all_fields = set(await self._get_field_names(entity_name))
        all_history_fields = set(await self._get_field_names(entity_name, is_history=True))
        
        # Generate SQL
        sql, params = self.sql_generator.get_entity_version_sql(entity_name, entity_id, version)
        
        # Execute the query
        result = await self.execute(sql, params)
        
        # Return None if no entity found
        if not result or len(result) == 0:
            return None
            
        # Convert the first row to a dictionary using history field names
        field_names = await self._get_field_names(entity_name, is_history=True)
        history_entity = {}
        
        # Map values by name and handle column length discrepancies
        for i, column_name in enumerate(field_names):
            if i < len(result[0]):
                history_entity[column_name] = result[0][i]
        
        # Find fields that exist in current entity but not in this version
        missing_fields = all_fields - set(history_entity.keys())
        
        # If this version doesn't have certain fields that exist in the current version,
        # they should be explicitly set to None
        for field in missing_fields:
            history_entity[field] = None
        
        # Remove history-specific fields
        for field in list(history_entity.keys()):
            if field in ['version', 'history_timestamp', 'history_user_id', 'history_comment'] and field not in all_fields:
                history_entity.pop(field)
        
        # Deserialize if requested
        if deserialize:
            meta = await self._get_entity_metadata(entity_name)
            return self._deserialize_entity(entity_name, history_entity, meta)
            
        return history_entity


    # Schema operations
    
    @async_method
    @auto_transaction
    async def _ensure_entity_schema(self, entity_name: str, sample_entity: Optional[Dict[str, Any]] = None) -> None:
        """
        Ensure entity tables and metadata exist.
        
        Args:
            entity_name: Name of the entity type
            sample_entity: Optional example entity to infer schema
        """
        # Check if the main table exists
        main_exists_sql, main_params = self.sql_generator.get_check_table_exists_sql(entity_name)
        main_result = await self.execute(main_exists_sql, main_params)
        main_exists = main_result and len(main_result) > 0
        
        # Check if the meta table exists
        meta_exists_sql, meta_params = self.sql_generator.get_check_table_exists_sql(f"{entity_name}_meta")
        meta_result = await self.execute(meta_exists_sql, meta_params)
        meta_exists = meta_result and len(meta_result) > 0
        
        # Check if the history table exists
        history_exists_sql, history_params = self.sql_generator.get_check_table_exists_sql(f"{entity_name}_history")
        history_result = await self.execute(history_exists_sql, history_params)
        history_exists = history_result and len(history_result) > 0
        
        # Get columns if the main table exists
        columns = []
        if main_exists:
            columns_sql, columns_params = self.sql_generator.get_list_columns_sql(entity_name)
            columns_result = await self.execute(columns_sql, columns_params)
            if columns_result:
                columns = [(row[0], row[1]) for row in columns_result]
        
        # Create main table if needed
        if not main_exists:
            # Default columns if no sample entity
            if not sample_entity:
                default_columns = [
                    ("id", "TEXT"),
                    ("created_at", "TEXT"),
                    ("created_by", "TEXT"),
                    ("updated_at", "TEXT"),
                    ("updated_by", "TEXT"),
                    ("deleted_at", "TEXT")
                ]
                main_sql = self.sql_generator.get_create_table_sql(entity_name, default_columns)
            else:
                # Use sample entity to determine columns
                columns = [(field, "TEXT") for field in sample_entity.keys()]
                # Ensure required columns exist
                req_columns = ["id", "created_at", "created_by", "updated_at", "updated_by", "deleted_at"]
                for col in req_columns:
                    if col not in sample_entity:
                        columns.append((col, "TEXT"))
                main_sql = self.sql_generator.get_create_table_sql(entity_name, columns)
                
            await self.execute(main_sql, ())
            
            # Update columns for history table creation
            if not columns:
                columns = [(col, "TEXT") for col in req_columns]
            
        # Create meta table if needed
        if not meta_exists:
            meta_sql = self.sql_generator.get_create_meta_table_sql(entity_name)
            await self.execute(meta_sql, ())
            
        # Create history table if needed
        if not history_exists:
            # Get current columns if table exists and columns empty
            if not columns and main_exists:
                columns_sql, columns_params = self.sql_generator.get_list_columns_sql(entity_name)
                columns_result = await self.execute(columns_sql, columns_params)
                if columns_result:
                    columns = [(row[0], row[1]) for row in columns_result]
                
            # Create history table with current columns plus history-specific ones
            history_sql = self.sql_generator.get_create_history_table_sql(entity_name, columns)
            await self.execute(history_sql, ())
            
        # Update metadata if sample entity provided
        if sample_entity:
            await self._update_entity_metadata(entity_name, sample_entity)
    
    @async_method
    @auto_transaction
    async def _update_entity_metadata(self, entity_name: str, entity: Dict[str, Any]) -> None:
        """
        Update metadata table based on entity fields and add missing columns to the table.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity dictionary with fields to register
        """
        # Ensure meta table exists
        try:
            main_exists_sql, main_params = self.sql_generator.get_check_table_exists_sql(f"{entity_name}_meta")
            meta_exists = bool(await self.execute(main_exists_sql, main_params))
            
            if not meta_exists:
                meta_sql = self.sql_generator.get_create_meta_table_sql(entity_name)
                await self.execute(meta_sql, ())
        except Exception as e:
            logger.error(f"Error checking/creating meta table for {entity_name}: {e}")
            raise
        
        # Get existing metadata
        try:
            meta = await self._get_entity_metadata(entity_name, use_cache=False)
        except Exception as e:
            logger.error(f"Error getting metadata for {entity_name}: {e}")
            meta = {}  # Use empty dict as fallback
        
        # Track new fields to add
        new_fields = []
        
        # Check each field in the entity
        for field_name, value in entity.items():
            # Skip system fields that should already exist
            if field_name in ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at']:
                continue
                
            # Check if field is in metadata
            if field_name not in meta:
                # Determine the type
                value_type = self._infer_type(value)
                logger.info(f"Found new field {field_name} in {entity_name} with type {value_type}")
                
                # Add to metadata
                meta_sql = self.sql_generator.get_meta_upsert_sql(entity_name)
                try:
                    await self.execute(meta_sql, (field_name, value_type))
                    meta[field_name] = value_type  # Update local meta dict
                    new_fields.append(field_name)  # Track for column addition
                except Exception as e:
                    logger.error(f"Error updating metadata for field {field_name}: {e}")
        
        # Now add any new columns to the tables
        for field_name in new_fields:
            # Check if column exists in table
            try:
                exists = await self._check_column_exists(entity_name, field_name)
                if not exists:
                    logger.info(f"Adding column {field_name} to table {entity_name}")
                    sql = self.sql_generator.get_add_column_sql(entity_name, field_name)
                    await self.execute(sql, ())
            except Exception as e:
                logger.error(f"Error adding column {field_name} to {entity_name}: {e}")
                raise
                
            # Add to history table as well
            try:
                history_exists = await self._check_column_exists(f"{entity_name}_history", field_name)
                if not history_exists:
                    logger.info(f"Adding column {field_name} to history table {entity_name}_history")
                    sql = self.sql_generator.get_add_column_sql(f"{entity_name}_history", field_name)
                    await self.execute(sql, ())
            except Exception as e:
                logger.warning(f"Error adding column {field_name} to history table: {e}")
                # Continue even if history update fails
        
        # Update cache
        self._meta_cache[entity_name] = meta
    
    # Utility methods
    
    @async_method
    async def _check_column_exists(self, table_name: str, column_name: str) -> bool:
        """
        Check if a column exists in a table.
        
        This method handles different database formats properly.
        
        Args:
            table_name: Name of the table to check
            column_name: Name of the column to check
            
        Returns:
            bool: True if column exists, False otherwise
        """
        try:
            # Get SQL for checking column existence
            sql, params = self.sql_generator.get_check_column_exists_sql(table_name, column_name)
            result = await self.execute(sql, params)
            
            # Handle empty result
            if not result or len(result) == 0:
                return False
                
            # Handle SQLite PRAGMA result format
            if isinstance(result[0][0], int) and len(result[0]) > 1:
                # SQLite returns rows with format (cid, name, type, notnull, dflt_value, pk)
                # Check if any row has matching column name at index 1
                return any(row[1] == column_name for row in result)
                
            # Handle PostgreSQL/MySQL format - they return the column name directly
            # or sometimes a row count
            return bool(result[0][0])
                
        except Exception as e:
            logger.warning(f"Error checking if column {column_name} exists in {table_name}: {e}")
            return False  # Assume it doesn't exist if check fails
    
    @async_method
    async def _get_entity_metadata(self, entity_name: str, use_cache: bool = True) -> Dict[str, str]:
        """
        Get metadata for an entity type.
        
        Args:
            entity_name: Name of the entity type
            use_cache: Whether to use cached metadata
            
        Returns:
            Dictionary of field names to types
        """
        # Check cache first if enabled
        if use_cache and entity_name in self._meta_cache:
            return self._meta_cache[entity_name]
            
        # Check if meta table exists
        meta_exists_sql, meta_params = self.sql_generator.get_check_table_exists_sql(f"{entity_name}_meta")
        meta_exists = bool(await self.execute(meta_exists_sql, meta_params))
        
        # Return empty dict if table doesn't exist
        if not meta_exists:
            self._meta_cache[entity_name] = {}
            return {}
            
        # Query metadata
        result = await self.execute(f"SELECT [name], [type] FROM [{entity_name}_meta]", ())
        
        # Process results
        meta = {}
        for row in result:
            meta[row[0]] = row[1]
            
        # Cache results
        self._meta_cache[entity_name] = meta
        return meta
    

    @async_method
    @auto_transaction
    async def _add_to_history(self, entity_name: str, entity: Dict[str, Any], 
                            user_id: Optional[str] = None, 
                            comment: Optional[str] = None) -> None:
        """
        Add an entry to entity history.
        
        Args:
            entity_name: Name of the entity type
            entity: Entity dictionary to record
            user_id: Optional ID of the user making the change
            comment: Optional comment about the change
        """
        # Ensure entity has required fields
        if 'id' not in entity:
            return
            
        # Get the current highest version
        history_sql = f"SELECT MAX([version]) FROM [{entity_name}_history] WHERE [id] = ?"
        version_result = await self.execute(history_sql, (entity['id'],))
        
        # Calculate the next version number
        next_version = 1
        if version_result and version_result[0][0] is not None:
            next_version = version_result[0][0] + 1
            
        # Prepare history entry
        history_entry = entity.copy()
        now = datetime.datetime.utcnow().isoformat()
        
        # Add history-specific fields
        history_entry['version'] = next_version
        history_entry['history_timestamp'] = now
        history_entry['history_user_id'] = user_id
        history_entry['history_comment'] = comment
        
        # Get the list of columns in the history table to ensure we only use existing columns
        field_names = await self._get_field_names(entity_name, is_history=True)
        
        # Filter history_entry to only include fields that exist in the table
        filtered_entry = {k: v for k, v in history_entry.items() if k in field_names}
        
        # Generate insert SQL using only the filtered fields
        fields = list(filtered_entry.keys())
        placeholders = ', '.join(['?'] * len(fields))
        fields_str = ', '.join([f"[{field}]" for field in fields])
        history_sql = f"INSERT INTO [{entity_name}_history] ({fields_str}) VALUES ({placeholders})"
        
        # Execute insert
        params = tuple(filtered_entry[field] for field in fields)
        await self.execute(history_sql, params)

