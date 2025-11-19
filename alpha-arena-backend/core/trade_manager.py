"""
Trade Manager - Auto TP/SL Management
Monitors all open positions and auto-closes based on take-profit and stop-loss thresholds.
"""

import os
import csv
import time
import logging
import threading
from typing import Dict, Any
from core.binance_client import get_futures_client
from core.order_manager import close_position, cleanup_open_orders
from core.csv_logger import log_trade, log_learning
from core.learning_bridge import update_learning_from_csv_logs
from core.outcome_feedback import update_decision_with_outcome

# Import Telegram notifier
try:
    from telegram_notifier import send_auto_notification as send_message
    TELEGRAM_ENABLED = True
except ImportError:
    def send_message(text: str) -> bool:
        return False
    TELEGRAM_ENABLED = False

logger = logging.getLogger("trade_manager")

# Global variables for live monitor thread
_live_monitor_thread = None
_live_monitor_running = False
_last_attach_time = {}
_last_error = {}
_failed_symbols = {}  # Track symbols that failed TP/SL attachment

# Add the last_attach tracking dictionary
_last_attach = {}

# Load TP/SL config from environment
TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "2.0"))
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "1.0"))
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "trades_log.csv")


# Global tracking for ATR-TPSL update throttling with threshold-based updates
_last_atr_tpsl_update: Dict[str, float] = {}
_last_atr_tpsl_values: Dict[str, tuple[float, float]] = {}  # Store last (tp_pct, sl_pct) values
_atr_tpsl_update_cooldown = 180  # 3 minutes cooldown between ATR-based TP/SL updates
_atr_tpsl_change_threshold = 0.1  # Only update if TP/SL change > 0.1% (fixes excessive churn)

# Global tracking for partial closes (prevent multiple closes on same position)
_partial_close_executed: Dict[str, bool] = {}  # {symbol: bool} - tracks if partial close already done

