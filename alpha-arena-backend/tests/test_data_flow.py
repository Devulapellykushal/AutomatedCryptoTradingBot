#!/usr/bin/env python3
"""
Test script to verify data flow from orchestrator to API server
"""

import os
import sys
import json
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_data_flow():
    print("🔍 Testing data flow from orchestrator to API server...")
    
    try:
        # Import required modules
        from main import load_agent_configs, initialize_agents
        from core.orchestrator import TradingOrchestrator
        from hackathon_config import CAPITAL
        
        # Load configs
        print("📥 Loading agent configurations...")
        agent_configs = load_agent_configs()
        print(f"✅ Loaded {len(agent_configs)} agent configurations")
        
        # Initialize portfolios
        print("💰 Initializing portfolios...")
        portfolios = initialize_agents(agent_configs)
        print(f"✅ Initialized {len(portfolios)} portfolios")
        
        # Create orchestrator
        print("🤖 Creating orchestrator...")
        orchestrator = TradingOrchestrator(agent_configs, portfolios)
        print("✅ Orchestrator created")
        
        # Get dashboard data
        print("📊 Getting dashboard data...")
        dashboard_data = orchestrator.get_dashboard_data()
        print("✅ Dashboard data retrieved")
        
        # Print key information
        print("\n📋 Dashboard Data Summary:")
        print(f"   Iteration: {dashboard_data.get('iteration', 'N/A')}")
        print(f"   Mode: {dashboard_data.get('mode', 'N/A')}")
        print(f"   Total Equity: ${dashboard_data.get('total_equity', 0):,.2f}")
        print(f"   Agents Count: {len(dashboard_data.get('agents', []))}")
        print(f"   Open Positions: {len(dashboard_data.get('open_positions', []))}")
        
        # Print first agent if available
        agents = dashboard_data.get('agents', [])
        if agents:
            first_agent = agents[0]
            print(f"\n🤖 First Agent:")
            print(f"   ID: {first_agent.get('agent_id', 'N/A')}")
            print(f"   Symbol: {first_agent.get('symbol', 'N/A')}")
            print(f"   Equity: ${first_agent.get('equity', 0):,.2f}")
            print(f"   P&L: ${first_agent.get('pnl', 0):+.2f}")
        
        # Try to send to API server
        print("\n📡 Testing API server update...")
        try:
            from api_server import update_dashboard_data
            update_dashboard_data(dashboard_data)
            print("✅ Data sent to API server successfully")
        except Exception as e:
            print(f"⚠️  Could not send to API server: {e}")
            
        return dashboard_data
        
    except Exception as e:
        print(f"❌ Error in data flow test: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    data = test_data_flow()
    if data:
        print("\n🎉 Data flow test completed successfully!")
    else:
        print("\n💥 Data flow test failed!")