import pytest
from .. import Error, TrackError, ApiKeyError, try_catch, UserError
from ... import log as logger

def test_basic_error_str_contains_description_and_location():
    err = Error(description="Something went wrong", action="Retry", critical=True)
    output = err.to_string()
    assert "Something went wrong" in output
    assert "Retry" in output
    assert "line" in output  # should include line number in location

def test_error_chain_bubbles_critical_flag():
    try:
        raise ValueError("Base error")
    except ValueError as e:
        wrapped = Error(error=e, critical=True)
    assert wrapped.critical is True

def test_track_error_sets_location():
    try:
        raise ValueError("Inner")
    except Exception as e:
        err = TrackError(e)
    assert "line" in err.location
    assert "test_track_error_sets_location" in err.location

def test_api_key_error_has_expected_fields():
    err = ApiKeyError(description="Invalid key", action="Check your key")
    assert isinstance(err, Error)
    assert err.description == "Invalid key"
    assert err.action == "Check your key"
    assert "line" in err.location

def test_trace_includes_all_locations():
    try:
        try:
            raise ValueError("low-level")
        except Exception as e:
            raise TrackError(e)
    except Exception as e:
        err = Error(e)
    trace = err.trace()
    assert isinstance(trace, list)
    assert any("line" in entry for entry in trace)

def test_error_encoding_with_nested_errors():
    try:
        raise ValueError("base")
    except Exception as e:
        err = Error(error=TrackError(e), description="top level")
    encoded = err.to_string()
    logger.info(encoded)
    assert "top level" in encoded
    assert "line" in encoded


def test_try_catch():
    class Database:
        @try_catch
        def connect(self, connection_string):
            # Simulate a database connection error
            raise ValueError("Connection refused")
        
        @try_catch
        def query(self, sql):
            # Normal execution
            return f"Results for: {sql}"

    class Postgres(Database):
        def __init__(self):
            pass
            
        # Not decorated method - will pass through to parent
        @try_catch
        def reconnect(self, connection_string):
            return super().connect(connection_string)

    @try_catch
    def do():
         db = Postgres()
         db.reconnect("whatever")
    
    @try_catch(description="Could not pay",action="Refund the client", critical=True)
    def pay_stripe_error():
        try:           
            raise Exception("Stripe Failure")
        except Exception as e:
            raise UserError(e,"Could not process payment with Stripe","Investigate stripe error",user_message="Your payment could not be processed. You have not been charged")
        do()

    @try_catch(description="App failed",action="Investigate App issue", critical=True)
    def main_stripe_error():
        pay_stripe_error()


    @try_catch(user_message="Internal Error. Please try again later",description="Web service failed",action="Investigate web service issue")
    def server_process_request_stripe_error():
        main_stripe_error()

    try:
        server_process_request_stripe_error()
    except Error as e:
        # Print the full error information
        logger.error(f"Error:\n{e.to_string()}")
        # send nessage back to user
        user_message = e.user_message() 

    @try_catch(description="Could not pay",action="Refund the client", critical=True)
    def pay_processing_error():
        try:
            ret = 4
        except Exception as e:
            raise UserError(e,"Could not process payment with Stripe","Investigate stripe error",user_message="Your payment could not be processed. You have not been charged")
        do()

    @try_catch(description="App failed",action="Investigate", critical=True)
    def main_processing_error():
        pay_processing_error()

    @try_catch(user_message="Internal Error. Please try again later")
    def server_process_request_processing_error():
        main_processing_error()


    try:
        server_process_request_processing_error()
    except Error as e:
        # Print the full error information
        logger.error(f"Error:\n{e.to_string()}")
        # send nessage back to user
        user_message = e.user_message() 

   #    # todo: assert on  the log
        

def test_readme_example():
    # Low-level payment processor
    @try_catch(
        description="Could not process payment with Stripe",
        action="Investigate stripe error",
        critical=True
    )
    def process_payment():
        try:           
            # Code that might fail
            raise Exception("Stripe Failure")
        except Exception as e:
            # Create a user-friendly error
            raise UserError(
                e,
                "Could not process payment with Stripe",
                "Investigate stripe error",
                user_message="Your payment could not be processed. You have not been charged"
            )

    # Mid-level application logic
    @try_catch(
        description="App failed",
        action="Investigate App issue", 
        critical=True
    )
    def execute_transaction():
        process_payment()  # This will propagate errors upward with added context

    # Top-level API endpoint
    @try_catch(
        user_message="Internal Error. Please try again later",
        description="Web service failed",
        action="Investigate web service issue"
    )
    def api_endpoint():
        try:
            execute_transaction()
            return {"success": True}
        except Error as e:
            # Log the full error details for debugging
            logger.error(f"API Error:\n{e.to_string()}")
            
            # Return only the user-friendly message
            return {"success": False, "error": e.user_message()}
    
    api_endpoint()
   
    # todo: assert on 
    """Could not process payment with Stripe: Stripe Failure
Call chain: process_payment -> execute_transaction
Consequences: Could not process payment with Stripe -> App failed
Action: Investigate stripe error -> Investigate App issue
Official message: Your payment could not be processed. You have not been charged
Location: ...test_error.py process_payment line 146"""
    #assert False