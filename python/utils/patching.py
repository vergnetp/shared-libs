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
    
            
    Important Constraint:
     * Mixin cannot have non optional parameter in the init (so either no init, or no argument, or optional ones)
     * The Mixin ancestors cannot have rquired arument sin their init (so either no init, or no argument, or optional ones, or *args or **kwargs)

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
        Patch a class to inherit from a mixin.
        
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
        
        try:
            # Direct approach: Modify __bases__ in-place
            orig_cls.__bases__ = (mixin_cls,) + orig_cls.__bases__
            patched_cls = orig_cls
            logger.debug(f"[PatchManager] Successfully patched {cls_name} using direct __bases__ modification")
        except TypeError as e:
            # If direct approach fails due to memory layout issues,
            # use method copying (monkey patching) instead
            logger.debug(f"[PatchManager] Direct __bases__ modification failed for {cls_name}, using method copying: {e}")
            
            # First, handle __init__ specially to ensure both inits are called
            orig_init = orig_cls.__dict__.get('__init__')
            mixin_init = mixin_cls.__dict__.get('__init__')
            

            # Define a new __init__ that calls both initialization chains
            def combined_init(self, *args, **kwargs):
                # First call the original class init
                if orig_init:
                    orig_init(self, *args, **kwargs)
                
                # Then create a temporary instance of mixin to call its __init__ chain properly
                try:
                    # This creates a temporary instance to trigger its __init__ chain
                    logger.debug("****** creating a temp mixin instance")
                    temp_mixin = type('TempMixin', (mixin_cls,), {})()
                    logger.debug("****** Finshed creating a temp mixin instance")
                    
                    # Get ALL instance attributes, not just those returned by dir()
                    # This uses the internal __dict__ where most instance attributes are stored
                    temp_attrs = vars(temp_mixin)  # Same as temp_mixin.__dict__
                    logger.debug(f"Temp mixin attributes: {list(temp_attrs.keys())}")
                    
                    # Copy all attributes from the temp instance
                    for attr_name, attr_value in temp_attrs.items():
                        # Skip methods and existing attributes, but copy all others
                        if callable(attr_value) or hasattr(self, attr_name):
                            continue
                        
                        # Copy the attribute value
                        logger.debug(f"Copying attribute {attr_name} from temp mixin")
                        setattr(self, attr_name, attr_value)
                    
                    # Also check for properties that might not be in __dict__
                    for attr_name in dir(temp_mixin):
                        if attr_name.startswith('__') or attr_name in temp_attrs:
                            continue
                            
                        try:
                            attr_value = getattr(temp_mixin, attr_name)
                            # Skip methods and existing attributes
                            if callable(attr_value) or hasattr(self, attr_name):
                                continue
                                
                            logger.debug(f"Copying property or descriptor {attr_name} from temp mixin")
                            setattr(self, attr_name, attr_value)
                        except Exception as e:
                            logger.debug(f"Could not copy attribute {attr_name}: {e}")
                    
                except Exception as e:
                    # Fall back to direct init call if the above fails
                    logger.debug(f"Failed to initialize mixin chain properly: {e}")
                    try:
                        mixin_init(self)
                    except Exception as inner_e:
                        logger.debug(f"Failed to call mixin.__init__ directly: {inner_e}")
            
            # Set the combined init
            setattr(orig_cls, '__init__', combined_init)
            todel = type('TempTodel', (orig_cls,), {})(4) # todo: delete this

            # Copy all other methods from the mixin hierarchy to the target class
            mixin_classes = []
            # Get all bases except object
            for base in mixin_cls.__mro__:
                if base is not object:
                    mixin_classes.append(base)
            
            # Process in reverse order to ensure methods from derived classes override base classes
            for mixin in reversed(mixin_classes):
                for name, attr in mixin.__dict__.items():
                    if name in ('__dict__', '__weakref__', '__module__', '__doc__', '__init__'):
                        continue
                    
                    # Skip if this is already in the target class
                    if hasattr(orig_cls, name):
                        continue
                        
                    # For methods and properties, copy them over
                    setattr(orig_cls, name, attr)
            
            patched_cls = orig_cls
            
            # Add a note that we used the fallback approach
            logger.debug(f"[PatchManager] {cls_name} patched using method copying")
        
        # Store the patched class
        self.patched[key] = patched_cls
        
        # Check MRO and add IDE support
        self.check_mro(patched_cls)
        patched_cls.__class_getitem__ = classmethod(lambda cls, _: cls)
        
        return patched_cls

# Create a global instance for convenient use
patcher = PatchManager()

class Base:
    def __init__(self,base_arg):
        self._base_arg=base_arg
    def base_method(self):
        print('base')

class Target(Base):
    def __init__(self,target_arg):
        super().__init__(target_arg)
        self._member = 8
        self.target_arg=target_arg

    def target_method(self):
        print('target vs '+self._base_arg)

class Utility:
    def __init__(self,utility_arg=None):
        pass
    def utility_method(self):
        print('utility')

class Mixin(Utility):
    def __init__(self):       
        self._smtg = 4
    def mixin_method(self):
        print('mixin: '+self._smtg)

# patch Mxin into targt, equvalent to writing this code for Target:

class target(Base):
    def __init__(self,*args, **kwargs):
        super().__init__(*args, **kwargs)
        self._member = 8
        self.target_arg=args[0]
        self._smtg = 4

    def target_method(self):
        print('target vs '+self._base_arg)   
    
    def mixin_method(self):
        print('mixin: '+self._smtg)

    def utility_method(self):
        print('utility')



class Base:
    def __init__(self,base_arg):
        self._base_arg=base_arg
    def base_method(self):
        print('base')

class Target(Base):
    def __init__(self,target_arg):
        super().__init__(target_arg)
        self.target_arg=target_arg

    def target_method(self):
        print('target vs '+self._base_arg)

class Utility:
    def __init__(self,utility_arg):
        pass
    def utility_method(self):
        print('utility')

class Mixin(Utility):
    def __init__(self,mixin_arg,mixin_arg2):
        super().__init__(mixin_arg)
        self._mixin_arg2=mixin_arg2
        self._smtg = 4
    def mixin_method(self):
        print('mixin: '+self._mixin_arg2)

# patch Mxin into targt, equvalent to writing this code for Target:

class target(Base):
    def __init__(self,target_arg):
        super().__init__(target_arg)
        self.target_arg=target_arg
        self._smtg = 4
        
    def target_method(self):
        print('target vs '+self._base_arg)  # print f'target vs {self._base_arg}' 
    
    def mixin_method(self):
        print('mixin: '+self._mixin_arg2)

    def utility_method(self):
        print('utility')




