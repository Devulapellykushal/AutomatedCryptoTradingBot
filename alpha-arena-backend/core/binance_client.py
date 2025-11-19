"""
Centralized Binance Futures Client Manager
Uses python-binance library to connect to Binance Futures Testnet.
"""

import os
import logging
import math
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv
from binance.client import Client
from decimal import Decimal, ROUND_DOWN

# Initialize logging
logger = logging.getLogger("binance_client")

# Load environment variables
load_dotenv()

# Configuration - Binance Futures (supports both legacy and documented envs)
# Prefer BINANCE_API_SECRET but accept BINANCE_SECRET_KEY from README
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY", "")

# Determine testnet mode:
# 1) Explicit BINANCE_TESTNET takes precedence when provided
# 2) Fallback to BINANCE_MODE in {demo, testnet} → testnet
# 3) Default to True (safe by default)
_env_testnet_raw = os.getenv("BINANCE_TESTNET")
_env_mode = (os.getenv("BINANCE_MODE") or "").strip().lower()
if _env_testnet_raw is not None:
    BINANCE_TESTNET = _env_testnet_raw.strip().lower() in ["1", "true", "yes", "on"]
else:
    BINANCE_TESTNET = _env_mode in ["demo", "testnet"] or True

IS_TESTNET = BINANCE_TESTNET


class BinanceClientManager:
    """Centralized manager for Binance Futures connections using python-binance"""
    
    def __init__(self):
        self.is_testnet = IS_TESTNET
        self.api_key = BINANCE_API_KEY
        self.api_secret = BINANCE_API_SECRET
        
        # Client instance
        self.client: Optional[Client] = None
        
        # Log mode
        mode = "🧪 TESTNET" if self.is_testnet else "🌐 LIVE"
        logger.info(f"🌐 Alpha Arena Trading Engine | Mode={mode} | Binance Futures=✅")
        logger.info(f"Binance Futures Client Manager initialized in {mode} mode")
    
    def create_futures_client(self) -> Optional[Client]:
        """Create and initialize Binance Futures client"""
        try:
            # Initialize Binance client
            client = Client(self.api_key, self.api_secret)
            
            # Switch to testnet URL if needed
            if self.is_testnet:
                client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"
                mode_msg = "✅ Connected to Binance Futures Testnet"
                logger.info(mode_msg)
                print(mode_msg)
            else:
                mode_msg = "✅ Connected to Binance Futures Live (Mainnet)"
                logger.info(mode_msg)
                print(mode_msg)
            
            self.client = client
            return client
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Binance Futures client: {e}")
            print(f"❌ Failed to initialize Binance Futures client: {e}")
            return None
    
    def initialize_all_clients(self) -> Dict[str, bool]:
        """Initialize all clients and return status"""
        results = {
            'futures': False,
            'data': False
        }
        
        # Print startup banner
        print("\n" + "="*80)
        if self.is_testnet:
            print("🧪 CONNECTED TO BINANCE FUTURES TESTNET ✅")
            print("="*80)
            print("   → Using simulated USDT balances")
            print("   → Safe environment (no real funds)")
            print("   → Testnet URL: https://testnet.binancefuture.com")
        else:
            print("🌐 BINANCE FUTURES LIVE TRADING MODE")
            print("="*80)
            print("⚠️  LIVE TRADING MODE")
            print("   → REAL MONEY AT RISK")
            print("   → Use with extreme caution!")
        print("="*80 + "\n")
        
        # Initialize Futures client
        if self.create_futures_client():
            results['futures'] = True
            results['data'] = True  # Same client for data
        
        return results
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Binance Futures"""
        result = {
            'success': False,
            'client_type': 'futures',
            'mode': 'testnet' if self.is_testnet else 'live',
            'error': None
        }
        
        try:
            if self.client:
                # Test price fetch
                ticker = self.client.futures_symbol_ticker(symbol="BTCUSDT")
                result['success'] = True
                result['btc_price'] = float(ticker['price'])
                
                # Test balance fetch
                if self.api_key and self.api_secret:
                    balance = self.client.futures_account_balance()
                    usdt_balance = 0.0
                    for b in balance:
                        if b['asset'] == 'USDT':
                            usdt_balance = float(b['balance'])
                            break
                    result['balance_check'] = 'OK'
                    result['usdt_balance'] = usdt_balance
            else:
                result['error'] = "Client not initialized"
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Connection test failed: {e}")
        
        return result
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get current connection information"""
        return {
            'mode': 'testnet' if self.is_testnet else 'live',
            'rest_url': 'https://testnet.binancefuture.com/fapi' if self.is_testnet else 'https://fapi.binance.com',
            'futures_client': self.client is not None,
            'data_client': self.client is not None,
            'authenticated': bool(self.api_key and self.api_secret)
        }


