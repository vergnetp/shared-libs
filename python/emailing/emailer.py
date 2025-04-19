import smtplib
import os
import io
import ssl
import zipfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional

from .. import log as logger
from ..errors import TrackError

MAX_FILE_SIZE_MB = 25  # MB file size limit

def compress_file(data: str | bytes) -> bytes:
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
        raise TrackError(f"Error compressing file: {e}")

def send_email(subject: str, recipients: List[str], text: Optional[str] = None, html: Optional[str] = None,
               use_gmail: bool = True, attached_file: Optional[str | bytes] = None, 
               compress: Optional[bool] = False, attached_file_name: Optional[str] = None):
    """
    Sends an email with optional text, HTML content, and an attached file.

    Args:
        subject (str): Subject of the email.
        recipients (List[str]): List of recipient email addresses.
        text (Optional[str]): Plain text version of the email content.
        html (Optional[str]): HTML version of the email content.
        use_gmail (bool): Use Gmail SMTP server. Default is True.
        attached_file (Optional[str | bytes]): File path or bytes to attach.
        compress (Optional[bool]): Compress the file before attaching. Default is False.
        attached_file_name (Optional[str]): Name of the file attachment.

    Raises:
        Exception: For email-sending failures.
    """
    try:
        # Prepare the file for attachment
        if attached_file:
            if isinstance(attached_file, str):
                if not os.path.exists(attached_file):
                    raise TrackError(f"File does not exist: {attached_file}")
                if not attached_file_name:
                    attached_file_name = os.path.basename(attached_file)
                with open(attached_file, 'rb') as f:
                    attached_file = f.read()
            
            if compress:
                attached_file = compress_file(attached_file)
                if attached_file_name:
                    base_name, _ = os.path.splitext(attached_file_name)
                    attached_file_name = f"{base_name}.zip"
                else:
                    attached_file_name = "compressed_file.zip"

            if len(attached_file) > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise TrackError(f"File size exceeds {MAX_FILE_SIZE_MB} MB limit.")

        # Set SMTP server and credentials
        smtp_server, sender, password = (
            ('smtp.gmail.com', 'info@digitalpixo.com', os.environ.get("APP_GMAIL_PWD"))
            if use_gmail else 
            ('mail.privateemail.com', 'contact@digitalpixo.com', os.environ.get("APP_ADMIN_TOKEN"))
        )
        if not password:
            raise TrackError("SMTP credentials are missing.")

        # Build the email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = ', '.join(recipients)

        if text is None and html:
            text = html  # Fallback to HTML if text is missing

        if text:
            msg.attach(MIMEText(text, 'plain'))
        if html:
            msg.attach(MIMEText(html, 'html'))

        # Add the attachment
        if attached_file:
            if not attached_file_name:
                raise TrackError("Attachment filename is required.")
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attached_file)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{attached_file_name}"')
            msg.attach(part)

        # Send the email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        logger.info(f"Email sent successfully to {recipients} with subject: {subject}")

    except Exception as e:
        logger.error(f"Error sending email to {recipients} with subject: {subject}. Error: {e}")
        raise
