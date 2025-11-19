#!/usr/bin/env python3
"""
Verify that data is flowing from trading bot to API server
"""

import asyncio
import websockets
import json
import time

async def verify_data_flow():
    print("🔍 Verifying data flow from trading bot to API server...")
    
    try:
        # Connect to WebSocket
        uri = "ws://localhost:8000/ws"
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WebSocket server")
            
            # Listen for messages for 30 seconds
            start_time = time.time()
            message_count = 0
            
            while time.time() - start_time < 30:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    message_count += 1
                    data = json.loads(message)
                    
                    print(f"📥 Message #{message_count} - Type: {data.get('type', 'unknown')}")
                    
                    if data.get('type') == 'initial':
                        dashboard_data = data.get('data', {})
                        print(f"   Initial data - Iteration: {dashboard_data.get('iteration', 'N/A')}")
                        print(f"   Mode: {dashboard_data.get('mode', 'N/A')}")
                        print(f"   Total Equity: ${dashboard_data.get('total_equity', 0):,.2f}")
                        print(f"   Agents: {len(dashboard_data.get('agents', []))}")
                        
                    elif data.get('type') == 'update':
                        dashboard_data = data.get('data', {})
                        print(f"   Update data - Iteration: {dashboard_data.get('iteration', 'N/A')}")
                        print(f"   Mode: {dashboard_data.get('mode', 'N/A')}")
                        print(f"   Total Equity: ${dashboard_data.get('total_equity', 0):,.2f}")
                        print(f"   Agents: {len(dashboard_data.get('agents', []))}")
                        
                    elif data.get('type') == 'heartbeat':
                        print("   💓 Heartbeat received")
                        
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await websocket.send(json.dumps({"type": "ping"}))
                    print("   🏓 Ping sent")
                    
            print(f"\n✅ Received {message_count} messages in 30 seconds")
            return True
            
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")
        return False

if __name__ == "__main__":
    print("📡 Testing WebSocket data flow...")
    try:
        result = asyncio.run(verify_data_flow())
        if result:
            print("\n🎉 Data flow verification completed successfully!")
        else:
            print("\n💥 Data flow verification failed!")
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")