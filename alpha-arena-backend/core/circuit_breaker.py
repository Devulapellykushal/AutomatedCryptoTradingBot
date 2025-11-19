"""
Circuit Breaker Module - Pauses new entries during extreme market conditions
Implements Item #7 from bulletproof improvements

Detects:
- Candle spread volatility (high-low spread > 2.5× median) - adjusted for crypto volatility
- Funding rate spikes (>0.1% change in last hour)
- Maker/Taker spread widening (>0.25% threshold)

Uses adaptive pause duration:
- Minor spikes (2.5-3.0× median): 5 minutes
- Extreme spikes (3.0×+ median): 10 minutes
"""

import logging
import time
from typing import Dict, Optional, Tuple
from core.binance_client import get_futures_client

logger = logging.getLogger(__name__)

# Circuit breaker state per symbol
_circuit_breaker_state: Dict[str, Dict] = {}
_circuit_breaker_active_until: Dict[str, float] = {}

# Default pause duration (5-10 minutes)
DEFAULT_PAUSE_DURATION = 600  # 10 minutes


def check_candle_spread_volatility(client, symbol: str, limit: int = 30) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Check if candle spread (high-low)/close > 2.5× 30-bar median (adjusted for crypto volatility)
    
    Returns:
        (should_pause, reason, severity_multiplier): 
            - True if entry should be paused
            - Reason string if paused
            - Severity multiplier (1.0 for minor, 2.0 for extreme) for adaptive pause duration
    """
    try:
        klines = client.futures_klines(symbol=symbol, interval="3m", limit=limit)
        if len(klines) < limit:
            return False, None, None
        
        # Calculate spreads for each candle
        spreads = []
        for k in klines:
            high = float(k[2])
            low = float(k[3])
            close = float(k[4])
            
            if close > 0:
                spread_pct = ((high - low) / close) * 100
                spreads.append(spread_pct)
        
        if len(spreads) < limit:
            return False, None, None
        
        # Calculate median spread
        sorted_spreads = sorted(spreads)
        median_spread = sorted_spreads[len(sorted_spreads) // 2]
        
        # Current candle spread
        current_spread = spreads[-1]
        
        # Check if current spread > 2.5× median (more reasonable threshold for crypto)
        if median_spread > 0 and current_spread > (median_spread * 2.5):
            # Determine severity: 3.0x+ = extreme (longer pause), 2.5-3.0x = minor (shorter pause)
            severity_ratio = current_spread / median_spread if median_spread > 0 else 1.0
            severity_multiplier = 2.0 if severity_ratio >= 3.0 else 1.0
            
            return True, f"Candle spread volatility spike (current: {current_spread:.2f}%, median: {median_spread:.2f}%)", severity_multiplier
        
        return False, None, None
    except Exception as e:
        logger.warning(f"[CircuitBreaker] Error checking candle spread for {symbol}: {e}")
        return False, None, None


def check_funding_rate_spike(client, symbol: str) -> Tuple[bool, Optional[str]]:
    """
    Check if funding rate change > 0.1% in last hour
    
    Returns:
        (should_pause, reason): True if entry should be paused
    """
    try:
        # Get current funding rate
        funding_info = client.futures_funding_rate(symbol=symbol, limit=1)
        
        if not funding_info or len(funding_info) == 0:
            return False, None
        
        current_rate = float(funding_info[0].get('fundingRate', 0))
        
        # Get funding rate history (last 20 periods = ~80 minutes for 8h funding)
        history = client.futures_funding_rate(symbol=symbol, limit=20)
        
        if len(history) < 2:
            return False, None
        
        # Get rate from 1-2 periods ago (roughly 1 hour back)
        previous_rate = float(history[1].get('fundingRate', 0))
        
        # Calculate change
        rate_change = abs(current_rate - previous_rate) * 100  # Convert to percentage
        
        if rate_change > 0.1:
            return True, f"Funding rate spike detected (change: {rate_change:.2f}% in last hour)"
        
        return False, None
    except Exception as e:
        logger.warning(f"[CircuitBreaker] Error checking funding rate for {symbol}: {e}")
        return False, None


def check_maker_taker_spread(client, symbol: str, threshold_multiplier: float = 2.0) -> Tuple[bool, Optional[str]]:
    """
    Check if maker/taker spread has widened significantly
    
    Args:
        threshold_multiplier: How many times wider than average to trigger (default 2.0)
    
    Returns:
        (should_pause, reason): True if entry should be paused
    """
    try:
        # Get order book to calculate spread
        order_book = client.futures_order_book(symbol=symbol, limit=5)
        
        if not order_book or 'bids' not in order_book or 'asks' not in order_book:
            return False, None
        
        bids = order_book['bids']
        asks = order_book['asks']
        
        if len(bids) == 0 or len(asks) == 0:
            return False, None
        
        # Best bid and ask
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        
        # Calculate spread percentage
        mid_price = (best_bid + best_ask) / 2
        spread_pct = ((best_ask - best_bid) / mid_price) * 100 if mid_price > 0 else 0
        
        # For now, use a simple threshold (can be enhanced with historical average)
        # Typical spread for BTC/BNB is ~0.01-0.05%, so 0.15%+ is considered wide
        if spread_pct > 0.25:
            return True, f"Spread widening detected (spread: {spread_pct:.3f}%)"
        
        return False, None
    except Exception as e:
        logger.warning(f"[CircuitBreaker] Error checking spread for {symbol}: {e}")
        return False, None


def check_circuit_breaker(client, symbol: str, pause_duration: int = DEFAULT_PAUSE_DURATION) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Comprehensive circuit breaker check - pauses new entries if any condition is met
    Uses adaptive pause duration based on severity (shorter for minor spikes)
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        pause_duration: Base pause duration in seconds (default 10 minutes, adjusted by severity)
    
    Returns:
        (should_pause, reason, pause_until_timestamp): 
            - True if entry should be paused
            - Reason string if paused
            - Timestamp until when paused (None if not paused)
    """
    # Check if already paused
    if symbol in _circuit_breaker_active_until:
        pause_until = _circuit_breaker_active_until[symbol]
        if time.time() < pause_until:
            remaining = int(pause_until - time.time())
            reason = _circuit_breaker_state.get(symbol, {}).get('reason', 'Circuit breaker active')
            return True, reason, pause_until
    
    # Check all circuit breaker conditions (candle spread now returns severity)
    candle_result = check_candle_spread_volatility(client, symbol)
    funding_result = check_funding_rate_spike(client, symbol)
    spread_result = check_maker_taker_spread(client, symbol)
    
    checks = [
        candle_result,
        (funding_result[0], funding_result[1], 2.0) if funding_result[0] else (False, None, None),  # Funding spikes are severe
        (spread_result[0], spread_result[1], 1.0) if spread_result[0] else (False, None, None),  # Spread widening is minor
    ]
    
    for check_result in checks:
        should_pause = check_result[0]
        reason = check_result[1] if len(check_result) > 1 else None
        severity_multiplier = check_result[2] if len(check_result) > 2 else 1.0
        
        if should_pause and reason:
            # Adaptive pause duration: minor spikes = 5 min, extreme = 10 min
            adaptive_duration = int(pause_duration * severity_multiplier)
            if severity_multiplier <= 1.0:
                adaptive_duration = min(adaptive_duration, 300)  # Cap at 5 minutes for minor
            
            # Activate circuit breaker
            pause_until = time.time() + adaptive_duration
            _circuit_breaker_active_until[symbol] = pause_until
            _circuit_breaker_state[symbol] = {
                'reason': reason,
                'activated_at': time.time(),
                'pause_until': pause_until
            }
            
            logger.warning(f"[CircuitBreaker] {symbol}: Entry paused for {adaptive_duration//60} minutes - {reason}")
            return True, reason, pause_until
    
    return False, None, None


def is_entry_paused(symbol: str) -> bool:
    """Check if entry is currently paused for a symbol"""
    if symbol not in _circuit_breaker_active_until:
        return False
    
    pause_until = _circuit_breaker_active_until[symbol]
    if time.time() >= pause_until:
        # Pause expired, clean up
        del _circuit_breaker_active_until[symbol]
        if symbol in _circuit_breaker_state:
            del _circuit_breaker_state[symbol]
        return False
    
    return True


def get_circuit_breaker_status(symbol: str) -> Optional[Dict]:
    """Get current circuit breaker status for a symbol"""
    if symbol not in _circuit_breaker_active_until:
        return None
    
    pause_until = _circuit_breaker_active_until[symbol]
    if time.time() >= pause_until:
        # Expired, clean up
        del _circuit_breaker_active_until[symbol]
        if symbol in _circuit_breaker_state:
            del _circuit_breaker_state[symbol]
        return None
    
    state = _circuit_breaker_state.get(symbol, {})
    remaining = int(pause_until - time.time())
    return {
        'active': True,
        'reason': state.get('reason', 'Circuit breaker active'),
        'remaining_seconds': remaining,
        'pause_until': pause_until
    }

