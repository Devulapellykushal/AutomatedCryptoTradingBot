"""
Binance Error Handler - Maps and handles common Binance API errors gracefully
Implements item #8 from bulletproof improvements
"""

import logging
from typing import Optional, Dict, Any
# Use the same import as order_manager.py for consistency
from binance.exceptions import BinanceAPIException

logger = logging.getLogger(__name__)


def handle_binance_error(error: Exception, context: str = "", symbol: str = "") -> Dict[str, Any]:
    """
    Handle Binance API errors with appropriate actions.
    
    Args:
        error: The exception/error from Binance API
        context: Context description (e.g., "place_tp", "reattach_sl")
        symbol: Trading symbol (if applicable)
        
    Returns:
        Dict with:
        - handled: bool - Whether error was handled
        - action: str - Recommended action ("skip", "retry", "fallback", "fail")
        - message: str - Human-readable message
        - retry_after: Optional[float] - Seconds to wait before retry (if applicable)
    """
    if not isinstance(error, BinanceAPIException):
        return {
            "handled": False,
            "action": "fail",
            "message": f"Unknown error: {error}",
            "retry_after": None
        }
    
    error_code = error.code
    error_message = str(error)
    
    # Error code mapping and handling strategies
    error_handlers = {
        # Margin insufficient - skip and log (no retries)
        -2019: {
            "action": "skip",
            "message": f"Margin insufficient for {symbol} ({context}) - skipping",
            "retry_after": None,
            "log_level": "warning"
        },
        
        # Order not found / timing race condition - one retry after delay
        -2021: {
            "action": "retry",
            "message": f"Order timing issue for {symbol} ({context}) - will retry once after 400ms",
            "retry_after": 0.4,
            "log_level": "warning"
        },
        
        # Parameter issue - fallback to alternate mode
        -1106: {
            "action": "fallback",
            "message": f"Parameter issue for {symbol} ({context}) - falling back to reduceOnly mode",
            "retry_after": None,
            "log_level": "warning",
            "fallback_mode": "reduceOnly"
        },
        
        # Unknown order (on cancel) - convert to no-op
        -2011: {
            "action": "skip",
            "message": f"Order already filled/canceled for {symbol} ({context}) - treating as no-op",
            "retry_after": None,
            "log_level": "debug"
        },
        
        # Exceeds max open orders - throttle
        -2010: {
            "action": "skip",
            "message": f"Max open orders reached for {symbol} ({context}) - throttling",
            "retry_after": 60.0,  # Wait 60 seconds
            "log_level": "warning"
        },
        
        # Duplicate reduce-only order - treat as success
        -4164: {
            "action": "skip",
            "message": f"Duplicate reduce-only order for {symbol} ({context}) - order already exists",
            "retry_after": None,
            "log_level": "debug",
            "treat_as_success": True
        },
        
        # Position not found / not synced yet - retry once
        -2021: {
            "action": "retry",
            "message": f"Position not synced for {symbol} ({context}) - will retry once after 300ms",
            "retry_after": 0.3,
            "log_level": "warning"
        }
    }
    
    handler = error_handlers.get(error_code)
    
    if handler:
        # Log at appropriate level
        log_msg = f"[BinanceError] {handler['message']} (Code: {error_code})"
        if handler.get("log_level") == "warning":
            logger.warning(log_msg)
        elif handler.get("log_level") == "debug":
            logger.debug(log_msg)
        else:
            logger.error(log_msg)
        
        return {
            "handled": True,
            "action": handler["action"],
            "message": handler["message"],
            "retry_after": handler.get("retry_after"),
            "error_code": error_code,
            "fallback_mode": handler.get("fallback_mode"),
            "treat_as_success": handler.get("treat_as_success", False)
        }
    
    # Unknown error code - fail
    logger.error(f"[BinanceError] Unhandled error for {symbol} ({context}): Code {error_code}, Message: {error_message}")
    return {
        "handled": False,
        "action": "fail",
        "message": f"Unhandled Binance error: {error_message}",
        "retry_after": None,
        "error_code": error_code
    }


def should_retry_after_error(error: Exception, attempt_count: int = 0, max_retries: int = 1) -> tuple[bool, Optional[float]]:
    """
    Determine if an error should be retried and how long to wait.
    
    Args:
        error: The exception/error
        attempt_count: Current retry attempt count
        max_retries: Maximum number of retries allowed
        
    Returns:
        Tuple of (should_retry: bool, wait_seconds: Optional[float])
    """
    if attempt_count >= max_retries:
        return False, None
    
    if not isinstance(error, BinanceAPIException):
        return False, None
    
    error_handler = handle_binance_error(error)
    
    if error_handler["action"] == "retry" and error_handler.get("retry_after"):
        return True, error_handler["retry_after"]
    
    return False, None


def is_error_fatal(error: Exception) -> bool:
    """
    Check if an error should stop further processing (fatal).
    
    Args:
        error: The exception/error
        
    Returns:
        True if error is fatal (should stop), False if can continue
    """
    if not isinstance(error, BinanceAPIException):
        return True  # Unknown errors are fatal
    
    error_handler = handle_binance_error(error)
    
    # Fatal actions: "fail"
    # Non-fatal: "skip", "retry", "fallback"
    return error_handler["action"] == "fail"

