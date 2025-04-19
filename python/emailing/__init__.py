"""
emailing package: expose send_email(subject: str, recipients: List[str], text: Optional[str] = None, html: Optional[str] = None,
               use_gmail: bool = True, attached_file: Optional[str | bytes] = None, 
               compress: Optional[bool] = False, attached_file_name: Optional[str] = None)
"""
from .emailer import *