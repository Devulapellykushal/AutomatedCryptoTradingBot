"""
Trade State Manager - Prevents multiple exits and tracks position lifecycle
Implements trade state machine: open → monitoring → closed

Prevents duplicate TP/SL orders and multiple exit attempts.
"""

import logging
import time
from typing import Dict, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)

# Trade state machine: {symbol: "OPEN" | "MONITORING" | "CLOSING" | "CLOSED"}
_trade_states: Dict[str, str] = {}

# Track TP/SL order IDs per symbol to prevent duplicates (hash-based deduplication)
_tpsl_order_hashes: Dict[str, Set[str]] = defaultdict(set)  # {symbol: {hash1, hash2, ...}}

# Track last exit attempt per symbol (prevents multiple close attempts)
_last_exit_attempt: Dict[str, float] = {}
_exit_debounce_seconds = 5.0  # 5 second debounce between exit attempts


def get_trade_state(symbol: str) -> str:
    """Get current state of a trade"""
    return _trade_states.get(symbol, "NONE")


def set_trade_state(symbol: str, state: str):
    """Set trade state (OPEN, MONITORING, CLOSING, CLOSED)"""
    _trade_states[symbol] = state
    logger.debug(f"[TradeState] {symbol}: {state}")


def is_exit_allowed(symbol: str) -> bool:
    """
    Check if exit is allowed (not in cooldown, not already closing)
    
    Returns:
        True if exit allowed, False if in debounce or already closing
    """
    current_state = get_trade_state(symbol)
    
    # Can't exit if already closing or closed
    if current_state in ["CLOSING", "CLOSED"]:
        return False
    
    # Check debounce
    now = time.time()
    if symbol in _last_exit_attempt:
        elapsed = now - _last_exit_attempt[symbol]
        if elapsed < _exit_debounce_seconds:
            return False
    
    return True


def record_exit_attempt(symbol: str):
    """Record that an exit attempt was made"""
    _last_exit_attempt[symbol] = time.time()
    set_trade_state(symbol, "CLOSING")


def record_exit_complete(symbol: str):
    """Record that exit is complete"""
    set_trade_state(symbol, "CLOSED")
    # Clean up after 1 hour
    if symbol in _last_exit_attempt:
        del _last_exit_attempt[symbol]


def generate_tpsl_hash(symbol: str, side: str, tp_price: float, sl_price: float) -> str:
    """
    Generate hash for TP/SL order pair to detect duplicates
    
    Args:
        symbol: Trading symbol
        side: Position side
        tp_price: Take profit price
        sl_price: Stop loss price
    
    Returns:
        Hash string for deduplication
    """
    # Round prices to 2 decimal places for hash stability
    tp_rounded = round(tp_price, 2)
    sl_rounded = round(sl_price, 2)
    
    # Create hash from symbol + side + prices
    hash_str = f"{symbol}_{side}_{tp_rounded}_{sl_rounded}"
    return hash_str


def is_tpsl_duplicate(symbol: str, hash_str: str) -> bool:
    """
    Check if TP/SL order pair is duplicate
    
    Returns:
        True if duplicate, False if new
    """
    if hash_str in _tpsl_order_hashes[symbol]:
        logger.debug(f"[TPSL Dedupe] Duplicate TP/SL detected for {symbol}: {hash_str}")
        return True
    return False


def register_tpsl_order(symbol: str, hash_str: str):
    """Register TP/SL order hash to prevent duplicates"""
    _tpsl_order_hashes[symbol].add(hash_str)
    logger.debug(f"[TPSL Dedupe] Registered TP/SL for {symbol}: {hash_str}")


def clear_tpsl_hashes(symbol: str):
    """Clear TP/SL hashes when position is fully closed"""
    if symbol in _tpsl_order_hashes:
        del _tpsl_order_hashes[symbol]


def reset_trade_state(symbol: str):
    """Reset trade state (for new positions)"""
    if symbol in _trade_states:
        del _trade_states[symbol]
    clear_tpsl_hashes(symbol)
    if symbol in _last_exit_attempt:
        del _last_exit_attempt[symbol]

