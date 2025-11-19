"""
Bootstrap startup self-check module.
Loads validated settings, initializes Binance client, runs guard checks,
and prints final effective configuration.
"""
import logging
import sys
from typing import Optional
from binance.client import Client
from core.settings import settings
from core.binance_client import make_binance_futures_client
from core.binance_guard import BinanceGuard

logger = logging.getLogger(__name__)


def initialize_binance_client() -> Optional[Client]:
    """
    Initialize Binance client with proper error handling.
    
    Returns:
        Binance Client instance or None if failed
    """
    try:
        client = make_binance_futures_client()
        if client is None:
            logger.error("❌ Failed to create Binance Futures client")
            return None
        logger.info("✅ Binance Futures client initialized successfully")
        return client
    except Exception as e:
        logger.error(f"❌ Error initializing Binance client: {e}")
        return None


def run_guard_checks(client: Client, symbols: list) -> bool:
    """
    Run guard checks for all symbols.
    
    Args:
        client: Binance client instance
        symbols: List of symbols to check
        
    Returns:
        True if all checks pass, False otherwise
    """
    guard = BinanceGuard(client)
    
    for symbol in symbols:
        symbol = symbol.replace("/", "").upper()  # Normalize symbol
        if not guard.run_all_checks(symbol, settings.max_leverage):
            logger.error(f"❌ Guard checks failed for {symbol}")
            return False
    
    logger.info("✅ All guard checks passed")
    return True


def print_effective_configuration():
    """Print final effective configuration."""
    print("\n" + "="*60)
    print("   TRADING BOT CONFIGURATION SUMMARY")
    print("="*60)
    print(f"Mode: {'TESTNET' if settings.binance_testnet else 'LIVE'}")
    print(f"Symbols: {settings.symbols}")
    print(f"Timeframe: {settings.timeframe}")
    print(f"Starting Capital: ${settings.starting_capital:,.2f}")
    print(f"Max Leverage: {settings.max_leverage}x")
    print(f"Risk Fraction: {settings.risk_fraction*100:.1f}%")
    print(f"Max Drawdown: {settings.max_drawdown*100:.1f}%")
    print(f"Take Profit: {settings.take_profit_percent}%")
    print(f"Stop Loss: {settings.stop_loss_percent}%")
    print(f"Max Open Trades: {settings.max_open_trades}")
    print(f"Max Daily Orders: {settings.max_daily_orders}")
    print(f"Max Margin Per Trade: ${settings.max_margin_per_trade:,.2f}")
    print(f"Risk Per Trade: {settings.risk_per_trade_percent}%")
    print(f"Auto Scale Quantity: {settings.auto_scale_qty}")
    print(f"Telegram Notifications: {settings.telegram_auto_notifications}")
    print("="*60 + "\n")


def bootstrap() -> Optional[Client]:
    """
    Bootstrap the trading system.
    
    Returns:
        Binance Client instance if successful, None otherwise
    """
    print("🚀 Starting Trading Bot Bootstrap Process...")
    
    # 1. Load validated settings
    try:
        settings.log_settings()
        print("✅ Settings loaded and validated")
    except Exception as e:
        logger.error(f"❌ Failed to load settings: {e}")
        print("❌ Bootstrap failed: Settings validation error")
        return None
    
    # 2. Initialize Binance client
    client = initialize_binance_client()
    if client is None:
        print("❌ Bootstrap failed: Binance client initialization failed")
        return None
    
    # 3. Run guard checks
    symbols = list(settings.parsed_symbols)
    if not run_guard_checks(client, symbols):
        print("❌ Bootstrap failed: Guard checks failed")
        return None
    
    # 4. Print final effective configuration
    print_effective_configuration()
    
    print("✅ Bootstrap completed successfully!")
    return client


def main():
    """Main entry point for bootstrap process."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    client = bootstrap()
    if client is None:
        sys.exit(1)
    
    # For testing purposes, we can return the client
    return client


if __name__ == "__main__":
    main()