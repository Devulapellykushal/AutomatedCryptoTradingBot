"""
Dual-ATR Regime Engine - Fast/Slow ATR analysis for volatility regime detection
Implements item #3 from bulletproof improvements
"""

import logging
from typing import Dict, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Regime thresholds
VR_EXTREME = 1.8  # VR >= 1.8 → Extreme volatility
VR_HIGH = 1.2     # 1.2 <= VR < 1.8 → High volatility
VR_NORMAL_LOW = 0.5  # 0.5 <= VR < 1.2 → Normal, VR < 0.5 → Low (FIXED: Lower threshold to allow trades in stable uptrends)


def calculate_dual_atr(client, symbol: str, fast_period: int = 7, slow_period: int = 21, lookback: int = 30) -> Optional[Tuple[float, float, float]]:
    """
    Calculate fast ATR, slow ATR, and volatility ratio (VR).
    
    Args:
        client: Binance futures client
        symbol: Trading symbol (e.g., "BTCUSDT")
        fast_period: Fast ATR period (default 7)
        slow_period: Slow ATR period (default 21)
        lookback: Number of candles to fetch (default 30, should be >= slow_period)
        
    Returns:
        Tuple of (atr_fast, atr_slow, volatility_ratio) or None if calculation fails
    """
    try:
        # Fetch klines (need at least slow_period + a few for accuracy)
        klines = client.futures_klines(symbol=symbol, interval="3m", limit=max(lookback, slow_period + 5))
        
        if len(klines) < slow_period + 5:
            logger.warning(f"[RegimeEngine] Insufficient data for {symbol}: {len(klines)} candles (need {slow_period + 5})")
            return None
        
        # Extract price data
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]
        current_price = closes[-1]
        
        # Calculate True Range
        tr_values = []
        for i in range(1, len(highs)):
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i-1])
            tr3 = abs(lows[i] - closes[i-1])
            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)
        
        if len(tr_values) < slow_period:
            return None
        
        # Calculate ATR_fast (7-period) and ATR_slow (21-period)
        atr_fast = sum(tr_values[-fast_period:]) / fast_period
        atr_slow = sum(tr_values[-slow_period:]) / slow_period
        
        # Calculate Volatility Ratio (VR) = ATR_fast / ATR_slow
        if atr_slow > 0:
            volatility_ratio = atr_fast / atr_slow
        else:
            volatility_ratio = 1.0  # Default to normal if slow ATR is zero
        
        logger.debug(f"[RegimeEngine] {symbol} - ATR_fast={atr_fast:.4f}, ATR_slow={atr_slow:.4f}, VR={volatility_ratio:.3f}")
        
        return atr_fast, atr_slow, volatility_ratio
        
    except Exception as e:
        logger.warning(f"[RegimeEngine] Failed to calculate dual ATR for {symbol}: {e}")
        return None


def classify_regime(volatility_ratio: float) -> str:
    """
    Classify volatility regime based on Volatility Ratio (VR).
    
    Args:
        volatility_ratio: VR = ATR_fast / ATR_slow
        
    Returns:
        Regime classification: "EXTREME", "HIGH", "NORMAL", or "LOW"
    """
    if volatility_ratio >= VR_EXTREME:
        return "EXTREME"
    elif volatility_ratio >= VR_HIGH:
        return "HIGH"
    elif volatility_ratio >= VR_NORMAL_LOW:
        return "NORMAL"
    else:
        return "LOW"


def get_regime_adjustments(regime: str, atr_slow: float, price: float) -> Dict[str, any]:
    """
    Get position size and TP/SL adjustments based on regime.
    
    Args:
        regime: Volatility regime ("EXTREME", "HIGH", "NORMAL", "LOW")
        atr_slow: Slow ATR value
        price: Current price
        
    Returns:
        Dict with adjustments:
        - size_multiplier: Position size multiplier (e.g., 0.75 = reduce by 25%)
        - sl_adjustment: SL width adjustment factor
        - tp_adjustment: TP width adjustment factor
        - skip_entry: Whether to skip new entries
    """
    # Calculate ATR as percentage of price
    atr_pct = (atr_slow / price * 100) if price > 0 else 0
    
    if regime == "EXTREME":
        return {
            "size_multiplier": 0.0,  # Skip new entries
            "sl_adjustment": 1.5,  # Widen SL by 50%
            "tp_adjustment": 1.2,  # Widen TP by 20%
            "skip_entry": True,
            "reason": f"Extreme volatility (VR >= {VR_EXTREME})"
        }
    elif regime == "HIGH":
        return {
            "size_multiplier": 0.75,  # Reduce size by 25%
            "sl_adjustment": 1.3,  # Widen SL by 30%
            "tp_adjustment": 1.15,  # Widen TP by 15%
            "skip_entry": False,
            "reason": f"High volatility (VR >= {VR_HIGH})"
        }
    elif regime == "NORMAL":
        return {
            "size_multiplier": 1.0,  # No adjustment
            "sl_adjustment": 1.0,  # No adjustment
            "tp_adjustment": 1.0,  # No adjustment
            "skip_entry": False,
            "reason": "Normal volatility"
        }
    else:  # LOW
        # In low volatility, tighten stops or skip if ATR% is too low
        if atr_pct < 0.2:
            return {
                "size_multiplier": 0.0,  # Skip entry
                "sl_adjustment": 0.9,  # Slightly tighten
                "tp_adjustment": 0.9,  # Slightly tighten
                "skip_entry": True,
                "reason": f"Low volatility (VR < {VR_NORMAL_LOW}, ATR%={atr_pct:.2f}% < 0.2%)"
            }
        else:
            return {
                "size_multiplier": 1.0,  # No size adjustment
                "sl_adjustment": 0.9,  # Slightly tighten SL
                "tp_adjustment": 0.95,  # Slightly tighten TP
                "skip_entry": False,
                "reason": f"Low volatility (VR < {VR_NORMAL_LOW})"
            }


def get_regime_analysis(client, symbol: str) -> Optional[Dict[str, any]]:
    """
    Get complete regime analysis for a symbol.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        
    Returns:
        Dict with regime analysis or None if calculation fails:
        - regime: "EXTREME", "HIGH", "NORMAL", "LOW"
        - atr_fast: Fast ATR value
        - atr_slow: Slow ATR value
        - volatility_ratio: VR value
        - adjustments: Dict with size/TP/SL adjustments
    """
    result = calculate_dual_atr(client, symbol)
    
    if result is None:
        return None
    
    atr_fast, atr_slow, volatility_ratio = result
    
    # Get current price for adjustments
    try:
        mark_price_data = client.futures_mark_price(symbol=symbol)
        current_price = float(mark_price_data.get("markPrice", 0))
    except Exception:
        current_price = 0
    
    regime = classify_regime(volatility_ratio)
    adjustments = get_regime_adjustments(regime, atr_slow, current_price)
    
    return {
        "regime": regime,
        "atr_fast": atr_fast,
        "atr_slow": atr_slow,
        "volatility_ratio": volatility_ratio,
        "adjustments": adjustments,
        "current_price": current_price
    }

