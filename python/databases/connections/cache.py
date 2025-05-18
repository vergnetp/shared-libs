
import time
import hashlib
import threading
from typing import Dict, Tuple, Any, Optional

class StatementCache:
    """Thread-safe cache for prepared SQL statements with dynamic sizing"""
    
    def __init__(self, initial_size=100, min_size=50, max_size=500, auto_resize=True):
        self._cache = {}
        self._max_size = initial_size
        self._min_size = min_size
        self._hard_max = max_size
        self._auto_resize = auto_resize
        self._lru = []  # Track usage for LRU eviction
        self._lock = threading.RLock()  # Use a reentrant lock for thread safety
        self._hits = 0
        self._misses = 0
        self._last_resize_check = time.time()
        self._resize_interval = 300  # Check resize every 5 minutes
  
    @staticmethod
    def hash(sql: str) -> str:
        """Generate a hash for the SQL statement"""
        return hashlib.md5(sql.encode('utf-8')).hexdigest()

    @property
    def hit_ratio(self) -> float:
        """Calculate the cache hit ratio"""
        with self._lock:
            total = self._hits + self._misses
            return self._hits / total if total > 0 else 0
    
    def _check_resize(self):
        """Dynamically resize the cache based on hit ratio and usage"""
        with self._lock:
            # Implementation unchanged - already thread-safe with lock
            pass
    
    def get(self, sql_hash) -> Optional[Tuple[Any, str]]:
        """Get a prepared statement from the cache in a thread-safe manner"""
        with self._lock:
            if sql_hash in self._cache:
                # Update LRU tracking
                if sql_hash in self._lru:
                    self._lru.remove(sql_hash)
                self._lru.append(sql_hash)
                self._hits += 1
                self._check_resize()
                return self._cache[sql_hash]
            self._misses += 1
            self._check_resize()
            return None
    
    def put(self, sql_hash, statement, sql):
        """Add a prepared statement to the cache in a thread-safe manner"""
        with self._lock:
            # Evict least recently used if at capacity
            if len(self._cache) >= self._max_size and sql_hash not in self._cache:
                if self._lru:  # Check if there are any items in the LRU list
                    lru_hash = self._lru.pop(0)
                    self._cache.pop(lru_hash, None)
            
            # Add to cache and update LRU
            self._cache[sql_hash] = (statement, sql)
            if sql_hash in self._lru:
                self._lru.remove(sql_hash)
            self._lru.append(sql_hash)
