import json
import traceback
import os
import sys
import re
from typing import Optional, Dict, Any, List, Tuple, Union

def _get_location(frame_offset: int = 2) -> str:
    """Get filename, function name, and line number from the call stack."""
    try:
        frame = sys._getframe(frame_offset)
        code = frame.f_code
        return f'{code.co_filename} {code.co_name} line {frame.f_lineno}'
    except Exception:
        return "unknown location"

def _get_caller_details(exception: Exception, tag: Optional[str] = None) -> Optional[Tuple[str, str, str, int]]:
    """
    Extract detailed location information including class from an exception's traceback.
    
    Args:
        exception: The exception to extract information from
        tag: Optional tag for debugging
        
    Returns:
        tuple: (component, function_name, filename, line_number) or None if extraction fails
    """
    try:
        if not hasattr(exception, '__traceback__'):
            return None
            
        # Extract traceback info
        tb = traceback.extract_tb(exception.__traceback__)
        if not tb:
            return None
        
        # Find a suitable frame (skipping our error handling code)
        for frame_summary in reversed(tb):
            filename, lineno, funcname, line = frame_summary
            
            # Skip our own error handling framework
            if 'try_catch.py' not in filename:
                # Try to get the frame object for more detailed information
                frame = None
                tb_frame = exception.__traceback__
                
                # Find matching frame in traceback
                while tb_frame:
                    if tb_frame.tb_frame.f_code.co_name == funcname and tb_frame.tb_lineno == lineno:
                        frame = tb_frame.tb_frame
                        break
                    tb_frame = tb_frame.tb_next
                
                # Extract class name if this is a class method
                component = None
                if frame and 'self' in frame.f_locals:
                    try:
                        self_obj = frame.f_locals.get('self')
                        if self_obj and hasattr(self_obj, '__class__'):
                            component = self_obj.__class__.__name__
                    except Exception:
                        pass
                
                # Fallback to module name if not a class method
                if not component:
                    module_name = os.path.basename(filename).split('.')[0]
                    component = module_name
                    
                return (component, funcname, filename, lineno)
        
        # Fallback to the last frame if no suitable frame was found
        filename, lineno, funcname, _ = tb[-1]
        module_name = os.path.basename(filename).split('.')[0]
        return (module_name, funcname, filename, lineno)
        
    except Exception:
        return None

def _get_exception_location(exception: Exception) -> Optional[str]:
    """Extract the location information from an exception's traceback as a formatted string."""
    details = _get_caller_details(exception)
    if not details:
        return None
    return f'{details[0]}.{details[1]} in {details[2]} line {details[3]}'

def _clean_description(description: Optional[str]) -> Optional[str]:
    """Remove 'An error happened in X:' prefix from descriptions."""
    if description:
        return re.sub(r'^An error happened in [^:]+: ', '', description)
    return description


