"""
Learning Bridge - Connects CSV logs to learning system for feedback loop
When trades close, retrieves original decision from CSV and updates learning_memory.json
so future cycles can use this data for better decisions.
"""

import csv
import os
import time
import logging
from typing import Dict, Any, Optional, List
from core.learning_memory import update_learning_memory, load_learning_memory
from core.csv_logger import LEARNING_LOG as CSV_LEARNING_LOG

logger = logging.getLogger(__name__)

DECISIONS_LOG = "logs/decisions_log.csv"
TRADES_LOG = "logs/trades_log.csv"

# Simple in-memory cache for recent decisions (key: symbol_agent_entry_price)
_decision_cache: Dict[str, Dict[str, Any]] = {}


def find_matching_decision(symbol: str, entry_price: float, agent_id: str, 
                          lookback_seconds: int = 3600) -> Optional[Dict[str, Any]]:
    """
    Find the matching decision from decisions_log.csv or cache for a trade that's closing.
    
    Args:
        symbol: Trading symbol
        entry_price: Entry price of the trade
        agent_id: Agent ID
        lookback_seconds: How far back to look (default 1 hour)
    
    Returns:
        Decision dict or None if not found
    """
    # First check in-memory cache (fastest)
    binance_symbol = symbol.replace("/", "").upper()
    cache_key = f"{binance_symbol}_{agent_id}_{entry_price:.2f}"
    if cache_key in _decision_cache:
        cached = _decision_cache[cache_key]
        # Check if still valid (within lookback window)
        if time.time() - cached.get("timestamp", 0) < lookback_seconds:
            return cached
    
    # Fallback to CSV lookup
    if not os.path.exists(DECISIONS_LOG):
        return None
    
    try:
        current_time = time.time()
        cutoff_time = current_time - lookback_seconds
        
        with open(DECISIONS_LOG, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            # Read all matching decisions (most recent first)
            matching_decisions = []
            for row in reader:
                try:
                    row_time = float(row.get("timestamp", 0))
                    if (row.get("symbol", "").replace("/", "").upper() == symbol.replace("/", "").upper() and
                        row.get("agent_id", "") == agent_id and
                        row.get("status", "") == "executed" and
                        row_time >= cutoff_time):
                        
                        matching_decisions.append({
                            "timestamp": row_time,
                            "signal": row.get("signal", ""),
                            "confidence": float(row.get("confidence", 0)),
                            "reasoning": row.get("reasoning", ""),
                            "strategy_used": "",  # Not in decisions log, will get from trades
                            "market_price": float(row.get("market_price", 0)),
                            "volatility_regime": row.get("volatility_regime", ""),
                            "leverage": int(row.get("leverage", 1))
                        })
                except (ValueError, KeyError):
                    continue
            
            # Return most recent matching decision
            if matching_decisions:
                # Sort by timestamp descending (most recent first)
                matching_decisions.sort(key=lambda x: x["timestamp"], reverse=True)
                return matching_decisions[0]
    
    except Exception as e:
        logger.warning(f"Error finding matching decision for {symbol}: {e}")
    
    return None


def update_learning_from_csv_logs(symbol: str, entry_price: float, exit_price: float,
                                   pnl: float, pnl_pct: float, exit_reason: str,
                                   agent_id: str = "system", strategy_used: str = "unknown") -> bool:
    """
    When a trade closes, update learning_memory.json using data from CSV logs.
    This creates the feedback loop: Decision → Outcome → Learning → Better Decisions
    
    Args:
        symbol: Trading symbol
        entry_price: Entry price
        exit_price: Exit price
        pnl: Profit/Loss amount
        pnl_pct: Profit/Loss percentage
        exit_reason: Why trade closed (TAKE_PROFIT, STOP_LOSS, etc.)
        agent_id: Agent ID
        strategy_used: Strategy used
    
    Returns:
        True if successfully updated learning memory
    """
    try:
        # Find the original decision from CSV logs
        decision_data = find_matching_decision(symbol, entry_price, agent_id)
        
        if not decision_data:
            # If no matching decision found, create a minimal decision from available data
            logger.debug(f"No matching decision found for {symbol} @ {entry_price}, creating minimal entry")
            decision_data = {
                "signal": "long" if exit_price > entry_price else "short",
                "confidence": 0.7,  # Default confidence
                "reasoning": f"Trade closed: {exit_reason}",
                "strategy_used": strategy_used
            }
        
        # Determine outcome status
        if pnl > 0:
            outcome_status = "win"
        elif pnl < 0:
            outcome_status = "loss"
        else:
            outcome_status = "breakeven"
        
        # Calculate confidence accuracy (how well confidence predicted outcome)
        predicted_win = decision_data.get("confidence", 0.5) > 0.5
        actual_win = pnl > 0
        confidence_accuracy = 1.0 if predicted_win == actual_win else 0.0
        
        # Prepare outcome dict
        outcome = {
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "outcome_status": outcome_status
        }
        
        # Prepare decision dict for learning memory
        decision = {
            "signal": decision_data.get("signal", "long"),
            "confidence": decision_data.get("confidence", 0.7),
            "reasoning": decision_data.get("reasoning", ""),
            "strategy_used": strategy_used or decision_data.get("strategy_used", "unknown")
        }
        
        # Update learning memory (this feeds into future AI decisions!)
        success = update_learning_memory(symbol, decision, outcome)
        
        if success:
            logger.info(f"✅ Learning updated: {symbol} {outcome_status.upper()} (PnL: {pnl:+.2f}) → Future decisions will use this")
        else:
            logger.warning(f"Failed to update learning memory for {symbol}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error updating learning from CSV logs for {symbol}: {e}", exc_info=True)
        return False


def sync_csv_to_learning(symbol: str, hours: int = 24) -> int:
    """
    Sync recent CSV learning logs to learning_memory.json.
    Useful for bulk sync or recovery.
    
    Args:
        symbol: Trading symbol
        hours: How many hours back to sync
    
    Returns:
        Number of entries synced
    """
    if not os.path.exists(CSV_LEARNING_LOG):
        return 0
    
    synced = 0
    cutoff_time = time.time() - (hours * 3600)
    
    try:
        with open(CSV_LEARNING_LOG, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    row_time = float(row.get("timestamp", 0))
                    if row_time < cutoff_time:
                        continue
                    
                    if row.get("symbol", "").replace("/", "").upper() != symbol.replace("/", "").upper():
                        continue
                    
                    # Extract data from CSV
                    decision = {
                        "signal": row.get("decision_signal", "hold"),
                        "confidence": float(row.get("decision_confidence", 0.5)),
                        "reasoning": row.get("decision_reasoning", ""),
                        "strategy_used": row.get("strategy_used", "unknown")
                    }
                    
                    outcome = {
                        "pnl": float(row.get("outcome_pnl", 0)),
                        "pnl_pct": float(row.get("outcome_pnl_pct", 0)),
                        "exit_reason": row.get("exit_reason", ""),
                        "outcome_status": row.get("outcome_status", "pending")
                    }
                    
                    # Update learning memory
                    if update_learning_memory(symbol, decision, outcome):
                        synced += 1
                        
                except (ValueError, KeyError) as e:
                    logger.debug(f"Skipping invalid CSV row: {e}")
                    continue
    
    except Exception as e:
        logger.error(f"Error syncing CSV to learning for {symbol}: {e}")
    
    return synced

