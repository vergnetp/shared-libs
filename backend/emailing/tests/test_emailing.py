import pytest
import smtplib
from unittest import mock
from io import BytesIO
import zipfile
import os
from email.mime.multipart import MIMEMultipart

from .. import Emailer, EmailConfig
from ..adapters.smtp_adapter import SMTPAdapter
from ...errors import TrackError, Error

# ----------------------------------------------------------------------
# EmailConfig Tests
# ----------------------------------------------------------------------

def test_email_config_basic():
    """Test basic EmailConfig creation and validation."""
    # Test default values
    config = EmailConfig()
    assert config.provider == "smtp"
    assert config.max_file_size_mb == 25
    
    # Test custom values
    config = EmailConfig(
        provider="smtp",
        from_address="test@example.com",
        reply_to="reply@example.com",
        default_subject_prefix="[TEST] ",
        max_file_size_mb=50,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="password"
    )
    
    assert config.from_address == "test@example.com"
    assert config.reply_to == "reply@example.com"
    assert config.default_subject_prefix == "[TEST] "
    assert config.max_file_size_mb == 50
    assert config.get_provider_setting("smtp_host") == "smtp.example.com"
    assert config.get_provider_setting("smtp_port") == 587
    assert config.get_provider_setting("smtp_user") == "user"
    assert config.get_provider_setting("smtp_password") == "password"

def test_email_config_validation():
    """Test EmailConfig validation."""
    # Test invalid provider
    with pytest.raises(ValueError, match="Invalid provider"):
        EmailConfig(provider="invalid")
    
    # Test invalid max_file_size_mb
    with pytest.raises(ValueError, match="max_file_size_mb must be positive"):
        EmailConfig(max_file_size_mb=0)
    
    with pytest.raises(ValueError, match="max_file_size_mb must be positive"):
        EmailConfig(max_file_size_mb=-1)

def test_email_config_with_overrides():
    """Test EmailConfig.with_overrides method."""
    config = EmailConfig(
        from_address="original@example.com",
        smtp_host="original.example.com"
    )
    
    # Override some values
    new_config = config.with_overrides(
        from_address="new@example.com",
        reply_to="new-reply@example.com"
    )
    
    # Check original config is unchanged
    assert config.from_address == "original@example.com"
    assert config.reply_to is None
    
    # Check new config has overrides
    assert new_config.from_address == "new@example.com"
    assert new_config.reply_to == "new-reply@example.com"
    assert new_config.get_provider_setting("smtp_host") == "original.example.com"

def test_email_config_to_dict():
    """Test EmailConfig.to_dict method."""
    config = EmailConfig(
        from_address="test@example.com",
        reply_to="reply@example.com",
        smtp_host="smtp.example.com"
    )
    
    config_dict = config.to_dict()
    
    assert config_dict["provider"] == "smtp"
    assert config_dict["from_address"] == "test@example.com"
    assert config_dict["reply_to"] == "reply@example.com"
    assert config_dict["smtp_host"] == "smtp.example.com"

# ----------------------------------------------------------------------
# SMTP Adapter Tests
# ----------------------------------------------------------------------

def test_smtp_adapter_init_validation():
    """Test SMTPAdapter initialization validation."""
    # Valid config
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    adapter = SMTPAdapter(config)
    assert adapter.username == "user@example.com"
    assert adapter.password == "password"
    
    # Missing username
    config = EmailConfig(
        smtp_password="password"
    )
    with pytest.raises(ValueError, match="SMTP username/email is required"):
        SMTPAdapter(config)
    
    # Missing password
    config = EmailConfig(
        smtp_user="user@example.com"
    )
    with pytest.raises(ValueError, match="SMTP password is required"):
        SMTPAdapter(config)

@mock.patch('smtplib.SMTP_SSL')
def test_smtp_adapter_connect(mock_smtp_ssl):
    """Test SMTPAdapter._connect method."""
    # Set up mock
    mock_server = mock.MagicMock()
    mock_smtp_ssl.return_value = mock_server
    
    # Create adapter
    config = EmailConfig(
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_user="user@example.com",
        smtp_password="password",
        use_ssl=True
    )
    adapter = SMTPAdapter(config)
    
    # Connect
    server = adapter._connect()
    
    # Check mock was called correctly - use assert_called_once() instead
    mock_smtp_ssl.assert_called_once()
    mock_server.login.assert_called_once_with("user@example.com", "password")
    assert server == mock_server

@mock.patch('smtplib.SMTP')
def test_smtp_adapter_connect_no_ssl(mock_smtp):
    """Test SMTPAdapter._connect method without SSL."""
    # Set up mock
    mock_server = mock.MagicMock()
    mock_smtp.return_value = mock_server
    
    # Create adapter
    config = EmailConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="password",
        use_ssl=False
    )
    adapter = SMTPAdapter(config)
    
    # Connect
    server = adapter._connect()
    
    # Check mock was called correctly
    mock_smtp.assert_called_once_with("smtp.example.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user@example.com", "password")
    assert server == mock_server

