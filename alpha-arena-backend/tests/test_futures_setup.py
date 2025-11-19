#!/usr/bin/env python3
"""
Quick verification script for Binance Futures Testnet setup
Tests connection, authentication, and basic functionality
"""

import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

def test_futures_setup():
    """Test Binance Futures Testnet configuration"""
    
    print("\n" + "="*80)
    print("🧪 BINANCE FUTURES TESTNET SETUP VERIFICATION")
    print("="*80 + "\n")
    
    # Check environment variables
    print("📋 Environment Configuration:")
    binance_mode = os.getenv("BINANCE_MODE", "not_set")
    account_types = os.getenv("BINANCE_ACCOUNT_TYPES", "not_set")
    futures_key = os.getenv("BINANCE_USDM_TESTNET_KEY", "not_set")
    futures_secret = os.getenv("BINANCE_USDM_TESTNET_SECRET", "not_set")
    mode = os.getenv("MODE", "not_set")
    
    print(f"   BINANCE_MODE: {binance_mode}")
    print(f"   BINANCE_ACCOUNT_TYPES: {account_types}")
    print(f"   BINANCE_USDM_TESTNET_KEY: {futures_key[:15]}..." if len(futures_key) > 15 else f"   BINANCE_USDM_TESTNET_KEY: {futures_key}")
    print(f"   MODE: {mode}")
    
    # Validate configuration
    issues = []
    if binance_mode != "testnet":
        issues.append("⚠️  BINANCE_MODE should be 'testnet'")
    if account_types != "usdm":
        issues.append("⚠️  BINANCE_ACCOUNT_TYPES should be 'usdm'")
    if futures_key == "not_set" or len(futures_key) < 20:
        issues.append("⚠️  BINANCE_USDM_TESTNET_KEY not configured")
    if futures_secret == "not_set" or len(futures_secret) < 20:
        issues.append("⚠️  BINANCE_USDM_TESTNET_SECRET not configured")
    
    if issues:
        print("\n❌ Configuration Issues Found:")
        for issue in issues:
            print(f"   {issue}")
        print("\n💡 Please update your .env file with correct Futures API keys")
        print("   Get keys from: https://testnet.binancefuture.com\n")
        return False
    
    print("   ✅ Configuration looks good!\n")
    
    # Test connection
    print("🔌 Testing Binance Futures Connection...")
    try:
        from core.binance_client import get_client_manager, test_futures_connection
        
        # Initialize manager
        manager = get_client_manager()
        
        # Create Futures client
        print("   Initializing Futures client...")
        futures_client = manager.create_futures_client()
        
        if not futures_client:
            print("   ❌ Failed to initialize Futures client")
            return False
        
        print("   ✅ Futures client initialized\n")
        
        # Run smoke test
        print("🧪 Running Connection Smoke Test...")
        success = test_futures_connection(futures_client)
        
        if success:
            print("\n" + "="*80)
            print("✅ FUTURES TESTNET SETUP COMPLETE!")
            print("="*80)
            print("\n🚀 You're ready to trade!")
            print("\nNext steps:")
            print("   1. Run: python main.py")
            print("   2. Monitor: tail -f logs/trading.log")
            print("   3. Check positions on: https://testnet.binancefuture.com\n")
            return True
        else:
            print("\n❌ Connection test failed")
            print("   Please check your API keys and try again\n")
            return False
            
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        print("   Make sure all dependencies are installed: pip install -r requirements.txt\n")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = test_futures_setup()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
