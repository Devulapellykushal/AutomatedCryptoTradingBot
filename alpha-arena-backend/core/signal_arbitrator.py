"""
Signal Arbitrator - Resolves conflicting BUY/SELL signals from multiple agents
Implements Priority #2 from analysis: Meta-agent arbitration to prevent self-cancelling trades

Aggregates signals by confidence×weight and chooses the strongest direction.
"""

import logging
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# Track recent signals per symbol to prevent conflicts
_recent_signals: Dict[str, List[Dict[str, Any]]] = {}  # {symbol: [signal1, signal2, ...]}
_signal_window_seconds = 60  # Consider signals within 60 seconds


def arbitrate_signals(
    symbol: str,
    agent_signals: List[Dict[str, Any]],
    current_time: float
) -> Tuple[str, float, str]:
    """
    Arbitrate conflicting signals from multiple agents for the same symbol.
    
    Args:
        symbol: Trading symbol
        agent_signals: List of signals from agents [{"agent_id": str, "signal": str, "confidence": float, "reasoning": str}, ...]
        current_time: Current timestamp
    
    Returns:
        Tuple of (final_signal, aggregated_confidence, arbitration_reason)
    """
    if not agent_signals:
        return "hold", 0.0, "No signals received"
    
    # Filter signals to only BUY/SELL (exclude HOLD)
    active_signals = [s for s in agent_signals if s.get("signal", "hold") in ["long", "short"]]
    
    if not active_signals:
        return "hold", 0.0, "All agents recommend HOLD"
    
    # Group signals by direction
    long_signals = [s for s in active_signals if s.get("signal") == "long"]
    short_signals = [s for s in active_signals if s.get("signal") == "short"]
    
    # Calculate weighted confidence for each direction
    long_weighted_conf = sum(s.get("confidence", 0.0) for s in long_signals) / max(len(long_signals), 1)
    short_weighted_conf = sum(s.get("confidence", 0.0) for s in short_signals) / max(len(short_signals), 1)
    
    # Apply agent weight multiplier (some agents are more reliable)
    agent_weights = {
        "trend_following": 1.2,
        "momentum": 1.1,
        "multi_timeframe": 1.15,
        "breakout": 1.0,
        "mean_reversion": 0.9,
        "scalping": 0.95,
        "macd_momentum": 1.0
    }
    
    # Weight by agent style
    long_total_weight = sum(
        s.get("confidence", 0.0) * agent_weights.get(s.get("agent_style", ""), 1.0)
        for s in long_signals
    )
    short_total_weight = sum(
        s.get("confidence", 0.0) * agent_weights.get(s.get("agent_style", ""), 1.0)
        for s in short_signals
    )
    
    # Decision logic: Choose direction with higher weighted confidence
    if long_total_weight > short_total_weight and long_total_weight > 0.5:
        final_signal = "long"
        final_confidence = min(long_total_weight / len(agent_signals) if len(agent_signals) > 0 else long_total_weight, 0.95)
        reason = f"LONG wins ({len(long_signals)} agents, weighted conf: {long_total_weight:.2f} vs SHORT: {short_total_weight:.2f})"
    elif short_total_weight > long_total_weight and short_total_weight > 0.5:
        final_signal = "short"
        final_confidence = min(short_total_weight / len(agent_signals) if len(agent_signals) > 0 else short_total_weight, 0.95)
        reason = f"SHORT wins ({len(short_signals)} agents, weighted conf: {short_total_weight:.2f} vs LONG: {long_total_weight:.2f})"
    else:
        # No clear winner or both below threshold
        final_signal = "hold"
        final_confidence = max(long_total_weight, short_total_weight)
        reason = f"Conflict unresolved (LONG: {long_total_weight:.2f}, SHORT: {short_total_weight:.2f}) - HOLD"
    
    # Store recent signal for conflict detection
    if symbol not in _recent_signals:
        _recent_signals[symbol] = []
    
    _recent_signals[symbol].append({
        "signal": final_signal,
        "confidence": final_confidence,
        "time": current_time,
        "reason": reason
    })
    
    # Clean old signals (outside window)
    _recent_signals[symbol] = [
        s for s in _recent_signals[symbol]
        if (current_time - s.get("time", 0)) < _signal_window_seconds
    ]
    
    logger.info(f"[SignalArbitrator] {symbol}: {reason}")
    
    return final_signal, final_confidence, reason


def check_signal_conflict(symbol: str, new_signal: str, current_time: float) -> Tuple[bool, Optional[str]]:
    """
    Check if new signal conflicts with recent signals (prevent rapid BUY/SELL flips).
    
    Args:
        symbol: Trading symbol
        new_signal: New signal ("long", "short", "hold")
        current_time: Current timestamp
    
    Returns:
        Tuple of (has_conflict, conflict_reason)
    """
    if symbol not in _recent_signals or len(_recent_signals[symbol]) == 0:
        return False, None
    
    # Get most recent signal
    recent = _recent_signals[symbol][-1]
    recent_signal = recent.get("signal", "hold")
    recent_time = recent.get("time", 0)
    
    # Check if signals are opposite and within short time window
    if new_signal != "hold" and recent_signal != "hold":
        if (new_signal == "long" and recent_signal == "short") or \
           (new_signal == "short" and recent_signal == "long"):
            time_diff = current_time - recent_time
            if time_diff < 30:  # Within 30 seconds - too rapid flip
                return True, f"Rapid signal flip detected ({new_signal} after {recent_signal} within {time_diff:.1f}s)"
    
    return False, None


def get_signal_summary(symbol: str) -> Dict[str, Any]:
    """Get summary of recent signals for a symbol"""
    if symbol not in _recent_signals:
        return {"count": 0, "recent_signals": []}
    
    signals = _recent_signals[symbol]
    return {
        "count": len(signals),
        "recent_signals": signals[-5:],  # Last 5 signals
        "most_recent": signals[-1] if signals else None
    }

