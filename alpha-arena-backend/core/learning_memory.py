"""
Learning Memory Module - Tracks trading performance and enables adaptive learning
"""
import json
import os
import time
from typing import Dict, Any, List
from datetime import datetime, timedelta

LEARNING_LOG = "db/learning_memory.json"

def load_learning_memory() -> Dict[str, Any]:
    """Load learning memory from file"""
    if not os.path.exists(LEARNING_LOG):
        return {}
    try:
        with open(LEARNING_LOG, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_learning_memory(data: Dict[str, Any]) -> bool:
    """Save learning memory to file"""
    try:
        os.makedirs(os.path.dirname(LEARNING_LOG), exist_ok=True)
        with open(LEARNING_LOG, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False

def update_learning_memory(symbol: str, decision: Dict[str, Any], outcome: Dict[str, Any]) -> bool:
    """
    Update learning memory with trade decision and outcome
    
    Args:
        symbol: Trading pair symbol
        decision: Decision dictionary from AI agent
        outcome: Trade outcome with performance metrics
    
    Returns:
        bool: Success status
    """
    try:
        learning_data = load_learning_memory()
        
        # Create entry
        entry = {
            "timestamp": time.time(),
            "decision": decision,
            "outcome": outcome,
            "performance": calculate_performance(decision, outcome)
        }
        
        # Add to symbol history
        if symbol not in learning_data:
            learning_data[symbol] = []
        
        learning_data[symbol].append(entry)
        
        # Keep only last 1000 entries per symbol to prevent file bloat
        if len(learning_data[symbol]) > 1000:
            learning_data[symbol] = learning_data[symbol][-1000:]
        
        return save_learning_memory(learning_data)
    except Exception:
        return False

def calculate_performance(decision: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculate performance metrics for a trade
    
    Args:
        decision: Trading decision
        outcome: Trade outcome
    
    Returns:
        Dict with performance metrics
    """
    try:
        pnl = outcome.get("pnl", 0.0)
        pnl_pct = outcome.get("pnl_pct", 0.0)
        confidence = decision.get("confidence", 0.5)
        
        # Calculate confidence accuracy (how well confidence matched actual performance)
        confidence_accuracy = 1.0 - abs(confidence - (1.0 if pnl > 0 else 0.0))
        
        return {
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "confidence": confidence,
            "confidence_accuracy": confidence_accuracy,
            "timestamp": time.time()
        }
    except Exception:
        return {
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "confidence": 0.5,
            "confidence_accuracy": 0.0,
            "timestamp": time.time()
        }

def get_recent_performance(symbol: str, hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get recent performance data for a symbol
    
    Args:
        symbol: Trading pair symbol
        hours: Number of hours to look back
    
    Returns:
        List of recent performance entries
    """
    learning_data = load_learning_memory()
    if symbol not in learning_data:
        return []
    
    cutoff_time = time.time() - (hours * 3600)
    recent_data = [entry for entry in learning_data[symbol] if entry["timestamp"] > cutoff_time]
    
    return recent_data

def analyze_strategy_performance(hours: int = 168) -> Dict[str, Any]:
    """
    Analyze strategy performance across all symbols
    
    Args:
        hours: Number of hours to analyze (default 1 week)
    
    Returns:
        Dict with strategy performance statistics
    """
    learning_data = load_learning_memory()
    strategy_stats = {}
    
    cutoff_time = time.time() - (hours * 3600)
    
    # Collect data from all symbols
    all_trades = []
    for symbol, trades in learning_data.items():
        for trade in trades:
            if trade["timestamp"] > cutoff_time:
                all_trades.append(trade)
    
    # Analyze by strategy
    for trade in all_trades:
        decision = trade.get("decision", {})
        strategy = decision.get("strategy_used", "unknown")
        performance = trade.get("performance", {})
        
        if strategy not in strategy_stats:
            strategy_stats[strategy] = {
                "trades": 0,
                "wins": 0,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "avg_confidence": 0.0,
                "avg_confidence_accuracy": 0.0
            }
        
        strategy_stats[strategy]["trades"] += 1
        if performance.get("pnl", 0.0) > 0:
            strategy_stats[strategy]["wins"] += 1
        
        strategy_stats[strategy]["total_pnl"] += performance.get("pnl", 0.0)
        strategy_stats[strategy]["total_pnl_pct"] += performance.get("pnl_pct", 0.0)
        strategy_stats[strategy]["avg_confidence"] += performance.get("confidence", 0.0)
        strategy_stats[strategy]["avg_confidence_accuracy"] += performance.get("confidence_accuracy", 0.0)
    
    # Calculate averages
    for strategy, stats in strategy_stats.items():
        if stats["trades"] > 0:
            stats["win_rate"] = stats["wins"] / stats["trades"]
            stats["avg_pnl"] = stats["total_pnl"] / stats["trades"]
            stats["avg_pnl_pct"] = stats["total_pnl_pct"] / stats["trades"]
            stats["avg_confidence"] = stats["avg_confidence"] / stats["trades"]
            stats["avg_confidence_accuracy"] = stats["avg_confidence_accuracy"] / stats["trades"]
    
    return strategy_stats

def get_strategy_weights() -> Dict[str, float]:
    """
    Get adaptive strategy weights based on recent performance
    
    Returns:
        Dict mapping strategy names to weight multipliers
    """
    strategy_stats = analyze_strategy_performance()
    weights = {}
    
    # Base weights - all strategies start equal
    base_weight = 1.0
    
    for strategy, stats in strategy_stats.items():
        # Adjust weight based on win rate and average PnL
        win_rate = stats.get("win_rate", 0.0)
        avg_pnl = stats.get("avg_pnl", 0.0)
        
        # Weight formula: base + win_rate_bonus + pnl_bonus
        weight = base_weight + (win_rate * 0.5) + (avg_pnl * 0.1)
        
        # Ensure minimum weight of 0.1
        weights[strategy] = max(0.1, weight)
    
    return weights

def format_recent_performance(performance_data: List[Dict[str, Any]]) -> str:
    """
    Format recent performance data for LLM prompts
    
    Args:
        performance_data: List of performance entries
    
    Returns:
        Formatted string for prompt inclusion
    """
    if not performance_data:
        return "No recent performance data available."
    
    formatted = []
    for entry in performance_data[-5:]:  # Last 5 entries
        decision = entry.get("decision", {})
        performance = entry.get("performance", {})
        
        formatted.append(
            f"- {decision.get('signal', 'hold').upper()} {decision.get('strategy_used', 'unknown')} "
            f"(Conf: {decision.get('confidence', 0.0):.2f}) -> "
            f"PnL: ${performance.get('pnl', 0.0):+.2f} ({performance.get('pnl_pct', 0.0):+.2f}%)"
        )
    
    return "\n".join(formatted)