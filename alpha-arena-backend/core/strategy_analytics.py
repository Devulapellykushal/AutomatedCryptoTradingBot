"""
Strategy Analytics Module - Analyzes strategy performance and provides adaptive weighting
"""
from typing import Dict, Any, List
from core.learning_memory import analyze_strategy_performance, get_strategy_weights

def get_adaptive_strategy_weights() -> Dict[str, float]:
    """
    Get adaptive strategy weights based on recent performance
    
    Returns:
        Dict mapping strategy names to weight multipliers
    """
    return get_strategy_weights()

def analyze_strategy_effectiveness() -> Dict[str, Any]:
    """
    Analyze the effectiveness of different strategies
    
    Returns:
        Dict with strategy performance statistics
    """
    return analyze_strategy_performance()

def recommend_strategy_adjustments() -> List[Dict[str, Any]]:
    """
    Recommend adjustments to strategy usage based on performance
    
    Returns:
        List of adjustment recommendations
    """
    strategy_stats = analyze_strategy_performance()
    recommendations = []
    
    for strategy, stats in strategy_stats.items():
        # Recommend reducing usage of poor performers
        if stats.get("win_rate", 0) < 0.4:
            recommendations.append({
                "strategy": strategy,
                "action": "reduce_usage",
                "reason": f"Low win rate: {stats.get('win_rate', 0):.2f}",
                "adjustment": 0.5
            })
        # Recommend increasing usage of top performers
        elif stats.get("win_rate", 0) > 0.6 and stats.get("avg_pnl", 0) > 0:
            recommendations.append({
                "strategy": strategy,
                "action": "increase_usage",
                "reason": f"High win rate: {stats.get('win_rate', 0):.2f} with positive PnL",
                "adjustment": 1.5
            })
    
    return recommendations

def get_strategy_performance_summary() -> str:
    """
    Get a formatted summary of strategy performance
    
    Returns:
        Formatted string summary
    """
    strategy_stats = analyze_strategy_performance()
    
    if not strategy_stats:
        return "No strategy performance data available."
    
    summary_lines = ["Strategy Performance Summary:"]
    summary_lines.append("=" * 50)
    
    for strategy, stats in strategy_stats.items():
        summary_lines.append(f"{strategy}:")
        summary_lines.append(f"  Trades: {stats.get('trades', 0)}")
        summary_lines.append(f"  Win Rate: {stats.get('win_rate', 0):.2f}")
        summary_lines.append(f"  Avg PnL: ${stats.get('avg_pnl', 0):+.2f}")
        summary_lines.append(f"  Avg PnL%: {stats.get('avg_pnl_pct', 0):+.2f}%")
        summary_lines.append(f"  Confidence Accuracy: {stats.get('avg_confidence_accuracy', 0):.2f}")
        summary_lines.append("")
    
    return "\n".join(summary_lines)