class Error(Exception):
    """
    Custom support-friendly error with chainable metadata.
    
    This error class helps create detailed error traces for debugging
    while maintaining a clean interface for user-facing messages.
    """
    def __init__(
            self, 
            error: Optional[Exception] = None, 
            description: Optional[str] = None, 
            action: Optional[str] = None, 
            critical: bool = False, 
            location: Optional[str] = None, 
            context: Optional[str] = None
        ):
        """
        Initialize error with detailed context.
        
        Args:
            error: The original exception (if any)
            description: Human-readable description of what went wrong
            action: Recommended action to fix the issue
            critical: Whether this is a critical error
            location: Where the error occurred (auto-detected if not provided)
            context: Call context string for tracing call chains
        """
        self.description = description
        self.action = action
        self.critical = critical
        self.context = context or ""
        self._user_message = None
        
        # Set location
        if location:
            self.location = location
        elif error and isinstance(error, Exception):
            self.location = _get_exception_location(error) or _get_location()
        else:
            self.location = _get_location()
            
        self.error = error

        # Bubble up the critical flag
        if hasattr(error, 'critical') and error.critical:
            self.critical = True
            
        # Flag to prevent recursive string representation
        self._in_str_call = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary representation."""
        try:
            return json.loads(self._encode())
        except Exception:
            base_dict = {
                "description": self.description,
                "error": str(self.error) if self.error else None,
                "location": self.location
            }
            
            # Add user_message if available
            if self._user_message:
                base_dict["user_message"] = self._user_message
                
            return base_dict

    def _encode(self) -> str:
        """JSON encode the error with nested details."""
        try:
            dic = self.__dict__.copy()
            # Remove internal flags
            if "_in_str_call" in dic:
                del dic["_in_str_call"]
                
            nested = self._get_nested_error()
            if nested:
                dic['error'] = nested
            return json.dumps(dic, indent=4)
        except Exception:
            # Fallback to basic representation
            basic_dict = {
                "description": self.description,
                "error": str(self.error) if self.error else None,
                "location": self.location
            }
            return json.dumps(basic_dict, indent=4)

    def _get_nested_error(self) -> Optional[Union[Dict[str, Any], str]]:
        """Extract structured information from nested errors."""
        try:
            if self.error is None:
                return None

            if isinstance(self.error, Error):
                return json.loads(self.error._encode())

            if isinstance(self.error, Exception):
                tb = traceback.extract_tb(self.error.__traceback__)
                if tb:
                    filename, lineno, funcname, _ = tb[-1]
                    return {'description': str(self.error), 'location': f'{filename} {funcname} line {lineno}'}
                else:
                    return {'description': str(self.error), 'location': 'unknown'}

            return str(self.error)  # fallback
        except Exception as e:
            return {"description": "Error while getting nested error", "detail": str(e)}

    def trace(self) -> List[str]:
        """Return a list of error locations, from most recent to deepest."""
        try:
            locations = []
            
            # Add the current error's location
            if hasattr(self, 'location'):
                locations.append(self.location)
                
            # Add the nested error's location if it exists
            if self.error and isinstance(self.error, Exception) and hasattr(self.error, '__traceback__'):
                tb = traceback.extract_tb(self.error.__traceback__)
                if tb:
                    filename, lineno, funcname, _ = tb[-1]
                    location = f'{filename} {funcname} line {lineno}'
                    if location not in locations:
                        locations.append(location)
                        
            return locations
        except Exception:
            return ["Error generating trace"]

    def to_string(self) -> str:
        """Generate a comprehensive string representation of the error."""
        # Prevent recursive calls
        if getattr(self, '_in_str_call', False):
            return f"{self.description or 'Error'}"
        
        try:
            self._in_str_call = True
            
            # Build a comprehensive error message
            parts = []
            
            # 1. Description with error source
            inner = self._get_inner_error() or self
            if inner.error:
                details = _get_caller_details(inner.error)
                if details:
                    parts.append(f"An error happened in {details[0]}.{details[1]}: {str(inner.error)}")
                else:
                    parts.append(f"{str(inner)}")
            else:
                parts.append(f"{str(inner)}")
            
            # 2. Call chain
            call_chain = self._get_call_chain()
            if call_chain:
                parts.append(f"Call chain: {call_chain}")
            
            # 3. Consequences
            consequences = self._get_consequences()
            if consequences:
                parts.append(f"Consequences: {consequences}")
            
            # 4. Actions
            actions = self._get_actions()
            if actions:
                parts.append(f"Action: {actions}")
            
            # 5. User message
            user_msg = self._get_user_message()
            if user_msg:
                parts.append(f"Official message: {user_msg}")
            
            # 6. Location
            parts.append(f"Location: {inner.location}")
            
            return "\n".join(parts)
        finally:
            self._in_str_call = False
            
    def _get_call_chain(self) -> str:
        """Extract the call chain from context strings."""
        chain_parts = []
        
        # Process this error's context
        if self.context:
            for part in self.context.split(" -> "):
                if part and part not in chain_parts:
                    chain_parts.append(part)
        
        # Add nested error contexts
        current = self.error
        while current and isinstance(current, Error):
            if current.context:
                for part in current.context.split(" -> "):
                    if part and part not in chain_parts:
                        chain_parts.append(part)
            current = getattr(current, 'error', None)
        
        chain_parts.reverse()
        return " -> ".join(chain_parts) if chain_parts else ""
        
    def _get_consequences(self) -> str:
        """Extract consequences from error descriptions."""
        consequences = []
        
        current = self
        while current and hasattr(current, 'description'):
            if current.description:
                desc = _clean_description(current.description)
                if desc and desc not in consequences:
                    consequences.append(desc)
            current = getattr(current, 'error', None)            
       
        consequences.reverse()
        return " -> ".join(consequences) if consequences else ""
        
    def _get_inner_error(self) -> 'Error':
        """Get the innermost error in the chain."""
        current = self
        inner = self
        
        while current and hasattr(current, 'error') and current.error:
            if isinstance(current.error, Error):
                inner = current.error
            current = current.error
        
        return inner

    def _get_actions(self) -> str:
        """Extract action recommendations from the error chain."""
        actions = []
        
        # Start with this error
        if self.action and self.action not in actions:
            actions.append(self.action)
        
        # Add from nested errors
        current = self.error
        while current and hasattr(current, 'action'):
            if current.action and current.action not in actions:
                actions.append(current.action)
            current = getattr(current, 'error', None)
            
        actions.reverse()
        return " -> ".join(actions) if actions else ""
        
    def _get_user_message(self) -> str:
        """Get the first user message from the error chain."""
        msg = "Internal Error"       
        current = self
        while current:         
            if getattr(current, '_user_message', None):
                msg = current._user_message
            current = getattr(current, 'error', None)          
        return msg

    def add_context(self, context: str) -> 'Error':
        """Add a context to the call chain."""
        # Don't add empty context
        if not context:
            return self
            
        # Initialize context if needed
        if not self.context:
            self.context = context
            return self
            
        # Add context if not already present
        parts = self.context.split(" -> ")
        if context not in parts:
            self.context = f"{context} -> {self.context}"
            
        return self
        
    def user_message(self) -> str:
        """Return the user-friendly error message."""
        msg = self._get_user_message()
        return msg if msg else "Internal Error"

    def __str__(self) -> str:
        """String representation for easier debugging."""
        try:
            return self.to_string()
        except Exception as e:
            return f"Error (string representation failed: {e})"


class TrackError(Error):
    """
    Used to track non-handled exceptions across intermediate functions.
    
    This error type is designed to maintain call context without adding
    redundant descriptions. It's useful for tracking errors through a call
    chain while preserving the original error's details.
    """
    def __init__(self, error: Exception, context: Optional[str] = None):
        """
        Initialize a TrackError to follow an exception through the call stack.
        
        Args:
            error: The original exception being tracked
            context: Call context to add to the chain
        """
        super().__init__(
            error=error,
            # No description - we're just tracking the error
            context=context
        )

class ApiKeyError(Error):
    """Specific error indicating an invalid or expired API key."""
    def __init__(self, description: Optional[str] = None, action: Optional[str] = None):
        super().__init__(description=description, action=action)
        
        
class UserError(Error):
    """Error that can be presented to the user with a friendly message."""
    def __init__(
            self, 
            error: Optional[Exception] = None, 
            description: Optional[str] = None, 
            action: Optional[str] = None, 
            critical: bool = False, 
            location: Optional[str] = None, 
            context: Optional[str] = None, 
            user_message: str = "Internal Error"
        ):
        super().__init__(
            error=error,
            description=description,
            action=action,
            critical=critical,
            location=location,
            context=context
        )
        self._user_message = user_message