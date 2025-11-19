#!/usr/bin/env python3
"""
Kushal Trading Bot - Main Entry Point
Orchestrates the complete trading system with multi-agent AI decision making
"""

import os
import sys
import time
import signal
import logging
import json
from typing import Dict
import importlib

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import core modules
from core.orchestrator import TradingOrchestrator
from core.portfolio import Portfolio
from core.trading_engine import close_all_positions
from core.storage import init_db, log_equity
from hackathon_config import CAPITAL, REFRESH_INTERVAL_SEC, load_symbols

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/trading_bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")

# Import Telegram notifier
try:
    from telegram_notifier import send_auto_notification as send_message, send_initial_message
    TELEGRAM_ENABLED = True
except ImportError:
    def send_message(text: str) -> bool:
        return False
    def send_initial_message() -> bool:
        return False
    TELEGRAM_ENABLED = False

# Graceful shutdown handler
def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n🚨 Shutdown signal received...")
    
    # Force flush all CSV buffers before shutdown
    try:
        from core.csv_logger import force_flush_all
        print("💾 Flushing CSV logs to disk...")
        force_flush_all()
        print("✅ CSV logs saved")
    except Exception as e:
        logger.warning(f"Error flushing CSV logs: {e}")
    
    # Stop the live monitor if it's running
    try:
        from core.trade_manager import stop_live_monitor
        stop_live_monitor()
    except Exception as e:
        logger.warning(f"Error stopping live monitor: {e}")
    
    # Stop the sentinel agent if it's running
    try:
        from core.sentinel_agent import stop_sentinel_agent
        stop_sentinel_agent()
    except Exception as e:
        logger.warning(f"Error stopping sentinel agent: {e}")
    
    # Send Telegram notification
    try:
        send_message("🛑 TRADING BOT STOPPED\nReceived shutdown signal")
    except Exception:
        pass
    
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def load_agent_configs():
    """
    Load all agent configurations from agents_config directory
    and filter by ALLOWED_SYMBOLS from .env
    
    Returns:
        Dict of agent_id -> agent_config
    """
    from hackathon_config import AGENTS_CONFIG_DIR
    
    agent_configs = {}
    allowed_symbols = set(load_symbols())  # Get allowed symbols from .env
    
    if not os.path.exists(AGENTS_CONFIG_DIR):
        logger.warning(f"Agents config directory not found: {AGENTS_CONFIG_DIR}")
        return agent_configs
    
    # Load all JSON config files
    for filename in os.listdir(AGENTS_CONFIG_DIR):
        if filename.endswith('.json'):
            filepath = os.path.join(AGENTS_CONFIG_DIR, filename)
            try:
                with open(filepath, 'r') as f:
                    config = json.load(f)
                
                agent_id = config.get('agent_id')
                symbol = config.get('symbol')
                
                # Only include agents for allowed symbols
                if agent_id and symbol and symbol in allowed_symbols:
                    agent_configs[agent_id] = config
                    logger.info(f"Loaded agent config: {agent_id} for {symbol}")
                elif agent_id and symbol and symbol not in allowed_symbols:
                    logger.info(f"Skipping agent {agent_id} for {symbol} (not in ALLOWED_SYMBOLS)")
                    
            except Exception as e:
                logger.error(f"Error loading agent config {filename}: {e}")
    
    logger.info(f"Loaded {len(agent_configs)} agent configurations")
    return agent_configs


def initialize_agents(agent_configs: Dict[str, Dict]) -> Dict[str, Portfolio]:
    """
    Initialize portfolios for all agents
    
    Args:
        agent_configs: Dictionary of agent_id -> agent_config
        
    Returns:
        Dict of agent_id -> Portfolio
    """
    portfolios = {}
    
    for agent_id, config in agent_configs.items():
        portfolios[agent_id] = Portfolio(agent_id=agent_id, capital=CAPITAL)
        logger.info(f"Initialized portfolio for {agent_id}")
    
    return portfolios


