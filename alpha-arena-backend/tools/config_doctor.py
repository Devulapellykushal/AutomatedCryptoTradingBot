#!/usr/bin/env python3
"""
Config Doctor CLI Tool
Interactive configuration validator for the trading bot.
"""
import os
import sys
import argparse
from pathlib import Path
from core.settings import settings
from core.binance_client import make_binance_futures_client
from core.binance_guard import BinanceGuard


def check_environment_file():
    """Check if .env file exists and is readable."""
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file not found!")
        print("   Please create a .env file. You can copy from .env.example:")
        print("   cp .env.example .env")
        return False
    
    print("✅ .env file found")
    return True


def validate_settings():
    """Validate settings and print configuration summary."""
    try:
        print("\n📋 Configuration Summary:")
        print(f"   Binance Testnet: {settings.binance_testnet}")
        print(f"   Trading Symbols: {settings.symbols}")
        print(f"   Timeframe: {settings.timeframe}")
        print(f"   Starting Capital: ${settings.starting_capital:,.2f}")
        print(f"   Max Leverage: {settings.max_leverage}x")
        print(f"   Risk Fraction: {settings.risk_fraction*100:.1f}%")
        print(f"   Max Drawdown: {settings.max_drawdown*100:.1f}%")
        print(f"   Take Profit: {settings.take_profit_percent}%")
        print(f"   Stop Loss: {settings.stop_loss_percent}%")
        print(f"   Max Open Trades: {settings.max_open_trades}")
        print(f"   Max Daily Orders: {settings.max_daily_orders}")
        print(f"   Max Margin Per Trade: ${settings.max_margin_per_trade:,.2f}")
        print(f"   Risk Per Trade: {settings.risk_per_trade_percent}%")
        print(f"   Auto Scale Quantity: {settings.auto_scale_qty}")
        print(f"   Telegram Notifications: {settings.telegram_auto_notifications}")
        
        # Validate TP/SL relationship
        if settings.take_profit_percent <= settings.stop_loss_percent:
            print("❌ WARNING: Take profit should be greater than stop loss!")
            return False
            
        print("✅ Settings validation passed")
        return True
    except Exception as e:
        print(f"❌ Settings validation failed: {e}")
        return False


def test_binance_connection():
    """Test Binance API connection."""
    try:
        print("\n🔗 Testing Binance Connection...")
        client = make_binance_futures_client()
        if client is None:
            print("❌ Failed to create Binance client")
            return False
            
        # Test API permissions
        guard = BinanceGuard(client)
        if not guard.validate_api_permissions():
            print("❌ API key validation failed")
            return False
            
        print("✅ Binance connection successful")
        return True
    except Exception as e:
        print(f"❌ Binance connection test failed: {e}")
        return False


def check_symbols():
    """Check if symbols are valid and available."""
    try:
        print("\n🔍 Checking Symbols...")
        client = make_binance_futures_client()
        if client is None:
            print("❌ Cannot check symbols without Binance client")
            return False
            
        guard = BinanceGuard(client)
        symbols = settings.parsed_symbols
        allowed_symbols = settings.parsed_allowed_symbols
        
        print(f"   Configured symbols: {', '.join(symbols)}")
        print(f"   Allowed symbols: {', '.join(allowed_symbols)}")
        
        # Check each symbol
        all_valid = True
        for symbol in symbols:
            if symbol in allowed_symbols:
                if guard.validate_symbol_exists(symbol):
                    print(f"   ✅ {symbol} - Valid and available")
                else:
                    print(f"   ❌ {symbol} - Symbol not found on exchange")
                    all_valid = False
            else:
                print(f"   ❌ {symbol} - Not in allowed symbols list")
                all_valid = False
                
        return all_valid
    except Exception as e:
        print(f"❌ Symbol validation failed: {e}")
        return False


def interactive_config_check():
    """Run interactive configuration check."""
    print("🤖 Trading Bot Config Doctor")
    print("=" * 40)
    
    # Check environment file
    if not check_environment_file():
        return False
    
    # Validate settings
    if not validate_settings():
        return False
    
    # Test Binance connection
    if not test_binance_connection():
        return False
    
    # Check symbols
    if not check_symbols():
        return False
    
    print("\n🎉 All checks passed! Your configuration looks good.")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Trading Bot Config Doctor")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run configuration checks"
    )
    
    args = parser.parse_args()
    
    if args.check:
        success = interactive_config_check()
        sys.exit(0 if success else 1)
    else:
        # Default behavior - show help
        parser.print_help()


if __name__ == "__main__":
    main()