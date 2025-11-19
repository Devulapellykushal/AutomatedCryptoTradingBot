"""
Alpha Arena Trading Engine – Binance Futures with python-binance
Supports USDT-M Futures using python-binance library.
Uses centralized binance_client module for testnet/mainnet switching.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import time
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Import centralized Binance client manager
from core.binance_client import (
    get_client_manager,
    get_futures_client,
    get_data_client,
    is_testnet_mode,
    get_price as binance_get_price,
    get_balance as binance_get_balance,
    get_full_balance,
    place_order as binance_place_order
)

# Initialize logging
logger = logging.getLogger("trading")

# LAZY INITIALIZATION: Don't initialize clients at module import time
# This prevents blocking hangs when the module is imported
_client_manager = None
_futures_client = None
_data_client = None

def _get_client_manager():
    """Lazy getter for client manager - initializes only when needed"""
    global _client_manager
    if _client_manager is None:
        _client_manager = get_client_manager()
        _client_manager.initialize_all_clients()
    return _client_manager

def _get_futures():
    """Lazy getter for futures client"""
    global _futures_client
    if _futures_client is None:
        try:
            # Ensure client manager is initialized first
            _get_client_manager()
            _futures_client = get_futures_client()
            if _futures_client is None:
                logger.warning("[LazyInit] Futures client is None after initialization")
        except Exception as e:
            logger.error(f"[LazyInit] Error initializing futures client: {e}")
            import traceback
            logger.error(traceback.format_exc())
    return _futures_client

def _get_data():
    """Lazy getter for data client"""
    global _data_client
    if _data_client is None:
        _data_client = get_data_client() or _get_futures()
    return _data_client

# Legacy aliases for compatibility - use lazy getters
def futures():
    """Legacy alias - use _get_futures() directly"""
    return _get_futures()

def DATA():
    """Legacy alias - use _get_data() directly"""
    return _get_data()

USDM = futures  # Function reference
spot = None  # No spot trading, futures only

# ============================================================================
# LIVE FUTURES TRADING FUNCTIONS
# ============================================================================

def place_futures_order(
    symbol: str,
    side: str,
    amount: float,
    leverage: int = 5,
    reduce_only: bool = False
) -> Dict[str, Any]:
    """
    Place a market order on Binance Futures Testnet using python-binance.
    
    Args:
        symbol: Trading pair (e.g., 'BNB/USDT')
        side: 'buy' or 'sell'
        amount: Quantity to trade
        leverage: Leverage to use (1-125, default 5)
        reduce_only: If True, only reduce existing position
        
    Returns:
        Order result dictionary
    """
    futures_client = _get_futures()
    if not futures_client:
        logger.error("Futures client not available")
        return {"error": "Futures client not initialized"}
    
    try:
        # Convert symbol format: BNB/USDT -> BNBUSDT
        binance_symbol = symbol.replace("/", "")
        
        # Use the helper function from binance_client
        order = binance_place_order(
            client=futures_client,
            symbol=binance_symbol,
            side=side,
            quantity=amount,
            order_type="MARKET",
            leverage=leverage
        )
        
        logger.info(f"✅ Futures {side.upper()} order executed: {amount} {symbol} @ {order.get('price', 'N/A')}")
        return order
        
    except BinanceAPIException as e:
        error_msg = f"Binance API error: {e}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Order execution failed: {e}"
        logger.error(error_msg)
        return {"error": error_msg}

def close_futures_position(
    symbol: str,
    side: str,
    amount: float
) -> Dict[str, Any]:
    """
    Close a futures position (reduce-only order).
    
    Args:
        symbol: Trading pair
        side: 'buy' to close short, 'sell' to close long
        amount: Quantity to close
        
    Returns:
        Order result dictionary
    """
    return place_futures_order(symbol, side, amount, leverage=1, reduce_only=True)

def get_futures_position(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get current futures position for a symbol using python-binance.
    
    Args:
        symbol: Trading pair (e.g., 'BNB/USDT')
        
    Returns:
        Position info or None if no position
    """
    futures_client = _get_futures()
    if not futures_client:
        return None
    
    try:
        # Convert symbol format: BNB/USDT -> BNBUSDT
        binance_symbol = symbol.replace("/", "")
        
        # Get position information
        positions = futures_client.futures_position_information(symbol=binance_symbol)
        
        for pos in positions:
            if float(pos.get('positionAmt', 0)) != 0:
                return pos
        return None
    except Exception as e:
        logger.error(f"Error fetching position: {e}")
        return None

def get_futures_balance() -> Dict[str, Any]:
    """
    Get futures account balance using python-binance.
    
    Returns:
        Dictionary with balance info
    """
    futures_client = _get_futures()
    if not futures_client:
        logger.warning("Futures client not available")
        return {"free": 0.0, "used": 0.0, "total": 0.0}
    
    try:
        # Use the helper function
        return get_full_balance(futures_client)
    except Exception as e:
        logger.error(f"Error fetching balance: {e}")
        return {"free": 0.0, "used": 0.0, "total": 0.0}