@mock.patch('smtplib.SMTP_SSL')
def test_smtp_adapter_send_email_basic(mock_smtp_ssl):
    """Test SMTPAdapter.send_email with basic options."""
    # Set up mock
    mock_server = mock.MagicMock()
    mock_smtp_ssl.return_value = mock_server
    
    # Create adapter
    config = EmailConfig(
        smtp_user="sender@example.com",
        smtp_password="password"
    )
    adapter = SMTPAdapter(config)
    
    # Send email
    result = adapter.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Test content"
    )
    
    # Check mock was called correctly
    mock_smtp_ssl.assert_called_once()
    mock_server.login.assert_called_once()
    mock_server.sendmail.assert_called_once()
    
    # Check call arguments
    args = mock_server.sendmail.call_args[0]
    sender = args[0]
    recipients = args[1]
    message = args[2]
    
    assert sender == "sender@example.com"
    assert recipients == ["recipient@example.com"]
    assert "Test Subject" in message
    assert "Test content" in message
    
    # Check result
    assert result["status"] == "sent"
    assert result["recipients"] == 1
    assert result["subject"] == "Test Subject"
    assert result["has_attachments"] is False

@mock.patch('smtplib.SMTP_SSL')
def test_smtp_adapter_send_email_html(mock_smtp_ssl):
    """Test SMTPAdapter.send_email with HTML content."""
    # Set up mock
    mock_server = mock.MagicMock()
    mock_smtp_ssl.return_value = mock_server
    
    # Create adapter
    config = EmailConfig(
        smtp_user="sender@example.com",
        smtp_password="password"
    )
    adapter = SMTPAdapter(config)
    
    # Send email
    result = adapter.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Plain text",
        html="<p>HTML content</p>"
    )
    
    # Check call arguments
    args = mock_server.sendmail.call_args[0]
    message = args[2]
    
    assert "Plain text" in message
    assert "<p>HTML content</p>" in message
    
    # Check result
    assert result["status"] == "sent"

@mock.patch('smtplib.SMTP_SSL')
def test_smtp_adapter_send_email_full_options(mock_smtp_ssl):
    """Test SMTPAdapter.send_email with all options."""
    # Set up mock
    mock_server = mock.MagicMock()
    mock_smtp_ssl.return_value = mock_server
    
    # Create adapter
    config = EmailConfig(
        from_address="default@example.com",
        reply_to="default-reply@example.com",
        default_subject_prefix="[DEFAULT] ",
        smtp_user="sender@example.com",
        smtp_password="password"
    )
    adapter = SMTPAdapter(config)
    
    # Send email
    result = adapter.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Test content",
        from_address="custom@example.com",
        reply_to="custom-reply@example.com",
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        headers={"X-Custom": "Value"}
    )
    
    # Check call arguments
    args = mock_server.sendmail.call_args[0]
    sender = args[0]
    recipients_list = args[1]
    message = args[2]
    
    assert sender == "custom@example.com"
    assert set(recipients_list) == {"recipient@example.com", "cc@example.com", "bcc@example.com"}
    assert "Test Subject" in message
    assert "Test content" in message
    assert "custom@example.com" in message
    assert "custom-reply@example.com" in message
    assert "cc@example.com" in message
    assert "X-Custom: Value" in message
    
    # Check result
    assert result["status"] == "sent"
    assert result["recipients"] == 3
    assert result["subject"] == "[DEFAULT] Test Subject"

@mock.patch('smtplib.SMTP_SSL')
def test_smtp_adapter_send_email_with_attachment(mock_smtp_ssl):
    """Test SMTPAdapter.send_email with attachments."""
    # Set up mock
    mock_server = mock.MagicMock()
    mock_smtp_ssl.return_value = mock_server
    
    # Create adapter
    config = EmailConfig(
        smtp_user="sender@example.com",
        smtp_password="password"
    )
    adapter = SMTPAdapter(config)
    
    # Create test attachment
    attachment = {
        "filename": "test.txt",
        "content": b"Test content",
        "content_type": "text/plain"
    }
    
    # Send email
    result = adapter.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Test content",
        attachments=[attachment]
    )
    
    # Check call arguments
    args = mock_server.sendmail.call_args[0]
    message = args[2]
    
    assert "Content-Disposition: attachment; filename=\"test.txt\"" in message
    assert "Content-Type: text/plain" in message
    
    # Check result
    assert result["status"] == "sent"
    assert result["has_attachments"] is True