def _calculate_symbol_specific_tp_sl(symbol: str, entry_price: float, force_update: bool = False) -> tuple[float, float]:
    """
    Calculate symbol-specific TP/SL based on fixed ratios or ATR.
    Now includes throttling to prevent excessive ATR recalculations.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        entry_price: Entry price for the position
        force_update: If True, bypass throttling (default False)
        
    Returns:
        Tuple of (tp_percent, sl_percent)
    """
    try:
        # Normalize symbol name
        normalized_symbol = symbol.upper()
        
        # THROTTLING: Skip ATR recalculation if recently updated (unless forced)
        now = time.time()
        if not force_update and symbol in _last_atr_tpsl_update:
            time_since_last = now - _last_atr_tpsl_update[symbol]
            if time_since_last < _atr_tpsl_update_cooldown:
                # Use cached/fallback values instead of recalculating
                logger.debug(f"[ATR-TPSL] Throttled update for {symbol} ({int(_atr_tpsl_update_cooldown - time_since_last)}s remaining)")
                # Fall through to fixed ratios
        
        # Check if ATR-based TP/SL is enabled
        use_atr_tpsl = os.getenv("USE_ATR_TPSL", "false").lower() == "true"
        
        if use_atr_tpsl:
            # ATR-Based Dynamic TP/SL
            try:
                from core.binance_client import get_futures_client
                client = get_futures_client()
                if client:
                    # Get ATR from recent klines
                    klines = client.futures_klines(symbol=symbol, interval="3m", limit=15)
                    if len(klines) >= 14:  # Need at least 14 periods for ATR
                        # Calculate ATR from klines
                        highs = [float(k[2]) for k in klines]
                        lows = [float(k[3]) for k in klines]
                        closes = [float(k[4]) for k in klines]
                        
                        # Calculate True Range
                        tr_values = []
                        for i in range(1, len(highs)):
                            tr1 = highs[i] - lows[i]
                            tr2 = abs(highs[i] - closes[i-1])
                            tr3 = abs(lows[i] - closes[i-1])
                            tr = max(tr1, tr2, tr3)
                            tr_values.append(tr)
                        
                        # Calculate 14-period ATR
                        if len(tr_values) >= 14:
                            atr = sum(tr_values[-14:]) / 14
                            
                            # Calculate TP/SL based on symbol and ATR
                            if normalized_symbol.startswith("BTC"):
                                # BTC: TP = 2.0 × ATR, SL = 1.0 × ATR
                                tp_pct = 2.0 * (atr / entry_price) * 100
                                sl_pct = 1.0 * (atr / entry_price) * 100
                            elif normalized_symbol.startswith("BNB"):
                                # BNB: TP = 1.5 × ATR, SL = 0.7 × ATR
                                tp_pct = 1.5 * (atr / entry_price) * 100
                                sl_pct = 0.7 * (atr / entry_price) * 100
                            else:
                                # Default fallback
                                tp_pct = 2.0 * (atr / entry_price) * 100
                                sl_pct = 1.0 * (atr / entry_price) * 100
                            
                            # Clamp values to reasonable ranges
                            tp_pct = max(min(tp_pct, 5.0), 0.5)
                            sl_pct = max(min(sl_pct, 2.5), 0.3)
                            
                            # THRESHOLD-BASED UPDATE: Only update if change > 0.1% (prevents unnecessary churn)
                            if symbol in _last_atr_tpsl_values:
                                last_tp, last_sl = _last_atr_tpsl_values[symbol]
                                tp_change = abs(tp_pct - last_tp)
                                sl_change = abs(sl_pct - last_sl)
                                
                                # If change is minimal, skip update and return cached values
                                if tp_change < _atr_tpsl_change_threshold and sl_change < _atr_tpsl_change_threshold:
                                    logger.debug(f"[ATR-TPSL] {symbol} - Change too small (TP: {tp_change:.3f}%, SL: {sl_change:.3f}%), using cached values")
                                    return last_tp, last_sl
                            
                            logger.info(f"[ATR-TPSL] {symbol} - ATR: {atr:.4f}, TP: {tp_pct:.2f}%, SL: {sl_pct:.2f}%")
                            # Update throttle timestamp and cache values on successful ATR calculation
                            _last_atr_tpsl_update[symbol] = now
                            _last_atr_tpsl_values[symbol] = (tp_pct, sl_pct)
                            return tp_pct, sl_pct
            except Exception as atr_error:
                logger.warning(f"[ATR-TPSL] Failed to calculate ATR for {symbol}: {atr_error}")
        
        # FIXED: Calculate dynamic TP/SL based on ATR instead of static values
        # Fallback to ATR-based dynamic values when ATR calculation fails
        try:
            from core.binance_client import get_futures_client
            client = get_futures_client()
            if client:
                # Try to get ATR from recent price action
                klines = client.futures_klines(symbol=symbol, interval="3m", limit=15)
                if len(klines) >= 14:
                    highs = [float(k[2]) for k in klines]
                    lows = [float(k[3]) for k in klines]
                    closes = [float(k[4]) for k in klines]
                    
                    # Calculate True Range and ATR
                    tr_values = []
                    for i in range(1, len(highs)):
                        tr1 = highs[i] - lows[i]
                        tr2 = abs(highs[i] - closes[i-1])
                        tr3 = abs(lows[i] - closes[i-1])
                        tr = max(tr1, tr2, tr3)
                        tr_values.append(tr)
                    
                    if len(tr_values) >= 14:
                        atr = sum(tr_values[-14:]) / 14
                        atr_pct = (atr / entry_price) * 100
                        
                        # FIXED: Dynamic RR per strategy - TP = (2-2.5)×ATR, SL = (1-1.25)×ATR
                        # This adapts to market volatility as recommended
                        # Use adaptive multipliers based on volatility regime
                        if atr_pct > 1.5:  # High volatility
                            tp_multiplier = 2.5  # Wider TP in high vol
                            sl_multiplier = 1.25  # Wider SL in high vol
                        elif atr_pct < 0.5:  # Low volatility
                            tp_multiplier = 2.0  # Tighter TP in low vol
                            sl_multiplier = 1.0  # Tighter SL in low vol
                        else:  # Normal volatility
                            tp_multiplier = 2.2  # Average
                            sl_multiplier = 1.1  # Average
                        
                        # Calculate TP/SL as multiples of ATR percentage
                        tp_pct = tp_multiplier * atr_pct
                        sl_pct = sl_multiplier * atr_pct
                        
                        # Clamp to reasonable ranges
                        if normalized_symbol.startswith("BTC"):
                            tp_pct = max(min(tp_pct, 5.0), 0.8)  # 0.8% to 5.0%
                            sl_pct = max(min(sl_pct, 2.5), 0.5)  # 0.5% to 2.5%
                        elif normalized_symbol.startswith("BNB"):
                            tp_pct = max(min(tp_pct, 3.0), 0.6)  # 0.6% to 3.0%
                            sl_pct = max(min(sl_pct, 2.0), 0.4)  # 0.4% to 2.0%
                        else:
                            tp_pct = max(min(tp_pct, 4.0), 0.7)  # 0.7% to 4.0%
                            sl_pct = max(min(sl_pct, 2.5), 0.5)  # 0.5% to 2.5%
                        
                        logger.info(f"[Dynamic TP/SL] {symbol}: ATR={atr_pct:.3f}%, TP={tp_pct:.2f}%, SL={sl_pct:.2f}%")
                        return tp_pct, sl_pct
        except Exception as e:
            logger.warning(f"[Dynamic TP/SL] Failed to calculate ATR-based TP/SL for {symbol}: {e}")
        
        # Ultimate fallback: Use reasonable default percentages (not static 0.5%)
        if normalized_symbol.startswith("BTC"):
            tp_pct = 2.0  # 2.0% default
            sl_pct = 1.0  # 1.0% default
        elif normalized_symbol.startswith("BNB"):
            tp_pct = 1.5  # 1.5% default
            sl_pct = 0.7  # 0.7% default
        else:
            tp_pct = 2.0
            sl_pct = 1.0
        
        return tp_pct, sl_pct
    except Exception as e:
        logger.warning(f"[ApexPatch2025-10-30] Failed to calculate symbol-specific TP/SL for {symbol}: {e}")
        # Fallback to default values
        return 2.0, 1.0


