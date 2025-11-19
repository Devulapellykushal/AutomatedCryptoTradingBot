#!/usr/bin/env python3
"""
Comprehensive Import Check - Verifies all modules and dependencies
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 80)
print("🔍 COMPREHENSIVE IMPORT CHECK")
print("=" * 80)

checks_passed = 0
checks_failed = 0
failed_imports = []

def check_import(module_name, description):
    """Check if a module can be imported"""
    global checks_passed, checks_failed, failed_imports
    try:
        __import__(module_name)
        print(f"✅ {description}")
        checks_passed += 1
        return True
    except Exception as e:
        print(f"❌ {description}: {e}")
        checks_failed += 1
        failed_imports.append((module_name, str(e)))
        return False

print("\n📦 CORE MODULES:")
print("-" * 80)
check_import("core.orchestrator", "Orchestrator")
check_import("core.portfolio", "Portfolio")
check_import("core.trading_engine", "Trading Engine")
check_import("core.storage", "Storage")
check_import("core.settings", "Settings")
check_import("core.risk_engine", "Risk Engine")
check_import("core.order_manager", "Order Manager")
check_import("core.trade_manager", "Trade Manager")
check_import("core.sentinel_agent", "Sentinel Agent")
check_import("core.ai_agent", "AI Agent")
check_import("core.binance_client", "Binance Client")
check_import("core.data_engine", "Data Engine")
check_import("core.signal_engine", "Signal Engine")
check_import("core.coordinator_agent", "Coordinator Agent")

print("\n📊 NEW MODULES (Learning & Logging):")
print("-" * 80)
check_import("core.csv_logger", "CSV Logger")
check_import("core.learning_memory", "Learning Memory")
check_import("core.learning_bridge", "Learning Bridge")
check_import("core.regime_engine", "Regime Engine")
check_import("core.binance_error_handler", "Binance Error Handler")
check_import("core.market_analysis", "Market Analysis")
check_import("core.circuit_breaker", "Circuit Breaker")

print("\n🔗 IMPORT VERIFICATION:")
print("-" * 80)

# Check if learning_bridge is used in trade_manager
try:
    import core.trade_manager as tm
    if hasattr(tm, 'update_learning_from_csv_logs'):
        print("✅ trade_manager imports learning_bridge.update_learning_from_csv_logs")
        checks_passed += 1
    else:
        print("⚠️  trade_manager missing update_learning_from_csv_logs")
        checks_failed += 1
except Exception as e:
    print(f"❌ Failed to check trade_manager: {e}")
    checks_failed += 1

# Check if orchestrator uses csv_logger
try:
    import core.orchestrator as orch
    if hasattr(orch, 'csv_log_trade') or 'csv_logger' in str(orch.__dict__):
        print("✅ orchestrator uses csv_logger")
        checks_passed += 1
    else:
        print("⚠️  orchestrator may not be using csv_logger properly")
        checks_failed += 1
except Exception as e:
    print(f"❌ Failed to check orchestrator: {e}")
    checks_failed += 1

# Check if ai_agent uses learning_memory
try:
    import core.ai_agent as ai
    if 'get_recent_performance' in str(ai.__dict__) or 'learning_memory' in str(ai.__file__):
        print("✅ ai_agent uses learning_memory")
        checks_passed += 1
    else:
        print("⚠️  ai_agent may not be using learning_memory")
        checks_failed += 1
except Exception as e:
    print(f"❌ Failed to check ai_agent: {e}")
    checks_failed += 1

# Check if orchestrator caches decisions
try:
    with open('core/orchestrator.py', 'r') as f:
        content = f.read()
        if '_decision_cache' in content or 'learning_bridge' in content:
            print("✅ orchestrator integrates with learning_bridge cache")
            checks_passed += 1
        else:
            print("⚠️  orchestrator may not be caching decisions")
            checks_failed += 1
except Exception as e:
    print(f"❌ Failed to check orchestrator integration: {e}")
    checks_failed += 1

print("\n" + "=" * 80)
print("📊 SUMMARY:")
print("=" * 80)
print(f"✅ Passed: {checks_passed}")
print(f"❌ Failed: {checks_failed}")
print(f"📈 Success Rate: {checks_passed/(checks_passed+checks_failed)*100:.1f}%")

if failed_imports:
    print("\n⚠️  FAILED IMPORTS:")
    for module, error in failed_imports:
        print(f"   {module}: {error}")

if checks_failed == 0:
    print("\n🎉 ALL CHECKS PASSED! Everything is properly integrated.")
    sys.exit(0)
else:
    print(f"\n⚠️  {checks_failed} check(s) failed. Please review.")
    sys.exit(1)

