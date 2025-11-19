import sqlite3, time, os
from typing import Optional, Dict, Any, List
from hackathon_config import MAIN_DB

def init_db():
    """Initialize main database with trades, equity, positions, and order tracking"""
    os.makedirs("db", exist_ok=True)
    con = sqlite3.connect(MAIN_DB)
    cur = con.cursor()
    
    # Trades table (completed trades)
    cur.execute("""CREATE TABLE IF NOT EXISTS trades(
        ts REAL, agent_id TEXT, symbol TEXT, side TEXT, qty REAL, 
        entry REAL, exit REAL, pnl REAL, confidence REAL, reasoning TEXT)""")
    
    # Equity tracking table
    cur.execute("""CREATE TABLE IF NOT EXISTS equity_history(
        ts REAL, agent_id TEXT, equity REAL)""")
    
    # Open positions table (CRITICAL for restart recovery)
    cur.execute("""CREATE TABLE IF NOT EXISTS open_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity REAL NOT NULL,
        entry_price REAL NOT NULL,
        leverage INTEGER NOT NULL,
        opened_at REAL NOT NULL,
        confidence REAL,
        reasoning TEXT,
        exchange_order_id TEXT,
        status TEXT DEFAULT 'open',
        closed_at REAL,
        close_reason TEXT,
        last_verified REAL
    )""")
    
    # Create unique index to prevent duplicate open positions
    cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_open_position_unique 
        ON open_positions(symbol, agent_id) WHERE status='open'""")
    
    # Order history table (all orders, not just completed)
    cur.execute("""CREATE TABLE IF NOT EXISTS order_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        agent_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        order_type TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL,
        leverage INTEGER,
        status TEXT NOT NULL,
        order_id TEXT,
        message TEXT,
        execution_time_ms INTEGER
    )""")
    
    # API metrics for monitoring
    cur.execute("""CREATE TABLE IF NOT EXISTS api_metrics (
        timestamp REAL NOT NULL,
        endpoint TEXT NOT NULL,
        duration_ms INTEGER,
        status TEXT,
        error TEXT
    )""")
    
    con.commit()
    con.close()

def log_trade(agent_id: str, symbol: str, side: str, qty: float, entry: float, 
              exit: float, pnl: float, confidence: float, reasoning: str = ""):
    """Log a completed trade to database"""
    con = sqlite3.connect(MAIN_DB)
    cur = con.cursor()
    cur.execute("INSERT INTO trades (ts, agent_id, symbol, side, qty, entry, exit, pnl, confidence, reasoning) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (time.time(), agent_id, symbol, side, qty, entry, exit, pnl, confidence, reasoning))
    con.commit()
    con.close()

def log_equity(agent_id: str, equity: float):
    """Log current equity for an agent"""
    con = sqlite3.connect(MAIN_DB)
    cur = con.cursor()
    cur.execute("INSERT INTO equity_history (ts, agent_id, equity) VALUES(?,?,?)",
                (time.time(), agent_id, equity))
    con.commit()
    con.close()

def get_trades(agent_id: str = None, limit: int = 100):
    """Retrieve trades, optionally filtered by agent"""
    con = sqlite3.connect(MAIN_DB)
    cur = con.cursor()
    
    if agent_id:
        cur.execute("SELECT * FROM trades WHERE agent_id = ? ORDER BY ts DESC LIMIT ?", 
                   (agent_id, limit))
    else:
        cur.execute("SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,))
    
    trades = cur.fetchall()
    con.close()
    return trades

def get_equity_history(agent_id: str):
    """Retrieve equity history for an agent"""
    con = sqlite3.connect(MAIN_DB)
    cur = con.cursor()
    cur.execute("SELECT ts, equity FROM equity_history WHERE agent_id = ? ORDER BY ts", 
               (agent_id,))
    history = cur.fetchall()
    con.close()
    return history


# ============================================================================
# POSITION TRACKING (Critical for 1-month continuous operation)
# ============================================================================

def log_position_open(
    symbol: str,
    agent_id: str,
    side: str,
    quantity: float,
    entry_price: float,
    leverage: int,
    confidence: float = 0.0,
    reasoning: str = "",
    exchange_order_id: str = None
) -> Optional[int]:
    """Log opening of a new position"""
    try:
        con = sqlite3.connect(MAIN_DB)
        cur = con.cursor()
        cur.execute(
            """INSERT INTO open_positions 
            (symbol, agent_id, side, quantity, entry_price, leverage, opened_at, 
             confidence, reasoning, exchange_order_id, status, last_verified) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
            (symbol, agent_id, side, quantity, entry_price, leverage, time.time(),
             confidence, reasoning, exchange_order_id, time.time())
        )
        position_id = cur.lastrowid
        con.commit()
        con.close()
        return position_id
    except sqlite3.IntegrityError:
        # Position already exists
        return None
    except Exception as e:
        print(f"Error logging position open: {e}")
        return None


