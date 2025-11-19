"""
Sentinel Agent - Background monitoring for position health and PnL drift detection.
"""
import time
import logging
import threading
from typing import Dict, Any
from core.binance_client import get_futures_client
from core.order_manager import get_current_position

# Import Telegram notifier
try:
    from telegram_notifier import send_auto_notification as send_message
    TELEGRAM_ENABLED = True
except ImportError:
    def send_message(text: str) -> bool:
        return False
    TELEGRAM_ENABLED = False

logger = logging.getLogger("sentinel_agent")

# Global variables for sentinel agent
_sentinel_thread = None
_sentinel_running = False


# Global tracking for re-attach throttling (prevent too frequent attempts)
# ENHANCED: Per-cycle debounce (once every N cycles, not just time-based)
_last_reattach_attempt: Dict[str, float] = {}
_reattach_attempt_count: Dict[str, int] = {}  # Track attempt count per symbol
_reattach_cooldown = 60  # 60 seconds cooldown between re-attach attempts per symbol
_reattach_cycles_cooldown = 3  # Require N cycles between attempts (debounce)

def reattach_missing_tpsl(client, symbol: str, position: Dict[str, Any]) -> bool:
    """
    Attempt to reattach missing TP/SL orders for a position.
    Now includes throttling to prevent excessive re-attach attempts.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        position: Position information
        
    Returns:
        True if reattachment was successful, False otherwise
    """
    try:
        # ENHANCED THROTTLING: Dual-layer debounce (time + cycle count)
        now = time.time()
        
        # Check time-based cooldown
        if symbol in _last_reattach_attempt:
            time_since_last = now - _last_reattach_attempt[symbol]
            if time_since_last < _reattach_cooldown:
                logger.debug(f"[SentinelAgent] Re-attach cooldown active for {symbol} ({int(_reattach_cooldown - time_since_last)}s remaining)")
                return False
        
        # Check cycle-based debounce (prevent too many attempts in quick succession)
        if symbol in _reattach_attempt_count:
            attempt_count = _reattach_attempt_count[symbol]
            if attempt_count >= _reattach_cycles_cooldown:
                # Reset counter after cooldown period
                _reattach_attempt_count[symbol] = 0
            else:
                _reattach_attempt_count[symbol] = attempt_count + 1
                logger.debug(f"[SentinelAgent] Re-attach cycle debounce active for {symbol} ({attempt_count + 1}/{_reattach_cycles_cooldown} cycles)")
                return False
        else:
            _reattach_attempt_count[symbol] = 1
        
        position_amt = float(position.get("positionAmt", 0))
        entry_price = float(position.get("entryPrice", 0))
        
        if position_amt == 0:
            return False
            
        # Determine position side
        side = "BUY" if position_amt > 0 else "SELL"
        
        # LEVERAGE CONSISTENCY (Item #2): Retrieve stored leverage from position record
        # This ensures we use the same leverage as entry, preventing margin mismatches
        stored_leverage = None
        try:
            from core.storage import get_open_position
            stored_position = get_open_position(symbol, "system")  # Default agent_id
            if stored_position:
                stored_leverage = stored_position.get("leverage")
                if stored_leverage:
                    logger.debug(f"[SentinelAgent] Using stored leverage {stored_leverage}x for {symbol} (locked at entry)")
        except Exception as e:
            logger.warning(f"[SentinelAgent] Could not retrieve stored leverage for {symbol}: {e}")
        
        # Use stored leverage if available, otherwise default to 2x
        leverage = stored_leverage if stored_leverage else 2
        
        # Calculate TP/SL prices based on current configuration
        from core.settings import settings
        tp_pct = settings.take_profit_percent / 100
        sl_pct = settings.stop_loss_percent / 100
        
        # Calculate trigger prices
        from core.order_manager import calculate_tp_sl_triggers
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(
            is_long=(side == "BUY"),
            entry=entry_price,
            tp_pct=tp_pct,
            sl_pct=sl_pct
        )
        
        # Place TP/SL orders (will check for existing orders internally)
        # LEVERAGE CONSISTENCY: Pass stored leverage to maintain consistency
        from core.order_manager import place_take_profit_and_stop_loss
        tp_order_id, sl_order_id = place_take_profit_and_stop_loss(
            client=client,
            symbol=symbol,
            side=side,
            qty=abs(position_amt),
            tp_price=tp_trigger,
            sl_price=sl_trigger,
            agent_id="sentinel_agent",
            leverage=leverage  # Use stored leverage from entry
        )
        
        # Update throttle timestamp
        _last_reattach_attempt[symbol] = now
        
        if tp_order_id and sl_order_id:
            logger.info(f"✅ [SentinelAgent] TP/SL successfully attached for {symbol}")
            return True
        elif tp_order_id or sl_order_id:
            logger.warning(f"[SentinelAgent] ⚠️ Partial reattach for {symbol} - TP: {bool(tp_order_id)}, SL: {bool(sl_order_id)}")
            return False
        else:
            logger.warning(f"[SentinelAgent] Failed to reattach TP/SL for {symbol}")
            return False
            
    except Exception as e:
        logger.error(f"[SentinelAgent] Error reattaching TP/SL for {symbol}: {e}")
        # Update throttle timestamp even on error to prevent spam
        _last_reattach_attempt[symbol] = time.time()
        return False

def check_position_health(client, symbol: str) -> Dict[str, Any]:
    """
    Check position health for a symbol.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        
    Returns:
        Dict with health check results
    """
    try:
        # Get current position
        position = get_current_position(symbol)
        if not position or float(position.get("positionAmt", 0)) == 0:
            return {"symbol": symbol, "status": "no_position"}
        
        position_amt = float(position.get("positionAmt", 0))
        entry_price = float(position.get("entryPrice", 0))
        
        # Get open orders for this symbol
        open_orders = client.futures_get_open_orders(symbol=symbol)
        
        # Check for TP and SL orders with closePosition=True or reduceOnly=True
        tp_orders = [o for o in open_orders if o['type'] == 'TAKE_PROFIT_MARKET' and (o.get('closePosition') or o.get('reduceOnly'))]
        sl_orders = [o for o in open_orders if o['type'] == 'STOP_MARKET' and (o.get('closePosition') or o.get('reduceOnly'))]
        
        has_tp = len(tp_orders) > 0
        has_sl = len(sl_orders) > 0
        
        # Attempt reattach if missing TP/SL
        reattached = False
        if not has_tp or not has_sl:
            logger.warning(f"[SentinelAgent] Missing TP/SL for {symbol} - attempting reattach")
            reattached = reattach_missing_tpsl(client, symbol, position)
            
            # Recheck orders after reattach attempt
            if reattached:
                open_orders = client.futures_get_open_orders(symbol=symbol)
                tp_orders = [o for o in open_orders if o['type'] == 'TAKE_PROFIT_MARKET' and (o.get('closePosition') or o.get('reduceOnly'))]
                sl_orders = [o for o in open_orders if o['type'] == 'STOP_MARKET' and (o.get('closePosition') or o.get('reduceOnly'))]
                has_tp = len(tp_orders) > 0
                has_sl = len(sl_orders) > 0
        
        # Log detailed information about found orders
        if has_tp and has_sl:
            logger.info(f"✅ TP/SL successfully attached for {symbol}")
        elif has_tp or has_sl:
            logger.warning(f"[SentinelAgent] Incomplete TP/SL for {symbol} - TP: {has_tp} ({len(tp_orders)}), SL: {has_sl} ({len(sl_orders)})")
        else:
            logger.warning(f"[SentinelAgent] Missing TP/SL for {symbol} - reattach failed")
        
        # Calculate PnL
        mark_price_data = client.futures_mark_price(symbol=symbol)
        mark_price = float(mark_price_data.get("markPrice", 0))
        
        if position_amt > 0:  # Long position
            pnl_pct = ((mark_price - entry_price) / entry_price) * 100
        else:  # Short position
            pnl_pct = ((entry_price - mark_price) / entry_price) * 100
        
        # Check for excessive drawdown (> 2%)
        has_excessive_drawdown = pnl_pct < -2.0
        
        return {
            "symbol": symbol,
            "status": "healthy" if (has_tp and has_sl and not has_excessive_drawdown) else "issues",
            "has_tp": has_tp,
            "has_sl": has_sl,
            "tp_orders_count": len(tp_orders),
            "sl_orders_count": len(sl_orders),
            "pnl_pct": pnl_pct,
            "has_excessive_drawdown": has_excessive_drawdown,
            "reattached": reattached
        }
    except Exception as e:
        logger.error(f"Error checking position health for {symbol}: {e}")
        return {"symbol": symbol, "status": "error", "error": str(e)}