def test_connections() -> Dict[str, Any]:
    """Test connections to Binance Futures using python-binance"""
    results = {
        "data_connection": False,
        "trading_connection": False,
        "spot_connection": False,
        "futures_connection": False,
        "errors": []
    }
    
    # Test futures client (data + trading combined)
    try:
        logger.debug("[TestConnection] Initializing futures client...")
        futures_client = _get_futures()
        logger.debug(f"[TestConnection] Futures client result: {futures_client is not None}")
        
        if futures_client:
            try:
                # Test price fetch
                logger.debug("[TestConnection] Testing price fetch...")
                ticker = futures_client.futures_symbol_ticker(symbol="BTCUSDT")
                price = float(ticker['price'])
                results["data_connection"] = True
                results["futures_connection"] = True
                results["trading_connection"] = True
                logger.info(f"✅ Binance Futures client OK - BTC/USDT: {price}")
            except Exception as e:
                error = f"Futures client failed: {e}"
                results["errors"].append(error)
                logger.error(error)
                import traceback
                logger.debug(traceback.format_exc())
        else:
            error_msg = "Futures client not initialized (returned None)"
            results["errors"].append(error_msg)
            logger.error(error_msg)
    except Exception as e:
        error = f"Error during connection test: {e}"
        results["errors"].append(error)
        logger.error(error)
        import traceback
        logger.error(traceback.format_exc())
    
    return results

def get_account_summary(account_type: str = "futures") -> Dict[str, Any]:
    """Get account summary including balance and open positions."""
    try:
        futures_client = _get_futures()
        if not futures_client:
            error_msg = "Futures client not initialized"
            logger.error(error_msg)
            return {"error": error_msg}
        
        # Get balance
        balance_info = get_futures_balance()
        
        # Get account info for positions
        account = futures_client.futures_account()
        
        # Get open positions
        positions = []
        for pos in account.get('positions', []):
            if float(pos.get('positionAmt', 0)) != 0:
                positions.append(pos)
        
        # Get open orders
        open_orders = futures_client.futures_get_open_orders()
        
        return {
            'total_balance': balance_info.get('total', 0),
            'free_balance': balance_info.get('free', 0),
            'used_balance': balance_info.get('used', 0),
            'open_positions': positions,
            'open_orders': open_orders,
            'timestamp': int(time.time() * 1000)
        }
        
    except Exception as e:
        error_msg = f"Error getting account summary: {e}"
        logger.error(error_msg)
        return {"error": error_msg}

@dataclass
class OrderResult:
    """Container for order execution results"""
    success: bool
    order_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    qty: Optional[float] = None
    price: Optional[float] = None
    filled_qty: Optional[float] = None
    avg_price: Optional[float] = None
    status: Optional[str] = None
    fee: Optional[Dict[str, float]] = None
    error: Optional[str] = None
    timestamp: float = 0.0  # Will be set in __post_init__

    def __post_init__(self):
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

def choose_trade_client(account_type: str = "futures") -> Optional[Client]:
    """
    Select the appropriate trading client.
    Simplified for Futures Demo Trading - always returns Futures client.
    """
    return _get_futures()

def get_trade_client(account_type: str = "futures") -> Optional[Client]:
    """
    Get trade client - unified for Futures Demo Trading.
    Always returns Futures client regardless of account_type.
    """
    return _get_futures()

def fetch_public_ticker(symbol: str) -> Dict[str, Any]:
    """Fetch ticker data from the data client using python-binance."""
    try:
        data_client = _get_data()
        if not data_client:
            raise Exception("Data client not initialized")
        
        # Convert symbol format: BTC/USDT -> BTCUSDT
        binance_symbol = symbol.replace("/", "")
        
        ticker = data_client.futures_symbol_ticker(symbol=binance_symbol)
        
        # Convert to standard format
        return {
            'symbol': symbol,
            'last': float(ticker['price']),
            'timestamp': int(ticker.get('time', time.time() * 1000))
        }
    except Exception as e:
        logger.error(f"Failed to fetch ticker for {symbol}: {e}")
        raise

