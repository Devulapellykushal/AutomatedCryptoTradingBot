"""
Outcome Feedback Module - Links trade outcomes back to decisions for learning
Implements Priority #6: Outcome feedback logging (append TP/SL/ROI to decision_log)

When trades close, updates the original decision log with outcome data.
"""

import csv
import os
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

DECISIONS_LOG = "logs/decisions_log.csv"
OUTCOMES_LOG = "logs/outcomes_feedback.csv"


def update_decision_with_outcome(
    symbol: str,
    entry_price: float,
    exit_price: float,
    exit_reason: str,  # "TAKE_PROFIT", "STOP_LOSS", "MANUAL"
    pnl: float,
    pnl_pct: float,
    agent_id: str = "system",
    timestamp_window: float = 3600  # Look back 1 hour for matching decision
) -> bool:
    """
    Update decision log with trade outcome (TP/SL/ROI).
    
    Args:
        symbol: Trading symbol
        entry_price: Entry price
        exit_price: Exit price
        exit_reason: Why trade closed
        pnl: Profit/Loss amount
        pnl_pct: Profit/Loss percentage
        agent_id: Agent ID
        timestamp_window: How far back to search for matching decision
    
    Returns:
        True if successfully updated
    """
    if not os.path.exists(DECISIONS_LOG):
        return False
    
    try:
        # Read all decisions
        decisions = []
        with open(DECISIONS_LOG, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            decisions = list(reader)
        
        # Find matching decision (same symbol, agent, executed status, within time window)
        current_time = time.time()
        best_match = None
        best_match_score = 0
        
        for decision in decisions:
            try:
                decision_time = float(decision.get("timestamp", 0))
                decision_symbol = decision.get("symbol", "")
                decision_agent = decision.get("agent_id", "")
                decision_status = decision.get("status", "")
                
                # Must be executed and within time window
                if (decision_status == "executed" and
                    decision_symbol.replace("/", "").upper() == symbol.replace("/", "").upper() and
                    decision_agent == agent_id and
                    (current_time - decision_time) <= timestamp_window):
                    
                    # Score based on time proximity (more recent = better match)
                    time_score = 1.0 / (1.0 + (current_time - decision_time) / 3600)
                    
                    if time_score > best_match_score:
                        best_match_score = time_score
                        best_match = decision
            except (ValueError, KeyError):
                continue
        
        if not best_match:
            logger.debug(f"No matching decision found for {symbol} @ {entry_price}")
            # Log outcome separately if no match found
            _log_standalone_outcome(symbol, entry_price, exit_price, exit_reason, pnl, pnl_pct, agent_id)
            return False
        
        # Update decision with outcome - append to outcomes log (append-only for audit trail)
        outcome_row = {
            "timestamp": current_time,
            "decision_timestamp": best_match.get("timestamp", ""),
            "agent_id": agent_id,
            "symbol": symbol,
            "entry_price": f"{entry_price:.4f}",
            "exit_price": f"{exit_price:.4f}",
            "exit_reason": exit_reason,
            "pnl": f"{pnl:.4f}",
            "pnl_pct": f"{pnl_pct:.4f}",
            "roi_pct": f"{pnl_pct:.4f}",
            "original_signal": best_match.get("signal", ""),
            "original_confidence": best_match.get("confidence", ""),
            "tp_sl_hit": exit_reason,
            "strategy_used": best_match.get("strategy_used", "")
        }
        
        # Append to outcomes feedback log
        os.makedirs("logs", exist_ok=True)
        file_exists = os.path.exists(OUTCOMES_LOG)
        outcome_header = [
            "timestamp", "decision_timestamp", "agent_id", "symbol",
            "entry_price", "exit_price", "exit_reason", "pnl", "pnl_pct", "roi_pct",
            "original_signal", "original_confidence", "tp_sl_hit", "strategy_used"
        ]
        
        with open(OUTCOMES_LOG, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=outcome_header)
            if not file_exists:
                writer.writeheader()
            writer.writerow(outcome_row)
        
        logger.info(f"✅ Outcome feedback logged: {symbol} {exit_reason} PnL={pnl:+.2f} ({pnl_pct:+.2f}%)")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update decision with outcome: {e}", exc_info=True)
        return False


def _log_standalone_outcome(
    symbol: str,
    entry_price: float,
    exit_price: float,
    exit_reason: str,
    pnl: float,
    pnl_pct: float,
    agent_id: str
):
    """Log outcome even if no matching decision found"""
    try:
        os.makedirs("logs", exist_ok=True)
        file_exists = os.path.exists(OUTCOMES_LOG)
        
        outcome_header = [
            "timestamp", "decision_timestamp", "agent_id", "symbol",
            "entry_price", "exit_price", "exit_reason", "pnl", "pnl_pct", "roi_pct",
            "original_signal", "original_confidence", "tp_sl_hit", "strategy_used"
        ]
        
        with open(OUTCOMES_LOG, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=outcome_header)
            if not file_exists:
                writer.writeheader()
            
            writer.writerow({
                "timestamp": time.time(),
                "decision_timestamp": "",
                "agent_id": agent_id,
                "symbol": symbol,
                "entry_price": f"{entry_price:.4f}",
                "exit_price": f"{exit_price:.4f}",
                "exit_reason": exit_reason,
                "pnl": f"{pnl:.4f}",
                "pnl_pct": f"{pnl_pct:.4f}",
                "roi_pct": f"{pnl_pct:.4f}",
                "original_signal": "",
                "original_confidence": "",
                "tp_sl_hit": exit_reason,
                "strategy_used": ""
            })
    except Exception as e:
        logger.warning(f"Failed to log standalone outcome: {e}")

