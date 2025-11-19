"""
Precision Safety Net for Binance Futures Trading
Implements normalization for prices and quantities before placing any order.
"""

import logging
from typing import Tuple, Optional
from binance.client import Client

logger = logging.getLogger("precision_safety")

# Precision map for different symbols
PRECISION_MAP = {
    "BTCUSDT": {"price": 2, "qty": 3},
    "BNBUSDT": {"price": 2, "qty": 4},
}

def normalize(symbol: str, price: Optional[float] = None, qty: Optional[float] = None) -> Tuple[Optional[float], Optional[float]]:
    """
    Normalize price and quantity to symbol-specific precision.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        price: Price to normalize
        qty: Quantity to normalize
        
    Returns:
        Tuple of (normalized_price, normalized_qty)
    """
    # Get precision settings for the symbol
    precision_settings = PRECISION_MAP.get(symbol, {"price": 2, "qty": 2})
    
    # Normalize price if provided
    if price is not None:
        price = round(price, precision_settings["price"])
    
    # Normalize quantity if provided
    if qty is not None:
        qty = round(qty, precision_settings["qty"])
    
    return price, qty

def get_min_notional_value(symbol: str) -> float:
    """
    Get minimum notional value for a symbol.
    
    Args:
        symbol: Trading symbol
        
    Returns:
        Minimum notional value in USD
    """
    # Binance Futures minimum notional values
    MIN_NOTIONAL_MAP = {
        "BTCUSDT": 5.0,
        "BNBUSDT": 5.0,
    }
    
    return MIN_NOTIONAL_MAP.get(symbol, 5.0)

def is_below_min_notional(qty: float, price: float, symbol: str) -> bool:
    """
    Check if order notional value is below minimum.
    
    Args:
        qty: Order quantity
        price: Order price
        symbol: Trading symbol
        
    Returns:
        True if below minimum notional, False otherwise
    """
    notional = qty * price
    min_notional = get_min_notional_value(symbol)
    return notional < min_notional