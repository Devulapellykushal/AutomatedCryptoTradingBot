#!/usr/bin/env python3
"""
View Learning Analytics - Command line tool to view adaptive learning metrics
"""
import sys
import os
import json
import argparse
from datetime import datetime

# Add the parent directory to the path so we can import core modules
sys.path.append(os.path.join(os.path.dirname(__file__)))

from core.learning_memory import (
    load_learning_memory,
    analyze_strategy_performance,
    get_recent_performance
)
from core.strategy_analytics import (
    get_strategy_performance_summary,
    recommend_strategy_adjustments
)

def view_all_performance():
    """View all strategy performance data"""
    print("STRATEGY PERFORMANCE ANALYSIS")
    print("=" * 50)
    summary = get_strategy_performance_summary()
    print(summary)

def view_recent_trades(symbol=None, hours=24):
    """View recent trades"""
    print(f"RECENT TRADES (Last {hours} hours)")
    print("=" * 50)
    
    learning_data = load_learning_memory()
    
    if not learning_data:
        print("No trading data found in learning memory.")
        return
    
    # If symbol specified, only show that symbol
    if symbol:
        if symbol in learning_data:
            show_symbol_trades(symbol, learning_data[symbol], hours)
        else:
            print(f"No data found for symbol {symbol}")
        return
    
    # Show all symbols
    for sym, trades in learning_data.items():
        show_symbol_trades(sym, trades, hours)

def show_symbol_trades(symbol, trades, hours):
    """Show trades for a specific symbol"""
    print(f"\n{symbol}:")
    print("-" * 30)
    
    # Filter by time period
    cutoff_time = datetime.now().timestamp() - (hours * 3600)
    recent_trades = [trade for trade in trades if trade["timestamp"] > cutoff_time]
    
    if not recent_trades:
        print("  No recent trades")
        return
    
    for trade in recent_trades[-5:]:  # Show last 5 trades
        decision = trade.get("decision", {})
        outcome = trade.get("outcome", {})
        performance = trade.get("performance", {})
        
        timestamp = datetime.fromtimestamp(trade["timestamp"]).strftime("%Y-%m-%d %H:%M")
        
        print(f"  {timestamp} | {decision.get('signal', 'hold').upper()} | "
              f"{decision.get('strategy_used', 'unknown')} | "
              f"Conf: {decision.get('confidence', 0.0):.2f} | "
              f"PnL: ${outcome.get('pnl', 0.0):+.2f} ({outcome.get('pnl_pct', 0.0):+.2f}%)")

def view_recommendations():
    """View strategy recommendations"""
    print("STRATEGY RECOMMENDATIONS")
    print("=" * 50)
    
    recommendations = recommend_strategy_adjustments()
    
    if not recommendations:
        print("No recommendations at this time.")
        return
    
    for rec in recommendations:
        print(f"{rec['strategy']}: {rec['action']}")
        print(f"  Reason: {rec['reason']}")
        print(f"  Suggested adjustment: {rec['adjustment']}x")
        print()

def view_raw_data():
    """View raw learning data"""
    print("RAW LEARNING DATA")
    print("=" * 50)
    
    learning_data = load_learning_memory()
    
    if not learning_data:
        print("No learning data found.")
        return
    
    print(json.dumps(learning_data, indent=2))

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="View trading AI learning analytics")
    parser.add_argument("--all", action="store_true", help="View all performance data")
    parser.add_argument("--recent", action="store_true", help="View recent trades")
    parser.add_argument("--symbol", type=str, help="Filter by symbol (e.g., BTC/USDT)")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    parser.add_argument("--recommendations", action="store_true", help="View strategy recommendations")
    parser.add_argument("--raw", action="store_true", help="View raw learning data")
    
    args = parser.parse_args()
    
    # If no arguments provided, show help
    if not any([args.all, args.recent, args.recommendations, args.raw]):
        parser.print_help()
        return
    
    # Execute requested actions
    if args.all:
        view_all_performance()
        print()
        view_recommendations()
    
    if args.recent:
        view_recent_trades(args.symbol, args.hours)
    
    if args.recommendations:
        view_recommendations()
    
    if args.raw:
        view_raw_data()

if __name__ == "__main__":
    main()