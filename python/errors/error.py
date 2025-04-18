import json
import traceback
import sys


def _get_location(frame_offset=2):
    """Get filename, function name, and line number from the call stack."""
    frame = sys._getframe(frame_offset)
    code = frame.f_code
    return f'{code.co_filename} {code.co_name} line {frame.f_lineno}'


class Error(Exception):
    """
    Custom support-friendly error with chainable metadata.
    """
    def __init__(self, error=None, description=None, action=None, critical=False, location=None):
        self.description = description
        self.action = action
        self.critical = critical
        self.location = location or _get_location()
        self.error = error

        # Bubble up the critical flag
        if hasattr(error, 'critical') and error.critical:
            self.critical = True

    def to_dict(self):
        return json.loads(self._encode())

    def _encode(self):
        dic = self.__dict__.copy()
        nested = self._get_nested_error()
        if nested:
            dic['error'] = nested
        return json.dumps(dic, indent=4)

    def _get_nested_error(self):
        tmp = getattr(self, 'error', None)
        while isinstance(tmp, TrackError):
            tmp = tmp.error

        if tmp is None:
            return None

        if isinstance(tmp, Error):
            return json.loads(tmp._encode())

        if isinstance(tmp, Exception):
            tb = traceback.extract_tb(tmp.__traceback__)
            if tb:
                filename, lineno, funcname, _ = tb[-1]
                return {'description': str(tmp), 'location': f'{filename} {funcname} line {lineno}'}
            else:
                return {'description': str(tmp), 'location': 'unknown'}

        return str(tmp)  # fallback

    def trace(self):
        cache = []
        self._trace(self, cache)
        return cache

    @staticmethod
    def _trace(err, cache=None):
        if cache is None:
            cache = []

        if err is None:
            return

        if hasattr(err, 'location'):
            cache.append(err.location)
        elif hasattr(err, '__traceback__'):
            tb = traceback.extract_tb(err.__traceback__)
            if tb:
                filename, lineno, funcname, _ = tb[-1]
                cache.append(f'{filename} {funcname} line {lineno}')
            else:
                cache.append('unknown')
        else:
            cache.append('unknown')

        if hasattr(err, 'error'):
            Error._trace(err.error, cache)

    def __str__(self):
        return f"Error:\n{self._encode()}\nTrace:\n{self.trace()}"


class TrackError(Error):
    """
    Used to track non-handled exceptions across intermediate functions.
    """
    def __init__(self, error):
        super().__init__(error=error)
        self.location = _get_location()


class ApiKeyError(Error):
    """
    Specific error indicating an invalid or expired API key.
    """
    def __init__(self, description=None, action=None):
        super().__init__(description=description, action=action)
        self.location = _get_location()