# Singleton instance
_client_manager = None

def get_client_manager() -> BinanceClientManager:
    """Get or create the singleton BinanceClientManager instance"""
    global _client_manager
    if _client_manager is None:
        _client_manager = BinanceClientManager()
    return _client_manager


def initialize_binance_clients() -> Dict[str, Any]:
    """Initialize all Binance clients and return status"""
    manager = get_client_manager()
    return manager.initialize_all_clients()


def get_futures_client() -> Optional[Client]:
    """Get the initialized futures client"""
    manager = get_client_manager()
    # If client is None, try to initialize it
    if manager.client is None:
        logger.debug("[get_futures_client] Client is None, attempting to initialize...")
        manager.initialize_all_clients()
    return manager.client


def get_data_client() -> Optional[Client]:
    """Get the initialized data client (same as futures client)"""
    manager = get_client_manager()
    return manager.client


def is_testnet_mode() -> bool:
    """Check if running in testnet mode"""
    manager = get_client_manager()
    return manager.is_testnet


def get_connection_info() -> Dict[str, Any]:
    """Get connection information"""
    manager = get_client_manager()
    return manager.get_connection_info()


def make_binance_futures_client() -> Optional[Client]:
    """
    Create and initialize Binance Futures client for Testnet.
    This is the unified client creation function.
    
    Returns:
        Initialized Binance Client configured for Futures
    """
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY")
    _env_testnet_raw = os.getenv("BINANCE_TESTNET")
    _env_mode = (os.getenv("BINANCE_MODE") or "").strip().lower()
    if _env_testnet_raw is not None:
        testnet = _env_testnet_raw.strip().lower() in ["1", "true", "yes", "on"]
    else:
        testnet = _env_mode in ["demo", "testnet"] or True

    try:
        client = Client(api_key, api_secret)
        
        if testnet:
            client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"
            print("✅ Connected to Binance Futures Testnet")
            logger.info("Connected to Binance Futures Testnet")
        else:
            print("✅ Connected to Binance Futures Live (Mainnet)")
            logger.info("Connected to Binance Futures Live (Mainnet)")
        
        return client
    except Exception as e:
        logger.error(f"Failed to create Binance Futures client: {e}")
        print(f"❌ Failed to create Binance Futures client: {e}")
        return None


# ============================================================================
# HELPER FUNCTIONS FOR TRADING ENGINE
# ============================================================================

