"""
Retry wrapper for Binance API calls with exponential backoff.
"""
import time
import random
import logging
from typing import Callable, Any, Optional, Type
from functools import wraps
from binance.exceptions import BinanceAPIException

logger = logging.getLogger(__name__)


def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple = (BinanceAPIException,)
):
    """
    Retry wrapper with exponential backoff for Binance API calls.
    
    Args:
        max_retries: Maximum number of retries
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add jitter to delay
        exceptions: Tuple of exceptions to catch and retry
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    # Short-circuit for precision errors - don't retry
                    if "Precision is over" in str(e):
                        logger.error(f"Precision error for {func.__name__}: {e} - skipping retries")
                        raise e
                    
                    # If this was the last attempt, re-raise the exception
                    if attempt == max_retries:
                        logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}")
                        raise e
                    
                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )
                    
                    # Add jitter if requested
                    if jitter:
                        delay *= (0.5 + random.random() * 0.5)
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    
                    # Wait before retrying
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            else:
                raise Exception(f"Max retries exceeded for {func.__name__}")
        return wrapper
    return decorator


# Specific retry decorators for common use cases
retry_api_call = retry_with_exponential_backoff(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True
)

retry_long_api_call = retry_with_exponential_backoff(
    max_retries=5,
    base_delay=2.0,
    max_delay=120.0,
    exponential_base=2.0,
    jitter=True
)


# Example usage:
# @retry_api_call
# def get_account_info(client):
#     return client.futures_account()