def sentinel_loop(interval=300):  # 5 minutes
    """
    Sentinel agent loop that checks position health every 5 minutes.
    
    Args:
        interval: Check interval in seconds (default 300 = 5 minutes)
    """
    global _sentinel_running
    logger.info(f"🔄 [SentinelAgent] Started ({interval}s interval)")
    
    client = get_futures_client()
    if not client:
        logger.error("❌ [SentinelAgent] Binance Futures client not initialized")
        return
    
    # Symbols to monitor (should be configurable)
    symbols = ["BTCUSDT", "BNBUSDT"]
    
    while _sentinel_running:
        try:
            issues_found = []
            
            for symbol in symbols:
                health = check_position_health(client, symbol)
                
                if health.get("status") == "issues":
                    issue_details = []
                    if not health.get("has_tp"):
                        issue_details.append("Missing TP order")
                    if not health.get("has_sl"):
                        issue_details.append("Missing SL order")
                    if health.get("has_excessive_drawdown"):
                        issue_details.append(f"Excessive drawdown: {health.get('pnl_pct', 0):.2f}%")
                    
                    issues_found.append(f"{symbol}: {', '.join(issue_details)}")
                    
                    logger.warning(f"⚠️ [SentinelAgent] Issues found for {symbol}: {', '.join(issue_details)}")
                
                elif health.get("status") == "error":
                    logger.error(f"❌ [SentinelAgent] Error checking {symbol}: {health.get('error')}")
            
            # Send Telegram alert if issues found
            if issues_found and TELEGRAM_ENABLED:
                alert_msg = "⚠️ SENTINEL AGENT ALERT\nPosition health issues detected:\n" + "\n".join(issues_found)
                send_message(alert_msg)
            
            # Sleep for specified interval
            time.sleep(interval)
            
        except Exception as e:
            logger.error(f"❌ [SentinelAgent] Exception in loop: {e}")
            time.sleep(interval)  # Continue running even if there's an error


def start_sentinel_agent(interval=300):
    """
    Start the sentinel agent thread.
    
    Args:
        interval: Check interval in seconds (default 300 = 5 minutes)
    """
    global _sentinel_thread, _sentinel_running
    
    if '_sentinel_thread' in globals() and _sentinel_thread is not None and _sentinel_thread.is_alive():
        logger.info("🔄 [SentinelAgent] Thread already running")
        return _sentinel_thread
    
    _sentinel_running = True
    _sentinel_thread = threading.Thread(target=sentinel_loop, args=(interval,), daemon=True)
    _sentinel_thread.start()
    logger.info("✅ [SentinelAgent] Thread started successfully")
    return _sentinel_thread


def stop_sentinel_agent():
    """
    Stop the sentinel agent thread gracefully.
    """
    global _sentinel_running, _sentinel_thread
    
    if '_sentinel_thread' in globals() and _sentinel_thread is not None and _sentinel_thread.is_alive():
        _sentinel_running = False
        _sentinel_thread.join(timeout=5)  # Wait up to 5 seconds for thread to finish
        logger.info("🛑 [SentinelAgent] Thread stopped")
    else:
        logger.info("🔄 [SentinelAgent] Thread was not running")


if __name__ == "__main__":
    # Test the sentinel agent
    start_sentinel_agent(30)  # Run every 30 seconds for testing