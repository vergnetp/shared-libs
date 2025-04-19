# This module provides exceptions designed for support and debugging purposes.

Use Error to wrap exceptions with additional context like a description or a recommended action.

Use TrackError to trace function call paths (stack traces) through your application.

When converted to a string, errors are pretty-printed recursively down to the root cause.

The critical flag bubbles up when set to True anywhere in the chain.

## Example

```
def get_data():
    try:
        try:
            f = open('my database', 'r')
        except Exception as e:
            raise Error(e, description="Connection to 'my database' failed", action='check inner exception')
        return f.read()
    except Exception as e:
        raise TrackError(e)

def appli():
    try:
        data = get_data()
    except Exception as e:
        raise Error(e, description='could not get data from database', action='cancel the order', critical=True)

def api():
    try:
        appli()
    except Exception as e:
        raise Error(e, description='Internal Error', action='Please try again later')

try:
    api()
except Exception as e:    
    print(e)
    
```

The above returns:

```
Error:
{
    "description": "Internal Error",
    "action": "Please try again later",
    "critical": True,
    "location": "...\\test.py api line 23",
    "error": {
        "description": "could not get data from database",
        "action": "cancel the order",
        "critical": True,
        "location": "...\\test.py appli line 17",
        "error": {
            "description": "Connection to \"my database\" failed",
            "action": "check inner exception",
            "location": "...\\test.py get_data line 7",
            "error": {
                "description": "[Errno 2] No such file or directory: 'my database'",
                "location": "...\\test.py get_data line 5"
            }
        }
    }
}

Stack:
['...\\test.py api line 23', 
'...\\test.py appli line 17', 
'...\\test.py get_data line 11', 
'...\\test.py get_data line 7', 
'...\\test.py get_data line 5']

```
