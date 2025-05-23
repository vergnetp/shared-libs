import functools
from .error import UserError

def success_or_error(success_msg=None, error_msg=None):
    """
    Decorator that catches exceptions and returns a success/error response.
    
    Unlike try_catch which re-raises a wrapped exception, this decorator
    returns a dictionary with success status and appropriate message.
    
    Args:
        success_msg: Message to include on success
        error_msg: Message to include on error (falls back to user_message or str(e))
        
    Returns:
        A decorator function
        
    Example:
        @success_or_error(
            success_msg="Profile updated successfully",
            error_msg="Could not update profile"
        )
        async def update_profile(profile_data):
            # Function that may raise exceptions
            ...
            
        # Result will be: {"success": True|False, "message": "..."}
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Execute the original function
                result = await func(*args, **kwargs)
                return {
                    "success": True,
                    "message": success_msg or "Operation completed successfully",
                    "result": result
                }
            except UserError as e:
                # Get the user message from the UserError
                message = error_msg or e.user_message() or 'Internal Error'
                return {
                    "success": False,
                    "message": message
                }
            except Exception as e:
                # Handle other exceptions
                message = error_msg or 'Internal Error'
                return {
                    "success": False,
                    "message": message
                }
        return wrapper
    return decorator