def _get_symbol_filters(client: Client, symbol: str) -> Dict[str, Any]:
    """
    Fetch precision and filter info (tickSize, stepSize, minQty) for a futures symbol.
    
    Args:
        client: Binance client
        symbol: Trading symbol (e.g., 'BTCUSDT')
        
    Returns:
        Dictionary with precision and filter information
    """
    try:
        info = client.futures_exchange_info()
        sym = next((s for s in info.get("symbols", []) if s.get("symbol") == symbol), None)
        if not sym:
            raise Exception(f"Symbol {symbol} not found in exchange info")

        filters = {f["filterType"]: f for f in sym.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        lot_size = filters.get("LOT_SIZE", {}) or filters.get("MARKET_LOT_SIZE", {})

        return {
            "pricePrecision": sym.get("pricePrecision", 8),
            "quantityPrecision": sym.get("quantityPrecision", 8),
            "tickSize": float(price_filter.get("tickSize", "0.01")),
            "stepSize": float(lot_size.get("stepSize", "0.001")),
            "minQty": float(lot_size.get("minQty", "0.0")),
        }
    except Exception as e:
        logger.warning(f"Could not fetch symbol filters for {symbol}: {e}. Using defaults.")
        return {
            "pricePrecision": 8,
            "quantityPrecision": 8,
            "tickSize": 0.01,
            "stepSize": 0.001,
            "minQty": 0.0,
        }

def _adjust_precision(
    client: Client, 
    symbol: str, 
    qty: float, 
    price: Optional[float] = None
) -> Tuple[float, Optional[float]]:
    """
    Adjust quantity and price to conform to Binance futures precision and filters.
    
    Args:
        client: Binance client
        symbol: Trading symbol (e.g., 'BTCUSDT')
        qty: Order quantity
        price: Order price (optional, for limit orders)
        
    Returns:
        Tuple of (adjusted_quantity, adjusted_price)
    """
    f = _get_symbol_filters(client, symbol)
    
    # Quantity: round down to quantityPrecision and enforce stepSize multiple
    q = float(Decimal(str(qty)).quantize(Decimal(10) ** -f["quantityPrecision"], rounding=ROUND_DOWN))
    if f["stepSize"] > 0:
        q = math.floor(q / f["stepSize"]) * f["stepSize"]
    if q < f["minQty"]:
        q = f["minQty"]
    
    # Round to avoid floating point issues
    q = round(q, f["quantityPrecision"])

    # Price: if provided, round down to pricePrecision and enforce tickSize multiple
    p = price
    if p is not None:
        p = float(Decimal(str(p)).quantize(Decimal(10) ** -f["pricePrecision"], rounding=ROUND_DOWN))
        if f["tickSize"] > 0:
            p = math.floor(p / f["tickSize"]) * f["tickSize"]
        # Round to avoid floating point issues
        p = round(p, f["pricePrecision"])

    return q, p

def get_price(client: Optional[Client] = None, symbol: str = "BTCUSDT") -> float:
    """
    Get current futures price for a symbol.
    
    Args:
        client: Binance client (if None, will use global client)
        symbol: Trading symbol (e.g., 'BTCUSDT')
        
    Returns:
        Current price as float
    """
    if client is None:
        client = get_futures_client()
    
    if client is None:
        raise Exception("Binance client not initialized")
    
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        return float(ticker["price"])
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
        raise


def get_balance(client: Optional[Client] = None) -> float:
    """
    Get futures account USDT balance.
    
    Args:
        client: Binance client (if None, will use global client)
        
    Returns:
        USDT balance as float
    """
    if client is None:
        client = get_futures_client()
    
    if client is None:
        raise Exception("Binance client not initialized")
    
    try:
        balances = client.futures_account_balance()
        for b in balances:
            if b["asset"] == "USDT":
                return float(b["balance"])
        return 0.0
    except Exception as e:
        logger.error(f"Error fetching balance: {e}")
        raise


def get_full_balance(client: Optional[Client] = None) -> Dict[str, float]:
    """
    Get detailed futures account balance.
    
    Args:
        client: Binance client (if None, will use global client)
        
    Returns:
        Dictionary with balance details
    """
    if client is None:
        client = get_futures_client()
    
    if client is None:
        raise Exception("Binance client not initialized")
    
    try:
        balances = client.futures_account_balance()
        usdt_balance = 0.0
        for b in balances:
            if b["asset"] == "USDT":
                usdt_balance = float(b["balance"])
                break
        
        # Get account info for more details
        account = client.futures_account()
        
        return {
            'free': float(account.get('availableBalance', 0)),
            'used': float(account.get('totalInitialMargin', 0)),
            'total': usdt_balance
        }
    except Exception as e:
        logger.error(f"Error fetching full balance: {e}")
        return {"free": 0.0, "used": 0.0, "total": 0.0}


def place_order(
    client: Optional[Client] = None,
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    quantity: float = 0.001,
    order_type: str = "MARKET",
    leverage: int = 5,
    price: Optional[float] = None,
    reduce_only: bool = False
) -> Dict[str, Any]:
    """
    Place a futures order with automatic precision adjustment.
    
    Args:
        client: Binance client (if None, will use global client)
        symbol: Trading symbol (e.g., 'BTCUSDT')
        side: 'BUY' or 'SELL' (or 'buy'/'sell')
        quantity: Order quantity
        order_type: Order type ('MARKET', 'LIMIT', etc.)
        leverage: Leverage to use (1-125)
        price: Order price (required for LIMIT orders)
        reduce_only: If True, only reduce existing position
        
    Returns:
        Order response dictionary
    """
    if client is None:
        client = get_futures_client()
    
    if client is None:
        raise Exception("Binance client not initialized")
    
    try:
        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logger.info(f"Set leverage to {leverage}x for {symbol}")
        
        # Normalize side
        normalized_side = "BUY" if side.lower() == "buy" else "SELL"
        
        # Adjust precision for quantity and price
        adj_qty, adj_price = _adjust_precision(client, symbol, quantity, price)
        
        logger.info(f"Adjusted order params: qty={quantity:.8f} -> {adj_qty}, price={price} -> {adj_price}")
        
        # Prepare order parameters
        params = {"reduceOnly": "true" if reduce_only else "false"}
        
        # Create order
        if order_type.upper() == "MARKET":
            order = client.futures_create_order(
                symbol=symbol,
                side=normalized_side,
                type="MARKET",
                quantity=adj_qty,
                **params
            )
        else:
            # LIMIT or other order types require price
            if adj_price is None:
                raise Exception(f"{order_type} orders require a 'price' argument")
            order = client.futures_create_order(
                symbol=symbol,
                side=normalized_side,
                type=order_type.upper(),
                quantity=adj_qty,
                price=adj_price,
                timeInForce="GTC",
                **params
            )
        
        price_str = f"@ {adj_price}" if adj_price else "@ MARKET"
        logger.info(f"✅ Order placed: {normalized_side} {adj_qty} {symbol} {price_str}")
        return order
        
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise


def test_binance_connection(client: Optional[Client] = None) -> bool:
    """
    Test connection to Binance Futures Testnet.
    Quick diagnostic for startup validation.
    
    Args:
        client: Binance client to test (if None, will create new one)
        
    Returns:
        True if connection successful
    """
    try:
        if client is None:
            client = make_binance_futures_client()
        
        if client is None:
            print("❌ Binance Futures client not initialized")
            return False
        
        # Test ticker fetch
        ticker = client.futures_symbol_ticker(symbol="BTCUSDT")
        print(f"✅ Binance Futures Ticker (BTCUSDT): ${ticker['price']}")
        
        # Test balance fetch
        try:
            balances = client.futures_account_balance()
            usdt_balance = 0.0
            for b in balances:
                if b['asset'] == 'USDT':
                    usdt_balance = float(b['balance'])
                    break
            print(f"💰 Testnet Balance (USDT): {usdt_balance:.2f}")
        except Exception as e:
            print(f"⚠️  Balance fetch failed (may need valid testnet keys): {e}")
        
        print("✅ Binance Futures connection test passed")
        return True
        
    except Exception as e:
        print(f"❌ Binance connection test failed: {e}")
        logger.error(f"Connection test failed: {e}")
        return False
