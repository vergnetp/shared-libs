import functools
import asyncio


def auto_transaction(func):
    """
    Decorator that automatically wraps a function in a transaction.
    Works for both sync and async functions.
    
    If the decorated function is called when a transaction is already in progress,
    it will use the existing transaction. Otherwise, it will create a new transaction,
    commit it if the function succeeds, or roll it back if an exception occurs.

    Need to be applied to methods of a class that offers in_transaction, begin_transaction (and commit/rollback)
    
    Usage:
        @auto_transaction
        def some_function(self, ...):
            # Function body, runs within a transaction
            
        @auto_transaction
        async def some_async_function(self, ...):
            # Async function body, runs within a transaction
    """
    @functools.wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        if self.in_transaction():
            return func(self, *args, **kwargs)
        else:
            self.begin_transaction()
            try:
                result = func(self, *args, **kwargs)
                self.commit_transaction()
                return result
            except:
                self.rollback_transaction()
                raise

    @functools.wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        if await self.in_transaction():
            return await func(self, *args, **kwargs)
        else:
            await self.begin_transaction()
            try:
                result = await func(self, *args, **kwargs)
                await self.commit_transaction()
                return result
            except:
                await self.rollback_transaction()
                raise

    # Choose the appropriate wrapper based on whether the function is async or not
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
    