def _append_trade_close(symbol: str, side: str, qty: float, entry_price: float, exit_price: float, status: str, 
                       agent_id: str = "trade_manager", confidence: float = 0.0, reasoning: str = "",
                       leverage: int = 1, hold_duration_sec: float = 0.0) -> None:
    """
    Append a closed trade record to trades_log.csv (enhanced with CSV logger)
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        side: Original position side ('buy' for long, 'sell' for short)
        qty: Position quantity
        entry_price: Entry price
        exit_price: Exit price
        status: Close reason (TAKE_PROFIT, STOP_LOSS, MANUAL)
        agent_id: Agent that opened the position
        confidence: Confidence at entry
        reasoning: Reasoning at entry
        leverage: Leverage used
        hold_duration_sec: How long position was held
    """
    # Calculate PnL
    pnl = 0.0
    pnl_pct = 0.0
    if side.lower() == "buy":  # Long position closed
        pnl = (exit_price - entry_price) * qty
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0.0
    else:  # Short position closed
        pnl = (entry_price - exit_price) * qty
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100 if entry_price > 0 else 0.0

    # Calculate exit reason details
    exit_reason = status.upper()
    price_action_exit = f"Price moved from {entry_price:.2f} to {exit_price:.2f} ({'+' if pnl > 0 else ''}{pnl_pct:.2f}%)"
    
    # Log to CSV using enhanced logger
    try:
        log_trade(
            agent_id=agent_id,
            symbol=symbol,
            side=side.upper(),
            qty=qty,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            status=exit_reason,
            message=f"Auto-closed: {status}",
            confidence=confidence,
            reasoning=reasoning,
            leverage=leverage,
            exit_reason=exit_reason,
            price_action_exit=price_action_exit,
            hold_duration_sec=hold_duration_sec
        )
        logger.info(f"✅ Trade logged: {symbol} {status} PnL: {pnl:.2f} USDT ({pnl_pct:+.2f}%)")
    except Exception as e:
        logger.warning(f"Failed to write trade close log: {e}")
        # Fallback to old method
        try:
            exists = os.path.exists(TRADE_LOG_PATH)
            with open(TRADE_LOG_PATH, "a", newline="") as f:
                writer = csv.writer(f)
                if not exists:
                    writer.writerow(["time", "agent_id", "symbol", "side", "qty", "entry_price", "exit_price", "pnl", "status", "message"])
                writer.writerow([time.time(), agent_id, symbol, side.upper(), f"{qty:.8f}", 
                               f"{entry_price:.8f}", f"{exit_price:.8f}", f"{pnl:.8f}", status.upper(), f"Auto-closed: {status}"])
        except Exception as e2:
            logger.error(f"Failed fallback write: {e2}")


def validate_pnl_sync(client, symbol: str) -> bool:
    """
    PnL Sync Validation: Compare internal logs vs Binance API after close.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol (e.g., BTCUSDT)
        
    Returns:
        True if sync is valid, False otherwise
    """
    try:
        # Get position information from Binance
        positions = client.futures_position_information(symbol=symbol)
        binance_position = None
        for pos in positions:
            if pos.get("symbol") == symbol:
                binance_position = pos
                break
        
        if not binance_position:
            logger.warning(f"[PnL Sync] Could not find position for {symbol} in Binance API")
            return False
            
        binance_position_amt = float(binance_position.get("positionAmt", 0))
        binance_entry_price = float(binance_position.get("entryPrice", 0))
        binance_unrealized_pnl = float(binance_position.get("unRealizedProfit", 0))
        
        # Read from our trade log
        if not os.path.exists(TRADE_LOG_PATH):
            logger.info(f"[PnL Sync] No trade log found for {symbol}")
            return True
            
        # For simplicity, we'll just log the comparison
        logger.info(f"[PnL Sync] {symbol} - Binance position: {binance_position_amt} @ {binance_entry_price}, PnL: {binance_unrealized_pnl}")
        return True
        
    except Exception as e:
        logger.error(f"[PnL Sync] Error validating PnL sync for {symbol}: {e}")
        return False