def test_smtp_adapter_add_attachment():
    """Test SMTPAdapter._add_attachment method."""
    config = EmailConfig(
        smtp_user="sender@example.com",
        smtp_password="password"
    )
    adapter = SMTPAdapter(config)
    
    # Create message container
    msg = MIMEMultipart()
    
    # Create test attachment
    attachment = {
        "filename": "test.txt",
        "content": b"Test content",
        "content_type": "text/plain"
    }
    
    # Add attachment
    adapter._add_attachment(msg, attachment)
    
    # Check attachment was added
    assert len(msg.get_payload()) == 1
    part = msg.get_payload()[0]
    assert part.get_filename() == "test.txt"
    assert part.get_content_type() == "text/plain"

def test_smtp_adapter_add_attachment_validation():
    """Test SMTPAdapter._add_attachment validation."""
    config = EmailConfig(
        smtp_user="sender@example.com",
        smtp_password="password"
    )
    adapter = SMTPAdapter(config)
    
    # Create message container
    msg = MIMEMultipart()
    
    # Test missing filename
    with pytest.raises(ValueError, match="Attachment filename is required"):
        adapter._add_attachment(msg, {"content": b"content"})
    
    # Test missing content
    with pytest.raises(ValueError, match="Attachment content is required"):
        adapter._add_attachment(msg, {"filename": "test.txt"})

# ----------------------------------------------------------------------
# Emailer Tests
# ----------------------------------------------------------------------

def test_emailer_init_successful():
    """Test successful Emailer initialization with SMTP provider."""
    # Test with SMTP provider
    config = EmailConfig(
        provider="smtp",
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    assert isinstance(emailer.adapter, SMTPAdapter)

def test_emailer_init_unsupported_provider():
    """Test Emailer initialization with unsupported provider raises error."""
    # Use one of the valid providers in EmailConfig but not supported in Emailer
    config = EmailConfig(
        provider="aws_ses",  # This is valid in EmailConfig but not implemented in Emailer
        smtp_user="user@example.com",
        smtp_password="password"
    )
    
    # This should raise ValueError
    with pytest.raises(ValueError, match="Unsupported provider"):
        Emailer(config)

def test_compress_file_with_string(tmp_path):
    """Test Emailer.compress_file with a file path."""
    # Create test file
    file_path = tmp_path / "test.txt"
    content = b"Hello, World!"
    file_path.write_bytes(content)
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Compress file
    compressed = emailer.compress_file(str(file_path))
    
    # Check result
    assert isinstance(compressed, bytes)
    assert len(compressed) > 0
    
    # Verify it's a valid ZIP file
    zip_file = zipfile.ZipFile(BytesIO(compressed))
    assert zip_file.namelist() == ['compressed_file']
    assert zip_file.read('compressed_file') == content

def test_compress_file_with_bytes():
    """Test Emailer.compress_file with bytes."""
    # Create test content
    content = b"Sample data"
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Compress file
    compressed = emailer.compress_file(content)
    
    # Check result
    assert isinstance(compressed, bytes)
    assert len(compressed) > 0
    
    # Verify it's a valid ZIP file
    zip_file = zipfile.ZipFile(BytesIO(compressed))
    assert zip_file.namelist() == ['compressed_file']
    assert zip_file.read('compressed_file') == content

@mock.patch.object(SMTPAdapter, 'send_email')
def test_emailer_send_email_minimal(mock_send_email):
    """Test Emailer.send_email with minimal options."""
    # Set up mock
    mock_send_email.return_value = {"status": "sent"}
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Send email
    result = emailer.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Test content"
    )
    
    # Check mock was called correctly
    mock_send_email.assert_called_once()
    
    # Check call arguments
    args = mock_send_email.call_args[1]
    assert args["subject"] == "Test Subject"
    assert args["recipients"] == ["recipient@example.com"]
    assert args["text"] == "Test content"
    assert args["attachments"] is None
    
    # Check result
    assert result["status"] == "sent"

