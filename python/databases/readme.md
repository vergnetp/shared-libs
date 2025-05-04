## 📖 Utilities


### class `ConnectionPool`
Abstract connection pool interface that standardizes behavior across database drivers. This interface provides a consistent API for connection pool operations, regardless of the underlying database driver. It abstracts away driver-specific details and ensures that all pools implement the core functionality needed by the connection management system.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:pink">@async</code>| `acquire` |`timeout: Optional[float] = None`|`Any`|Connection Management| Acquires a connection from the pool with optional timeout. |
|<code style="background-color:pink">@async</code>| `release` |`connection: Any`||Connection Management| Releases a connection back to the pool. |
|<code style="background-color:pink">@async</code>| `close` |`force: bool = False, timeout: Optional[float] = None`||Resource Management| Closes the pool and all connections. When force=False, waits for all connections to be released naturally. When force=True, terminates any executing operations (may cause data loss). |
|<code style="background-color:pink">@async</code>| `health_check` ||`bool`|Diagnostic| Checks if the pool is healthy by testing a connection. |
|<code style="background-color:lightgreen">@property</code>| `min_size` ||`int`|Configuration| Gets the minimum number of connections the pool maintains. |
|<code style="background-color:lightgreen">@property</code>| `max_size` ||`int`|Configuration| Gets the maximum number of connections the pool can create. |
|<code style="background-color:lightgreen">@property</code>| `size` ||`int`|Diagnostic| Gets the current number of connections in the pool (both in-use and idle). |
|<code style="background-color:lightgreen">@property</code>| `in_use` ||`int`|Diagnostic| Gets the number of connections currently in use (checked out from the pool). |
|<code style="background-color:lightgreen">@property</code>| `idle` ||`int`|Diagnostic| Gets the number of idle connections in the pool (available for checkout). |


-----
### class `StatementCache`
Thread-safe cache for prepared SQL statements with dynamic sizing.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:lightblue">@staticmethod</code>| `hash` |`sql: str`|`str`|Utility| Hash a SQL statement for cache lookup using MD5. |
|<code style="background-color:lightgreen">@property</code>| `hit_ratio` ||`float`|Diagnostic| Calculate the cache hit ratio (hits / total operations). |
|| `get` |`sql_hash`|`Optional[Tuple[Any, str]]`|Cache Management| Get a prepared statement from the cache in a thread-safe manner. |
|| `put` |`sql_hash, statement, sql`||Cache Management| Add a prepared statement to the cache in a thread-safe manner. |

-----
### class `CircuitBreaker`
Circuit breaker implementation that can be used as a decorator for sync and async methods. The circuit breaker pattern prevents cascading system failures by monitoring error rates. If too many failures occur within a time window, the circuit 'opens' and immediately rejects new requests without attempting to call the failing service. After a recovery timeout period, the circuit transitions to 'half-open' state, allowing a few test requests through. If these succeed, the circuit 'closes' and normal operation resumes; if they fail, the circuit opens again to protect system resources.

|Decorators| Method |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|<code style="background-color:lightblue">@classmethod</code>| `get_or_create` |`name, failure_threshold=5, recovery_timeout=30.0, half_open_max_calls=3, window_size=60.0`|`CircuitBreaker`|Factory| Get an existing circuit breaker or create a new one with the specified parameters. |
|<code style="background-color:lightgreen">@property</code>| `state` ||`CircuitState`|State| Get the current state of the circuit breaker (CLOSED, OPEN, or HALF_OPEN). |
|| `record_success` |||State Management| Record a successful call through the circuit breaker. |
|| `record_failure` |||State Management| Record a failed call through the circuit breaker. |
|| `allow_request` ||`bool`|State Management| Check if a request should be allowed through the circuit breaker. |

-----
### Functions

|Decorators| Function |Args|Returns| Category| Description |
| ------------------------------ |---| --|---| --| -------------------------------- |
|| `circuit_breaker` |`name=None, failure_threshold=5, recovery_timeout=30.0, half_open_max_calls=3, window_size=60.0`|`Callable`|Resilience| Decorator that applies circuit breaker pattern to a function or method. |
|| `retry_with_backoff` |`max_retries=3, base_delay=0.1, max_delay=10.0, exceptions=None, total_timeout=30.0`|`Callable`|Resilience| Decorator for retrying functions with exponential backoff on specified exceptions. |
|| `track_slow_method` |`threshold=2.0`|`Callable`|Instrumentation| Decorator that logs a warning if the execution of the method took longer than the threshold (in seconds). |
|| `overridable` |`method`|`Callable`|Documentation| Marks a method as overridable for documentation / IDE purposes. |