def cleanup_on_shutdown(portfolios: Dict[str, Portfolio]):
    """Cleanup function to close all positions on shutdown"""
    print("\n" + "="*80)
    print("🛑 SHUTTING DOWN GRACEFULLY...")
    print("="*80)
    
    # Stop monitoring threads
    try:
        from core.trade_manager import stop_live_monitor
        from core.sentinel_agent import stop_sentinel_agent
        stop_live_monitor()
        stop_sentinel_agent()
    except Exception as e:
        logger.warning(f"Error stopping monitoring threads: {e}")
    
    # Send Telegram notification for shutdown
    try:
        send_message("🛑 TRADING BOT SHUTTING DOWN\nGracefully closing all positions...")
    except Exception:
        pass
    
    try:
        # Close all open positions
        summary = close_all_positions(portfolios)
        
        if summary.get("total_positions_closed", 0) > 0:
            print(f"\n✅ Closed {summary['total_positions_closed']} position(s)")
            print(f"💰 Total P&L from closed positions: {summary['total_pnl']:+.2f}")
        else:
            print("\n✅ No open positions to close")
            
        # Save final equity for all agents
        for agent_id, portfolio in portfolios.items():
            log_equity(agent_id, portfolio.equity)
            print(f"  [{agent_id}] Final equity: ${portfolio.equity:.2f}")
            
        # Send Telegram summary
        try:
            total_equity = sum(p.equity for p in portfolios.values())
            total_pnl = total_equity - (CAPITAL * len(portfolios))
            
            telegram_msg = (
                f"✅ TRADING BOT SHUTDOWN COMPLETE\n"
                f"Total Equity: ${total_equity:,.2f}\n"
                f"Total P&L: ${total_pnl:+.2f}"
            )
            send_message(telegram_msg)
        except Exception:
            pass
            
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        print(f"⚠️  Error during cleanup: {e}")
        
        # Send Telegram error notification
        try:
            send_message(f"⚠️ ERROR DURING SHUTDOWN\n{str(e)}")
        except Exception:
            pass
    
    print("\n" + "="*80)
    print("✅ SHUTDOWN COMPLETE")
    print("="*80 + "\n")


def test_connections() -> Dict[str, bool]:
    """Test connections to Binance Futures using python-binance."""
    from core.trading_engine import test_connections as engine_test_connections
    
    results = engine_test_connections()
    
    return results


