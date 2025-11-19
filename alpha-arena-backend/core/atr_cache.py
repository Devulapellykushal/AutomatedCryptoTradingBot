"""
ATR Cache for TP/SL Drift Prevention
Caches ATR values per symbol to prevent recalculating every cycle.
"""

import time
from typing import Dict, Optional, Any
import threading

# Global cache with thread safety
_atr_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()

# Default cache duration (3 minutes)
DEFAULT_CACHE_DURATION = 180

def get_cached_atr(symbol: str) -> Optional[float]:
    """
    Get cached ATR value for a symbol if still valid.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        
    Returns:
        Cached ATR value if valid, None otherwise
    """
    with _cache_lock:
        if symbol in _atr_cache:
            cache_entry = _atr_cache[symbol]
            # Check if cache is still valid
            if time.time() - cache_entry["timestamp"] < cache_entry["duration"]:
                return cache_entry["atr"]
            else:
                # Remove expired cache entry
                del _atr_cache[symbol]
    return None

def set_cached_atr(symbol: str, atr: float, duration: int = DEFAULT_CACHE_DURATION) -> None:
    """
    Cache ATR value for a symbol.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        atr: ATR value to cache
        duration: Cache duration in seconds (default 180 seconds)
    """
    with _cache_lock:
        _atr_cache[symbol] = {
            "atr": atr,
            "timestamp": time.time(),
            "duration": duration
        }

def clear_atr_cache(symbol: Optional[str] = None) -> None:
    """
    Clear ATR cache for a specific symbol or all symbols.
    
    Args:
        symbol: Trading symbol to clear (if None, clears all cache)
    """
    with _cache_lock:
        if symbol:
            if symbol in _atr_cache:
                del _atr_cache[symbol]
        else:
            _atr_cache.clear()

def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.
    
    Returns:
        Dictionary with cache statistics
    """
    with _cache_lock:
        current_time = time.time()
        valid_entries = 0
        expired_entries = 0
        
        for symbol, entry in _atr_cache.items():
            if current_time - entry["timestamp"] < entry["duration"]:
                valid_entries += 1
            else:
                expired_entries += 1
        
        return {
            "total_entries": len(_atr_cache),
            "valid_entries": valid_entries,
            "expired_entries": expired_entries
        }