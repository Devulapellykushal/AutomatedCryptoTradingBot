"""
Comprehensive CSV Logging System with Buffering
Stores all trading decisions, errors, trades, and learning data in CSV files.
Buffered writes for optimal performance (flushed every 5-10 cycles).
"""

import csv
import os
import time
import logging
from typing import Dict, Any, Optional, List
from collections import deque

logger = logging.getLogger(__name__)

# CSV File Paths
CSV_DIR = "logs"
DECISIONS_LOG = os.path.join(CSV_DIR, "decisions_log.csv")
TRADES_LOG = os.path.join(CSV_DIR, "trades_log.csv")
ERRORS_LOG = os.path.join(CSV_DIR, "errors_log.csv")
LEARNING_LOG = os.path.join(CSV_DIR, "learning_log.csv")

# In-memory buffers (flushed every N cycles)
_decisions_buffer: deque = deque(maxlen=1000)
_trades_buffer: deque = deque(maxlen=1000)
_errors_buffer: deque = deque(maxlen=1000)
_learning_buffer: deque = deque(maxlen=1000)

# Flush counter
_flush_counter = 0
_FLUSH_INTERVAL = 7  # Flush every 7 cycles (between 5-10)


def ensure_csv_dir():
    """Ensure CSV directory exists"""
    os.makedirs(CSV_DIR, exist_ok=True)


def _append_to_csv(file_path: str, header: List[str], row: List[Any], buffer: deque):
    """Append row to buffer (will be flushed to CSV later)"""
    buffer.append(row)


def flush_all_csvs():
    """Flush all buffers to CSV files (called every 5-10 cycles)"""
    global _flush_counter
    _flush_counter += 1
    
    if _flush_counter < _FLUSH_INTERVAL:
        return  # Not time to flush yet
    
    _flush_counter = 0  # Reset counter
    
    try:
        ensure_csv_dir()
        
        # Flush decisions
        if _decisions_buffer:
            _flush_buffer(DECISIONS_LOG, _decisions_buffer, _get_decisions_header())
            _decisions_buffer.clear()
        
        # Flush trades
        if _trades_buffer:
            _flush_buffer(TRADES_LOG, _trades_buffer, _get_trades_header())
            _trades_buffer.clear()
        
        # Flush errors
        if _errors_buffer:
            _flush_buffer(ERRORS_LOG, _errors_buffer, _get_errors_header())
            _errors_buffer.clear()
        
        # Flush learning
        if _learning_buffer:
            _flush_buffer(LEARNING_LOG, _learning_buffer, _get_learning_header())
            _learning_buffer.clear()
            
        logger.debug(f"✅ Flushed all CSV buffers to disk")
    except Exception as e:
        logger.error(f"❌ Error flushing CSV buffers: {e}")


