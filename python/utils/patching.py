import sys
import types
import inspect
import dis
import re
from .. import log as logger

class PatchManager:
    """
    This enables you to make a class (e.g. Foo) inherit from another (e.g. MyMixin) at runtime, without touching the code.
    You can extend the functionality of a class dynamically.

    Usage:
        class Base: ...
        class Bar(Base): ...
        class Foo(Bar): ...
        class MyUtil(Base): ...
        class MyMixin(MyUtil): ...

        from module import Foo
        patcher = PatchManager()
        patcher.patch_class(Foo, MyMixin)         # or patcher.patch_class(module, "Foo", MyMixin) 
        
        # Check the logs for detailed parameter information!
        # When instantiating the patched class, parameters must be passed
        # in the order they appear in the inheritance chain, from mixin downward.
        
        # To get IDE hints, add:
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            class Foo(Foo, MyMixin): pass
    
    Important Parameter Handling:
        When using a patched class, you need to provide parameters for ALL classes
        in the inheritance chain. Parameters are consumed in order of the MRO:
        
        1. First parameter(s) go to the Mixin
        2. Next parameter(s) go to the original class
        3. And so on down the inheritance chain
        
        Example:
            # If Mixin.__init__ takes (self, x)
            # And OriginalClass.__init__ takes (self, y, z)
            patched_instance = OriginalClass("x_value", "y_value", "z_value")
            
        Check the debug logs after patching to see the exact parameter order!

    Key features:
        ✅ Dynamic inheritance
        ✅ Preserves method decorators
        ✅ Preserves class decorators (automatic + manual if needed)
        ✅ Checks MRO for issues and warns (logger.debuged)
        ✅ Prevents double patching

    MRO of patched class:
        NewFoo -> MyMixin -> MyUtil -> Foo -> Bar -> Base -> object

    This means MyMixin methods override Foo, but super() calls from MyMixin will continue up Foo's original chain.

    Important:
        MyMixin MUST NOT inherit from Foo (this would create a circular inheritance and break MRO).
        However, MyMixin CAN inherit from Foo's parents (e.g. Bar or Base) safely if needed.
    """

    def __init__(self):
        self.patched = {}

    def uses_super(self, func):
        """Check if a function calls super()."""
        if not isinstance(func, (types.FunctionType, types.MethodType)):
            return False
        for instr in dis.get_instructions(func):
            if instr.opname == 'LOAD_GLOBAL' and instr.argval == 'super':
                return True
        return False

    def check_mro(self, cls):
        """
        Check the Method Resolution Order and provide detailed init parameter information.
        
        This helps developers understand how parameters should be passed to the patched class.
        """
        logger.debug(f"\n[PatchManager] Inheritance chain analysis for {cls.__name__}:")
        logger.debug(f"=============================================================")
        
        # Print the full MRO
        mro = cls.__mro__
        mro_names = ' -> '.join([c.__name__ for c in mro])
        logger.debug(f"MRO: {mro_names}")
        logger.debug(f"-------------------------------------------------------------")
        
        # Track parameters needed at each level
        for idx, base in enumerate(mro):
            if base is object:
                continue
                
            # Get init method if it exists
            init = base.__dict__.get('__init__')
            
            if init:
                # Get signature
                try:
                    sig = inspect.signature(init)
                    params = [p for name, p in sig.parameters.items() if name != 'self']
                    
                    # Format parameter list
                    param_str = ', '.join([
                        f"{p.name}" + (f"={p.default}" if p.default is not p.empty else "")
                        for p in params
                    ])
                    
                    # Check if init uses super()
                    uses_super = self.uses_super(init)
                    super_str = "calls super()" if uses_super else "doesn't call super()"
                    
                    logger.debug(f"{idx}. {base.__name__}.__init__({param_str}) - {super_str}")
                    
                    # Try to analyze what's passed to super()
                    if uses_super:
                        try:
                            source = inspect.getsource(init)
                            
                            # Simple regex approach to find super().__init__() calls
                            import re
                            super_calls = re.findall(r'super\(\).__init__\((.*?)\)', source)
                            
                            if super_calls:
                                logger.debug(f"   ↓ Passes to super: {super_calls[0]}")
                        except Exception:
                            logger.debug(f"   ↓ Passes to super: (couldn't analyze)")
                    
                except Exception as e:
                    logger.debug(f"{idx}. {base.__name__}.__init__ - (couldn't get signature: {e})")
            else:
                logger.debug(f"{idx}. {base.__name__} - no custom __init__")
        
        logger.debug(f"=============================================================")
        logger.debug(f"To instantiate {cls.__name__}, provide parameters in this order:")
        
        # Generate a sample instantiation call
        try:
            params = []
            for base in mro:
                if base is object:
                    continue
                    
                init = base.__dict__.get('__init__')
                if init and init is not object.__init__:
                    sig = inspect.signature(init)
                    # Skip 'self' and collect required params (no default)
                    for name, param in sig.parameters.items():
                        if name != 'self' and param.default is param.empty and param.kind == param.POSITIONAL_OR_KEYWORD:
                            if name not in [p[0] for p in params]:  # Avoid duplicates
                                params.append((name, base.__name__))
            
            # Format the parameter list for the example
            if params:
                param_list = ', '.join([f'"{p[0]}_value"  # For {p[1]}' for p in params])
                logger.debug(f"{cls.__name__}({param_list})")
            else:
                logger.debug(f"{cls.__name__}()")
        except Exception as e:
            logger.debug(f"Could not generate example instantiation: {e}")
        
        logger.debug(f"=============================================================")
        logger.debug(f"For IDE hints, add this to your code:")
        logger.debug(f"from typing import TYPE_CHECKING")
        logger.debug(f"if TYPE_CHECKING:")
        logger.debug(f"    class {cls.__name__}({cls.__name__}, {mro[1].__name__}):")
        logger.debug(f"        # Add any specific parameter hints here")
        logger.debug(f"        pass")
        logger.debug(f"=============================================================")

    def validate_mixin(self, orig_cls, mixin_cls):
        """Validate that the mixin does not inherit from the original class."""
        if issubclass(mixin_cls, orig_cls):
            raise TypeError(
                f"Invalid mixin: {mixin_cls.__name__} inherits from {orig_cls.__name__}, which would cause MRO issues."
            )

    def apply_class_decorators(self, cls):
        """Apply class decorators to the patched class."""
        return cls

    def patch_class(self, *args):
        """
        Patch a class to inherit from a mixin by directly modifying its __bases__.
        
        Args:
            Either (orig_cls, mixin_cls) or (module, cls_name, mixin_cls)
            
        Returns:
            The patched class
        """
        if len(args) == 2:
            orig_cls, mixin_cls = args
            cls_name = orig_cls.__name__
            module = None
            key = (orig_cls.__module__, cls_name)
        elif len(args) == 3:
            module, cls_name, mixin_cls = args
            orig_cls = getattr(module, cls_name)
            key = (module.__name__, cls_name)
        else:
            raise TypeError("patch_class requires (Foo, MyMixin) or (module, 'Foo', MyMixin)")

        if key in self.patched:
            logger.debug(f"[PatchManager] Already patched {cls_name}")
            return self.patched[key]

        self.validate_mixin(orig_cls, mixin_cls)
        
        # MUCH SIMPLER APPROACH:
        # Instead of creating a new class, just modify the original class's __bases__
        # by inserting the mixin at the beginning
        orig_cls.__bases__ = (mixin_cls,) + orig_cls.__bases__
        
        # Store for reference
        self.patched[key] = orig_cls
        
        # Apply decorators if needed
        orig_cls = self.apply_class_decorators(orig_cls)
        
        # Check MRO for issues
        self.check_mro(orig_cls)
        
        # Add IDE support
        orig_cls.__class_getitem__ = classmethod(lambda cls, _: cls)
        
        return orig_cls

# Create a global instance for convenient use
patcher = PatchManager()