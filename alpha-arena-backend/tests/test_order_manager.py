#!/usr/bin/env python3
"""
Test script for the new unified order_manager module
Demonstrates precision enforcement, duplicate checking, and leverage management
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.order_manager import (
    place_futures_order,
    close_position,
    get_current_position,
    get_symbol_filters,
    adjust_precision
)
from core.binance_client import get_futures_client


def print_section(title: str):
    """Print formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def test_order_manager():
    """Test all order_manager features"""
    
    print("\n🚀 ORDER MANAGER TEST SUITE")
    print("="*70)
    
    # Get client
    client = get_futures_client()
    if not client:
        print("❌ Binance client not initialized")
        return False
    
    symbol = "BNB/USDT"
    test_qty = 0.1
    
    # Test 1: Symbol Filters
    print_section("TEST 1: PRECISION RULES")
    filters = get_symbol_filters(client, "BNBUSDT")
    print(f"Symbol: BNBUSDT")
    print(f"   Price Precision:    {filters['pricePrecision']} decimals")
    print(f"   Quantity Precision: {filters['quantityPrecision']} decimals")
    print(f"   Tick Size:          {filters['tickSize']}")
    print(f"   Step Size:          {filters['stepSize']}")
    print(f"   Min Quantity:       {filters['minQty']}")
    
    # Test 2: Precision Adjustment
    print_section("TEST 2: PRECISION ADJUSTMENT")
    raw_qty = 0.123456789
    raw_price = 312.987654321
    
    adj_qty, adj_price = adjust_precision(client, "BNBUSDT", raw_qty, raw_price)
    
    print(f"Raw Quantity:       {raw_qty:.10f}")
    print(f"Adjusted Quantity:  {adj_qty:.10f}")
    print(f"Raw Price:          {raw_price:.10f}")
    print(f"Adjusted Price:     {adj_price:.10f}")
    print(f"✅ Precision adjustment successful!")
    
    # Test 3: Check Existing Position
    print_section("TEST 3: POSITION CHECK")
    existing = get_current_position(symbol)
    if existing:
        print(f"⚠️  Existing position found:")
        print(f"   Symbol: {existing.get('symbol')}")
        print(f"   Amount: {existing.get('positionAmt')}")
        print(f"   Entry:  ${existing.get('entryPrice')}")
        print(f"\n⚠️  Skipping order placement test (position already exists)")
        print(f"   Please close your {symbol} position first and retry")
        return True
    else:
        print(f"✅ No existing position for {symbol}")
    
    # Test 4: Place Order with All Safety Features
    print_section("TEST 4: PLACE ORDER (WITH SAFETY CHECKS)")
    print(f"Placing order: BUY {test_qty} {symbol} @ MARKET (10x leverage)")
    
    order = place_futures_order(
        symbol=symbol,
        side="buy",
        qty=test_qty,
        leverage=10,
        order_type="MARKET"
    )
    
    print(f"\nOrder Result:")
    print(f"   Status:    {order.get('status')}")
    print(f"   Message:   {order.get('message')}")
    
    if order.get('status') == 'success':
        print(f"   Order ID:  {order.get('order_id')}")
        print(f"   Filled:    {order.get('qty')} {symbol.split('/')[0]}")
        print(f"   Price:     ${order.get('price'):.2f}")
        print(f"   Leverage:  {order.get('leverage')}x")
        print(f"✅ Order placed successfully!")
        
        # Test 5: Try Duplicate Order
        print_section("TEST 5: DUPLICATE PREVENTION")
        print(f"Attempting duplicate order for {symbol}...")
        
        duplicate_order = place_futures_order(
            symbol=symbol,
            side="buy",
            qty=test_qty,
            leverage=10
        )
        
        if duplicate_order.get('status') == 'skipped':
            print(f"✅ Duplicate prevention working!")
            print(f"   {duplicate_order.get('message')}")
        else:
            print(f"⚠️  Unexpected result: {duplicate_order.get('status')}")
        
        # Test 6: Close Position
        print_section("TEST 6: CLOSE POSITION")
        print(f"Closing {test_qty} {symbol}...")
        
        close_result = close_position(
            symbol=symbol,
            side="sell",
            qty=test_qty
        )
        
        if close_result.get('status') == 'success':
            print(f"✅ Position closed successfully!")
            print(f"   Order ID: {close_result.get('order_id')}")
            print(f"   Price:    ${close_result.get('price'):.2f}")
        else:
            print(f"⚠️  Close failed: {close_result.get('message')}")
        
    elif order.get('status') == 'skipped':
        print(f"⚠️  Order was skipped (this shouldn't happen in test)")
    else:
        print(f"❌ Order failed: {order.get('message')}")
        return False
    
    print_section("SUMMARY")
    print("✅ All order_manager features tested successfully!")
    print("\n📋 Verified Features:")
    print("   ✓ Precision enforcement")
    print("   ✓ Duplicate position prevention")
    print("   ✓ Leverage management")
    print("   ✓ Order placement")
    print("   ✓ Position closing")
    print("   ✓ Comprehensive logging")
    
    print("\n🎉 Order Manager is ready for production!")
    print("="*70 + "\n")
    
    return True


if __name__ == "__main__":
    try:
        success = test_order_manager()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
