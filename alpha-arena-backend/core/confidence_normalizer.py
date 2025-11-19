"""
Confidence Normalizer - Scales confidence by recent accuracy
Prevents over-confidence bias in flat markets

Implements confidence normalization based on:
- Recent accuracy (correct direction / total signals)
- Volatility regime (adjust confidence based on market conditions)
- Rolling performance window
"""

import logging
import time
from typing import Dict, Optional
from collections import deque

logger = logging.getLogger(__name__)

# Track recent decisions and outcomes per agent
_decision_history: Dict[str, deque] = {}  # {agent_id: deque of (signal, confidence, timestamp, outcome)}
_history_window = 20  # Last 20 decisions per agent


def normalize_confidence(
    agent_id: str,
    raw_confidence: float,
    symbol: str,
    volatility_regime: str = "NORMAL"
) -> float:
    """
    Normalize confidence based on recent accuracy and market conditions.
    
    Args:
        agent_id: Agent identifier
        raw_confidence: Raw confidence from LLM/strategy
        symbol: Trading symbol
        volatility_regime: Current volatility regime
    
    Returns:
        Normalized confidence (0.0 - 1.0)
    """
    # Initialize history if needed
    if agent_id not in _decision_history:
        _decision_history[agent_id] = deque(maxlen=_history_window)
    
    history = _decision_history[agent_id]
    
    # Calculate recent accuracy
    recent_accuracy = calculate_recent_accuracy(agent_id)
    
    # Base normalization factor
    if recent_accuracy > 0.6:  # Good performance
        accuracy_multiplier = 1.0  # Keep confidence as-is
    elif recent_accuracy > 0.4:  # Moderate performance
        accuracy_multiplier = 0.9  # Slight reduction
    else:  # Poor performance
        accuracy_multiplier = 0.7  # Significant reduction
    
    # Volatility-based adjustment
    if volatility_regime == "EXTREME":
        volatility_multiplier = 0.85  # Reduce confidence in extreme vol
    elif volatility_regime == "HIGH":
        volatility_multiplier = 0.95
    elif volatility_regime == "LOW":
        volatility_multiplier = 1.05  # Slightly boost in low vol (more predictable)
    else:  # NORMAL
        volatility_multiplier = 1.0
    
    # Apply normalization
    normalized_conf = raw_confidence * accuracy_multiplier * volatility_multiplier
    
    # Clamp to reasonable range (0.3 - 0.95)
    normalized_conf = max(0.3, min(0.95, normalized_conf))
    
    # Prevent over-confidence in neutral markets
    # If confidence is very high (>0.9) but accuracy is low, reduce more
    if raw_confidence > 0.9 and recent_accuracy < 0.5:
        normalized_conf = raw_confidence * 0.75  # Significant reduction
    
    return normalized_conf


def record_decision(agent_id: str, signal: str, confidence: float):
    """Record a decision (before outcome is known)"""
    if agent_id not in _decision_history:
        _decision_history[agent_id] = deque(maxlen=_history_window)
    
    _decision_history[agent_id].append({
        "signal": signal,
        "confidence": confidence,
        "timestamp": time.time(),
        "outcome": None  # Will be updated later
    })


def record_outcome(agent_id: str, was_correct: bool):
    """
    Record outcome of most recent decision
    
    Args:
        agent_id: Agent identifier
        was_correct: True if decision was correct (direction matched price movement)
    """
    if agent_id not in _decision_history:
        return
    
    history = _decision_history[agent_id]
    if len(history) > 0:
        # Update most recent decision with outcome
        history[-1]["outcome"] = was_correct


def calculate_recent_accuracy(agent_id: str) -> float:
    """
    Calculate recent accuracy for an agent
    
    Returns:
        Accuracy ratio (0.0 - 1.0), 0.5 if no history (neutral)
    """
    if agent_id not in _decision_history:
        return 0.5  # Neutral if no history
    
    history = _decision_history[agent_id]
    
    # Filter to decisions with outcomes
    decisions_with_outcomes = [d for d in history if d.get("outcome") is not None]
    
    if len(decisions_with_outcomes) == 0:
        return 0.5  # Neutral if no outcomes yet
    
    # Calculate accuracy
    correct_count = sum(1 for d in decisions_with_outcomes if d["outcome"] is True)
    total_count = len(decisions_with_outcomes)
    
    accuracy = correct_count / total_count if total_count > 0 else 0.5
    
    return accuracy


def get_confidence_stats(agent_id: str) -> Dict[str, float]:
    """Get confidence statistics for an agent"""
    if agent_id not in _decision_history:
        return {"accuracy": 0.5, "avg_confidence": 0.7, "decision_count": 0}
    
    history = _decision_history[agent_id]
    decisions_with_outcomes = [d for d in history if d.get("outcome") is not None]
    
    if len(decisions_with_outcomes) == 0:
        return {"accuracy": 0.5, "avg_confidence": 0.7, "decision_count": 0}
    
    correct_count = sum(1 for d in decisions_with_outcomes if d["outcome"] is True)
    total_count = len(decisions_with_outcomes)
    avg_confidence = sum(d["confidence"] for d in history) / len(history) if history else 0.7
    
    return {
        "accuracy": correct_count / total_count if total_count > 0 else 0.5,
        "avg_confidence": avg_confidence,
        "decision_count": len(history)
    }

