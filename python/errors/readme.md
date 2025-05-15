# Error Handling System

A robust error handling system for Python applications that provides structured error chaining, context tracking, and user-friendly error messages. This system is designed to make debugging easier and provide clear, actionable information for both developers and end-users.

## Features

- **Error Chaining**: Automatically chain and track errors through multiple layers of your application
- **Error Context**: Add context to errors as they propagate through your codebase
- **Detailed Logging**: Comprehensive error details for debugging, including file and line information
- **User-Friendly Messages**: Separate internal error details from user-facing messages
- **Try-Catch Decorator**: Simple decorator for wrapping functions and methods
- **Call Chain Tracking**: Visualize the exact path through which an error propagated
- **Action Recommendations**: Include recommended actions for fixing errors
- **Criticality Marking**: Flag errors that require immediate attention

## Core Components

### Error Classes

- `Error`: Base error class with chainable metadata
- `TrackError`: Used to track non-handled exceptions across functions
- `ApiKeyError`: Specific error for invalid or expired API keys
- `UserError`: Error with a dedicated user-friendly message

### Decorators

- `try_catch`: Wraps functions/methods to catch and enrich exceptions


## Usage Guide

### Executive Summary

* Wrap all methods in `@try_catch` decorator
* Add descriptive parameters (`description`, `action`, and `user_message`) in critical methods
* Handle exceptions at your entry points (main functions, API endpoints) with a `try/except` block and log `err.to_string()`
* Errors will automatically chain through your codebase, providing clear call paths and context

```python
@try_catch(
    description="Failed to process order",
    action="Check payment service logs", 
    user_message="Your order couldn't be processed. Please try again."
)
def process_order(order_id):
    # Business logic here
    
# At your application entry point
try:
    process_order(123)
except Error as e:
    logger.error(f"Order processing failed:\n{e.to_string()}")
    return {"error": e.user_message()}
```

### Error Classes

#### Base Error

The foundation of the error system:

```python
# Simple error with description
error = Error(description="Database connection timed out")

# Error with more context
error = Error(
    description="Failed to retrieve user profile",
    action="Check database connection",
    critical=True
)

# Wrapping an existing exception
try:
    # Code that might fail
    raise ValueError("Invalid user ID")
except Exception as e:
    error = Error(
        error=e,
        description="User lookup failed",
        action="Validate user ID format"
    )
```

#### UserError

For creating errors with user-friendly messages:

```python
# Create a user-friendly error
error = UserError(
    description="Authentication failed",
    action="Check credentials in config file",
    user_message="Invalid username or password. Please try again."
)

# Wrap an existing exception with a user message
try:
    # Code that might fail
    raise ConnectionError("Host unreachable")
except Exception as e:
    error = UserError(
        error=e,
        description="Failed to connect to authentication service",
        action="Check network connectivity",
        user_message="We're having trouble connecting to our servers. Please try again later."
    )
```

#### API Key Error

Specialized error for API authentication issues:

```python
error = ApiKeyError(
    description="Invalid API key provided",
    action="Regenerate API key in dashboard"
)
```

### Try-Catch Decorator

The `try_catch` decorator automatically wraps functions to provide error context:

```python
# Basic usage - automatically captures and wraps exceptions
@try_catch
def fetch_user_data(user_id):
    # Code that might fail
    return database.query(f"SELECT * FROM users WHERE id = {user_id}")

# With custom error parameters
@try_catch(
    description="User data retrieval failed",
    action="Verify database connection",
    critical=True
)
def get_user_profile(user_id):
    return fetch_user_data(user_id)

# With user-friendly message
@try_catch(
    description="Authentication failed",
    action="Check authentication service",
    user_message="Your session has expired. Please log in again."
)
def authenticate_user(username, password):
    # Authentication code
    pass
```

## Working with Error Objects

### Getting Error Information

```python
# Get string representation of the error (for logging)
error_string = error.to_string()

# Get structured dictionary of error information
error_dict = error.to_dict()

# Get JSON representation
error_json = error._encode()

# Get the user-friendly message
user_message = error.user_message()

# Get the error trace
trace = error.trace()
```

### Adding Context

As errors propagate through your application, you can add context:

```python
try:
    # Code that might raise an error
    process_payment()
except Error as e:
    # Add context about where this error occurred
    e.add_context("OrderService.checkout")
    raise e
```

## Best Practices

1. **Decorate Key Functions**: Use the `try_catch` decorator on all functions that:
   - Interact with external systems (databases, APIs, file systems)
   - Contain complex business logic
   - Serve as entry points to your application (API endpoints, UI handlers)

2. **Add Descriptive Action Recommendations**: Always include an `action` parameter that tells developers exactly what to check or fix:
   ```python
   @try_catch(
       description="Failed to connect to payment gateway",
       action="Check API credentials and network connectivity"
   )
   ```

