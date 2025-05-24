"""
database package: 
"""
from .generators import *
from .backends import *
from .config import *
from .connections import *
from .entity import *
from .factory import *

""" from ..utils import patcher
from typing import TYPE_CHECKING

patcher.patch_class(PostgresAsyncConnection, EntityAsyncMixin)
patcher.patch_class(MysqlAsyncConnection, EntityAsyncMixin)
patcher.patch_class(SqliteAsyncConnection, EntityAsyncMixin)
if TYPE_CHECKING:
    class PostgresAsyncConnection(PostgresAsyncConnection, EntityAsyncMixin): pass
    class MySqlAsyncConnection(PostgresAsyncConnection, EntityAsyncMixin): pass
    class SqliteAsyncConnection(PostgresAsyncConnection, EntityAsyncMixin): pass """