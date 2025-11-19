"""
Enhanced Signal Engine with 40+ Technical Indicators
Provides comprehensive feature generation for AI trading decisions
"""

import pandas as pd
import numpy as np
from typing import Optional

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute comprehensive technical indicators (40+ features)
    
    Categories:
    - Momentum: RSI, CCI, Stochastic, Williams %R, ROC
    - Trend: EMA(9,21,50,200), MACD, ADX, Aroon, Parabolic SAR
    - Volatility: Bollinger Bands, ATR, Donchian Channels, Keltner Channels
    - Volume: OBV, VWAP, Volume MA, Force Index
    - Candle Patterns: Body ratio, wicks, gaps, doji detection
    
    Args:
        df: DataFrame with OHLCV columns (o, h, l, c, v)
        
    Returns:
        DataFrame with all technical indicators added
    """
    if df.empty or len(df) < 50:
        return df
    
    # Make copy to avoid modifying original
    df = df.copy()
    
    # ============ TREND INDICATORS ============
    # Exact EMA periods for strategy alignment
    df["ema9"] = df["c"].ewm(span=9, adjust=False).mean()
    df["ema20"] = df["c"].ewm(span=20, adjust=False).mean()
    df["ema21"] = df["c"].ewm(span=21, adjust=False).mean()
    df["ema50"] = df["c"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["c"].ewm(span=200, adjust=False).mean()
    
    # MACD
    ema12 = df["c"].ewm(span=12, adjust=False).mean()
    ema26 = df["c"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]
    
    # ADX (Average Directional Index)
    df = compute_adx(df)
    
    # ============ MOMENTUM INDICATORS ============
    df["rsi"] = compute_rsi(df["c"], 14)
    df["rsi_9"] = compute_rsi(df["c"], 9)
    df["rsi_25"] = compute_rsi(df["c"], 25)
    
    # CCI (Commodity Channel Index)
    df["cci"] = compute_cci(df, 20)
    
    # Stochastic Oscillator
    df = compute_stochastic(df)
    
    # Williams %R
    df["williams_r"] = compute_williams_r(df, 14)
    
    # Rate of Change
    df["roc"] = ((df["c"] - df["c"].shift(12)) / df["c"].shift(12)) * 100
    
    # Momentum
    df["momentum"] = df["c"] - df["c"].shift(10)
    
    # ============ VOLATILITY INDICATORS ============
    df["atr"] = compute_atr(df, 14)
    df["atr_21"] = compute_atr(df, 21)
    
    # Bollinger Bands
    df = compute_bollinger_bands(df, 20, 2)
    
    # Donchian Channels
    df = compute_donchian_channels(df, 20)
    
    # Keltner Channels
    df = compute_keltner_channels(df, 20)
    
    # Historical Volatility
    df["volatility"] = df["c"].pct_change().rolling(20).std() * np.sqrt(252) * 100
    
    # ============ VOLUME INDICATORS ============
    df["obv"] = compute_obv(df)
    df["vwap"] = compute_vwap(df)
    df["volume_ma"] = df["v"].rolling(20).mean()
    df["volume_ratio"] = df["v"] / df["volume_ma"]
    df["force_index"] = compute_force_index(df)
    
    # ============ PRICE ACTION INDICATORS ============
    # Candle body and wick ratios
    df["body"] = abs(df["c"] - df["o"])
    df["body_pct"] = (df["body"] / df["c"]) * 100
    df["upper_wick"] = df["h"] - df[["o", "c"]].max(axis=1)
    df["lower_wick"] = df[["o", "c"]].min(axis=1) - df["l"]
    df["total_range"] = df["h"] - df["l"]
    df["upper_wick_ratio"] = df["upper_wick"] / df["total_range"]
    df["lower_wick_ratio"] = df["lower_wick"] / df["total_range"]
    
    # Doji detection
    df["is_doji"] = (df["body_pct"] < 0.1).astype(int)
    
    # Trend strength
    df["trend_strength"] = (df["ema9"] - df["ema21"]) / df["c"] * 100
    
    # Price distance from EMAs
    df["dist_ema9"] = ((df["c"] - df["ema9"]) / df["c"]) * 100
    df["dist_ema21"] = ((df["c"] - df["ema21"]) / df["c"]) * 100
    df["dist_ema50"] = ((df["c"] - df["ema50"]) / df["c"]) * 100
    
    # Gaps
    df["gap"] = df["o"] - df["c"].shift(1)
    df["gap_pct"] = (df["gap"] / df["c"].shift(1)) * 100
    
    # ============ DERIVED FEATURES ============
    # RSI divergence (simplified)
    df["rsi_slope"] = df["rsi"].diff(5)
    df["price_slope"] = df["c"].diff(5)
    
    # Volume trend
    df["volume_trend"] = df["v"].rolling(5).mean() / df["v"].rolling(20).mean()
    
    # Volatility expansion
    df["atr_expansion"] = df["atr"] / df["atr"].rolling(20).mean()
    
    # Fill NaN values using forward fill then backward fill
    df = df.ffill().bfill()
    
    return df


def compute_rsi(series: pd.Series, n: int = 14) -> pd.Series:
    """Compute Relative Strength Index"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1/n, min_periods=n).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Compute Average True Range"""
    high_low = df["h"] - df["l"]
    high_close = (df["h"] - df["c"].shift()).abs()
    low_close = (df["l"] - df["c"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def compute_cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Compute Commodity Channel Index"""
    tp = (df["h"] + df["l"] + df["c"]) / 3
    sma_tp = tp.rolling(n).mean()
    mad = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean())
    return (tp - sma_tp) / (0.015 * mad)


def compute_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    """Compute Stochastic Oscillator"""
    low_min = df["l"].rolling(k_period).min()
    high_max = df["h"].rolling(k_period).max()
    df["stoch_k"] = 100 * (df["c"] - low_min) / (high_max - low_min)
    df["stoch_d"] = df["stoch_k"].rolling(d_period).mean()
    return df


def compute_williams_r(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Compute Williams %R"""
    high_max = df["h"].rolling(n).max()
    low_min = df["l"].rolling(n).min()
    return -100 * (high_max - df["c"]) / (high_max - low_min)


def compute_adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """Compute Average Directional Index"""
    high_diff = df["h"].diff()
    low_diff = -df["l"].diff()
    
    pos_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
    neg_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
    
    atr = compute_atr(df, n)
    
    pos_di = 100 * pos_dm.ewm(span=n, adjust=False).mean() / atr
    neg_di = 100 * neg_dm.ewm(span=n, adjust=False).mean() / atr
    
    dx = 100 * abs(pos_di - neg_di) / (pos_di + neg_di)
    df["adx"] = dx.ewm(span=n, adjust=False).mean()
    df["plus_di"] = pos_di
    df["minus_di"] = neg_di
    
    return df


def compute_bollinger_bands(df: pd.DataFrame, n: int = 20, std: float = 2) -> pd.DataFrame:
    """Compute Bollinger Bands"""
    df["bb_middle"] = df["c"].rolling(n).mean()
    bb_std = df["c"].rolling(n).std()
    df["bb_upper"] = df["bb_middle"] + (std * bb_std)
    df["bb_lower"] = df["bb_middle"] - (std * bb_std)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"] * 100
    df["bb_position"] = (df["c"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]) * 100
    return df


def compute_donchian_channels(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Compute Donchian Channels"""
    df["donchian_upper"] = df["h"].rolling(n).max()
    df["donchian_lower"] = df["l"].rolling(n).min()
    df["donchian_middle"] = (df["donchian_upper"] + df["donchian_lower"]) / 2
    return df


def compute_keltner_channels(df: pd.DataFrame, n: int = 20, atr_mult: float = 2) -> pd.DataFrame:
    """Compute Keltner Channels"""
    df["keltner_middle"] = df["c"].ewm(span=n, adjust=False).mean()
    atr = compute_atr(df, n)
    df["keltner_upper"] = df["keltner_middle"] + (atr_mult * atr)
    df["keltner_lower"] = df["keltner_middle"] - (atr_mult * atr)
    return df


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """Compute On-Balance Volume"""
    obv = (np.sign(df["c"].diff()) * df["v"]).fillna(0).cumsum()
    return obv


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute Volume Weighted Average Price"""
    typical_price = (df["h"] + df["l"] + df["c"]) / 3
    return (typical_price * df["v"]).cumsum() / df["v"].cumsum()


def compute_force_index(df: pd.DataFrame, n: int = 13) -> pd.Series:
    """Compute Force Index"""
    force = df["c"].diff() * df["v"]
    return force.ewm(span=n, adjust=False).mean()


def get_feature_summary(df: pd.DataFrame) -> dict:
    """
    Get summary of all computed features for display/debugging
    
    Returns:
        Dictionary with feature counts by category
    """
    if df.empty:
        return {}
    
    last_row = df.iloc[-1]
    
    return {
        "total_features": len(df.columns),
        "trend_indicators": [
            "ema9", "ema21", "ema50", "ema200", "macd", "macd_signal", 
            "macd_histogram", "adx", "plus_di", "minus_di"
        ],
        "momentum_indicators": [
            "rsi", "rsi_9", "rsi_25", "cci", "stoch_k", "stoch_d", 
            "williams_r", "roc", "momentum"
        ],
        "volatility_indicators": [
            "atr", "atr_21", "bb_upper", "bb_middle", "bb_lower", "bb_width",
            "bb_position", "donchian_upper", "donchian_middle", "donchian_lower",
            "keltner_upper", "keltner_middle", "keltner_lower", "volatility"
        ],
        "volume_indicators": [
            "obv", "vwap", "volume_ma", "volume_ratio", "force_index", "volume_trend"
        ],
        "price_action": [
            "body", "body_pct", "upper_wick", "lower_wick", "upper_wick_ratio",
            "lower_wick_ratio", "is_doji", "gap", "gap_pct"
        ],
        "derived_features": [
            "trend_strength", "dist_ema9", "dist_ema21", "dist_ema50",
            "rsi_slope", "price_slope", "atr_expansion"
        ]
    }
