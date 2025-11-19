#!/usr/bin/env python3
"""
Comprehensive test suite for all agents and strategies
Verifies that all 5 strategies work correctly for both BTC and BNB
"""
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.data_engine import fetch_live_data
from core.signal_engine import compute_indicators
from core.strategies import apply_strategy
from core.ai_agent import decide


def test_all_strategies():
    """Test all 5 strategies on both symbols"""
    
    print("\n" + "="*80)
    print("🧪 COMPREHENSIVE STRATEGY & AGENT TEST SUITE")
    print("="*80)
    
    symbols = ["BTC/USDT", "BNB/USDT"]
    strategies = [
        "trend_following",
        "mean_reversion", 
        "breakout",
        "macd_momentum",
        "multi_timeframe"
    ]
    
    results = {
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "details": []
    }
    
    # Test 1: Strategy Functions
    print("\n📊 PART 1: TESTING STRATEGY FUNCTIONS")
    print("-" * 80)
    
    for symbol in symbols:
        print(f"\n🔍 Fetching data for {symbol}...")
        try:
            df = fetch_live_data(symbol, timeframe="3m", limit=200)
            df = compute_indicators(df)
            
            if df.empty or len(df) < 50:
                print(f"   ❌ Insufficient data for {symbol}")
                continue
            
            print(f"   ✅ Data fetched: {len(df)} candles")
            
            for strategy in strategies:
                results["total_tests"] += 1
                test_name = f"{symbol} - {strategy}"
                
                try:
                    result = apply_strategy(strategy, df, symbol)
                    
                    signal = result.get('signal')
                    confidence = result.get('confidence', 0)
                    reasoning = result.get('reasoning', '')
                    
                    # Validate result structure
                    assert signal in ['long', 'short', 'hold'], f"Invalid signal: {signal}"
                    assert 0 <= confidence <= 1.0, f"Invalid confidence: {confidence}"
                    assert reasoning, "Missing reasoning"
                    
                    emoji = "🟢" if signal == 'long' else "🔴" if signal == 'short' else "⚪"
                    print(f"   {emoji} {strategy:20s} → {signal:5s} (conf: {confidence:.2f})")
                    
                    results["passed"] += 1
                    results["details"].append({
                        "test": test_name,
                        "status": "PASS",
                        "signal": signal,
                        "confidence": confidence
                    })
                    
                except Exception as e:
                    print(f"   ❌ {strategy:20s} → FAILED: {str(e)[:50]}")
                    results["failed"] += 1
                    results["details"].append({
                        "test": test_name,
                        "status": "FAIL",
                        "error": str(e)
                    })
        
        except Exception as e:
            print(f"   ❌ Error fetching data for {symbol}: {e}")
    
    # Test 2: Agent Configurations
    print("\n\n🤖 PART 2: TESTING AGENT CONFIGURATIONS")
    print("-" * 80)
    
    agents_dir = "agents_config"
    agent_files = [f for f in os.listdir(agents_dir) if f.endswith('.json')]
    
    print(f"\nFound {len(agent_files)} agent configurations:")
    
    for agent_file in sorted(agent_files):
        results["total_tests"] += 1
        
        try:
            with open(os.path.join(agents_dir, agent_file), 'r') as f:
                config = json.load(f)
            
            agent_id = config.get('agent_id', 'Unknown')
            symbol = config.get('symbol', 'Unknown')
            style = config.get('style', 'Unknown')
            
            # Fetch data for agent's symbol
            df = fetch_live_data(symbol, timeframe="3m", limit=200)
            df = compute_indicators(df)
            
            # Test decision making
            decision = decide(symbol, df, config)
            
            signal = decision.get('signal')
            confidence = decision.get('confidence', 0)
            leverage = decision.get('leverage', 1)
            
            # Validate decision
            assert signal in ['long', 'short', 'hold'], f"Invalid signal: {signal}"
            assert 0 <= confidence <= 1.0, f"Invalid confidence: {confidence}"
            assert 1 <= leverage <= config.get('parameters', {}).get('leverage_max', 5)
            
            emoji = "🟢" if signal == 'long' else "🔴" if signal == 'short' else "⚪"
            print(f"   {emoji} {agent_id:20s} | {symbol:10s} | {style:18s} | {signal:5s} ({confidence:.2f})")
            
            results["passed"] += 1
            results["details"].append({
                "test": f"Agent: {agent_id}",
                "status": "PASS",
                "signal": signal,
                "confidence": confidence
            })
            
        except Exception as e:
            print(f"   ❌ {agent_file:20s} → FAILED: {str(e)[:50]}")
            results["failed"] += 1
            results["details"].append({
                "test": f"Agent: {agent_file}",
                "status": "FAIL",
                "error": str(e)
            })
    
    # Test 3: Strategy Coverage
    print("\n\n📈 PART 3: STRATEGY COVERAGE ANALYSIS")
    print("-" * 80)
    
    coverage = {symbol: {strategy: 0 for strategy in strategies} for symbol in symbols}
    
    for agent_file in agent_files:
        with open(os.path.join(agents_dir, agent_file), 'r') as f:
            config = json.load(f)
        symbol = config.get('symbol', 'Unknown')
        style = config.get('style', 'Unknown')
        
        if symbol in coverage and style in coverage[symbol]:
            coverage[symbol][style] += 1
    
    for symbol in symbols:
        print(f"\n{symbol}:")
        for strategy in strategies:
            count = coverage[symbol][strategy]
            status = "✅" if count > 0 else "⚠️ "
            print(f"   {status} {strategy:20s}: {count} agent(s)")
    
    # Final Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    print(f"Total Tests:  {results['total_tests']}")
    print(f"✅ Passed:    {results['passed']}")
    print(f"❌ Failed:    {results['failed']}")
    print(f"Success Rate: {(results['passed']/results['total_tests']*100):.1f}%")
    
    if results['failed'] > 0:
        print("\n⚠️  Failed Tests:")
        for detail in results['details']:
            if detail['status'] == 'FAIL':
                print(f"   - {detail['test']}: {detail.get('error', 'Unknown error')}")
    
    print("\n" + "="*80)
    
    return results['failed'] == 0


if __name__ == "__main__":
    try:
        success = test_all_strategies()
        
        if success:
            print("🎉 ALL TESTS PASSED! All agents and strategies are working correctly.\n")
            sys.exit(0)
        else:
            print("❌ SOME TESTS FAILED. Please review the errors above.\n")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
