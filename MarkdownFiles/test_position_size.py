#!/usr/bin/env python3
"""
Test script to verify the position_size calculation logic
"""

import sys
import os

# Add the core directory to the path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'alpha-arena-backend'))

# Change to the alpha-arena-backend directory to ensure imports work correctly
os.chdir(os.path.join(os.path.dirname(__file__), 'alpha-arena-backend'))

from core.risk_engine import position_size
from core.settings import settings

def test_position_size():
    """Test the position_size function with various inputs"""
    
    print("=== Position Size Calculation Test ===")
    print(f"MIN_MARGIN_PER_TRADE: ${settings.MIN_MARGIN_PER_TRADE}")
    print(f"MAX_MARGIN_PER_TRADE: ${settings.max_margin_per_trade}")
    print()
    
    # Test case 1: BTC trade
    print("Test Case 1: BTC Trade")
    equity = 5000.0  # $5000 account
    price = 70000.0  # $70,000 BTC price
    atr = 1000.0     # $1000 ATR
    risk_fraction = 0.1  # 10% risk
    leverage = 2
    symbol = "BTCUSDT"
    
    qty = position_size(equity, price, atr, risk_fraction, leverage, symbol)
    notional = qty * price
    margin = notional / leverage
    
    print(f"  Equity: ${equity}")
    print(f"  Price: ${price}")
    print(f"  ATR: ${atr}")
    print(f"  Risk Fraction: {risk_fraction}")
    print(f"  Leverage: {leverage}x")
    print(f"  Symbol: {symbol}")
    print(f"  Calculated Qty: {qty:.6f}")
    print(f"  Notional: ${notional:.2f}")
    print(f"  Margin: ${margin:.2f}")
    print()
    
    # Test case 2: BNB trade
    print("Test Case 2: BNB Trade")
    equity = 5000.0  # $5000 account
    price = 700.0    # $700 BNB price
    atr = 10.0       # $10 ATR
    risk_fraction = 0.1  # 10% risk
    leverage = 2
    symbol = "BNBUSDT"
    
    qty = position_size(equity, price, atr, risk_fraction, leverage, symbol)
    notional = qty * price
    margin = notional / leverage
    
    print(f"  Equity: ${equity}")
    print(f"  Price: ${price}")
    print(f"  ATR: ${atr}")
    print(f"  Risk Fraction: {risk_fraction}")
    print(f"  Leverage: {leverage}x")
    print(f"  Symbol: {symbol}")
    print(f"  Calculated Qty: {qty:.6f}")
    print(f"  Notional: ${notional:.2f}")
    print(f"  Margin: ${margin:.2f}")
    print()
    
    # Test case 3: Low equity scenario
    print("Test Case 3: Low Equity Scenario")
    equity = 1000.0  # $1000 account
    price = 700.0    # $700 BNB price
    atr = 10.0       # $10 ATR
    risk_fraction = 0.1  # 10% risk
    leverage = 2
    symbol = "BNBUSDT"
    
    qty = position_size(equity, price, atr, risk_fraction, leverage, symbol)
    notional = qty * price
    margin = notional / leverage
    
    print(f"  Equity: ${equity}")
    print(f"  Price: ${price}")
    print(f"  ATR: ${atr}")
    print(f"  Risk Fraction: {risk_fraction}")
    print(f"  Leverage: {leverage}x")
    print(f"  Symbol: {symbol}")
    print(f"  Calculated Qty: {qty:.6f}")
    print(f"  Notional: ${notional:.2f}")
    print(f"  Margin: ${margin:.2f}")
    print()

if __name__ == "__main__":
    test_position_size()