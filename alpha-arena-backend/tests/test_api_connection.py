#!/usr/bin/env python3
"""
Test script to verify API server is sending data correctly
"""

import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WebSocket server")
            
            # Wait for initial data
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(message)
            print(f"📥 Received message type: {data.get('type', 'unknown')}")
            
            if data.get('type') == 'initial':
                dashboard_data = data.get('data', {})
                print("📊 Dashboard Data:")
                print(f"   Iteration: {dashboard_data.get('iteration', 'N/A')}")
                print(f"   Mode: {dashboard_data.get('mode', 'N/A')}")
                print(f"   Total Equity: ${dashboard_data.get('total_equity', 0):,.2f}")
                print(f"   Agents Count: {len(dashboard_data.get('agents', []))}")
                print(f"   Open Positions: {len(dashboard_data.get('open_positions', []))}")
                
                # Try to get an update
                await websocket.send(json.dumps({"type": "get_data"}))
                try:
                    update_message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    update_data = json.loads(update_message)
                    print(f"🔄 Update received: {update_data.get('type', 'unknown')}")
                except asyncio.TimeoutError:
                    print("⏰ No update received within timeout")
                    
            else:
                print("❌ Unexpected initial message type")
                
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")

if __name__ == "__main__":
    print("🔍 Testing WebSocket connection to API server...")
    asyncio.run(test_websocket())