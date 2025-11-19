#!/usr/bin/env python3
"""
Binance Futures Testnet Connection Test Script
Verifies API authentication and connection using python-binance library.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.binance_client import get_client_manager, test_binance_connection


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


def test_binance_futures_connection():
    """
    Test Binance Futures Testnet API connection and authentication using python-binance
    """
    
    print("\n🚀 BINANCE FUTURES TESTNET CONNECTION TEST")
    print("="*60)
    
    # Initialize client manager
    manager = get_client_manager()
    
    # Print connection info
    print_section("CONNECTION INFORMATION")
    info = manager.get_connection_info()
    print(f"Mode: {info['mode'].upper()}")
    print(f"REST URL: {info['rest_url']}")
    print(f"Futures Client: {'✅ Yes' if info['futures_client'] else '❌ No'}")
    print(f"Authenticated: {'✅ Yes' if info['authenticated'] else '❌ No'}")
    
    # Initialize clients
    print_section("INITIALIZING CLIENTS")
    results = manager.initialize_all_clients()
    
    for client_type, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        print(f"{client_type.capitalize()} Client: {status}")
    
    # Test connections
    print_section("TESTING CONNECTIONS")
    
    # Test Futures
    if results.get('futures'):
        print("\n📈 Testing Futures Client...")
        futures_result = manager.test_connection()
        
        if futures_result['success']:
            print(f"✅ Futures connection successful!")
            print(f"   Mode: {futures_result['mode'].upper()}")
            print(f"   BTC/USDT Price: ${futures_result.get('btc_price', 'N/A')}")
            
            if futures_result.get('balance_check'):
                usdt_balance = futures_result.get('usdt_balance', 0)
                print(f"   USDT Balance: {usdt_balance:.2f}")
        else:
            print(f"❌ Futures connection failed: {futures_result['error']}")
    
    # Summary
    print_section("SUMMARY")
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    if success_count == total_count:
        print(f"✅ All clients initialized successfully ({success_count}/{total_count})")
        print(f"\n🎉 System ready for trading!")
        
        if manager.is_testnet:
            print("\n⚠️  TESTNET MODE ACTIVE")
            print("   → No real money at risk")
            print("   → Safe for testing")
            print("   → Get testnet keys from: https://testnet.binancefuture.com")
        else:
            print("\n⚠️  MAINNET MODE ACTIVE")
            print("   → REAL MONEY AT RISK")
            print("   → Trade with caution!")
    else:
        print(f"⚠️  Some clients failed ({success_count}/{total_count} successful)")
        print(f"\n⚠️  Check logs for error details")
    
    # Run smoke test
    print_section("SMOKE TEST")
    print("\n🔍 Running detailed connection test...")
    smoke_test_passed = test_binance_connection()
    
    print("\n" + "="*60 + "\n")
    
    return success_count == total_count and smoke_test_passed


if __name__ == "__main__":
    try:
        success = test_binance_futures_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
