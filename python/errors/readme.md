# This module is meant to offer Support friendly Exceptions

Error is to be raised when you want to want to add custom description or action (for support purpose mainly).

When converted to string, it will pretty print the chained Errors down to the possible unhandled error.

TrackError is to be raised in all functions you want to trace the stack for.

Note that the critical flag bubble up once True

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

def pass_through():
    try:
        return get_data()
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
    "location": "C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py api line 41",
    "error": {
        "description": "could not get data from database",
        "action": "cancel the order",
        "critical": True,
        "location": "C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py appli line 35",
        "error": {
            "description": "Connection to \"my database\" failed",
            "action": "check inner exception",
            "location": "C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py get_data line 20",
            "error": {
                "description": "[Errno 2] No such file or directory: 'my database'",
                "location": "C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py get_data line 18"
            }
        }
    }
}

Stack:
['C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py api line 41', 'C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py appli line 35', 'C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py pass_through line 29', 'C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py get_data line 23', 'C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py get_data line 20', 'C:\\Users\\vergn\\Desktop\\DigitalPixo\\repo\\server\\test.py get_data line 18']
```
