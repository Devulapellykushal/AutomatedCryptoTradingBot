"""
Professional Trading Strategies - Top 5 Most Reliable
Implements proven trading strategies with clear entry/exit rules
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple


class TradingStrategies:
    """
    Professional trading strategies implementation
    Each strategy returns: (signal, confidence, reasoning)
    """
    
    @staticmethod
    def trend_following(df: pd.DataFrame, params: Dict = None) -> Tuple[str, float, str]:
        """
        TREND FOLLOWING - Most Reliable Strategy
        
        BUY when:
        - Price > 20-period EMA
        - MACD line > MACD signal line
        - RSI between 40-70 (not overbought)
        
        SELL when:
        - Price < 20-period EMA
        - MACD line < MACD signal line
        - RSI between 30-60 (not oversold)
        
        Args:
            df: DataFrame with technical indicators
            params: Optional parameters for customization
                - rsi_buy_min: RSI lower bound for buy (default 40)
                - rsi_buy_max: RSI upper bound for buy (default 70)
                - rsi_sell_min: RSI lower bound for sell (default 30)
                - rsi_sell_max: RSI upper bound for sell (default 60)
        
        Returns:
            (signal, confidence, reasoning)
        """
        if params is None:
            params = {}
        
        # Customizable parameters
        rsi_buy_min = params.get('rsi_buy_min', 40)
        rsi_buy_max = params.get('rsi_buy_max', 70)
        rsi_sell_min = params.get('rsi_sell_min', 30)
        rsi_sell_max = params.get('rsi_sell_max', 60)
        
        last = df.iloc[-1]
        price = last['c']
        ema_20 = last.get('ema20', last.get('ema21', last.get('ema9')))
        macd = last['macd']
        macd_signal = last.get('macd_signal', 0)
        rsi = last['rsi']
        
        # Calculate confidence based on how well conditions are met
        confidence = 0.0
        signals = []
        
        # BUY conditions
        if price > ema_20 and macd > macd_signal and rsi_buy_min < rsi < rsi_buy_max:
            signals.append("price_above_ema")
            confidence += 0.35
            
            if macd > macd_signal:
                signals.append("macd_bullish")
                confidence += 0.35
            
            if rsi_buy_min < rsi < rsi_buy_max:
                signals.append("rsi_healthy")
                confidence += 0.30
            
            reasoning = f"Trend Following BUY: Price ${price:.2f} > EMA20 ${ema_20:.2f}, MACD bullish ({macd:.4f} > {macd_signal:.4f}), RSI healthy at {rsi:.2f}"
            return "long", min(confidence, 0.95), reasoning
        
        # SELL conditions
        elif price < ema_20 and macd < macd_signal and rsi_sell_min < rsi < rsi_sell_max:
            signals.append("price_below_ema")
            confidence += 0.35
            
            if macd < macd_signal:
                signals.append("macd_bearish")
                confidence += 0.35
            
            if rsi_sell_min < rsi < rsi_sell_max:
                signals.append("rsi_healthy")
                confidence += 0.30
            
            reasoning = f"Trend Following SELL: Price ${price:.2f} < EMA20 ${ema_20:.2f}, MACD bearish ({macd:.4f} < {macd_signal:.4f}), RSI at {rsi:.2f}"
            return "short", min(confidence, 0.95), reasoning
        
        else:
            reasoning = f"Trend Following HOLD: Mixed signals - Price vs EMA20: {price > ema_20}, MACD: {macd > macd_signal}, RSI: {rsi:.2f}"
            return "hold", 0.3, reasoning
    
    @staticmethod
    def mean_reversion(df: pd.DataFrame) -> Tuple[str, float, str]:
        """
        MEAN REVERSION - Range Markets Strategy
        
        BUY when:
        - RSI < 30 (oversold)
        - Price near Bollinger Band lower
        - Volume increasing
        
        SELL when:
        - RSI > 70 (overbought)
        - Price near Bollinger Band upper
        - Volume decreasing
        
        Returns:
            (signal, confidence, reasoning)
        """
        last = df.iloc[-1]
        price = last['c']
        rsi = last['rsi']
        bb_lower = last.get('bb_lower', price * 0.98)
        bb_upper = last.get('bb_upper', price * 1.02)
        volume = last['v']
        avg_volume = df['v'].rolling(20).mean().iloc[-1]
        
        confidence = 0.0
        
        # BUY conditions (oversold + near lower band)
        if rsi < 30 and price <= bb_lower * 1.02:
            confidence += 0.5  # Strong oversold signal
            
            if price <= bb_lower:
                confidence += 0.3  # At or below lower band
            
            if volume > avg_volume:
                confidence += 0.2  # Volume confirmation
            
            reasoning = f"Mean Reversion BUY: RSI oversold at {rsi:.2f}, Price ${price:.2f} near BB lower ${bb_lower:.2f}, Volume: {volume/avg_volume:.2f}x avg"
            return "long", min(confidence, 0.95), reasoning
        
        # SELL conditions (overbought + near upper band)
        elif rsi > 70 and price >= bb_upper * 0.98:
            confidence += 0.5  # Strong overbought signal
            
            if price >= bb_upper:
                confidence += 0.3  # At or above upper band
            
            if volume < avg_volume:
                confidence += 0.2  # Volume confirmation (decreasing)
            
            reasoning = f"Mean Reversion SELL: RSI overbought at {rsi:.2f}, Price ${price:.2f} near BB upper ${bb_upper:.2f}, Volume: {volume/avg_volume:.2f}x avg"
            return "short", min(confidence, 0.95), reasoning
        
        else:
            reasoning = f"Mean Reversion HOLD: RSI {rsi:.2f} in neutral zone, Price between BB bands"
            return "hold", 0.3, reasoning
    
    @staticmethod
    def breakout_strategy(df: pd.DataFrame) -> Tuple[str, float, str]:
        """
        BREAKOUT STRATEGY - High Momentum
        
        BUY when:
        - Price breaks above Bollinger Band upper
        - Volume > average volume
        - RSI < 70 (not overbought)
        
        SELL when:
        - Price breaks below Bollinger Band lower
        - Volume > average volume
        - RSI > 30 (not oversold)
        
        Returns:
            (signal, confidence, reasoning)
        """
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        price = last['c']
        prev_price = prev['c']
        rsi = last['rsi']
        bb_upper = last.get('bb_upper', price * 1.02)
        bb_lower = last.get('bb_lower', price * 0.98)
        volume = last['v']
        avg_volume = df['v'].rolling(20).mean().iloc[-1]
        
        confidence = 0.0
        
        # BUY conditions (breakout above upper band)
        if price > bb_upper and volume > avg_volume and rsi < 70:
            confidence += 0.4  # Breakout confirmed
            
            if prev_price <= bb_upper:
                confidence += 0.3  # Fresh breakout (just happened)
            
            if volume > avg_volume * 1.5:
                confidence += 0.2  # Strong volume surge
            
            if rsi < 65:
                confidence += 0.1  # Room to run
            
            reasoning = f"Breakout BUY: Price ${price:.2f} broke above BB upper ${bb_upper:.2f}, Volume {volume/avg_volume:.2f}x avg, RSI {rsi:.2f}"
            return "long", min(confidence, 0.95), reasoning
        
        # SELL conditions (breakdown below lower band)
        elif price < bb_lower and volume > avg_volume and rsi > 30:
            confidence += 0.4  # Breakdown confirmed
            
            if prev_price >= bb_lower:
                confidence += 0.3  # Fresh breakdown
            
            if volume > avg_volume * 1.5:
                confidence += 0.2  # Strong volume surge
            
            if rsi > 35:
                confidence += 0.1  # Room to fall
            
            reasoning = f"Breakout SELL: Price ${price:.2f} broke below BB lower ${bb_lower:.2f}, Volume {volume/avg_volume:.2f}x avg, RSI {rsi:.2f}"
            return "short", min(confidence, 0.95), reasoning
        
        else:
            reasoning = f"Breakout HOLD: No breakout detected, Price within BB bands"
            return "hold", 0.3, reasoning
    
    @staticmethod
    def macd_momentum(df: pd.DataFrame) -> Tuple[str, float, str]:
        """
        MACD MOMENTUM - Trend Changes Strategy
        
        BUY when:
        - MACD crosses ABOVE signal line
        - MACD histogram turns positive
        - Price above 20-EMA
        
        SELL when:
        - MACD crosses BELOW signal line
        - MACD histogram turns negative
        - Price below 20-EMA
        
        Returns:
            (signal, confidence, reasoning)
        """
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        price = last['c']
        ema_20 = last.get('ema21', last.get('ema9'))
        macd = last['macd']
        macd_signal = last.get('macd_signal', 0)
        macd_histogram = last.get('macd_histogram', macd - macd_signal)
        
        prev_macd = prev['macd']
        prev_macd_signal = prev.get('macd_signal', 0)
        
        confidence = 0.0
        
        # BUY conditions (bullish MACD cross)
        if macd > macd_signal and macd_histogram > 0 and price > ema_20:
            confidence += 0.4  # MACD above signal
            
            # Check for fresh crossover
            if prev_macd <= prev_macd_signal and macd > macd_signal:
                confidence += 0.3  # Fresh bullish cross
            
            if macd_histogram > 0:
                confidence += 0.2  # Positive histogram
            
            if price > ema_20:
                confidence += 0.1  # Price confirmation
            
            reasoning = f"MACD Momentum BUY: MACD crossed above signal ({macd:.4f} > {macd_signal:.4f}), Histogram {macd_histogram:.4f}, Price ${price:.2f} > EMA20 ${ema_20:.2f}"
            return "long", min(confidence, 0.95), reasoning
        
        # SELL conditions (bearish MACD cross)
        elif macd < macd_signal and macd_histogram < 0 and price < ema_20:
            confidence += 0.4  # MACD below signal
            
            # Check for fresh crossover
            if prev_macd >= prev_macd_signal and macd < macd_signal:
                confidence += 0.3  # Fresh bearish cross
            
            if macd_histogram < 0:
                confidence += 0.2  # Negative histogram
            
            if price < ema_20:
                confidence += 0.1  # Price confirmation
            
            reasoning = f"MACD Momentum SELL: MACD crossed below signal ({macd:.4f} < {macd_signal:.4f}), Histogram {macd_histogram:.4f}, Price ${price:.2f} < EMA20 ${ema_20:.2f}"
            return "short", min(confidence, 0.95), reasoning
        
        else:
            reasoning = f"MACD Momentum HOLD: No clear crossover signal, MACD {macd:.4f} vs Signal {macd_signal:.4f}"
            return "hold", 0.3, reasoning
    
    @staticmethod
    def multi_timeframe(df: pd.DataFrame, symbol: str = None) -> Tuple[str, float, str]:
        """
        MULTI-TIMEFRAME CONFIRMATION - Professional Strategy
        
        Note: This is a simplified version using single timeframe with strong trend confirmation
        Full implementation would require fetching multiple timeframes
        
        BUY when:
        - Short-term: Price > EMA20, RSI > 50
        - Medium-term: MACD bullish, trend up
        - Long-term: Price > EMA50 (confirmation)
        
        SELL when:
        - Short-term: Price < EMA20, RSI < 50
        - Medium-term: MACD bearish, trend down
        - Long-term: Price < EMA50 (confirmation)
        
        Returns:
            (signal, confidence, reasoning)
        """
        last = df.iloc[-1]
        
        price = last['c']
        ema_20 = last.get('ema21', last.get('ema9'))
        ema_50 = last.get('ema50', ema_20)
        rsi = last['rsi']
        macd = last['macd']
        macd_signal = last.get('macd_signal', 0)
        
        # Short-term trend
        short_term_bullish = price > ema_20 and rsi > 50
        short_term_bearish = price < ema_20 and rsi < 50
        
        # Medium-term trend
        medium_term_bullish = macd > macd_signal and ema_20 > ema_50
        medium_term_bearish = macd < macd_signal and ema_20 < ema_50
        
        # Long-term trend
        long_term_bullish = price > ema_50
        long_term_bearish = price < ema_50
        
        confidence = 0.0
        
        # BUY conditions (all timeframes align bullish)
        if short_term_bullish and medium_term_bullish and long_term_bullish:
            confidence = 0.9  # All timeframes aligned
            reasoning = f"Multi-TF BUY: All timeframes bullish - Price ${price:.2f} > EMA20 ${ema_20:.2f} > EMA50 ${ema_50:.2f}, RSI {rsi:.2f}, MACD bullish"
            return "long", confidence, reasoning
        
        # SELL conditions (all timeframes align bearish)
        elif short_term_bearish and medium_term_bearish and long_term_bearish:
            confidence = 0.9  # All timeframes aligned
            reasoning = f"Multi-TF SELL: All timeframes bearish - Price ${price:.2f} < EMA20 ${ema_20:.2f} < EMA50 ${ema_50:.2f}, RSI {rsi:.2f}, MACD bearish"
            return "short", confidence, reasoning
        
        # Partial alignment
        elif short_term_bullish and (medium_term_bullish or long_term_bullish):
            confidence = 0.6
            reasoning = f"Multi-TF BUY (partial): 2/3 timeframes bullish, Price ${price:.2f}, RSI {rsi:.2f}"
            return "long", confidence, reasoning
        
        elif short_term_bearish and (medium_term_bearish or long_term_bearish):
            confidence = 0.6
            reasoning = f"Multi-TF SELL (partial): 2/3 timeframes bearish, Price ${price:.2f}, RSI {rsi:.2f}"
            return "short", confidence, reasoning
        
        else:
            reasoning = f"Multi-TF HOLD: Timeframes not aligned, mixed signals"
            return "hold", 0.3, reasoning


def apply_strategy(strategy_name: str, df: pd.DataFrame, symbol: str = None, mtf_data: Dict = None, params: Dict = None) -> Dict[str, any]:
    """
    Apply a specific trading strategy to the data
    
    Args:
        strategy_name: One of: trend_following, mean_reversion, breakout, macd_momentum, multi_timeframe
        df: DataFrame with technical indicators
        symbol: Trading pair symbol (optional)
        mtf_data: Multi-timeframe data dictionary (optional, for multi_timeframe strategy)
        params: Strategy-specific parameters (optional)
    
    Returns:
        Dictionary with signal, confidence, and reasoning
    """
    strategies = TradingStrategies()
    
    strategy_map = {
        "trend_following": lambda: strategies.trend_following(df, params),
        "mean_reversion": lambda: strategies.mean_reversion(df),
        "breakout": lambda: strategies.breakout_strategy(df),
        "macd_momentum": lambda: strategies.macd_momentum(df),
        "multi_timeframe": lambda: strategies.multi_timeframe(df, symbol, mtf_data),
        # Aliases
        "momentum": lambda: strategies.trend_following(df, params),
        "scalping": lambda: strategies.macd_momentum(df),
        "contrarian": lambda: strategies.mean_reversion(df),
    }
    
    strategy_func = strategy_map.get(strategy_name.lower(), lambda: strategies.trend_following(df, params))
    
    try:
        signal, confidence, reasoning = strategy_func()
        
        return {
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "strategy_used": strategy_name
        }
    except Exception as e:
        return {
            "signal": "hold",
            "confidence": 0.3,
            "reasoning": f"Strategy error: {str(e)}",
            "strategy_used": strategy_name
        }
        bearish_count = sum(1 for sig, _ in tf_signals if sig == 'bearish')
        total_count = len(tf_signals)
        
        # All aligned - high confidence
        if bullish_count == total_count:
            timeframes_str = ", ".join([tf for _, tf in tf_signals])
            reasoning = f"Multi-TF BUY: All {total_count} timeframes bullish [{timeframes_str}]"
            return "long", 0.9, reasoning
        
        elif bearish_count == total_count:
            timeframes_str = ", ".join([tf for _, tf in tf_signals])
            reasoning = f"Multi-TF SELL: All {total_count} timeframes bearish [{timeframes_str}]"
            return "short", 0.9, reasoning
        
        # Majority aligned - medium confidence
        elif bullish_count > total_count / 2:
            confidence = 0.5 + (bullish_count / total_count) * 0.3
            reasoning = f"Multi-TF BUY (majority): {bullish_count}/{total_count} timeframes bullish"
            return "long", confidence, reasoning
        
        elif bearish_count > total_count / 2:
            confidence = 0.5 + (bearish_count / total_count) * 0.3
            reasoning = f"Multi-TF SELL (majority): {bearish_count}/{total_count} timeframes bearish"
            return "short", confidence, reasoning
        
        else:
            reasoning = f"Multi-TF HOLD: Mixed signals ({bullish_count}B/{bearish_count}S/{total_count-bullish_count-bearish_count}N)"
            return "hold", 0.3, reasoning


def apply_strategy(strategy_name: str, df: pd.DataFrame, symbol: str = None) -> Dict[str, any]:
    """
    Apply a specific trading strategy to the data
    
    Args:
        strategy_name: One of: trend_following, mean_reversion, breakout, macd_momentum, multi_timeframe
        df: DataFrame with technical indicators
        symbol: Trading pair symbol (optional)
    
    Returns:
        Dictionary with signal, confidence, and reasoning
    """
    strategies = TradingStrategies()
    
    strategy_map = {
        "trend_following": strategies.trend_following,
        "mean_reversion": strategies.mean_reversion,
        "breakout": strategies.breakout_strategy,
        "macd_momentum": strategies.macd_momentum,
        "multi_timeframe": strategies.multi_timeframe,
        # Aliases
        "momentum": strategies.trend_following,
        "scalping": strategies.macd_momentum,
        "contrarian": strategies.mean_reversion,
    }
    
    strategy_func = strategy_map.get(strategy_name.lower(), strategies.trend_following)
    
    try:
        signal, confidence, reasoning = strategy_func(df)
        
        return {
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "strategy_used": strategy_name
        }
    except Exception as e:
        return {
            "signal": "hold",
            "confidence": 0.3,
            "reasoning": f"Strategy error: {str(e)}",
            "strategy_used": strategy_name
        }
    
    try:
        signal, confidence, reasoning = strategy_func(df)
        
        return {
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "strategy_used": strategy_name
        }
    except Exception as e:
        return {
            "signal": "hold",
            "confidence": 0.3,
            "reasoning": f"Strategy error: {str(e)}",
            "strategy_used": strategy_name
        }
