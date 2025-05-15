import json
import traceback
import os
import sys
import re
from .. import log as logger

def _get_location(frame_offset=2):
    """Get filename, function name, and line number from the call stack."""
    try:
        frame = sys._getframe(frame_offset)
        code = frame.f_code
        return f'{code.co_filename} {code.co_name} line {frame.f_lineno}'
    except Exception:
        return "unknown location"

def _get_exception_location(exception):
    """Extract the location information from an exception's traceback."""
    t = _get_caller_details(exception)
    if not t:
        return None
    return f'{t[1]} {t[2]} line {t[3]}'

def _get_caller_details(exception: Exception, tag=None):
    """
    Extract detailed location information including class from an exception's traceback.
    
    Returns:
        tuple: (module_or_class, funcname, filename, lineno) or None
    """
    try:
        if not hasattr(exception, '__traceback__'):
            return None
            
        # First, get the regular traceback info
        tb = traceback.extract_tb(exception.__traceback__)
        if not tb:
            return None
        
        # Go through frames to find a suitable one
        for frame_summary in reversed(tb):
            filename, lineno, funcname, line = frame_summary
          
            if  'try_catch.py' not in filename:
                
                # We found our target frame, now try to get the class
                
                # Try to access the actual frame object to extract more info
                frame = None
                tb_frame = exception.__traceback__
                while tb_frame:
                    if tb_frame.tb_frame.f_code.co_name == funcname and tb_frame.tb_lineno == lineno:
                        frame = tb_frame.tb_frame
                        break
                    tb_frame = tb_frame.tb_next
                
                # If we have the frame, check for 'self'
                component = None
                if frame and 'self' in frame.f_locals:
                    try:
                        # Try to get class from self
                        self_obj = frame.f_locals.get('self')
                        if self_obj and hasattr(self_obj, '__class__'):
                            component = self_obj.__class__.__name__
                    except Exception:
                        pass
                
                # Fallback to module name if we couldn't get the class
                if not component:
                    module_name = os.path.basename(filename).split('.')[0]
                    component = module_name
                #logger.info(f"**** {funcname} tag: {tag}")
                return (component, funcname, filename, lineno)
        
        # Fallback to the last frame if we couldn't find a suitable one       
        filename, lineno, funcname, _ = tb[-1]
        module_name = os.path.basename(filename).split('.')[0]
        return (module_name, funcname, filename, lineno)
        
    except Exception as e:
        return None

def _clean_description(description):
    """Remove 'An error happened in X:' prefix from descriptions."""
    if description:
        return re.sub(r'^An error happened in [^:]+: ', '', description)
    return description


class Error(Exception):
    """
    Custom support-friendly error with chainable metadata.
    """
    def __init__(self, error=None, description=None, action=None, critical=False, location=None, context=None):
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

    #def __str__(self):        
       # return self.to_string()
    
    def to_dict(self):
        try:
            return json.loads(self._encode())
        except Exception:
            base_dict = {
                "description": self.description,
                "error": str(self.error),
                "location": self.location
            }
            
            # Add user_message if available
            if hasattr(self, '_user_message'):
                base_dict["user_message"] = self._user_message
                
            return base_dict

    def _encode(self):
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
            basic_dict = {
                "description": self.description,
                "error": str(self.error),
                "location": self.location
            }
            return json.dumps(basic_dict, indent=4)

    def _get_nested_error(self):
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

    def trace(self):
        """Return a list of error locations, from most recent to deepest."""
        try:
            cache = []
            
            # Add the current error's location
            if hasattr(self, 'location'):
                cache.append(self.location)
                
            # Add the nested error's location if it exists
            if self.error and isinstance(self.error, Exception) and hasattr(self.error, '__traceback__'):
                tb = traceback.extract_tb(self.error.__traceback__)
                if tb:
                    filename, lineno, funcname, _ = tb[-1]
                    location = f'{filename} {funcname} line {lineno}'
                    if location not in cache:
                        cache.append(location)
                        
            return cache
        except Exception:
            return ["Error generating trace"]

    def to_string(self):
        """String representation of the error."""
        # Prevent recursive calls to __str__
        if getattr(self, '_in_str_call', False):
            return f"{self.description or 'Error'}"
        
        try:
            self._in_str_call = True
            
            # Build a single comprehensive error message
            parts = []            
           
            # 1. Description 
            inner = self._get_inner_error() or self
            if inner.error:
                t = _get_caller_details(inner.error, 'to_string')
                if t:
                    parts.append(f"An error happened in {t[0]}.{t[1]}: {str(inner.error)}")
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
            
            result = "\n".join(parts)

            return result
        finally:
            self._in_str_call = False
            
    def _get_call_chain(self):
        """Get the call chain as a string."""
        # Start with an empty chain
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

        # Return the chain
        return " -> ".join(chain_parts) if chain_parts else ""
        
    def _get_consequences(self):
        """Get the consequences as a string."""
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
        
    def _get_inner_error(self):
        """Get the innermost error in the chain."""
        current = self
        inner = self  # Start with self as the innermost error
        
        # Traverse the error chain to find the innermost error
        while current and hasattr(current, 'error') and current.error:
            if isinstance(current.error, Error):
                inner = current.error
            current = current.error
        
        return inner

    def _get_actions(self):
        """Get the actions as a string."""
        actions = []
        
        # Start with this error
        if self.action and self.action not in actions:
            actions.append(self.action)
        
        # Add from nested errors
        current = self.error
        while current and hasattr(current, 'action'):
            if current.action and current.action not in actions:
                actions.append(current.action)
            current = current.error
            
        actions.reverse()
        return " -> ".join(actions) if actions else ""
        
    def _get_user_message(self):
        """Get the first user message."""
        msg = "Internal Error"       
        current = self
        while current:         
            msg = getattr(current, '_user_message', None)  or msg
            current = getattr(current, 'error', None)          
        return msg

    def add_context(self, context):
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
        
    def user_message(self):
        """Return the user-friendly error message."""
        msg = self._get_user_message()
        return msg if msg else "Internal Error"


class TrackError(Error):
    """
    Used to track non-handled exceptions across intermediate functions.
    """
    def __init__(self, error, description=None, context=None):
        super().__init__(
            error=error, 
            description=description, 
            context=context
        )
        

class ApiKeyError(Error):
    """
    Specific error indicating an invalid or expired API key.
    """
    def __init__(self, description=None, action=None):
        super().__init__(description=description, action=action)
        
        
class UserError(Error):
    """
    Error that can be presented to the user with a friendly message.
    """
    def __init__(self, error=None, description=None, action=None, critical=False, location=None, context=None, user_message="Internal Error"):
        super().__init__(
            error=error,
            description=description,
            action=action,
            critical=critical,
            location=location,
            context=context
        )
        self._user_message = user_message
        
    def user_message(self):
        """Return the user-friendly error message."""
        return self._user_message or super().user_message()