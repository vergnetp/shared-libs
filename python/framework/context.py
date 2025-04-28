"""
This is to be able to pass the request id from the app (actually the middleware processing every request) to the logger.
Python contexts are kind of thread safe global variables
"""


from contextvars import ContextVar

# Global context variable for request_id
request_id_var: ContextVar[str] = ContextVar("request_id", default=None)