def live_trading_loop(symbols: list = ['BTC/USDT', 'BNB/USDT'], interval: int = 60):
    """Run the live trading loop with dashboard.
    
    Args:
        symbols: List of trading pairs to monitor
        interval: Time in seconds between each trading cycle
    """
    import signal as sig_module  # Rename to avoid conflict
    from core.binance_client import get_connection_info, is_testnet_mode, test_binance_connection
    
    # Initialize portfolios variable
    portfolios = {}
    
    try:
        # Initialize database
        init_db()
        
        # Load agent configurations
        agent_configs = load_agent_configs()
        
        # Initialize portfolios for agents
        portfolios = initialize_agents(agent_configs)
        logger.info("✅ All portfolios initialized")
        
        # === SYNC SYMBOL LOCKS WITH ACTUAL POSITIONS ON STARTUP ===
        logger.info("🔄 Initializing symbol lock system...")
        try:
            logger.debug("Importing symbol_lock module...")
            from core.symbol_lock import clear_all_locks_and_cooldowns
            logger.debug("Import successful, clearing locks...")
            # On fresh startup, just clear everything - no need to check Binance
            clear_all_locks_and_cooldowns()
            logger.info("✅ Symbol locks cleared on startup (fresh start)")
        except Exception as e:
            logger.warning(f"⚠️  Error during lock initialization: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Continue anyway - don't block startup
        
        logger.info("🔄 Initializing TradingOrchestrator...")
        # Initialize orchestrator with both agent configs and portfolios
        orchestrator = TradingOrchestrator(agent_configs, portfolios)
        logger.info("✅ TradingOrchestrator initialized")
        
        # === [ApexPatch2025-10-31] Live Monitor Thread Fix ===
        # === [Bulletproof Improvements] Enhanced Monitoring & Error Handling ===
        from core.trade_manager import start_live_monitor
        from core.sentinel_agent import start_sentinel_agent

        try:
            live_monitor_thread = start_live_monitor(5)  # Changed from 3 to 5 seconds to reduce API load
            if live_monitor_thread:
                # Thread is already started in start_live_monitor function
                logger.info("✅ Live monitor thread started successfully")
            else:
                logger.warning("⚠️ Live monitor thread not returned from trade_manager")
                
            # Start sentinel agent for position health monitoring (with enhanced debounce & leverage consistency)
            sentinel_thread = start_sentinel_agent(300)  # 5 minutes
            if sentinel_thread:
                logger.info("✅ Sentinel agent thread started successfully (with dual-layer debounce & leverage consistency)")
            else:
                logger.warning("⚠️ Sentinel agent thread not returned")
                
            # Verify new modules are available (regime_engine, binance_error_handler)
            try:
                from core.regime_engine import get_regime_analysis
                from core.binance_error_handler import handle_binance_error
                logger.info("✅ Regime engine and error handler modules loaded successfully")
            except ImportError as e:
                logger.warning(f"⚠️ Failed to import new modules: {e}")
        except Exception as e:
            logger.error(f"Failed to start monitoring threads: {e}")
        
        # Send initial Telegram message
        if TELEGRAM_ENABLED:
            send_initial_message()
        
        # Print comprehensive startup information
        is_testnet = is_testnet_mode()
        connection_info = get_connection_info()
        
        print("\n" + "="*80)
        print("🚀 KUSHAL TRADING BOT - STARTING UP")
        print("="*80)
        print(f"\n📡 CONNECTION STATUS:")
        print(f"   Mode: {'🧪 TESTNET (Safe Testing)' if is_testnet else '🟢 LIVE TRADING (Real Money)'}")
        print(f"   Exchange: {connection_info}")
        print(f"   Status: ✅ Connected")
        
        print(f"\n💰 ACCOUNT SETTINGS:")
        print(f"   Starting Capital: ${CAPITAL:,.2f}")
        from core.settings import settings
        risk_pct = settings.risk_fraction * 100
        print(f"   Risk per Trade: {risk_pct:.1f}% of equity (dynamic scaling)")
        print(f"   Max Leverage: {settings.max_leverage}x")
        
        print(f"\n📊 TRADING CONFIGURATION:")
        print(f"   Active Symbols: {', '.join(symbols)}")
        print(f"   Cycle Interval: {interval} seconds ({interval/60:.1f} minutes)")
        print(f"   Active Agents: {len(agent_configs)}")
        
        print(f"\n🛡️ SAFETY FEATURES ACTIVE:")
        print(f"   ✅ Global Kill-Switch (daily loss, consecutive losses, API lag)")
        print(f"   ✅ Circuit Breakers (volatility spikes, funding rate, spread widening)")
        print(f"   ✅ Dual-ATR Regime Analysis (EXTREME volatility protection)")
        print(f"   ✅ Correlation Filter (prevents over-exposure)")
        print(f"   ✅ Enhanced Error Handling (graceful Binance error recovery)")
        print(f"   ✅ Leverage Consistency (locked at entry)")
        print(f"   ✅ TP/SL Protection (dual-leg verification)")
        print(f"   ✅ Margin Validation (prevents -2019 errors)")
        
        print(f"\n🔄 BACKGROUND MONITORS:")
        print(f"   ✅ Live Monitor: Active (checks TP/SL every 5s)")
        print(f"   ✅ Sentinel Agent: Active (repairs TP/SL every 5min)")
        
        print("\n" + "="*80)
        print("✅ INITIALIZATION COMPLETE - Starting Trading Loop")
        print("="*80 + "\n")
        
        cycle_count = 0
        
        while True:
            try:
                cycle_count += 1
                
                # Clear, organized cycle header
                print("\n" + "═" * 80)
                cycle_time = time.strftime('%Y-%m-%d %H:%M:%S')
                header_text = f"TRADING CYCLE #{cycle_count} │ {cycle_time}"
                padding = (80 - len(header_text)) // 2
                print(" " * padding + header_text)
                print("═" * 80)
                print(f"📊 Analyzing market conditions and executing trades...")
                print("-" * 80)
                
                # Execute one trading cycle
                cycle_results = orchestrator.run_cycle()
                
                # Print cycle summary in layman-friendly format
                if cycle_results:
                    trades_executed = cycle_results.get('trades_executed', 0)
                    signals_generated = cycle_results.get('signals_generated', 0)
                    
                    if trades_executed > 0:
                        print(f"\n✅ Cycle Summary: {trades_executed} trade(s) executed, {signals_generated} signal(s) analyzed")
                    else:
                        print(f"\n⏸️  Cycle Summary: No trades executed (analyzed {signals_generated} signal(s))")
                
                # Manage open positions (TP/SL) - backup check
                from core.trade_manager import manage_open_positions
                position_summary = manage_open_positions()
                
                # Show position summary if available
                if position_summary and position_summary.get('total_positions', 0) > 0:
                    total_pos = position_summary.get('total_positions', 0)
                    print(f"\n📈 Open Positions: {total_pos} position(s) being monitored")
                
                # Wait for next cycle with clear indication
                print(f"\n" + "-" * 80)
                print(f"⏳ Waiting {interval} seconds ({interval/60:.1f} minutes) until next cycle...")
                print("═" * 80)
                time.sleep(interval)
                
            except KeyboardInterrupt:
                print("\n\n🚨 Keyboard interrupt received...")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                print(f"⚠️  Error in trading loop: {e}")
                
                # Send Telegram error notification
                try:
                    send_message(f"⚠️ TRADING LOOP ERROR\n{str(e)}")
                except Exception:
                    pass
                
                # Wait before retrying
                time.sleep(60)
        
        # Cleanup on exit
        cleanup_on_shutdown(portfolios)
        
    except Exception as e:
        logger.error(f"Critical error in trading loop: {e}", exc_info=True)
        print(f"❌ Critical error: {e}")
        
        # Send Telegram error notification
        try:
            send_message(f"❌ CRITICAL ERROR\n{str(e)}")
        except Exception:
            pass
        
        # Attempt cleanup
        if portfolios:
            cleanup_on_shutdown(portfolios)


if __name__ == "__main__":
    # Test connections first
    print("🔍 Testing Connection...")
    connection_results = test_connections()
    
    if not connection_results.get("futures_connection", False):
        print("❌ Failed to connect to Binance Futures")
        sys.exit(1)
    
    print("✅ Connection Verified")
    
    # Load symbols from .env
    from hackathon_config import load_symbols
    symbols = load_symbols()
    print(f"✅ Active trading symbols: {', '.join(symbols)}")
    
    # Start live trading loop
    live_trading_loop(symbols=symbols, interval=REFRESH_INTERVAL_SEC)