@mock.patch.object(SMTPAdapter, 'send_email')
def test_emailer_send_email_with_file_path(mock_send_email, tmp_path):
    """Test Emailer.send_email with a file path attachment."""
    # Set up mock
    mock_send_email.return_value = {"status": "sent"}
    
    # Create test file
    file_path = tmp_path / "test.txt"
    content = b"Hello, World!"
    file_path.write_bytes(content)
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Send email
    result = emailer.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Test content",
        attached_file=str(file_path)
    )
    
    # Check mock was called correctly
    mock_send_email.assert_called_once()
    
    # Check call arguments
    args = mock_send_email.call_args[1]
    assert args["subject"] == "Test Subject"
    assert args["recipients"] == ["recipient@example.com"]
    assert args["text"] == "Test content"
    
    # Check attachment
    attachments = args["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "test.txt"
    assert attachments[0]["content"] == content
    assert attachments[0]["content_type"] == "text/plain"
    
    # Check result
    assert result["status"] == "sent"

@mock.patch.object(SMTPAdapter, 'send_email')
def test_emailer_send_email_with_bytes(mock_send_email):
    """Test Emailer.send_email with bytes attachment."""
    # Set up mock
    mock_send_email.return_value = {"status": "sent"}
    
    # Create test content
    content = b"Sample data"
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Send email
    result = emailer.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Test content",
        attached_file=content,
        attached_file_name="data.bin"
    )
    
    # Check call arguments
    args = mock_send_email.call_args[1]
    
    # Check attachment
    attachments = args["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "data.bin"
    assert attachments[0]["content"] == content
    
    # Check result
    assert result["status"] == "sent"

@mock.patch.object(SMTPAdapter, 'send_email')
@mock.patch.object(Emailer, 'compress_file')
def test_emailer_send_email_with_compression(mock_compress_file, mock_send_email):
    """Test Emailer.send_email with compression."""
    # Set up mocks
    mock_send_email.return_value = {"status": "sent"}
    mock_compress_file.return_value = b"compressed data"
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Send email
    result = emailer.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Test content",
        attached_file=b"original data",
        attached_file_name="data.txt",
        compress=True
    )
    
    # Check compress_file was called
    mock_compress_file.assert_called_once_with(b"original data")
    
    # Check call arguments
    args = mock_send_email.call_args[1]
    
    # Check attachment
    attachments = args["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "data.zip"  # Should have .zip extension
    assert attachments[0]["content"] == b"compressed data"
    
    # Check result
    assert result["status"] == "sent"

@mock.patch.object(SMTPAdapter, 'send_email')
def test_emailer_send_email_with_full_options(mock_send_email):
    """Test Emailer.send_email with all options."""
    # Set up mock
    mock_send_email.return_value = {"status": "sent"}
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Send email
    result = emailer.send_email(
        subject="Test Subject",
        recipients=["recipient@example.com"],
        text="Plain text",
        html="<p>HTML content</p>",
        attached_file=b"file content",
        attached_file_name="data.txt",
        from_address="custom@example.com",
        reply_to="reply@example.com",
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        headers={"X-Custom": "Value"}
    )
    
    # Check call arguments
    args = mock_send_email.call_args[1]
    assert args["subject"] == "Test Subject"
    assert args["recipients"] == ["recipient@example.com"]
    assert args["text"] == "Plain text"
    assert args["html"] == "<p>HTML content</p>"
    assert args["from_address"] == "custom@example.com"
    assert args["reply_to"] == "reply@example.com"
    assert args["cc"] == ["cc@example.com"]
    assert args["bcc"] == ["bcc@example.com"]
    assert args["headers"] == {"X-Custom": "Value"}
    
    # Check attachment
    attachments = args["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "data.txt"
    assert attachments[0]["content"] == b"file content"
    
    # Check result
    assert result["status"] == "sent"

def test_emailer_send_email_with_missing_file(tmp_path):
    """Test Emailer.send_email with a missing file."""
    # Create non-existent file path
    file_path = tmp_path / "non_existent.txt"
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Send email should raise an error
    with pytest.raises(Error, match="File does not exist"):
        emailer.send_email(
            subject="Test Subject",
            recipients=["recipient@example.com"],
            text="Test content",
            attached_file=str(file_path)
        )

@mock.patch.object(Emailer, 'compress_file')
def test_emailer_send_email_with_oversized_file(mock_compress_file):
    """Test Emailer.send_email with a file exceeding size limit."""
    # Create a large content
    content = b"x" * (26 * 1024 * 1024)  # 26 MB (exceeds 25 MB default)
    
    # Create emailer
    config = EmailConfig(
        smtp_user="user@example.com",
        smtp_password="password",
        max_file_size_mb=25
    )
    emailer = Emailer(config)
    
    # Send email should raise an error
    with pytest.raises(Error, match="File size exceeds 25 MB limit"):
        emailer.send_email(
            subject="Test Subject",
            recipients=["recipient@example.com"],
            text="Test content",
            attached_file=content,
            attached_file_name="large.bin"
        )
    
    # Compress_file should not be called
    mock_compress_file.assert_not_called()

def test_emailer_close():
    """Test Emailer.close method."""
    # Create mock adapter
    mock_adapter = mock.MagicMock()
    
    # Create emailer with the mock adapter
    config = EmailConfig(
        smtp_user="user@example.com",  # Add required SMTP credentials
        smtp_password="password"
    )
    emailer = Emailer(config)
    
    # Replace adapter with our mock
    emailer.adapter = mock_adapter
    
    # Close emailer
    emailer.close()
    
    # Check adapter.close was called
    mock_adapter.close.assert_called_once()