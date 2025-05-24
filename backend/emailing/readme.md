# Email System

A flexible, provider-agnostic email system with attachments and automatic compression.

## Features

- **Class-Based Design**: Simple, encapsulated interface via the `Emailer` class
- **Provider Support**: SMTP (including Gmail), with easy extensibility
- **Attachment Handling**: Support for file attachments with optional compression
- **Rich Email Options**: HTML/text content, CC/BCC recipients, custom headers
- **Error Handling**: Robust error capturing and reporting

## Quick Start

### Basic Usage

```python
from myapp.emailing import Emailer, EmailConfig

# Create configuration
config = EmailConfig(
    provider="smtp",  
    from_address="noreply@example.com",
    smtp_host="smtp.gmail.com",
    smtp_port=465,
    smtp_user="myapp@gmail.com",
    smtp_password="app_password",
    use_ssl=True
)

# Create emailer
emailer = Emailer(config)

# Send a simple email
emailer.send_email(
    subject="Hello World", 
    recipients=["user@example.com"],
    text="This is a simple email message.",
    html="<p>This is a <strong>simple</strong> email message.</p>"
)
```

### Email with Attachment

```python
# Send an email with attachment
emailer.send_email(
    subject="Report Attached",
    recipients=["user@example.com"],
    text="Please find the report attached.",
    attached_file="path/to/report.pdf",
    compress=True  # Automatically compress the attachment
)
```

### Advanced Email Options

```python
# Send an email with all options
emailer.send_email(
    subject="Quarterly Report",
    recipients=["team@example.com"],
    text="Please review the quarterly report.",
    html="<h1>Quarterly Report</h1><p>Please review the attached report.</p>",
    attached_file="path/to/report.xlsx",
    attached_file_name="Q1_2025_Report.xlsx",
    compress=True,
    from_address="reports@example.com",
    reply_to="manager@example.com",
    cc=["manager@example.com"],
    bcc=["archive@example.com"],
    headers={
        "X-Priority": "1",
        "X-Report-ID": "Q1-2025-001"
    }
)
```

## Configuration

The `EmailConfig` class provides extensive configuration options:

```python
from myapp.emailing import EmailConfig

# Create configuration with all options
config = EmailConfig(
    # Provider selection
    provider="smtp",  # Options: "smtp" (only supported provider currently)
    
    # Default sender information
    from_address="noreply@example.com",
    reply_to="support@example.com",
    default_subject_prefix="[MyApp] ",
    
    # Attachment settings
    max_file_size_mb=25,
    
    # SMTP specific settings
    smtp_host="smtp.gmail.com",
    smtp_port=465,
    smtp_user="myapp@gmail.com",
    smtp_password="app_password",
    use_ssl=True
)
```

## Configuration Overrides

You can create temporary configuration overrides:

```python
# Create a new configuration with specific overrides
urgent_config = config.with_overrides(
    from_address="urgent@example.com",
    default_subject_prefix="[URGENT] "
)

# Create a new emailer with the urgent configuration
urgent_emailer = Emailer(urgent_config)
```

## Advanced Attachment Options

```python
from myapp.emailing import Emailer

# Create multiple attachments manually
attachments = [
    {
        "filename": "report.pdf",
        "content": open("path/to/report.pdf", "rb").read(),
        "content_type": "application/pdf"
    },
    {
        "filename": "data.csv",
        "content": open("path/to/data.csv", "rb").read(),
        "content_type": "text/csv"
    }
]

# Use the attachments parameter directly
emailer.adapter.send_email(
    subject="Multiple Attachments", 
    recipients=["user@example.com"],
    text="Please find multiple files attached.",
    attachments=attachments
)
```

## Class API

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `Emailer`

Main class for sending emails.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: EmailConfig` | | Initialization | Initialize the emailer with configuration. |
| `@try_catch` | `compress_file` | `data: Union[str, bytes]` | `bytes` | Utility | Compresses a file or bytes into a ZIP archive. |
| `@try_catch` | `send_email` | `subject: str`, `recipients: List[str]`, `text: Optional[str] = None`, `html: Optional[str] = None`, `attached_file: Optional[Union[str, bytes]] = None`, `compress: Optional[bool] = False`, `attached_file_name: Optional[str] = None`, `from_address: Optional[str] = None`, `reply_to: Optional[str] = None`, `cc: Optional[List[str]] = None`, `bcc: Optional[List[str]] = None`, `headers: Optional[Dict[str, str]] = None` | `Dict[str, Any]` | Email | Send an email with optional text, HTML content, and attachments. |
| | `close` | | `None` | Lifecycle | Close adapter connections and perform cleanup. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `EmailConfig`

Configuration for email operations.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `provider: str = "smtp"`, `from_address: Optional[str] = None`, `reply_to: Optional[str] = None`, `default_subject_prefix: str = ""`, `max_file_size_mb: int = 25`, `**provider_settings` | | Initialization | Initialize email configuration with connection parameters. |
| | `with_overrides` | `**overrides` | `EmailConfig` | Configuration | Create a new configuration with specific overrides. |
| | `get_provider_setting` | `key: str`, `default: Any = None` | `Any` | Configuration | Get a provider-specific setting. |
| | `to_dict` | | `Dict[str, Any]` | Serialization | Convert configuration to dictionary. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `_validate_config` | | | Validation | Validate configuration values and adjust if necessary. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `EmailAdapter`

Base interface for all email provider adapters.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| `@abstractmethod` | `send_email` | `subject: str`, `recipients: List[str]`, `text: Optional[str] = None`, `html: Optional[str] = None`, `from_address: Optional[str] = None`, `reply_to: Optional[str] = None`, `cc: Optional[List[str]] = None`, `bcc: Optional[List[str]] = None`, `attachments: Optional[List[Dict[str, Any]]] = None`, `headers: Optional[Dict[str, str]] = None` | `Dict[str, Any]` | Email | Send an email. |
| `@abstractmethod` | `close` | | `None` | Lifecycle | Close connections and perform cleanup. |

</details>

<br>

</div>

<div style="background-color:#f8f9fa; border:1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 24px;margin-top: 24px;">

### class `SMTPAdapter`

SMTP email provider adapter.

<details>
<summary><strong>Public Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `__init__` | `config: EmailConfig` | | Initialization | Initialize SMTP adapter with configuration. |
| `@try_catch` | `send_email` | `subject: str`, `recipients: List[str]`, `text: Optional[str] = None`, `html: Optional[str] = None`, `from_address: Optional[str] = None`, `reply_to: Optional[str] = None`, `cc: Optional[List[str]] = None`, `bcc: Optional[List[str]] = None`, `attachments: Optional[List[Dict[str, Any]]] = None`, `headers: Optional[Dict[str, str]] = None` | `Dict[str, Any]` | Email | Send an email via SMTP. |
| | `close` | | `None` | Lifecycle | Close SMTP connection if open. |

</details>

<br>

<details>
<summary><strong>Private/Internal Methods</strong></summary>

| Decorators | Method | Args | Returns | Category | Description |
|------------|--------|------|---------|----------|-------------|
| | `_connect` | | `smtplib.SMTP or smtplib.SMTP_SSL` | Connection | Connect to the SMTP server. |
| | `_add_attachment` | `msg: MIMEMultipart`, `attachment: Dict[str, Any]` | `None` | Email | Add an attachment to the email. |

</details>

<br>

</div>
