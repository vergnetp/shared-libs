from abc import ABC, abstractmethod
from typing import List, Optional, Union, Dict, Any, BinaryIO

class EmailAdapter(ABC):
    """
    Base interface for all email provider adapters.
    
    This abstract class defines the interface that all email
    provider implementations must follow.
    """
    
    @abstractmethod
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
        Send an email.
        
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
        pass
    
    @abstractmethod
    def close(self) -> None:
        """
        Close connections and perform cleanup.
        
        Returns:
            None
        """
        pass