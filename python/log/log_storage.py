from datetime import datetime
from typing import Dict, Any, Optional, List

class LogStorageInterface:
    """Interface for log storage backends"""
    
    async def store_log(self, log_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store a single log record.
        
        Args:
            log_record: The log record to store
            
        Returns:
            Dict with storage status
        """
        raise NotImplementedError("Subclasses must implement store_log")
    
    async def store_batch(self, log_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Store a batch of log records.
        
        Args:
            log_records: List of log records to store
            
        Returns:
            Dict with storage status
        """
        raise NotImplementedError("Subclasses must implement store_batch")