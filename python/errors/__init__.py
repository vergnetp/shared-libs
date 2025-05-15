"""
errors package: expose Error, TrackError and ApiKeyError. 

Eample:

    except Exception as e:
        raise Error(e, description="Connection to 'my database' failed", action='check inner exception')
        raise TrackError(e) # to simply add the exception in the tracked stack
"""
from .error import *
from .try_catch import try_catch