3. **Create User-Friendly Errors**: For user-facing applications, always provide clear, non-technical messages:
   ```python
   raise UserError(
       error=e,
       description="Payment validation failed",
       action="Check payment gateway logs",
       user_message="We couldn't verify your payment information. Please try again with a different card."
   )
   ```

4. **Use Context to Track Call Chains**: The context automatically builds a call chain that shows the exact path of execution:
   ```
   Call chain: Database.connect -> UserService.authenticate -> ApiController.login
   ```

5. **Log the Full Error Details**: Always log the complete error information for debugging:
   ```python
   try:
       some_operation()
   except Error as e:
       logger.error(f"Operation failed:\n{e.to_string()}")
   ```

6. **Propagate Error Objects**: Instead of raising new exceptions, propagate the existing error objects to preserve the chain:
   ```python
   try:
       validate_user_input()
   except Error as e:
       # Add context but preserve the original error
       e.add_context("FormValidator")
       raise e
   ```

## Real-World Examples

### Error Chain Output

The error system produces structured error messages that look like this:

```
Could not process payment with Stripe: Stripe Failure
Call chain: pay_stripe_error -> main_stripe_error -> server_process_request_stripe_error
Consequences: Could not process payment with Stripe -> App failed -> Web service failed
Action: Investigate stripe error -> Investigate App issue -> Investigate web service issue
Official message: Your payment could not be processed. You have not been charged
Location: c:\Users\Phil\Desktop\Projects\shared-libs\python\errors\tests\test_error.py pay_stripe_error line 86
```

This provides:
- The root cause description
- The exact call chain through which the error propagated
- The consequences at each level of the stack
- Recommended actions at each level
- A user-friendly message suitable for displaying to end-users
- The file, function, and line number where the error originated

### Multi-Layer Error Handling

```python
# Low-level payment processor
    @try_catch(
        description="Could not process payment with Stripe",
        action="Investigate stripe error",
        critical=True
    )
    def process_payment():
        try: 
            raise Exception("Stripe Failure")
        except Exception as e:
            # Manual user-friendly error
            raise UserError(
                e,
                "Stripe is kapput",
                "resign!",
                user_message="Your payment could not be processed. You have not been charged"
            )

    # "Forgotten" intermediary call
    def pass_through():
        process_payment()

    # Mid-level application logic
    @try_catch(
        description="App failed",
        action="Investigate App issue", 
        critical=True
    )
    def execute_transaction():
        pass_through()  # This will propagate errors upward with added context

    # Top-level API endpoint
    @try_catch(
        user_message="Internal Error. Please try again later",
        description="Web service failed",
        action="Investigate web service issue"
    )
    def api_endpoint():
        try:
            execute_transaction()
            return {"success": True}
        except Error as e:
            # probably: return {"success": False, "error": e.user_message()}
            raise e
    
    try:
        api_endpoint()
    except Error as e:
        msg = e.to_string()
        assert "An error happened in test_error.process_payment: Stripe Failure" in msg # We get the caller of the real Exception
        assert "Call chain: process_payment -> execute_transaction" in msg # We show what we can (user should really put @try_catch everytime it matters)
        assert "Consequences: Stripe is kapput -> App failed" in msg # We show the chained descriptions(or the real Exception if none found)
        assert "Action: resign! -> Investigate App issue" in msg # Chained actions. We ignore the try_catch argumenst if an Error (or subclasss like UserError) was manually raised in teh function
        assert "Official message: Your payment could not be processed. You have not been charged" in msg # the first user message ever available in the chain (or default)
        assert "Location:" in msg
```

## Implementation Details

### Error Output Format

The error system formats errors with the following sections:

1. **Description and Root Cause**: The description of what went wrong and the original exception message
2. **Call Chain**: The sequence of function calls that led to the error
3. **Consequences**: The cascading effects of the error through different layers
4. **Actions**: Recommended actions to resolve the issue
5. **User Message**: A user-friendly message suitable for end-users
6. **Location**: The file, function name, and line number where the error originated

### Automatic Context Resolution

The `try_catch` decorator automatically determines the class and method name where an error occurred:

```python
class UserService:
    @try_catch
    def authenticate(self, username, password):
        # If this fails, the error context will be "UserService.authenticate"
        database.query("SELECT * FROM users WHERE username = %s", username)
```

### Class Inheritance Support

The system correctly tracks method calls through inheritance chains:

```python
class BaseRepository:
    @try_catch
    def find_by_id(self, id):
        # Database code
        pass

class UserRepository(BaseRepository):
    # This will inherit the try_catch decorator
    # If find_by_id fails, the context will be "BaseRepository.find_by_id"
    pass
```

## Import Structure

```python
# Import the error classes
from your_package.errors import Error, UserError, ApiKeyError, TrackError

# Import the decorator
from your_package.errors import try_catch
```

