"""
logging package: info(msg)
"""
from .logging import *

def init_logger(
    service_name: str,
    redis_url: str = None,
    log_dir: str = None,
    min_level: str = "INFO",
    log_debug_to_file: bool = True,
    quiet_init: bool = True,
):

    Logger.get_instance(
        service_name=service_name,
        redis_url=redis_url,
        log_dir=log_dir,
        min_level=min_level,
        log_debug_to_file=log_debug_to_file,
        quiet_init=quiet_init,
        use_redis=bool(redis_url),
    ) 