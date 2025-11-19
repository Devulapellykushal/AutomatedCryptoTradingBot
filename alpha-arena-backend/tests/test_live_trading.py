#!/usr/bin/env python3
"""
Test script for live Futures trading on Binance Testnet
Verifies order placement and execution
"""

import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.order_manager import (
    place_futures_order,
    close_position,
    get_current_position
)
from core.trading_engine import get_futures_balance, futures


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


def test_futures_connection():
    """Test Binance Futures testnet connection"""
    print("\n🧪 BINANCE FUTURES TESTNET - VERIFICATION TEST")
    print("="*60)
    
    # Check if futures client is available
    if not futures:
        print("❌ Futures client not initialized!")
        print("   Check your .env configuration:")
        print("   - BINANCE_TESTNET=true")
        print("   - BINANCE_API_KEY and BINANCE_SECRET_KEY set")
        return False
    
    print("✅ Futures client initialized")
    
    # Get account balance
    print_section("FUTURES ACCOUNT BALANCE")
    balance = get_futures_balance()
    
    if 'error' in balance:
        print(f"❌ Error fetching balance: {balance['error']}")
        return False
    
    print(f"✅ Balance retrieved successfully")
    print(f"   Free: {balance.get('free', 0):.2f} USDT")
    print(f"   Used: {balance.get('used', 0):.2f} USDT")
    print(f"   Total: {balance.get('total', 0):.2f} USDT")
    
    # Test with small order
    symbol = "BNB/USDT"
    test_qty = 0.1  # Small test order
    leverage = 2
    
    print_section(f"TEST ORDER: {test_qty} {symbol}")
    print(f"Symbol: {symbol}")
    print(f"Side: BUY (LONG)")
    print(f"Quantity: {test_qty}")
    print(f"Leverage: {leverage}x")
    print(f"Type: MARKET (reduce_only=False)")
    
    # Place test order
    print("\n📊 Placing test order...")
    order = place_futures_order(
        symbol=symbol,
        side='buy',
        amount=test_qty,
        leverage=leverage,
        reduce_only=False
    )
    
    if 'error' in order:
        print(f"❌ Order failed: {order['error']}")
        print("\nPossible issues:")
        print("   - Insufficient testnet balance")
        print("   - Invalid API permissions")
        print("   - Symbol not available on testnet")
        print("\n💡 Get testnet funds at: https://testnet.binancefuture.com")
        return False
    
    print(f"✅ Order executed successfully!")
    print(f"   Order ID: {order.get('order_id', 'N/A')}")
    print(f"   Price: ${order.get('price', 'N/A')}")
    print(f"   Filled: {order.get('qty', 'N/A')} {symbol.split('/')[0]}")
    print(f"   Status: {order.get('order_status', 'N/A')}")
    
    # Check position
    print_section("OPEN POSITION CHECK")
    position = get_current_position(symbol)
    
    if position:
        print(f"✅ Position found:")
        print(f"   Symbol: {position.get('symbol', 'N/A')}")
        print(f"   Side: {position.get('side', 'N/A')}")
        print(f"   Contracts: {position.get('contracts', 'N/A')}")
        print(f"   Entry Price: ${position.get('entryPrice', 'N/A')}")
        print(f"   Unrealized PnL: ${position.get('unrealizedPnl', 0):.2f}")
    else:
        print("⚠️  No open position (order may have been filled and auto-closed)")
    
    # Close the position
    print_section("CLOSING POSITION")
    print(f"Closing {test_qty} {symbol} (reduce_only=True)...")
    
    close_order = close_position(
        symbol=symbol,
        side='sell',  # sell to close long
        qty=test_qty
    )
    
    if close_order.get('status') in ['error', 'skipped']:
        print(f"⚠️  Close failed: {close_order.get('message')}")
    else:
        print(f"✅ Position closed successfully!")
        print(f"   Close Order ID: {close_order.get('order_id', 'N/A')}")
        print(f"   Close Price: ${close_order.get('price', 'N/A')}")
    
    # Final balance check
    print_section("FINAL BALANCE")
    final_balance = get_futures_balance()
    if 'error' not in final_balance:
        print(f"✅ Final balance: {final_balance.get('total', 0):.2f} USDT")
        
        # Calculate P&L
        initial_total = balance.get('total', 0)
        final_total = final_balance.get('total', 0)
        pnl = final_total - initial_total
        
        if abs(pnl) > 0.01:
            emoji = "💚" if pnl > 0 else "💔"
            print(f"{emoji} Test P&L: ${pnl:+.2f}")
    
    return True


def main():
    """Main test function"""
    try:
        success = test_futures_connection()
        
        print("\n" + "="*60)
        if success:
            print("🎉 LIVE FUTURES TRADING VERIFICATION: PASSED")
            print("="*60)
            print("\n✅ Your system is ready for live futures trading!")
            print("\n📋 Next steps:")
            print("   1. Set MODE=live in .env")
            print("   2. Run: python main.py")
            print("   3. Watch live orders at: https://testnet.binancefuture.com")
            print("\n⚠️  Remember: This is TESTNET - no real money")
        else:
            print("❌ LIVE FUTURES TRADING VERIFICATION: FAILED")
            print("="*60)
            print("\n🔧 Troubleshooting:")
            print("   1. Verify API keys in .env")
            print("   2. Ensure BINANCE_TESTNET=true")
            print("   3. Get testnet funds: https://testnet.binancefuture.com")
            print("   4. Check API permissions (Futures trading enabled)")
        print("="*60 + "\n")
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