def _flush_buffer(file_path: str, buffer: deque, header: List[str]):
    """Write buffer to CSV file"""
    file_exists = os.path.exists(file_path)
    
    with open(file_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(header)
        
        for row in buffer:
            writer.writerow(row)


def _get_decisions_header() -> List[str]:
    """Get header for decisions log"""
    return [
        "timestamp", "agent_id", "symbol", "signal", "confidence", "reasoning",
        "status", "rejection_reason", "market_price", "atr", "volatility_regime",
        "volatility_ratio", "circuit_breaker_active", "circuit_breaker_reason",
        "position_size_calculated", "leverage", "risk_factors", "adjustments_applied",
        "min_confidence_required", "confidence_check_passed"
    ]


def _get_trades_header() -> List[str]:
    """Get header for trades log (enhanced)"""
    return [
        "time", "agent_id", "symbol", "side", "qty", "entry_price", "exit_price",
        "pnl", "pnl_pct", "status", "message", "order_id", "confidence", "reasoning",
        "leverage", "volatility_regime", "tp_percent", "sl_percent", "exit_reason",
        "price_action_exit", "market_conditions_exit", "strategy_used", "hold_duration_sec"
    ]


def _get_errors_header() -> List[str]:
    """Get header for errors log"""
    return [
        "timestamp", "component", "agent_id", "symbol", "error_type", "error_message",
        "context", "resolution", "retry_count", "order_id"
    ]


def _get_learning_header() -> List[str]:
    """Get header for learning log"""
    return [
        "timestamp", "agent_id", "symbol", "decision_signal", "decision_confidence",
        "decision_reasoning", "outcome_status", "outcome_pnl", "outcome_pnl_pct",
        "exit_reason", "strategy_used", "market_conditions_entry", "market_conditions_exit",
        "confidence_accuracy", "lesson_learned", "hold_duration_sec"
    ]


# ============================================================================
# DECISIONS LOGGING (All decisions: executed, rejected, skipped)
# ============================================================================

def log_decision(
    agent_id: str,
    symbol: str,
    signal: str,
    confidence: float,
    reasoning: str,
    status: str,  # "executed", "rejected", "skipped", "hold"
    rejection_reason: str = "",
    market_price: float = 0.0,
    atr: float = 0.0,
    volatility_regime: str = "",
    volatility_ratio: float = 0.0,
    circuit_breaker_active: bool = False,
    circuit_breaker_reason: str = "",
    position_size_calculated: float = 0.0,
    leverage: int = 1,
    risk_factors: str = "",
    adjustments_applied: str = "",
    min_confidence_required: float = 0.0,
    confidence_check_passed: bool = False
):
    """Log every decision (executed or rejected)"""
    row = [
        time.time(),
        agent_id,
        symbol,
        signal,
        f"{confidence:.4f}",
        reasoning[:500] if reasoning else "",  # Limit length
        status,
        rejection_reason[:200] if rejection_reason else "",
        f"{market_price:.4f}",
        f"{atr:.4f}",
        volatility_regime,
        f"{volatility_ratio:.4f}",
        "true" if circuit_breaker_active else "false",
        circuit_breaker_reason[:200] if circuit_breaker_reason else "",
        f"{position_size_calculated:.8f}",
        leverage,
        risk_factors[:200] if risk_factors else "",
        adjustments_applied[:200] if adjustments_applied else "",
        f"{min_confidence_required:.4f}",
        "true" if confidence_check_passed else "false"
    ]
    
    _append_to_csv(DECISIONS_LOG, _get_decisions_header(), row, _decisions_buffer)


# ============================================================================
# TRADES LOGGING (Enhanced with context)
# ============================================================================

def log_trade(
    agent_id: str,
    symbol: str,
    side: str,
    qty: float,
    entry_price: float,
    exit_price: float = 0.0,
    pnl: float = 0.0,
    pnl_pct: float = 0.0,
    status: str = "OPENED",
    message: str = "",
    order_id: str = "",
    confidence: float = 0.0,
    reasoning: str = "",
    leverage: int = 1,
    volatility_regime: str = "",
    tp_percent: float = 0.0,
    sl_percent: float = 0.0,
    exit_reason: str = "",
    price_action_exit: str = "",
    market_conditions_exit: str = "",
    strategy_used: str = "",
    hold_duration_sec: float = 0.0
):
    """Log trade with full context"""
    row = [
        time.time(),
        agent_id,
        symbol,
        side,
        f"{qty:.8f}",
        f"{entry_price:.4f}",
        f"{exit_price:.4f}" if exit_price > 0 else "",
        f"{pnl:.4f}" if pnl != 0.0 else "",
        f"{pnl_pct:.4f}" if pnl_pct != 0.0 else "",
        status,
        message[:200] if message else "",
        order_id,
        f"{confidence:.4f}" if confidence > 0 else "",
        reasoning[:500] if reasoning else "",
        leverage,
        volatility_regime,
        f"{tp_percent:.4f}" if tp_percent > 0 else "",
        f"{sl_percent:.4f}" if sl_percent > 0 else "",
        exit_reason,
        price_action_exit[:200] if price_action_exit else "",
        market_conditions_exit[:200] if market_conditions_exit else "",
        strategy_used,
        f"{hold_duration_sec:.2f}" if hold_duration_sec > 0 else ""
    ]
    
    _append_to_csv(TRADES_LOG, _get_trades_header(), row, _trades_buffer)


# ============================================================================
# ERRORS LOGGING (Structured error tracking)
# ============================================================================

def log_error(
    component: str,
    agent_id: str = "",
    symbol: str = "",
    error_type: str = "",
    error_message: str = "",
    context: str = "",
    resolution: str = "",
    retry_count: int = 0,
    order_id: str = ""
):
    """Log structured error information"""
    row = [
        time.time(),
        component,
        agent_id,
        symbol,
        error_type,
        error_message[:500] if error_message else "",
        context[:500] if context else "",
        resolution[:200] if resolution else "",
        retry_count,
        order_id
    ]
    
    _append_to_csv(ERRORS_LOG, _get_errors_header(), row, _errors_buffer)


# ============================================================================
# LEARNING LOGGING (Decision → Outcome mapping for ML)
# ============================================================================

def log_learning(
    agent_id: str,
    symbol: str,
    decision_signal: str,
    decision_confidence: float,
    decision_reasoning: str,
    outcome_status: str,  # "win", "loss", "breakeven", "pending"
    outcome_pnl: float = 0.0,
    outcome_pnl_pct: float = 0.0,
    exit_reason: str = "",
    strategy_used: str = "",
    market_conditions_entry: str = "",
    market_conditions_exit: str = "",
    confidence_accuracy: float = 0.0,
    lesson_learned: str = "",
    hold_duration_sec: float = 0.0
):
    """Log learning data (decision → outcome) for ML/learning system"""
    row = [
        time.time(),
        agent_id,
        symbol,
        decision_signal,
        f"{decision_confidence:.4f}",
        decision_reasoning[:500] if decision_reasoning else "",
        outcome_status,
        f"{outcome_pnl:.4f}" if outcome_pnl != 0.0 else "",
        f"{outcome_pnl_pct:.4f}" if outcome_pnl_pct != 0.0 else "",
        exit_reason,
        strategy_used,
        market_conditions_entry[:200] if market_conditions_entry else "",
        market_conditions_exit[:200] if market_conditions_exit else "",
        f"{confidence_accuracy:.4f}" if confidence_accuracy > 0 else "",
        lesson_learned[:500] if lesson_learned else "",
        f"{hold_duration_sec:.2f}" if hold_duration_sec > 0 else ""
    ]
    
    _append_to_csv(LEARNING_LOG, _get_learning_header(), row, _learning_buffer)


# ============================================================================
# FORCE FLUSH (for shutdown or critical moments)
# ============================================================================

def force_flush_all():
    """Force flush all buffers immediately (call on shutdown)"""
    global _flush_counter
    _flush_counter = _FLUSH_INTERVAL  # Trigger flush
    flush_all_csvs()

