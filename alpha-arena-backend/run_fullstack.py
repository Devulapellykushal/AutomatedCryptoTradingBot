#!/usr/bin/env python3
"""
Start both the trading bot and FastAPI server together
Runs in separate threads for real-time dashboard updates
"""

import os
import sys
import threading
import time
import asyncio
from dotenv import load_dotenv

# Load environment
load_dotenv()

def run_api_server():
    """Run the FastAPI server in a separate thread"""
    import uvicorn
    from api_server import app
    
    print("\n🚀 Starting FastAPI server...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",  # Reduce noise
        access_log=False
    )

def run_trading_bot():
    """Run the main trading bot"""
    import main
    from hackathon_config import REFRESH_INTERVAL_SEC, load_symbols
    
    # Give API server time to start
    time.sleep(2)

    print("\n🤖 Starting trading bot...")
    
    # Load symbols from .env
    symbols = load_symbols()
    print(f"✅ Active trading symbols: {', '.join(symbols)}")
    
    # Call the main trading loop with the correct interval and symbols
    if hasattr(main, 'live_trading_loop'):
        main.live_trading_loop(symbols=symbols, interval=REFRESH_INTERVAL_SEC)
    else:
        print("❌ live_trading_loop not found in main.py")
        sys.exit(1)

def update_dashboard_periodically():
    """Periodically send dashboard updates to API server"""
    from api_server import update_dashboard_data
    from main import load_agent_configs, initialize_agents
    from core.orchestrator import TradingOrchestrator
    
    # Wait for trading bot to initialize
    time.sleep(5)
    
    print("\n📊 Dashboard updater started")
    
    # This will be updated by the orchestrator
    # For now, just a placeholder
    while True:
        try:
            time.sleep(5)
            # Dashboard updates will come from orchestrator.run_cycle()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"⚠️  Dashboard update error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🚀 ALPHA ARENA - Full Stack Trading Bot")
    print("="*80)
    print("\n📡 Starting services...")
    print("   • FastAPI Server (port 8000)")
    print("   • Trading Bot")
    print("   • WebSocket Broadcaster")
    print("\n" + "="*80 + "\n")
    
    try:
        # Start API server in separate thread
        api_thread = threading.Thread(target=run_api_server, daemon=True)
        api_thread.start()
        
        # Give server time to start
        time.sleep(2)
        
        print("\n✅ API Server running at: http://localhost:8000")
        print("✅ API Docs at: http://localhost:8000/docs")
        print("✅ WebSocket at: ws://localhost:8000/ws\n")
        
        # Run trading bot in main thread
        run_trading_bot()
        
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)