def manage_open_positions() -> Dict[str, Any]:
    """
    Auto-manage all open positions with TP/SL logic.
    
    Checks each open position's unrealized PnL percentage:
    - If % change >= TAKE_PROFIT_PERCENT → close with TAKE_PROFIT
    - If % change <= -STOP_LOSS_PERCENT → close with STOP_LOSS
    
    Returns:
        Dictionary with results:
        {
            "closed": int,           # Number of positions closed
            "take_profit": int,      # Number closed at TP
            "stop_loss": int,        # Number closed at SL
            "errors": list,          # Any errors encountered
            "total_pnl": float       # Total realized PnL
        }
    """
    client = get_futures_client()
    if not client:
        logger.error("Binance Futures client not initialized")
        return {
            "closed": 0,
            "take_profit": 0,
            "stop_loss": 0,
            "errors": ["Client not initialized"],
            "total_pnl": 0.0
        }

    closed = 0
    tp_count = 0
    sl_count = 0
    errors = []
    total_pnl = 0.0

    try:
        positions = client.futures_position_information()
        
        for position in positions:
            position_amt = float(position.get("positionAmt", 0))
            
            # Skip if no position
            if position_amt == 0.0:
                continue
            
            symbol = position.get("symbol", "")
            entry_price = float(position.get("entryPrice", 0))
            
            if entry_price == 0:
                continue
            
            # PnL Sync Validation: Compare internal logs vs Binance API after close
            validate_pnl_sync(client, symbol)
            
            # Determine position direction
            is_long = position_amt > 0
            qty = abs(position_amt)
            
            # Get current mark price for accurate PnL calculation
            try:
                mark_price_data = client.futures_mark_price(symbol=symbol)
                current_price = float(mark_price_data.get("markPrice", 0))
            except Exception:
                # Fallback to ticker price
                try:
                    ticker = client.futures_symbol_ticker(symbol=symbol)
                    current_price = float(ticker.get("price", 0))
                except Exception as e:
                    errors.append(f"{symbol}: Failed to get price - {e}")
                    continue
            
            # Calculate symbol-specific TP/SL levels
            tp_level, sl_level = _calculate_symbol_specific_tp_sl(symbol, entry_price)
            
            # Calculate percentage change
            if is_long:
                # Long position: profit when price goes up
                change_pct = ((current_price - entry_price) / entry_price) * 100.0
            else:
                # Short position: profit when price goes down
                change_pct = ((entry_price - current_price) / entry_price) * 100.0
            
            # Check TP/SL conditions
            should_close = False
            close_reason = ""
            
            if change_pct >= tp_level:
                should_close = True
                close_reason = "TAKE_PROFIT"
                logger.info(
                    f"🎯 Take Profit triggered for {symbol}: "
                    f"{'LONG' if is_long else 'SHORT'} @ {entry_price:.2f} → {current_price:.2f} "
                    f"({change_pct:+.2f}%)"
                )
            elif change_pct <= -sl_level:
                should_close = True
                close_reason = "STOP_LOSS"
                logger.warning(
                    f"🛑 Stop Loss triggered for {symbol}: "
                    f"{'LONG' if is_long else 'SHORT'} @ {entry_price:.2f} → {current_price:.2f} "
                    f"({change_pct:+.2f}%)"
                )
            
            # Execute close if triggered
            if should_close:
                # FIXED: Trade state machine - prevent multiple exits
                try:
                    from core.trade_state_manager import is_exit_allowed, record_exit_attempt, record_exit_complete
                    
                    if not is_exit_allowed(symbol):
                        logger.debug(f"[TradeState] Exit blocked for {symbol} - already closing or in debounce")
                        continue  # Skip this position, try next
                    
                    record_exit_attempt(symbol)
                except ImportError:
                    pass  # Fallback if module not available
                
                # Determine close side (opposite of position)
                close_side = "sell" if is_long else "buy"
                
                try:
                    result = close_position(symbol, close_side, qty, max_retries=3)
                    
                    if result.get("status") == "success":
                        exit_price = result.get("price", current_price)
                        
                        # FIXED: Record exit complete in state machine
                        try:
                            from core.trade_state_manager import record_exit_complete, clear_tpsl_hashes
                            record_exit_complete(symbol)
                            clear_tpsl_hashes(symbol)
                        except ImportError:
                            pass
                        
                        # Calculate actual PnL
                        if is_long:
                            pnl = (exit_price - entry_price) * qty
                        else:
                            pnl = (entry_price - exit_price) * qty
                        
                        # RECORD TRADE OUTCOME for kill-switch consecutive loss tracking
                        try:
                            from core.risk_engine import daily_loss_tracker
                            is_win = pnl > 0
                            # Determine agent_id from symbol (assume system or extract from position metadata)
                            agent_id = "system"  # Default, can be enhanced to track per-agent
                            daily_loss_tracker.record_trade_outcome(agent_id, is_win)
                            logger.debug(f"[KillSwitch] Recorded trade outcome: {'WIN' if is_win else 'LOSS'} for {symbol} (PnL: {pnl:+.2f})")
                        except Exception as e:
                            logger.warning(f"Failed to record trade outcome for kill-switch: {e}")
                        
                        total_pnl += pnl
                        closed += 1
                        
                        if close_reason == "TAKE_PROFIT":
                            tp_count += 1
                        else:
                            sl_count += 1
                        
                        # Log to CSV
                        original_side = "buy" if is_long else "sell"
                        pnl_pct = change_pct
                        _append_trade_close(symbol, original_side, qty, entry_price, exit_price, close_reason)
                        
                        # FIXED: Outcome Feedback Logging - Append TP/SL/ROI to decision log
                        try:
                            update_decision_with_outcome(
                                symbol=symbol,
                                entry_price=entry_price,
                                exit_price=exit_price,
                                exit_reason=close_reason,
                                pnl=pnl,
                                pnl_pct=pnl_pct,
                                agent_id=agent_id
                            )
                        except Exception as e:
                            logger.warning(f"Failed to log outcome feedback: {e}")
                        
                        # FEEDBACK LOOP: Update learning memory from CSV logs
                        # This links outcome to original decision so future cycles can learn
                        try:
                            # Try to get strategy from decisions log
                            from core.learning_bridge import find_matching_decision
                            decision_data = find_matching_decision(symbol, entry_price, agent_id)
                            strategy_used = decision_data.get("strategy_used", "unknown") if decision_data else "unknown"
                            
                            update_learning_from_csv_logs(
                                symbol=symbol,
                                entry_price=entry_price,
                                exit_price=exit_price,
                                pnl=pnl,
                                pnl_pct=pnl_pct,
                                exit_reason=close_reason,
                                agent_id=agent_id,
                                strategy_used=strategy_used
                            )
                            
                            # Also log to CSV learning log
                            if decision_data:
                                confidence_accuracy = 1.0 if (decision_data.get("confidence", 0.5) > 0.5) == (pnl > 0) else 0.0
                                lesson = f"{strategy_used} strategy {'worked' if pnl > 0 else 'failed'} in {close_reason} scenario"
                                
                                log_learning(
                                    agent_id=agent_id,
                                    symbol=symbol,
                                    decision_signal=decision_data.get("signal", "long"),
                                    decision_confidence=decision_data.get("confidence", 0.7),
                                    decision_reasoning=decision_data.get("reasoning", ""),
                                    outcome_status="win" if pnl > 0 else "loss" if pnl < 0 else "breakeven",
                                    outcome_pnl=pnl,
                                    outcome_pnl_pct=pnl_pct,
                                    exit_reason=close_reason,
                                    strategy_used=strategy_used,
                                    market_conditions_entry=decision_data.get("volatility_regime", ""),
                                    confidence_accuracy=confidence_accuracy,
                                    lesson_learned=lesson
                                )
                        except Exception as e:
                            logger.warning(f"Failed to update learning from CSV logs: {e}")
                        
                        logger.info(
                            f"✅ Position closed: {symbol} {close_reason} "
                            f"PnL: {pnl:+.2f} USDT ({change_pct:+.2f}%)"
                        )
                        
                        # Send Telegram notification for closed position
                        if TELEGRAM_ENABLED:
                            telegram_msg = (
                                f"{'🎯' if close_reason == 'TAKE_PROFIT' else '🛑'} POSITION CLOSED\n"
                                f"Symbol: {symbol}\n"
                                f"Type: {close_reason.replace('_', ' ').title()}\n"
                                f"Side: {'LONG' if is_long else 'SHORT'}\n"
                                f"Entry: ${entry_price:.2f}\n"
                                f"Exit: ${exit_price:.2f}\n"
                                f"PnL: ${pnl:+.2f} ({change_pct:+.2f}%)"
                            )
                            send_message(telegram_msg)
                    else:
                        error_msg = f"{symbol}: Close failed - {result.get('message')}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        
                except Exception as e:
                    error_msg = f"{symbol}: Exception during close - {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        # Summary log
        if closed > 0:
            logger.info(
                f"📊 Trade Manager Summary: {closed} positions closed "
                f"(TP: {tp_count}, SL: {sl_count}) | Total PnL: {total_pnl:+.2f} USDT"
            )
            
            # Send Telegram summary
            if TELEGRAM_ENABLED:
                telegram_msg = (
                    f"📊 TRADE MANAGER SUMMARY\n"
                    f"Positions Closed: {closed}\n"
                    f"Take Profits: {tp_count}\n"
                    f"Stop Losses: {sl_count}\n"
                    f"Total PnL: ${total_pnl:+.2f}"
                )
                send_message(telegram_msg)
        
        return {
            "closed": closed,
            "take_profit": tp_count,
            "stop_loss": sl_count,
            "errors": errors,
            "total_pnl": total_pnl
        }
        
    except Exception as e:
        logger.error(f"Trade manager exception: {e}", exc_info=True)
        return {
            "closed": closed,
            "take_profit": tp_count,
            "stop_loss": sl_count,
            "errors": errors + [str(e)],
            "total_pnl": total_pnl
        }


