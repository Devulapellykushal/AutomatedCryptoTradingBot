"""
Exchange Filters and Rounding Helpers for Binance Futures Trading
Provides utilities for fetching exchange filters and applying proper rounding.
"""

import logging
import math
from typing import Dict, Any
from binance.client import Client
from core.binance_guard import BinanceGuard

logger = logging.getLogger("exchange_filters")

# Cache for symbol filters
_symbol_filters_cache: Dict[str, Dict[str, Any]] = {}

def get_symbol_filters(client: Client, symbol: str) -> Dict[str, Any]:
    """
    Get symbol filters from exchange info with caching.
    
    Args:
        client: Binance client instance
        symbol: Trading symbol (e.g., BTCUSDT)
        
    Returns:
        Dictionary with symbol filters
    """
    global _symbol_filters_cache
    
    # Return cached filters if available
    if symbol in _symbol_filters_cache:
        return _symbol_filters_cache[symbol]
    
    try:
        guard = BinanceGuard(client)
        filters = guard.get_symbol_filters(symbol)
        _symbol_filters_cache[symbol] = filters
        return filters
    except Exception as e:
        logger.error(f"Failed to get symbol filters for {symbol}: {e}")
        # Return default filters
        return {
            'tickSize': 0.01,
            'stepSize': 0.001,
            'minQty': 0.001,
            'minNotional': 5.0
        }

def round_tick(price: float, tick_size: float) -> float:
    """
    Round price to the nearest tick size.
    
    Args:
        price: Price to round
        tick_size: Tick size from exchange filters
        
    Returns:
        Rounded price
    """
    return round(price / tick_size) * tick_size

def round_step(qty: float, step_size: float) -> float:
    """
    Round quantity to the nearest step size.
    
    Args:
        qty: Quantity to round
        step_size: Step size from exchange filters
        
    Returns:
        Rounded quantity
    """
    return round(qty / step_size) * step_size

def apply_safety_margin(price: float, mark_price: float, tick_size: float, is_tp: bool, is_long: bool) -> float:
    """
    Apply safety margin to prevent immediate trigger of TP/SL orders.
    
    Args:
        price: Calculated trigger price
        mark_price: Current mark price
        tick_size: Tick size from exchange filters
        is_tp: True if this is a take profit order, False for stop loss
        is_long: True if this is for a long position, False for short
        
    Returns:
        Adjusted price with safety margin
    """
    # Ensure minimum distance of 2 ticks between trigger and mark price
    min_distance = tick_size * 2
    
    if is_long:
        if is_tp:  # Long TP should be above mark price
            if price - mark_price < min_distance:
                price = mark_price + min_distance
        else:  # Long SL should be below mark price
            if mark_price - price < min_distance:
                price = mark_price - min_distance
    else:
        if is_tp:  # Short TP should be below mark price
            if mark_price - price < min_distance:
                price = mark_price - min_distance
        else:  # Short SL should be above mark price
            if price - mark_price < min_distance:
                price = mark_price + min_distance
    
    return round_tick(price, tick_size)