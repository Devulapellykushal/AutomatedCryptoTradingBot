import os
import time
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime
from binance.client import Client

# Import centralized Binance client
from core.binance_client import get_data_client


def fetch_multi_timeframe_data(
    symbol: str = "BNB/USDT",
    timeframes: Optional[List[str]] = None,
    limit: int = 200
) -> Dict[str, pd.DataFrame]:
    """
    Fetch OHLCV data across multiple timeframes for multi-timeframe analysis.
    
    Args:
        symbol: Trading pair (e.g., 'BNB/USDT')
        timeframes: List of timeframes (e.g., ['1m', '5m', '15m', '1h', '4h'])
        limit: Number of candles per timeframe
        
    Returns:
        Dictionary mapping timeframe to DataFrame
    """
    if timeframes is None:
        timeframes = ['3m', '15m', '1h']
    
    result = {}
    for tf in timeframes:
        df = fetch_live_data(symbol, tf, limit)
        if not df.empty:
            result[tf] = df
        else:
            print(f"⚠️  Failed to fetch {symbol} data for {tf}")
    
    return result

def fetch_live_data(symbol="BNB/USDT", timeframe="3m", limit=200) -> pd.DataFrame:
    """
    Fetch OHLCV data from Binance Futures Testnet using python-binance.
    
    Args:
        symbol: Trading pair (e.g., 'BNB/USDT', 'BTC/USDT')
        timeframe: Candle timeframe (e.g., '1m', '3m', '5m', '15m', '1h', '1d')
        limit: Number of candles to fetch (max 1500)
        
    Returns:
        pd.DataFrame with OHLCV data
    """
    try:
        # Get data client dynamically (instead of module-level initialization)
        data_client = get_data_client()
        
        if data_client is None:
            print("❌ Binance Futures client not initialized")
            return pd.DataFrame(columns=["timestamp", "o", "h", "l", "c", "v"])  # type: ignore
        
        # Convert symbol format: BNB/USDT -> BNBUSDT
        binance_symbol = symbol.replace("/", "")
        
        # Map timeframe to Binance format
        timeframe_map = {
            "1m": Client.KLINE_INTERVAL_1MINUTE,
            "3m": Client.KLINE_INTERVAL_3MINUTE,
            "5m": Client.KLINE_INTERVAL_5MINUTE,
            "15m": Client.KLINE_INTERVAL_15MINUTE,
            "30m": Client.KLINE_INTERVAL_30MINUTE,
            "1h": Client.KLINE_INTERVAL_1HOUR,
            "2h": Client.KLINE_INTERVAL_2HOUR,
            "4h": Client.KLINE_INTERVAL_4HOUR,
            "6h": Client.KLINE_INTERVAL_6HOUR,
            "8h": Client.KLINE_INTERVAL_8HOUR,
            "12h": Client.KLINE_INTERVAL_12HOUR,
            "1d": Client.KLINE_INTERVAL_1DAY,
            "3d": Client.KLINE_INTERVAL_3DAY,
            "1w": Client.KLINE_INTERVAL_1WEEK,
            "1M": Client.KLINE_INTERVAL_1MONTH,
        }
        
        interval = timeframe_map.get(timeframe, Client.KLINE_INTERVAL_3MINUTE)
        
        # Fetch klines from Binance Futures
        klines = data_client.futures_klines(
            symbol=binance_symbol,
            interval=interval,
            limit=limit
        )
        
        if not klines:
            print(f"❌ No data received for {symbol}")
            return pd.DataFrame(columns=["timestamp", "o", "h", "l", "c", "v"])  # type: ignore
        
        # Convert to DataFrame
        # Binance klines format: [open_time, open, high, low, close, volume, close_time, ...]
        df = pd.DataFrame(klines, columns=[
            "timestamp", "o", "h", "l", "c", "v",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])  # type: ignore
        
        # Keep only needed columns and convert types
        df = df[["timestamp", "o", "h", "l", "c", "v"]]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["o"] = pd.to_numeric(df["o"])
        df["h"] = pd.to_numeric(df["h"])
        df["l"] = pd.to_numeric(df["l"])
        df["c"] = pd.to_numeric(df["c"])
        df["v"] = pd.to_numeric(df["v"])
        
        print(f"✅ Data fetched for {symbol} ({timeframe}): {len(df)} candles")
        return df  # type: ignore
        
    except Exception as e:
        print(f"❌ Error fetching data for {symbol}: {e}")
        return pd.DataFrame(columns=["timestamp", "o", "h", "l", "c", "v"])  # type: ignore


def fetch_ohlcv(symbol: str = "BTC/USDT", timeframe: str = "3m", limit: int = 200) -> pd.DataFrame:
    """
    Alias for fetch_live_data to maintain backward compatibility.
    """
    return fetch_live_data(symbol, timeframe, limit)