"""
emailing package: Flexible email system with provider adapters.

Main class:
- Emailer: Main class for sending emails

Configuration classes:
- EmailConfig: Configuration for email operations

Provider adapters:
- SMTPAdapter: SMTP email provider adapter (including Gmail)
"""

from .email_config import EmailConfig
from .emailer import Emailer
from .adapters.smtp_adapter import SMTPAdapter