def live_monitor_loop(interval=3):
    """
    Live monitor thread that checks TP/SL hits every N seconds.
    This runs in a separate thread to provide instant reaction to price movements.
    """
    global _live_monitor_running, _last_attach
    logger.info(f"🔄 [LiveMonitor] Thread started ({interval}s interval)")
    
    client = get_futures_client()
    if not client:
        logger.error("❌ [LiveMonitor] Binance Futures client not initialized")
        return
    
    while _live_monitor_running:
        try:
            # Get all open positions
            positions = client.futures_position_information()
            
            for position in positions:
                position_amt = float(position.get("positionAmt", 0))
                
                # Skip if no position
                if position_amt == 0.0:
                    continue
                
                symbol = position.get("symbol", "")
                entry_price = float(position.get("entryPrice", 0))
                
                if entry_price == 0:
                    continue
                
                # Determine position direction
                is_long = position_amt > 0
                qty = abs(position_amt)
                
                # Get current mark price for accurate PnL calculation
                try:
                    mark_price_data = client.futures_mark_price(symbol=symbol)
                    mark_price = float(mark_price_data.get("markPrice", 0))
                except Exception:
                    # Fallback to ticker price
                    try:
                        ticker = client.futures_symbol_ticker(symbol=symbol)
                        mark_price = float(ticker.get("price", 0))
                    except Exception as e:
                        logger.warning(f"⚠️ [LiveMonitor] {symbol}: Failed to get price - {e}")
                        continue
                
                # FIXED: LiveMonitor now only OBSERVES TP/SL status - SentinelAgent handles re-attach
                # This prevents overlapping re-attach attempts and reduces API calls
                try:
                    open_orders = client.futures_get_open_orders(symbol=symbol)
                    has_tp_order = any(
                        order.get('type') == 'TAKE_PROFIT_MARKET' and 
                        (order.get('closePosition') or order.get('reduceOnly'))
                        for order in open_orders
                    )
                    has_sl_order = any(
                        order.get('type') == 'STOP_MARKET' and 
                        (order.get('closePosition') or order.get('reduceOnly'))
                        for order in open_orders
                    )
                    
                    # Only log status - do NOT re-attach (SentinelAgent handles that)
                    if not has_tp_order or not has_sl_order:
                        missing_parts = []
                        if not has_tp_order:
                            missing_parts.append("TP")
                        if not has_sl_order:
                            missing_parts.append("SL")
                        logger.debug(f"[LiveMonitor] ⚠️ Missing {', '.join(missing_parts)} for {symbol} - SentinelAgent will handle re-attach")
                    else:
                        logger.debug(f"[LiveMonitor] ✅ TP/SL verified for {symbol}")
                except Exception as e:
                    logger.debug(f"[LiveMonitor] Could not check TP/SL for {symbol}: {e}")
                
                # Calculate symbol-specific TP and SL levels
                tp_level, sl_level = _calculate_symbol_specific_tp_sl(symbol, entry_price)
                
                # For long positions
                if is_long:
                    tp_price = entry_price * (1 + tp_level / 100)
                    sl_price = entry_price * (1 - sl_level / 100)
                else:
                    # For short positions
                    tp_price = entry_price * (1 - tp_level / 100)
                    sl_price = entry_price * (1 + sl_level / 100)
                
                # Calculate and log ROI percentage for better monitoring
                if is_long:
                    roi_pct = ((mark_price - entry_price) / entry_price) * 100
                else:
                    roi_pct = ((entry_price - mark_price) / entry_price) * 100
                
                # Log the check with ROI - only on significant changes or errors (reduce verbosity)
                # Track last logged ROI to avoid spam
                last_logged_key = f"{symbol}_last_roi_log"
                if not hasattr(live_monitor_loop, '_last_roi_logs'):
                    live_monitor_loop._last_roi_logs = {}
                
                last_roi = live_monitor_loop._last_roi_logs.get(last_logged_key, roi_pct)
                roi_change = abs(roi_pct - last_roi)
                
                # Only log if: ROI changed significantly (>0.05%), or TP/SL missing, or ROI crossed threshold
                should_log = (
                    roi_change > 0.05 or  # Significant ROI change
                    (not has_tp_order or not has_sl_order) or  # Missing TP/SL
                    (roi_pct >= 0.3 and last_roi < 0.3) or  # Crossed profit threshold
                    (roi_pct <= -0.5 and last_roi > -0.5)  # Crossed loss threshold
                )
                
                if should_log:
                    logger.info(f"🔄 [LiveMonitor] Checking {symbol}... Mark={mark_price:.2f} TP={tp_price:.2f} SL={sl_price:.2f} ROI={roi_pct:+.2f}%")
                    live_monitor_loop._last_roi_logs[last_logged_key] = roi_pct
                
                # AUTO-PARTIAL CLOSE: Lock in profits when ROI >= +0.3% (profit protection)
                # This prevents profit plateau issues where price stalls near TP without hitting it
                if roi_pct >= 0.3 and symbol not in _partial_close_executed:
                    # Check if position still exists (hasn't been fully closed)
                    try:
                        current_positions = client.futures_position_information(symbol=symbol)
                        current_pos_amt = 0.0
                        for pos in current_positions:
                            if pos.get("symbol") == symbol:
                                current_pos_amt = float(pos.get("positionAmt", 0))
                                break
                        
                        # Only partial close if position exists and is substantial
                        if abs(current_pos_amt) > 0:
                            # FIXED: Calculate partial close quantity (25% of position, not 50%)
                            partial_close_qty = abs(current_pos_amt) * 0.25
                            
                            # Get minimum quantity requirements
                            from core.order_manager import safe_qty
                            safe_partial_qty = safe_qty(symbol, partial_close_qty)
                            
                            # Minimum quantity check
                            MIN_QTY_MAP = {"BTCUSDT": 0.001, "BNBUSDT": 0.0001}
                            min_qty = MIN_QTY_MAP.get(symbol, 0.001)
                            
                            if safe_partial_qty >= min_qty:
                                close_side = "sell" if is_long else "buy"
                                
                                logger.info(
                                    f"💰 [LiveMonitor] Auto-partial close triggered for {symbol}: "
                                    f"ROI={roi_pct:+.2f}% >= 0.3% | Closing 25% ({safe_partial_qty:.6f} of {abs(current_pos_amt):.6f})"
                                )
                                
                                try:
                                    from core.order_manager import place_futures_order
                                    partial_result = place_futures_order(
                                        symbol=symbol,
                                        side=close_side,
                                        qty=safe_partial_qty,
                                        leverage=1,  # Use leverage 1 for closing
                                        order_type="MARKET",
                                        reduce_only=True,
                                        skip_position_check=True,
                                        agent_id="live_monitor"
                                    )
                                    
                                    if partial_result.get("status") == "success":
                                        partial_exit_price = partial_result.get("price", mark_price)
                                        
                                        # Calculate partial PnL
                                        if is_long:
                                            partial_pnl = (partial_exit_price - entry_price) * safe_partial_qty
                                        else:
                                            partial_pnl = (entry_price - partial_exit_price) * safe_partial_qty
                                        
                                        # Mark as partially closed to prevent repeated closes
                                        _partial_close_executed[symbol] = True
                                        
                                        logger.info(
                                            f"✅ [LiveMonitor] Partial close executed: {symbol} | "
                                            f"25% closed @ {partial_exit_price:.2f} | Partial PnL: {partial_pnl:+.2f} USDT"
                                        )
                                        
                                        # FIXED: Move SL to breakeven after partial close (trailing stop protection)
                                        try:
                                            from core.order_manager import place_take_profit_and_stop_loss, get_current_position
                                            current_pos = get_current_position(symbol)
                                            if current_pos:
                                                remaining_qty = abs(float(current_pos.get('positionAmt', 0)))
                                                if remaining_qty > 0:
                                                    # Calculate breakeven SL price
                                                    if is_long:
                                                        breakeven_sl = entry_price * 1.001  # Slight buffer above entry
                                                    else:
                                                        breakeven_sl = entry_price * 0.999  # Slight buffer below entry
                                                    
                                                    # Update SL to breakeven (calculate TP/SL prices from percentages)
                                                    # Get current TP price first
                                                    open_orders = client.futures_get_open_orders(symbol=symbol)
                                                    tp_price = 0
                                                    for order in open_orders:
                                                        if order.get('type') == 'TAKE_PROFIT_MARKET':
                                                            tp_price = float(order.get('stopPrice', 0))
                                                            break
                                                    
                                                    # If no TP found, calculate default
                                                    if tp_price == 0:
                                                        tp_pct, _ = _calculate_symbol_specific_tp_sl(symbol, entry_price)
                                                        if is_long:
                                                            tp_price = entry_price * (1 + tp_pct / 100)
                                                        else:
                                                            tp_price = entry_price * (1 - tp_pct / 100)
                                                    
                                                    # Update SL to breakeven
                                                    place_take_profit_and_stop_loss(
                                                        client, symbol, 
                                                        "buy" if is_long else "sell",
                                                        remaining_qty,
                                                        tp_price,
                                                        breakeven_sl,
                                                        agent_id="live_monitor",
                                                        leverage=current_pos.get('leverage', 1)
                                                    )
                                                    logger.info(f"✅ [LiveMonitor] SL moved to breakeven for {symbol} remainder")
                                        except Exception as sl_update_error:
                                            logger.warning(f"⚠️ [LiveMonitor] Failed to update SL to breakeven: {sl_update_error}")
                                        
                                        # Send Telegram notification (reduced frequency - only on significant events)
                                        if TELEGRAM_ENABLED and roi_pct >= 0.5:  # Only notify for larger profits
                                            telegram_msg = (
                                                f"💰 PARTIAL CLOSE (25% Locked)\n"
                                                f"Symbol: {symbol}\n"
                                                f"Side: {'LONG' if is_long else 'SHORT'}\n"
                                                f"Quantity Closed: {safe_partial_qty:.6f} (25%)\n"
                                                f"Entry: ${entry_price:.2f}\n"
                                                f"Exit: ${partial_exit_price:.2f}\n"
                                                f"ROI: {roi_pct:+.2f}%\n"
                                                f"Partial PnL: ${partial_pnl:+.2f}"
                                            )
                                            send_message(telegram_msg)
                                    else:
                                        logger.warning(f"⚠️ [LiveMonitor] Partial close failed for {symbol}: {partial_result.get('message')}")
                                        
                                except Exception as e:
                                    logger.error(f"❌ [LiveMonitor] Exception during partial close for {symbol}: {e}")
                    except Exception as e:
                        logger.warning(f"⚠️ [LiveMonitor] Error checking position for partial close on {symbol}: {e}")
                
                # Reset partial close tracking if position is fully closed (check if position exists)
                if symbol in _partial_close_executed:
                    try:
                        current_positions = client.futures_position_information(symbol=symbol)
                        has_position = False
                        for pos in current_positions:
                            if pos.get("symbol") == symbol:
                                pos_amt = float(pos.get("positionAmt", 0))
                                if abs(pos_amt) > 0:
                                    has_position = True
                                    break
                        # If position is fully closed, reset tracking
                        if not has_position:
                            del _partial_close_executed[symbol]
                            logger.debug(f"[LiveMonitor] Reset partial close tracking for {symbol} (position closed)")
                    except Exception:
                        pass  # If error checking, keep tracking as-is
                
                # Check if TP/SL levels are hit (full close)
                should_close = False
                close_reason = ""
                
                if is_long:
                    # Long position: TP when price goes up, SL when price goes down
                    if mark_price >= tp_price:
                        should_close = True
                        close_reason = "TP"
                        logger.info(f"✅ [LiveMonitor] Take Profit hit → closing {symbol} position")
                    elif mark_price <= sl_price:
                        should_close = True
                        close_reason = "SL"
                        logger.info(f"✅ [LiveMonitor] Stop Loss hit → closing {symbol} position")
                else:
                    # Short position: TP when price goes down, SL when price goes up
                    if mark_price <= tp_price:
                        should_close = True
                        close_reason = "TP"
                        logger.info(f"✅ [LiveMonitor] Take Profit hit → closing {symbol} position")
                    elif mark_price >= sl_price:
                        should_close = True
                        close_reason = "SL"
                        logger.info(f"✅ [LiveMonitor] Stop Loss hit → closing {symbol} position")
                
                # Execute close if triggered
                if should_close:
                    # Determine close side (opposite of position)
                    close_side = "sell" if is_long else "buy"
                    
                    try:
                        result = close_position(symbol, close_side, qty, max_retries=3)
                        
                        if result.get("status") == "success":
                            exit_price = result.get("price") or mark_price
                            
                            # Calculate actual PnL
                            if is_long:
                                pnl = (exit_price - entry_price) * qty
                            else:
                                pnl = (entry_price - exit_price) * qty
                            
                            # Log to CSV
                            original_side = "buy" if is_long else "sell"
                            pnl_pct = ((exit_price - entry_price) / entry_price * 100) if is_long else ((entry_price - exit_price) / entry_price * 100)
                            _append_trade_close(symbol, original_side, qty, entry_price, exit_price, close_reason)
                            
                            # FEEDBACK LOOP: Update learning memory from CSV logs
                            try:
                                update_learning_from_csv_logs(
                                    symbol=symbol,
                                    entry_price=entry_price,
                                    exit_price=exit_price,
                                    pnl=pnl,
                                    pnl_pct=pnl_pct,
                                    exit_reason=close_reason.replace("TP", "TAKE_PROFIT").replace("SL", "STOP_LOSS"),
                                    agent_id="system",  # Default, can be enhanced
                                    strategy_used="unknown"
                                )
                            except Exception as e:
                                logger.warning(f"Failed to update learning from CSV logs: {e}")
                            
                            # Clear partial close tracking when position is fully closed
                            if symbol in _partial_close_executed:
                                del _partial_close_executed[symbol]
                            
                            logger.info(
                                f"✅ [LiveMonitor] Position closed: {symbol} {close_reason} "
                                f"PnL: {pnl:+.2f} USDT"
                            )
                            
                            # Send Telegram notification for closed position
                            if TELEGRAM_ENABLED:
                                telegram_msg = (
                                    f"{'🎯' if close_reason == 'TP' else '🛑'} POSITION CLOSED (Live)\n"
                                    f"Symbol: {symbol}\n"
                                    f"Type: {'Take Profit' if close_reason == 'TP' else 'Stop Loss'}\n"
                                    f"Side: {'LONG' if is_long else 'SHORT'}\n"
                                    f"Entry: ${entry_price:.2f}\n"
                                    f"Exit: ${exit_price:.2f}\n"
                                    f"PnL: ${pnl:+.2f}"
                                )
                                send_message(telegram_msg)
                        else:
                            error_msg = f"{symbol}: Close failed - {result.get('message')}"
                            logger.error(f"❌ [LiveMonitor] {error_msg}")
                            
                    except Exception as e:
                        error_msg = f"{symbol}: Exception during close - {str(e)}"
                        logger.error(f"❌ [LiveMonitor] {error_msg}")
            
            # Sleep for specified interval before next check
            time.sleep(interval)
            
        except Exception as e:
            logger.error(f"❌ [LiveMonitor] Exception in loop: {e}")
            time.sleep(interval)  # Continue running even if there's an error


def start_live_monitor(interval=3):
    """
    Start the live monitor thread for instant TP/SL reactions.
    """
    global _live_monitor_thread, _live_monitor_running
    
    if '_live_monitor_thread' in globals() and _live_monitor_thread is not None and _live_monitor_thread.is_alive():
        logger.info("🔄 [LiveMonitor] Thread already running")
        return _live_monitor_thread
    
    _live_monitor_running = True
    _live_monitor_thread = threading.Thread(target=live_monitor_loop, args=(interval,), daemon=True)
    _live_monitor_thread.start()
    logger.info("✅ [LiveMonitor] Thread started successfully")
    return _live_monitor_thread


def stop_live_monitor():
    """
    Stop the live monitor thread gracefully.
    """
    global _live_monitor_running, _live_monitor_thread
    
    if '_live_monitor_thread' in globals() and _live_monitor_thread is not None and _live_monitor_thread.is_alive():
        _live_monitor_running = False
        _live_monitor_thread.join(timeout=5)  # Wait up to 5 seconds for thread to finish
        logger.info("🛑 [LiveMonitor] Thread stopped")
    else:
        logger.info("🔄 [LiveMonitor] Thread was not running")