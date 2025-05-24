import inspect

def get_caller_info(frames_back=1) -> tuple[str, str]:
    """
    Get the caller's class (or module if no class) and method name.
    
    Args:
        frames_back: How many frames to go back in the stack
                    (default: 1 - immediate caller)
    
    Returns:
        tuple: (component, subcomponent) names
    """
    frame = inspect.currentframe()
    try:
        # Navigate back the requested number of frames
        for _ in range(frames_back + 1):  # +1 to account for this function call
            if frame.f_back is None:
                break
            frame = frame.f_back
            
        # Get class name if available (component)
        if 'self' in frame.f_locals:
            component = frame.f_locals['self'].__class__.__name__
        else:
            # If not in a class method, use module name
            component = frame.f_globals['__name__'].split('.')[-1]
        
        # Get function name (subcomponent)
        subcomponent = frame.f_code.co_name
        
        return component, subcomponent
    finally:
        del frame  # Avoid reference cycles