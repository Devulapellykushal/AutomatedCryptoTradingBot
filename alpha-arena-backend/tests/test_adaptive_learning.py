"""
Test script for adaptive learning capabilities
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core.learning_memory import (
    update_learning_memory, 
    get_recent_performance, 
    analyze_strategy_performance,
    get_strategy_weights
)
from core.strategy_analytics import (
    get_adaptive_strategy_weights,
    analyze_strategy_effectiveness,
    recommend_strategy_adjustments,
    get_strategy_performance_summary
)

def simulate_trading_data():
    """Simulate some trading data for testing"""
    # Simulate some trades for different symbols and strategies
    sample_trades = [
        {
            "symbol": "BTC/USDT",
            "decision": {
                "signal": "long",
                "confidence": 0.85,
                "strategy_used": "trend_following",
                "reasoning": "Strong uptrend confirmed"
            },
            "outcome": {
                "pnl": 120.50,
                "pnl_pct": 2.45,
                "entry_price": 45000,
                "exit_price": 46100
            }
        },
        {
            "symbol": "BTC/USDT",
            "decision": {
                "signal": "short",
                "confidence": 0.75,
                "strategy_used": "mean_reversion",
                "reasoning": "RSI overbought, expecting pullback"
            },
            "outcome": {
                "pnl": -75.25,
                "pnl_pct": -1.65,
                "entry_price": 46200,
                "exit_price": 46500
            }
        },
        {
            "symbol": "ETH/USDT",
            "decision": {
                "signal": "long",
                "confidence": 0.90,
                "strategy_used": "breakout",
                "reasoning": "Breaking above resistance with high volume"
            },
            "outcome": {
                "pnl": 210.75,
                "pnl_pct": 3.85,
                "entry_price": 3200,
                "exit_price": 3325
            }
        },
        {
            "symbol": "BNB/USDT",
            "decision": {
                "signal": "short",
                "confidence": 0.65,
                "strategy_used": "macd_momentum",
                "reasoning": "MACD bearish crossover"
            },
            "outcome": {
                "pnl": -45.30,
                "pnl_pct": -0.95,
                "entry_price": 310,
                "exit_price": 315
            }
        }
    ]
    
    # Update learning memory with sample trades
    for trade in sample_trades:
        update_learning_memory(
            trade["symbol"], 
            trade["decision"], 
            trade["outcome"]
        )
    
    print("✓ Simulated trading data added to learning memory")

def test_learning_memory_functions():
    """Test the learning memory functions"""
    print("\n" + "="*60)
    print("TESTING LEARNING MEMORY FUNCTIONS")
    print("="*60)
    
    # Test getting recent performance
    btc_performance = get_recent_performance("BTC/USDT")
    print(f"\nBTC/USDT recent performance entries: {len(btc_performance)}")
    
    # Test strategy performance analysis
    strategy_performance = analyze_strategy_performance()
    print(f"\nStrategy performance analysis:")
    for strategy, stats in strategy_performance.items():
        print(f"  {strategy}: {stats.get('trades', 0)} trades, "
              f"Win Rate: {stats.get('win_rate', 0):.2f}, "
              f"Avg PnL: ${stats.get('avg_pnl', 0):.2f}")
    
    # Test strategy weights
    strategy_weights = get_strategy_weights()
    print(f"\nStrategy weights:")
    for strategy, weight in strategy_weights.items():
        print(f"  {strategy}: {weight:.2f}x")

def test_strategy_analytics():
    """Test the strategy analytics functions"""
    print("\n" + "="*60)
    print("TESTING STRATEGY ANALYTICS FUNCTIONS")
    print("="*60)
    
    # Test adaptive strategy weights
    adaptive_weights = get_adaptive_strategy_weights()
    print(f"\nAdaptive strategy weights:")
    for strategy, weight in adaptive_weights.items():
        print(f"  {strategy}: {weight:.2f}x")
    
    # Test strategy effectiveness analysis
    effectiveness = analyze_strategy_effectiveness()
    print(f"\nStrategy effectiveness analysis:")
    for strategy, stats in effectiveness.items():
        print(f"  {strategy}: {stats.get('trades', 0)} trades, "
              f"Win Rate: {stats.get('win_rate', 0):.2f}")
    
    # Test strategy recommendations
    recommendations = recommend_strategy_adjustments()
    print(f"\nStrategy adjustment recommendations:")
    if recommendations:
        for rec in recommendations:
            print(f"  {rec['strategy']}: {rec['action']} - {rec['reason']}")
    else:
        print("  No adjustments recommended")
    
    # Test performance summary
    summary = get_strategy_performance_summary()
    print(f"\nPerformance Summary:")
    print(summary)

def main():
    """Main test function"""
    print("Adaptive Learning System Test")
    print("="*60)
    
    # Simulate trading data
    simulate_trading_data()
    
    # Test learning memory functions
    test_learning_memory_functions()
    
    # Test strategy analytics
    test_strategy_analytics()
    
    print("\n" + "="*60)
    print("ADAPTIVE LEARNING TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()