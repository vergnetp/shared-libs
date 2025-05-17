import random
from typing import Any, Dict, List, Optional, Union, Callable, Type


class QueueRetryConfig:
    """
    Configuration for retry behavior in queue operations.
    
    Controls retry attempts, delay schedules, and timeout behavior
    for failed operations. Provides factory methods for common
    retry patterns like exponential backoff and fixed delay.
    """
    def __init__(
        self,
        max_attempts: int = 5,
        delays: Optional[List[float]] = None,
        timeout: Optional[float] = None
    ):
        """
        Initialize retry configuration.
        
        Args:
            max_attempts: Maximum number of retry attempts (default: 5)
            delays: List of delay times in seconds for each retry attempt (default: exponential backoff)
            timeout: Optional total time limit for retries in seconds (default: None, no limit)
        """
        self.max_attempts = max_attempts
        self.timeout = timeout
        
        # If delays are provided directly, use them
        if delays:
            self.delays = delays
        else:
            # Otherwise, use exponential backoff with fixed parameters
            self.delays = self._generate_exponential_delays()
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate retry configuration parameters."""
        errors = []
        
        if self.max_attempts <= 0:
            errors.append(f"max_attempts must be positive, got {self.max_attempts}")
            
        if self.delays and len(self.delays) == 0:
            errors.append("delays list cannot be empty")
            
        if self.timeout is not None and self.timeout <= 0:
            errors.append(f"timeout must be positive, got {self.timeout}")
            
        if errors:
            raise ValueError(f"Retry configuration validation failed: {'; '.join(errors)}")
    
    def _generate_exponential_delays(self) -> List[float]:
        """
        Generate exponential backoff delays with fixed parameters.
        
        Returns:
            List of delay times in seconds following exponential backoff pattern
        """
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
    
    def would_exceed_timeout(self, first_attempt_time: float, current_time: float) -> bool:
        """
        Check if the next retry would exceed the total timeout.
        
        Args:
            first_attempt_time: Timestamp of the first attempt
            current_time: Current timestamp
            
        Returns:
            True if the next retry would exceed the timeout, False otherwise
        """
        # If no timeout specified, never exceeds
        if self.timeout is None:
            return False
            
        # Calculate elapsed time so far
        elapsed = current_time - first_attempt_time
        
        # Get the delay for the next attempt (assuming we're at current attempt)
        next_attempt = 0  # This is a placeholder, should be replaced with actual attempt number
        next_delay = self.get_delay_for_attempt(next_attempt)
        
        # Check if elapsed time plus next delay would exceed total timeout
        return (elapsed + next_delay) > self.timeout
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration
        """
        return {
            "max_attempts": self.max_attempts,
            "delays": self.delays,
            "timeout": self.timeout
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueRetryConfig':
        """
        Create instance from dictionary.
        
        Args:
            data: Dictionary containing retry configuration
            
        Returns:
            QueueRetryConfig instance
        """
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
            max_attempts: Maximum number of retry attempts (default: 5)
            timeout: Optional total time limit for retries in seconds (default: None)
            
        Returns:
            QueueRetryConfig instance with fixed delays
        """
        delays = [delay] * max_attempts
        return cls(max_attempts=max_attempts, delays=delays, timeout=timeout)
    
    @classmethod
    def exponential(cls, base: float = 2.0, min_delay: float = 1.0, max_delay: float = 60.0, 
                   max_attempts: int = 5, timeout: Optional[float] = None) -> 'QueueRetryConfig':
        """
        Create an exponential backoff retry configuration.
        
        Args:
            base: Base factor for exponential backoff (default: 2.0)
            min_delay: Minimum delay in seconds (default: 1.0)
            max_delay: Maximum delay in seconds (default: 60.0)
            max_attempts: Maximum number of retry attempts (default: 5)
            timeout: Optional total time limit for retries in seconds (default: None)
            
        Returns:
            QueueRetryConfig instance with exponential backoff
        """
        delays = []
        for attempt in range(max_attempts):
            # Calculate exponential backoff with the given parameters
            delay = min(max_delay, max(min_delay, min_delay * (base ** attempt)))
            delays.append(delay)
            
        return cls(max_attempts=max_attempts, delays=delays, timeout=timeout)
    
    @classmethod
    def custom(cls, delays: List[float], max_attempts: Optional[int] = None, 
              timeout: Optional[float] = None) -> 'QueueRetryConfig':
        """
        Create a custom delay retry configuration.
        
        Args:
            delays: List of delay times in seconds
            max_attempts: Maximum attempts (defaults to length of delays)
            timeout: Optional total time limit for retries in seconds (default: None)
            
        Returns:
            QueueRetryConfig instance with custom delays
        """
        if max_attempts is None:
            max_attempts = len(delays)
        return cls(max_attempts=max_attempts, delays=delays, timeout=timeout)

