"""
Market analysis utilities: correlation, volatility regime classification
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


def calculate_correlation(symbol1: str, symbol2: str, client, lookback_periods: int = 50) -> Optional[float]:
    """
    Calculate price correlation between two symbols over recent periods.
    
    Args:
        symbol1: First symbol (e.g., "BTCUSDT")
        symbol2: Second symbol (e.g., "BNBUSDT")
        client: Binance futures client
        lookback_periods: Number of periods to analyze (default 50)
        
    Returns:
        Correlation coefficient (-1 to 1), or None if calculation fails
    """
    try:
        # Fetch recent price data for both symbols
        klines1 = client.futures_klines(symbol=symbol1, interval="3m", limit=lookback_periods)
        klines2 = client.futures_klines(symbol=symbol2, interval="3m", limit=lookback_periods)
        
        if len(klines1) < lookback_periods or len(klines2) < lookback_periods:
            logger.warning(f"[Correlation] Insufficient data for {symbol1}/{symbol2} correlation")
            return None
        
        # Extract closing prices
        closes1 = [float(k[4]) for k in klines1]
        closes2 = [float(k[4]) for k in klines2]
        
        # Calculate returns
        returns1 = pd.Series(closes1).pct_change().dropna()
        returns2 = pd.Series(closes2).pct_change().dropna()
        
        # Ensure same length
        min_len = min(len(returns1), len(returns2))
        returns1 = returns1[:min_len]
        returns2 = returns2[:min_len]
        
        # Calculate correlation
        correlation = returns1.corr(returns2)
        
        logger.debug(f"[Correlation] {symbol1}/{symbol2}: {correlation:.3f}")
        return correlation if not np.isnan(correlation) else None
        
    except Exception as e:
        logger.warning(f"[Correlation] Failed to calculate correlation for {symbol1}/{symbol2}: {e}")
        return None


def get_correlation_adjustment(symbol1: str, symbol2: str, client, correlation_threshold: float = 0.8) -> float:
    """
    Get position size adjustment factor based on correlation.
    
    If correlation > threshold, reduce second position size to avoid over-exposure.
    
    Args:
        symbol1: First symbol (e.g., "BTCUSDT")
        symbol2: Second symbol (e.g., "BNBUSDT")
        client: Binance futures client
        correlation_threshold: Correlation threshold above which to reduce size (default 0.8)
        
    Returns:
        Adjustment factor (0.5 to 1.0): 0.5 if highly correlated, 1.0 otherwise
    """
    correlation = calculate_correlation(symbol1, symbol2, client)
    
    if correlation is None:
        return 1.0  # No adjustment if correlation can't be calculated
    
    if correlation > correlation_threshold:
        # Reduce position size by 50% for highly correlated pairs
        logger.info(f"[Correlation] High correlation detected ({correlation:.3f} > {correlation_threshold}), reducing {symbol2} position size by 50%")
        return 0.5
    
    return 1.0


def classify_volatility_regime(symbol: str, client, lookback_periods: int = 30) -> str:
    """
    Classify current volatility regime as Low, Medium, or High.
    
    Uses ATR relative to price to determine volatility regime.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        client: Binance futures client
        lookback_periods: Number of periods to analyze (default 30)
        
    Returns:
        Regime classification: "LOW", "MEDIUM", or "HIGH"
    """
    try:
        # Fetch recent klines
        klines = client.futures_klines(symbol=symbol, interval="3m", limit=lookback_periods + 14)
        
        if len(klines) < lookback_periods + 14:
            return "MEDIUM"  # Default to medium if insufficient data
        
        # Extract price data
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]
        current_price = closes[-1]
        
        # Calculate ATR
        tr_values = []
        for i in range(1, len(highs)):
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i-1])
            tr3 = abs(lows[i] - closes[i-1])
            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)
        
        if len(tr_values) < 14:
            return "MEDIUM"
        
        # Calculate 14-period ATR
        atr = sum(tr_values[-14:]) / 14
        
        # Normalize ATR as percentage of price
        atr_pct = (atr / current_price) * 100
        
        # Classify based on ATR percentage thresholds
        # These thresholds are symbol-agnostic but can be tuned per symbol
        if atr_pct < 0.5:
            regime = "LOW"
        elif atr_pct < 1.5:
            regime = "MEDIUM"
        else:
            regime = "HIGH"
        
        logger.debug(f"[Volatility] {symbol} - ATR: {atr:.4f} ({atr_pct:.2f}%), Regime: {regime}")
        return regime
        
    except Exception as e:
        logger.warning(f"[Volatility] Failed to classify volatility regime for {symbol}: {e}")
        return "MEDIUM"  # Default to medium on error


def get_volatility_adjusted_confidence(base_confidence: float, regime: str) -> float:
    """
    Adjust confidence threshold based on volatility regime.
    
    - Low volatility: Increase threshold (be more selective)
    - High volatility: Decrease threshold (be more aggressive in trends)
    - Medium volatility: Use base threshold
    
    Args:
        base_confidence: Base confidence threshold (e.g., 0.65)
        regime: Volatility regime ("LOW", "MEDIUM", "HIGH")
        
    Returns:
        Adjusted confidence threshold
    """
    if regime == "LOW":
        # Increase threshold by 5% in low volatility (chop/range-bound)
        adjusted = base_confidence * 1.05
        logger.debug(f"[Volatility] Low volatility regime - increasing confidence threshold to {adjusted:.3f}")
    elif regime == "HIGH":
        # Decrease threshold by 3% in high volatility (strong trends)
        adjusted = base_confidence * 0.97
        logger.debug(f"[Volatility] High volatility regime - decreasing confidence threshold to {adjusted:.3f}")
    else:
        # Medium volatility - use base threshold
        adjusted = base_confidence
    
    return adjusted

