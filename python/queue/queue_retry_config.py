import random
from typing import Any, Dict, List, Optional

class QueueRetryConfig:
    """Configuration for retry behavior in queue operations."""
    
    def __init__(self, 
                max_attempts: int = 5,
                delays: Optional[List[float]] = None,
                timeout: Optional[float] = None):
        """
        Initialize retry configuration.
        
        Args:
            max_attempts: Maximum retry attempts
            delays: List of delay times in seconds for each retry attempt
                   (if None, uses exponential backoff with base=2, min=1s)
            timeout: Optional total time limit for retries in seconds
                     (if reached, stop retrying even if max_attempts not reached)
        """
        self.max_attempts = max_attempts
        self.timeout = timeout
        
        # If delays are provided directly, use them
        if delays:
            self.delays = delays
        else:
            # Otherwise, use exponential backoff with fixed parameters (base=2, min_delay=1s)
            self.delays = self._generate_exponential_delays()
    
    def _generate_exponential_delays(self) -> List[float]:
        """Generate exponential backoff delays with fixed parameters."""
        delays = []
        
        for attempt in range(self.max_attempts):
            # Calculate exponential backoff with base=2, min=1s
            delay = max(1.0, 2 ** attempt)
            delays.append(delay)
                
        return delays
    
    def get_delay_for_attempt(self, attempt: int) -> float:
        """
        Get the delay for a specific attempt with jitter.
        
        Args:
            attempt: The attempt number (0-based index)
            
        Returns:
            Delay in seconds with jitter applied
        """
        # Get raw delay with bounds checking
        index = min(attempt, len(self.delays) - 1)
        raw_delay = self.delays[index]
        
        # Add jitter (±10%)
        jitter = random.uniform(0.9, 1.1)
        return raw_delay * jitter
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for queue storage."""
        return {
            "max_attempts": self.max_attempts,
            "delays": self.delays,
            "timeout": self.timeout
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueRetryConfig':
        """Create instance from dictionary."""
        return cls(
            max_attempts=data.get("max_attempts", 5),
            delays=data.get("delays"),
            timeout=data.get("timeout")
        )
    
    @classmethod
    def fixed(cls, delay: float, max_attempts: int = 5, timeout: Optional[float] = None) -> 'QueueRetryConfig':
        """
        Create a fixed delay retry configuration.
        
        Args:
            delay: The fixed delay between retries in seconds
            max_attempts: Maximum number of retry attempts
            timeout: Optional total time limit for retries in seconds
            
        Returns:
            QueueRetryConfig instance with fixed delays
        """
        delays = [delay] * max_attempts
        return cls(max_attempts=max_attempts, delays=delays, timeout=timeout)
    
    @classmethod
    def exponential(cls, max_attempts: int = 5, timeout: Optional[float] = None) -> 'QueueRetryConfig':
        """
        Create an exponential backoff retry configuration.
        
        Uses fixed base=2 and min_delay=1s.
        
        Args:
            max_attempts: Maximum number of retry attempts
            timeout: Optional total time limit for retries in seconds
            
        Returns:
            QueueRetryConfig instance with exponential backoff
        """
        return cls(max_attempts=max_attempts, timeout=timeout)
    
    @classmethod
    def custom(cls, delays: List[float], max_attempts: Optional[int] = None, 
              timeout: Optional[float] = None) -> 'QueueRetryConfig':
        """
        Create a custom delay retry configuration.
        
        Args:
            delays: List of delay times in seconds
            max_attempts: Maximum attempts (defaults to length of delays)
            timeout: Optional total time limit for retries in seconds
            
        Returns:
            QueueRetryConfig instance with custom delays
        """
        if max_attempts is None:
            max_attempts = len(delays)
        return cls(max_attempts=max_attempts, delays=delays, timeout=timeout)