import functools
from .error import TrackError, Error, UserError


def get_defining_class(instance, method_name):
    """
    Find the actual class that defines a method in an inheritance hierarchy.
    
    Args:
        instance: The object instance
        method_name: The name of the method
        
    Returns:
        defining_class_name (str or None)
    """
    if not instance or not hasattr(instance, '__class__'):
        return None
        
    calling_cls = instance.__class__
    
    # Find where this method is actually defined in the MRO
    defining_cls = None
    for cls in calling_cls.__mro__:
        if method_name in cls.__dict__:
            defining_cls = cls
            break
    
    return defining_cls.__name__ if defining_cls else None

def try_catch(func=None, description=None, action=None, critical=False, user_message=None, log_success=False):
    """
    Decorator that logs method calls and wraps exceptions.
    
    Args:
        func: The function to decorate
        description: Optional error description 
        action: Optional action to take
        critical: Whether this error is critical
        user_message: Optional user-friendly error message (creates a UserError instead of TrackError)
        log_success (bool): whether to log as info the result if success (otherwise debug it only)
        
    Returns:
        Decorated function
    """
    # Handle case when decorator is used with or without parameters
    if func is None:
        # Called with parameters: @try_catch(description="...", etc.)
        return lambda f: try_catch(f, description, action, critical, user_message)
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from .. import log as logger
        def helper(current_context, error):
            should_raise_custom_error = any([description, action, critical, user_message])
            
            if should_raise_custom_error:                   
                custom_desc = description or f"An error happened in {current_context}: {error}"
                
                # Create appropriate error type
                if user_message is not None:
                    raise UserError(
                        error=error,
                        description=custom_desc,
                        action=action,
                        critical=critical,
                        context=current_context,
                        user_message=user_message
                    )
                else:
                    raise Error(
                        error=error,
                        description=custom_desc,
                        action=action,
                        critical=critical,
                        context=current_context
                    )                
     
                
            # Create a new TrackError
            track_desc = f"An error happened in {current_context}: {error}"
            raise TrackError(error,  context=current_context)


        # Get class info if it's a method
        if args and hasattr(args[0], '__class__'):
            cls_name = args[0].__class__.__name__  
            instance = args[0]
            method_name = func.__name__
            method_args = args[1:]

            defining_cls = get_defining_class(instance, method_name)

            current_context = f"{defining_cls}.{method_name}"
        else:
            current_context = func.__name__
            method_args = args
            
        try:
            result = func(*args, **kwargs)
            
            # For successful execution, log at debug level
            args_str = str(method_args)[:200] 
            result_str = str(result)[:200]
            if log_success:
                logger.info(f"{current_context}({args_str}) returned {result_str}")
            else:
                logger.debug(f"{current_context}({args_str}) returned {result_str}")
            
            return result
            
        except Exception as error:
            if hasattr(error,'context') and error.context:
                # This is one of ours, and it was raised in a nested try_catch - we wrap
                helper(current_context, error)
            elif hasattr(error, 'context') and not error.context:
                # This is one of ours and it was raised manually by the developer - we add context and raise as is
                #logger.info(f"^^^^ {error}")
                error.add_context(current_context)
                raise error                
            else:
                # This is not one of ours - we wrap
                helper(current_context, error)  
            
    return wrapper