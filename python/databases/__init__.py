"""
database package: 
"""
from .base import *
from .factory import *
from .mysql import *
from .sqlite import *
from .postgres import *


def init_database(db_type: str, **kwargs) -> Database:
    return DatabaseFactory(db_type, **kwargs)