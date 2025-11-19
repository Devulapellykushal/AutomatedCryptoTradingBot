"""
Symbol Lock Mechanism for Multi-Agent Conflict Prevention
Prevents multiple agents from entering the same symbol simultaneously.
"""

import time
import threading
import logging
from typing import Dict, Set, Any

logger = logging.getLogger(__name__)

# Global lock for thread safety
_lock = threading.Lock()

# Active positions tracker
_active_positions: Dict[str, Dict[str, Any]] = {}

# Cooldown tracker
_cooldown_tracker: Dict[str, float] = {}

def acquire_position_lock(symbol: str, agent_id: str, verify_binance: bool = False) -> bool:
    """
    Simple in-memory lock to prevent multiple agents trading the same symbol.
    Fast and clean - no Binance API calls.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        agent_id: Agent identifier
        verify_binance: Ignored - kept for compatibility only
        
    Returns:
        True if lock acquired, False if already locked or in cooldown
    """
    # Immediate return - no logging inside lock to avoid any delays
    try:
        with _lock:
            clear_expired_cooldowns()
            
            # Check cooldown
            if symbol in _cooldown_tracker and time.time() < _cooldown_tracker[symbol]:
                return False
            
            # Check if already locked
            if symbol in _active_positions:
                return False
            
            # Acquire lock
            _active_positions[symbol] = {
                "agent_id": agent_id,
                "acquired_at": time.time()
            }
            return True
    except Exception as e:
        # If lock fails for any reason, allow the trade (fail open)
        logger.error(f"Lock acquisition error for {symbol}: {e}")
        return True  # Fail open - don't block trades

def release_position_lock(symbol: str, success: bool = True):
    """
    Release the lock for a symbol.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        success: Whether the trade was successful
    """
    with _lock:
        # Remove from active positions
        if symbol in _active_positions:
            del _active_positions[symbol]
        
        # If trade was not successful, set cooldown
        if not success:
            _cooldown_tracker[symbol] = time.time() + 300  # 5 minute cooldown

def is_symbol_locked(symbol: str) -> bool:
    """
    Check if a symbol is currently locked.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        
    Returns:
        True if symbol is locked, False otherwise
    """
    with _lock:
        # Check cooldown
        if symbol in _cooldown_tracker:
            if time.time() < _cooldown_tracker[symbol]:
                return True
            else:
                # Cooldown expired, remove it
                del _cooldown_tracker[symbol]
        
        # Check active position
        return symbol in _active_positions

def get_active_positions() -> Dict[str, Dict[str, Any]]:
    """
    Get all active positions.
    
    Returns:
        Dictionary of active positions
    """
    with _lock:
        return _active_positions.copy()

def clear_expired_cooldowns():
    """
    Clear expired cooldowns to prevent memory buildup.
    """
    with _lock:
        current_time = time.time()
        expired_symbols = [
            symbol for symbol, cooldown_time in _cooldown_tracker.items() 
            if current_time >= cooldown_time
        ]
        for symbol in expired_symbols:
            del _cooldown_tracker[symbol]

def clear_all_locks_and_cooldowns() -> None:
    """
    Clear all locks and cooldowns (use on startup or reset).
    """
    with _lock:
        _active_positions.clear()
        _cooldown_tracker.clear()
        logger.info("🧹 Cleared all position locks and cooldowns")

def sync_with_binance_on_startup(client) -> None:
    """
    Sync locks with actual Binance positions on startup.
    Clears stale locks for symbols with no actual positions.
    
    Args:
        client: Binance futures client
    """
    if not client:
        # No client - clear all locks to be safe
        clear_all_locks_and_cooldowns()
        return
    
    with _lock:
        locked_symbols = list(_active_positions.keys())
        
        if not locked_symbols:
            # No locks exist - just clear expired cooldowns
            clear_expired_cooldowns()
            logger.debug("No locks to sync on startup")
            return
    
    # Import outside the lock to avoid circular import issues
    # Use lazy import to avoid circular dependency
    try:
        from core.order_manager import check_existing_position
        
        cleared_count = 0
        for symbol in locked_symbols:
            try:
                # Quick check with timeout protection
                actual_position = check_existing_position(client, symbol)
                with _lock:
                    if actual_position is None:
                        # No actual position - clear stale lock
                        if symbol in _active_positions:
                            del _active_positions[symbol]
                            cleared_count += 1
                            logger.info(f"🔄 Cleared stale lock for {symbol} (no actual position on Binance)")
                    else:
                        # Position exists - lock is valid
                        logger.debug(f"✅ Lock for {symbol} is valid (position exists on Binance)")
            except Exception as e:
                logger.warning(f"⚠️  Could not sync lock for {symbol}: {e}")
                # On error, clear the lock to be safe (prevents blocking)
                with _lock:
                    if symbol in _active_positions:
                        del _active_positions[symbol]
                        cleared_count += 1
        
        # Clear expired cooldowns
        with _lock:
            clear_expired_cooldowns()
        
        if cleared_count > 0:
            logger.info(f"✅ Startup sync: Cleared {cleared_count} stale lock(s)")
    except ImportError as e:
        logger.warning(f"⚠️  Could not import check_existing_position: {e} - clearing all locks")
        clear_all_locks_and_cooldowns()
    except Exception as e:
        logger.warning(f"⚠️  Error during startup sync: {e} - clearing all locks")
        clear_all_locks_and_cooldowns()