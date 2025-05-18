import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import formataddr
from email import encoders
import time
from typing import List, Optional, Union, Dict, Any

from . import EmailAdapter
from ..email_config import EmailConfig
from ...errors import Error, try_catch

class SMTPAdapter(EmailAdapter):
    """
    SMTP email provider adapter.
    
    Implements email sending via SMTP protocol, supporting
    both regular SMTP servers and Gmail.
    """
    
    def __init__(self, config: EmailConfig):
        """
        Initialize SMTP adapter with config.
        
        Args:
            config: Email configuration
        """
        self.config = config
        self.server = None
        
        # Extract SMTP settings from config
        self.host = config.get_provider_setting("smtp_host", "smtp.gmail.com")
        self.port = config.get_provider_setting("smtp_port", 465)
        self.username = config.get_provider_setting("smtp_user", config.from_address)
        self.password = config.get_provider_setting("smtp_password")
        self.use_ssl = config.get_provider_setting("use_ssl", True)
        
        # Verify required settings
        if not self.username:
            raise ValueError("SMTP username/email is required")
        if not self.password:
            raise ValueError("SMTP password is required")
            
    def _connect(self):
        """
        Connect to the SMTP server.
        
        Returns:
            SMTP server instance
        """
        # Create SSL context
        context = ssl.create_default_context()
        
        # Connect with SSL
        if self.use_ssl:
            server = smtplib.SMTP_SSL(self.host, self.port, context=context)
        else:
            server = smtplib.SMTP(self.host, self.port)
            server.starttls(context=context)
            
        # Login
        server.login(self.username, self.password)
        
        return server
    
    @try_catch(
        description="Failed to send email via SMTP",
        action="Check SMTP credentials and connectivity"
    )
    def send_email(
        self,
        subject: str,
        recipients: List[str],
        text: Optional[str] = None,
        html: Optional[str] = None,
        from_address: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via SMTP.
        
        Args:
            subject: Email subject
            recipients: List of recipient email addresses
            text: Plain text email body
            html: HTML email body
            from_address: Sender email address (overrides config default)
            reply_to: Reply-to address (overrides config default)
            cc: List of CC recipients
            bcc: List of BCC recipients
            attachments: List of attachment dictionaries
            headers: Additional email headers
            
        Returns:
            Dict with status information
        """
        # Validate basic parameters
        if not recipients:
            raise ValueError("At least one recipient is required")
        if not text and not html:
            raise ValueError("Either text or HTML content is required")
            
        # Set up sender
        sender = from_address or self.config.from_address or self.username
        reply_address = reply_to or self.config.reply_to or sender
        
        # Apply default subject prefix if any
        if self.config.default_subject_prefix:
            subject = f"{self.config.default_subject_prefix}{subject}"
            
        # Create message container
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = formataddr(("", sender))
        msg['To'] = ", ".join(recipients)
        
        # Add CC recipients if provided
        if cc:
            msg['Cc'] = ", ".join(cc)
            recipients.extend(cc)
            
        # Add BCC recipients (not visible in headers but added to recipients list)
        if bcc:
            recipients.extend(bcc)
            
        # Add Reply-To header
        if reply_address:
            msg['Reply-To'] = reply_address
            
        # Add custom headers if provided
        if headers:
            for name, value in headers.items():
                msg[name] = value
                
        # Add text content
        if text:
            msg.attach(MIMEText(text, 'plain'))
            
        # Add HTML content
        if html:
            msg.attach(MIMEText(html, 'html'))
            
        # Add attachments
        if attachments:
            for attachment in attachments:
                self._add_attachment(msg, attachment)
                
        # Connect to server and send
        server = self._connect()
        server.sendmail(sender, recipients, msg.as_string())
        server.quit()
                
        # Return success
        return {
            "status": "sent",
            "recipients": len(recipients),
            "subject": subject,
            "has_attachments": bool(attachments)
        }
                
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]) -> None:
        """
        Add an attachment to the email.
        
        Args:
            msg: Email message container
            attachment: Attachment details dictionary
            
        Returns:
            None
        """
        # Extract attachment details
        filename = attachment.get('filename')
        content = attachment.get('content')
        content_type = attachment.get('content_type', 'application/octet-stream')
        
        if not filename:
            raise ValueError("Attachment filename is required")
            
        if not content:
            raise ValueError("Attachment content is required")
            
        # Create attachment part
        part = MIMEBase(*content_type.split('/', 1))
        part.set_payload(content)
        
        # Encode and add headers
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            
        # Add to message
        msg.attach(part)
                
    def close(self) -> None:
        """
        Close SMTP connection if open.
        
        Returns:
            None
        """
        pass  # No persistent connection to close in this implementation