def get_open_position(symbol: str, agent_id: str) -> Optional[Dict[str, Any]]:
    """Get open position for symbol and agent (fast local check)"""
    con = sqlite3.connect(MAIN_DB)
    cur = con.cursor()
    cur.execute(
        """SELECT id, symbol, agent_id, side, quantity, entry_price, leverage, 
                  opened_at, confidence, reasoning, exchange_order_id, last_verified
           FROM open_positions 
           WHERE symbol = ? AND agent_id = ? AND status = 'open'""",
        (symbol, agent_id)
    )
    row = cur.fetchone()
    con.close()
    
    if row:
        return {
            'id': row[0],
            'symbol': row[1],
            'agent_id': row[2],
            'side': row[3],
            'quantity': row[4],
            'entry_price': row[5],
            'leverage': row[6],
            'opened_at': row[7],
            'confidence': row[8],
            'reasoning': row[9],
            'exchange_order_id': row[10],
            'last_verified': row[11]
        }
    return None


def get_all_open_positions() -> List[Dict[str, Any]]:
    """Get all open positions (for restart recovery)"""
    con = sqlite3.connect(MAIN_DB)
    cur = con.cursor()
    cur.execute(
        """SELECT id, symbol, agent_id, side, quantity, entry_price, leverage, 
                  opened_at, confidence, reasoning, exchange_order_id, last_verified
           FROM open_positions 
           WHERE status = 'open'
           ORDER BY opened_at"""
    )
    rows = cur.fetchall()
    con.close()
    
    positions = []
    for row in rows:
        positions.append({
            'id': row[0],
            'symbol': row[1],
            'agent_id': row[2],
            'side': row[3],
            'quantity': row[4],
            'entry_price': row[5],
            'leverage': row[6],
            'opened_at': row[7],
            'confidence': row[8],
            'reasoning': row[9],
            'exchange_order_id': row[10],
            'last_verified': row[11]
        })
    return positions


def mark_position_closed(
    position_id: int = None,
    symbol: str = None,
    agent_id: str = None,
    close_reason: str = "manual"
) -> bool:
    """Mark a position as closed"""
    try:
        con = sqlite3.connect(MAIN_DB)
        cur = con.cursor()
        
        if position_id:
            cur.execute(
                """UPDATE open_positions 
                   SET status = 'closed', closed_at = ?, close_reason = ?
                   WHERE id = ?""",
                (time.time(), close_reason, position_id)
            )
        elif symbol and agent_id:
            cur.execute(
                """UPDATE open_positions 
                   SET status = 'closed', closed_at = ?, close_reason = ?
                   WHERE symbol = ? AND agent_id = ? AND status = 'open'""",
                (time.time(), close_reason, symbol, agent_id)
            )
        else:
            return False
        
        con.commit()
        con.close()
        return True
    except Exception as e:
        print(f"Error marking position closed: {e}")
        return False


def update_position_verified(position_id: int) -> bool:
    """Update last_verified timestamp for a position"""
    try:
        con = sqlite3.connect(MAIN_DB)
        cur = con.cursor()
        cur.execute(
            "UPDATE open_positions SET last_verified = ? WHERE id = ?",
            (time.time(), position_id)
        )
        con.commit()
        con.close()
        return True
    except Exception as e:
        print(f"Error updating position verified: {e}")
        return False


def log_order(
    agent_id: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float],
    leverage: int,
    status: str,
    order_id: Optional[str] = None,
    message: Optional[str] = None,
    execution_time_ms: Optional[int] = None
) -> None:
    """Log all order attempts (success, skipped, error)"""
    try:
        con = sqlite3.connect(MAIN_DB)
        cur = con.cursor()
        cur.execute(
            """INSERT INTO order_history 
            (timestamp, agent_id, symbol, side, order_type, quantity, price, 
             leverage, status, order_id, message, execution_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (time.time(), agent_id, symbol, side, order_type, quantity, price,
             leverage, status, order_id, message, execution_time_ms)
        )
        con.commit()
        con.close()
    except Exception as e:
        print(f"Error logging order: {e}")


def log_api_call(
    endpoint: str,
    duration_ms: int,
    status: str = "success",
    error: Optional[str] = None
) -> None:
    """Log API call metrics for monitoring"""
    try:
        con = sqlite3.connect(MAIN_DB)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO api_metrics (timestamp, endpoint, duration_ms, status, error) VALUES (?, ?, ?, ?, ?)",
            (time.time(), endpoint, duration_ms, status, error)
        )
        con.commit()
        con.close()
    except Exception as e:
        pass  # Don't fail on metrics logging
