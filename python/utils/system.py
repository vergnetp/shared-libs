import psutil
from typing import Union

def can_file_fit_in_memory(file_size_mb: Union[int, float]) -> bool:
    """
    Check if there is enough available RAM for a file of the given size (MB).
    """
    return float(file_size_mb) * 1024 * 1024 < psutil.virtual_memory().available