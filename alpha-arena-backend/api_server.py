"""
FastAPI Server for Real-time Trading Dashboard
Provides WebSocket and REST API endpoints for frontend
"""

import asyncio
import json
from typing import Dict, Any, List, Set
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.binance_client import get_full_balance
from core.memory import load_thoughts
from core.learning_memory import load_learning_memory
from hackathon_config import CAPITAL

# Global state
dashboard_data: Dict[str, Any] = {
    "iteration": 0,
    "agents": [],
    "total_equity": CAPITAL,
    "total_pnl": 0.0,
    "total_pnl_pct": 0.0,
    "mode": "initializing",
    "balance": {
        "total": 0.0,
        "free": 0.0,
        "used": 0.0
    },
    "open_positions": [],
    "last_update": datetime.now().isoformat()
}

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        print(f"✅ WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        print(f"❌ WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"⚠️  Error sending to client: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        self.active_connections -= disconnected

manager = ConnectionManager()

# FastAPI app
app = FastAPI(
    title="Alpha Arena Trading API",
    description="Real-time trading bot dashboard API with WebSocket support",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST API Endpoints
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "service": "Alpha Arena Trading API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "dashboard": "/api/dashboard",
            "agents": "/api/agents",
            "positions": "/api/positions",
            "balance": "/api/balance",
            "llm_memory": "/api/llm/memory",
            "websocket": "/ws"
        }
    }

@app.get("/api/dashboard")
async def get_dashboard():
    """Get complete dashboard data"""
    return dashboard_data

@app.get("/api/agents")
async def get_agents():
    """Get all agent data"""
    return {
        "agents": dashboard_data.get("agents", []),
        "count": len(dashboard_data.get("agents", []))
    }

@app.get("/api/positions")
async def get_positions():
    """Get all open positions"""
    return {
        "positions": dashboard_data.get("open_positions", []),
        "count": len(dashboard_data.get("open_positions", []))
    }

@app.get("/api/balance")
async def get_balance():
    """Get current balance"""
    try:
        balance = get_full_balance()
        return {
            "success": True,
            "balance": balance
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "balance": dashboard_data.get("balance", {})
        }

@app.get("/api/llm/memory")
async def get_llm_memory():
    """Get LLM memory and context"""
    try:
        # Load current thoughts (AI decisions)
        thoughts = load_thoughts()
        
        # Load learning memory (performance data)
        learning_memory = load_learning_memory()
        
        return {
            "success": True,
            "thoughts": thoughts,
            "learning_memory": learning_memory,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "connections": len(manager.active_connections)
    }

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    
    try:
        # Send initial data
        await websocket.send_json({
            "type": "initial",
            "data": dashboard_data
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Receive message (ping/pong or requests)
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                data = json.loads(message)
                
                # Handle different message types
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data.get("type") == "get_data":
                    await websocket.send_json({
                        "type": "update",
                        "data": dashboard_data
                    })
                elif data.get("type") == "get_llm_memory":
                    # Load current thoughts (AI decisions)
                    thoughts = load_thoughts()
                    
                    # Load learning memory (performance data)
                    learning_memory = load_learning_memory()
                    
                    await websocket.send_json({
                        "type": "llm_memory",
                        "data": {
                            "thoughts": thoughts,
                            "learning_memory": learning_memory,
                            "timestamp": datetime.now().isoformat()
                        }
                    })
                    
            except asyncio.TimeoutError:
                # Send heartbeat if no message received
                await websocket.send_json({"type": "heartbeat"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        manager.disconnect(websocket)

# Update function to be called from main.py
def update_dashboard_data(data: Dict[str, Any]):
    """Update dashboard data and broadcast to all connected clients"""
    global dashboard_data
    dashboard_data = {
        **data,
        "last_update": datetime.now().isoformat()
    }
    
    # Broadcast to all WebSocket clients (if event loop exists)
    try:
        import asyncio
        # Check if there's a running event loop
        try:
            loop = asyncio.get_running_loop()
            # If there is, create task
            loop.create_task(manager.broadcast({
                "type": "update",
                "data": dashboard_data
            }))
        except RuntimeError:
            # No event loop running, ignore broadcast
            pass
    except Exception:
        # If anything fails, just continue without broadcasting
        pass

# Background task for periodic updates (optional)
async def periodic_broadcast():
    """Periodically broadcast data to connected clients"""
    while True:
        await asyncio.sleep(2)  # Broadcast every 2 seconds
        if manager.active_connections:
            await manager.broadcast({
                "type": "update",
                "data": dashboard_data
            })

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    print("\n" + "="*80)
    print("🚀 FastAPI Server Starting...")
    print("="*80)
    print(f"📡 WebSocket endpoint: ws://localhost:8000/ws")
    print(f"🌐 REST API: http://localhost:8000/api/dashboard")
    print(f"📊 API Docs: http://localhost:8000/docs")
    print("="*80 + "\n")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("\n🛑 FastAPI Server shutting down...")
    for connection in list(manager.active_connections):
        await connection.close()
    print("✅ All WebSocket connections closed\n")

# Run server (when executed directly)
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )