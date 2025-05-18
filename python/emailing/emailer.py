import os
import io
import zipfile
import mimetypes
from typing import List, Optional, Union, Dict, Any

from .email_config import EmailConfig
from .adapters.smtp_adapter import SMTPAdapter
from .adapters import EmailAdapter

from .. import log as logger
from ..errors import TrackError, Error, try_catch

class Emailer:
    """
    Main class for sending emails.
    
    Provides a unified interface for sending emails with
    different providers, handling attachments, and managing
    configuration.
    """
    
    def __init__(self, config: EmailConfig):
        """
        Initialize the emailer with configuration.
        
        Args:
            config: Email configuration
        """
        self.config = config
        
        # Initialize the appropriate adapter based on provider
        if config.provider == "smtp":
            self.adapter = SMTPAdapter(config)
        else:
            raise ValueError(f"Unsupported provider: {config.provider}")
            
    @try_catch
    def compress_file(self, data: Union[str, bytes]) -> bytes:
        """
        Compresses a file or bytes into a ZIP archive.
    
        Args:
            data (str | bytes): Path to the file or raw bytes to compress.
    
        Returns:
            bytes: The compressed ZIP file content.
        """
        try:
            if isinstance(data, str):
                with open(data, 'rb') as f:
                    data = f.read()
                    
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.writestr('compressed_file', data)  # Use a placeholder filename
                
            return zip_buffer.getvalue()
            
        except Exception as e:
            # Using Error instead of TrackError with named parameters
            raise Error(e, description="Error compressing file")
    
    @try_catch
    def send_email(
        self,
        subject: str,
        recipients: List[str],
        text: Optional[str] = None,
        html: Optional[str] = None,
        attached_file: Optional[Union[str, bytes]] = None, 
        compress: Optional[bool] = False,
        attached_file_name: Optional[str] = None,
        from_address: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email with optional text, HTML content, and attachments.
    
        Args:
            subject (str): Subject of the email.
            recipients (List[str]): List of recipient email addresses.
            text (Optional[str]): Plain text version of the email content.
            html (Optional[str]): HTML version of the email content.
            attached_file (Optional[str | bytes]): File path or bytes to attach.
            compress (Optional[bool]): Compress the file before attaching.
            attached_file_name (Optional[str]): Name of the file attachment.
            from_address (Optional[str]): Sender email address (overrides default).
            reply_to (Optional[str]): Reply-to address (overrides default).
            cc (Optional[List[str]]): List of CC recipients.
            bcc (Optional[List[str]]): List of BCC recipients.
            headers (Optional[Dict[str, str]]): Additional email headers.
    
        Returns:
            Dict[str, Any]: Email sending status and details.
        """
        # Process attachment if provided
        attachments = None
        if attached_file:
            attachments = []
            
            # Process file path or raw bytes
            if isinstance(attached_file, str):
                # It's a file path
                if not os.path.exists(attached_file):
                    # Using Error with TrackError's expected constructor
                    raise Error(None, f"File does not exist: {attached_file}")
                    
                # Get filename if not provided
                if not attached_file_name:
                    attached_file_name = os.path.basename(attached_file)
                    
                # Read file if it's a path
                with open(attached_file, 'rb') as f:
                    attached_file = f.read()
                    
            # Calculate file size
            file_size_mb = len(attached_file) / (1024 * 1024)
                
            # Compress if requested
            if compress:
                attached_file = self.compress_file(attached_file)
                
                # Update filename for compressed file
                if attached_file_name:
                    base_name, _ = os.path.splitext(attached_file_name)
                    attached_file_name = f"{base_name}.zip"
                else:
                    attached_file_name = "compressed_file.zip"
                    
            # Check size limit
            if file_size_mb > self.config.max_file_size_mb:
                # Using Error with the correct arguments
                msg = f"File size exceeds {self.config.max_file_size_mb} MB limit"
                raise Error(None, msg, "Compress the file or use a smaller attachment")
                
            # Determine content type
            content_type = "application/octet-stream"
            if attached_file_name:
                guessed_type, _ = mimetypes.guess_type(attached_file_name)
                if guessed_type:
                    content_type = guessed_type
                    
            # Add attachment to list
            attachments.append({
                "filename": attached_file_name or "attachment.bin",
                "content": attached_file,
                "content_type": content_type
            })
            
        # Send email using the adapter
        result = self.adapter.send_email(
            subject=subject,
            recipients=recipients,
            text=text,
            html=html,
            from_address=from_address,
            reply_to=reply_to,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            headers=headers
        )
        
        # Log success
        logger.info(
            f"Email sent successfully",
            recipients=len(recipients),
            subject=subject,
            has_attachments=bool(attachments)
        )
        
        return result
        
    def close(self):
        """
        Close adapter connections and perform cleanup.
        
        Returns:
            None
        """
        if hasattr(self, 'adapter') and self.adapter:
            self.adapter.close()