def execute_trade(
    symbol: str,
    side: str,
    qty: float,
    account_type: str = "futures",
    order_type: str = "market",
    price: Optional[float] = None,
    **params
) -> OrderResult:
    """
    Execute a trade on Binance Futures.
    
    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        side: 'buy' or 'sell'
        qty: Quantity to trade
        account_type: 'futures' (spot not supported)
        order_type: 'market', 'limit', etc.
        price: Required for limit orders
        **params: Additional order parameters
        
    Returns:
        OrderResult with trade details
    """
    try:
        client = choose_trade_client(account_type)
        
        if not client:
            return OrderResult(success=False, error="Trading client not initialized")
        
        # Convert symbol format
        binance_symbol = symbol.replace("/", "")
        
        # Place order using helper function
        order = binance_place_order(
            client=client,
            symbol=binance_symbol,
            side=side,
            quantity=qty,
            order_type=order_type.upper(),
            leverage=params.get('leverage', 5)
        )
        
        # Process the order result
        return OrderResult(
            success=True,
            order_id=str(order.get('orderId')),
            symbol=symbol,
            side=order.get('side'),
            qty=float(order.get('origQty', 0)),
            price=float(order.get('price', 0)) if order.get('price') else None,
            filled_qty=float(order.get('executedQty', 0)),
            avg_price=float(order.get('avgPrice', 0)) if order.get('avgPrice') else None,
            status=order.get('status'),
            fee=None
        )
        
    except BinanceAPIException as e:
        error_msg = f"Binance API error for {side} order: {e}"
        logger.error(error_msg)
        return OrderResult(success=False, error=error_msg)
    except Exception as e:
        error_msg = f"Error executing {side} order: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return OrderResult(success=False, error=error_msg)

# For backward compatibility
execute_live_trade = execute_trade

def cancel_all_orders(symbol: Optional[str] = None, account_type: str = "futures") -> Dict[str, Any]:
    """Cancel all open orders, optionally for a specific symbol."""
    try:
        client = choose_trade_client(account_type)
        
        if not client:
            return {"error": "Trading client not initialized"}
        
        if symbol:
            binance_symbol = symbol.replace("/", "")
            client.futures_cancel_all_open_orders(symbol=binance_symbol)
            return {"status": f"Cancelled all orders for {symbol}"}
        else:
            # Cancel all orders for all symbols
            open_orders = client.futures_get_open_orders()
            for order in open_orders:
                try:
                    client.futures_cancel_order(
                        symbol=order['symbol'],
                        orderId=order['orderId']
                    )
                except Exception as e:
                    logger.warning(f"Failed to cancel order {order['orderId']}: {e}")
            return {"status": "Cancelled all open orders"}
            
    except Exception as e:
        error_msg = f"Error cancelling orders: {e}"
        logger.error(error_msg)
        return {"error": error_msg}

def close_all_positions(portfolios: Dict, account_type: str = "futures") -> Dict[str, Any]:
    """Close all open positions across all portfolios safely.
    
    Args:
        portfolios: Dictionary of agent_id -> Portfolio
        account_type: 'futures'
        
    Returns:
        Summary of closed positions
    """
    from core.data_engine import fetch_ohlcv
    
    summary = {
        "total_positions_closed": 0,
        "total_pnl": 0.0,
        "agents": {}
    }
    
    try:
        for agent_id, portfolio in portfolios.items():
            agent_summary = {
                "positions_closed": 0,
                "total_pnl": 0.0,
                "positions": []
            }
            
            open_positions = portfolio.get_open_positions()
            
            if not open_positions:
                continue
                
            print(f"\n🛡️  [{agent_id}] Closing {len(open_positions)} open position(s)...")
            
            for symbol, position in list(open_positions.items()):
                try:
                    # Fetch current price
                    df = fetch_ohlcv(symbol, timeframe="1m", limit=1)
                    if df.empty:
                        logger.warning(f"Could not fetch price for {symbol}, using entry price")
                        current_price = position.entry_price
                    else:
                        current_price = df['c'].iloc[-1]
                    
                    # Close position in portfolio
                    result = portfolio.close_position(symbol, current_price)
                    
                    if result:
                        pnl, pnl_pct = result
                        agent_summary["positions_closed"] += 1
                        agent_summary["total_pnl"] += pnl
                        agent_summary["positions"].append({
                            "symbol": symbol,
                            "side": position.side,
                            "pnl": pnl,
                            "pnl_pct": pnl_pct
                        })
                        
                        emoji = "🟢" if pnl > 0 else "🔴"
                        print(f"  {emoji} {symbol}: {position.side.upper()} closed | PnL: {pnl:+.2f} ({pnl_pct:+.2f}%)")
                        
                except Exception as e:
                    logger.error(f"Error closing position {symbol} for {agent_id}: {e}")
                    print(f"  ⚠️  Failed to close {symbol}: {e}")
            
            summary["total_positions_closed"] += agent_summary["positions_closed"]
            summary["total_pnl"] += agent_summary["total_pnl"]
            summary["agents"][agent_id] = agent_summary
            
            print(f"  ✅ [{agent_id}] Closed {agent_summary['positions_closed']} positions | Total PnL: {agent_summary['total_pnl']:+.2f}")
        
        return summary
        
    except Exception as e:
        logger.error(f"Error in close_all_positions: {e}", exc_info=True)
        return {"error": str(e)}
