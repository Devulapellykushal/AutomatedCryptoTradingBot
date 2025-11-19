import logging
import math
import os
import csv
import time
from datetime import datetime
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_DOWN
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Import Telegram notifier
try:
    from telegram_notifier import send_auto_notification as send_message
    TELEGRAM_ENABLED = True
except ImportError:
    def send_message(text: str) -> bool:
        return False
    TELEGRAM_ENABLED = False

# Import new modules
from core.binance_client import get_futures_client
from core.settings import settings
from core.binance_guard import BinanceGuard
from core.retry_wrapper import retry_api_call, retry_long_api_call
from core.symbol_lock import acquire_position_lock, release_position_lock
from core.csv_logger import log_error, log_trade as csv_log_trade

# Create retryable wrapper functions
@retry_api_call
def _retryable_futures_position_information(client, **kwargs):
    return client.futures_position_information(**kwargs)

@retry_api_call
def _retryable_futures_get_order(client, **kwargs):
    return client.futures_get_order(**kwargs)

@retry_api_call
def _retryable_futures_create_order(client, **kwargs):
    return client.futures_create_order(**kwargs)

@retry_api_call
def _retryable_futures_cancel_order(client, **kwargs):
    return client.futures_cancel_order(**kwargs)

@retry_api_call
def _retryable_futures_get_open_orders(client, **kwargs):
    return client.futures_get_open_orders(**kwargs)

@retry_api_call
def _retryable_futures_change_leverage(client, **kwargs):
    return client.futures_change_leverage(**kwargs)

@retry_api_call
def _retryable_futures_symbol_ticker(client, symbol, retries=5, delay=1):
    """Fetch latest futures ticker price safely with retry and backoff."""
    for i in range(retries):
        try:
            data = client.futures_symbol_ticker(symbol=symbol)
            if data and 'price' in data:
                return float(data['price'])
        except Exception as e:
            logger.warning(f"[RetryableTicker] {symbol}: attempt {i+1}/{retries} failed: {e}")
        time.sleep(delay * (i + 1))  # exponential backoff
    raise RuntimeError(f"[RetryableTicker] Failed to get price for {symbol} after {retries} tries")

@retry_api_call
def _retryable_futures_account_balance(client, **kwargs):
    return client.futures_account_balance(**kwargs)

# === [ApexPatch2025-10-31] Precision Normalizer ===
import math

PRECISION_MAP = {
    "BTCUSDT": {"price": 1, "qty": 3},
    "BNBUSDT": {"price": 2, "qty": 2}
}

def normalize(symbol, price=None, qty=None):
    """Round price and qty to Binance precision."""
    p = PRECISION_MAP.get(symbol, {"price": 2, "qty": 2})
    if price is not None:
        price = float(f"{price:.{p['price']}f}")
    if qty is not None:
        qty = float(f"{qty:.{p['qty']}f}")
    return price, qty

# Cache for exchange info to avoid repeated heavy API calls
_exchange_info_cache = {}
_exchange_info_cache_time = {}
_CACHE_TTL = 300  # 5 minutes

def normalize_order_precision(client, symbol, qty, price):
    """
    Normalizes order precision safely using Binance symbol filters.
    Automatically handles None price for MARKET orders.
    Uses caching to avoid repeated heavy API calls.
    """
    global _exchange_info_cache, _exchange_info_cache_time
    
    try:
        # Check cache first
        current_time = time.time()
        cache_key = symbol
        
        # Use cached exchange info if available and not expired
        if cache_key in _exchange_info_cache and cache_key in _exchange_info_cache_time:
            if current_time - _exchange_info_cache_time[cache_key] < _CACHE_TTL:
                symbol_info = _exchange_info_cache[cache_key]
                logger.debug(f"[Precision] Using cached exchange info for {symbol}")
            else:
                # Cache expired, fetch fresh
                symbol_info = None
        else:
            symbol_info = None
        
        # Fetch exchange info if not cached or expired
        if symbol_info is None:
            try:
                logger.debug(f"[Precision] Fetching exchange info for {symbol}...")
                info = client.futures_exchange_info()
                symbol_info = next((s for s in info['symbols'] if s['symbol'] == symbol), None)
                if not symbol_info:
                    raise ValueError(f"Symbol {symbol} not found in exchange info")
                
                # Cache the result
                _exchange_info_cache[cache_key] = symbol_info
                _exchange_info_cache_time[cache_key] = current_time
                logger.debug(f"[Precision] Cached exchange info for {symbol}")
            except Exception as e:
                logger.error(f"[Precision] Failed to fetch exchange info for {symbol}: {e}")
                # Fallback to default precision if API call fails
                logger.warning(f"[Precision] Using fallback precision for {symbol}")
                if price is None:
                    price = 0.0  # Will be fetched via mark price below
                return round(qty, 6), round(price, 2) if price else (round(qty, 6), None)
            
        filters = {f['filterType']: f for f in symbol_info['filters']}
        tick_size = float(filters['PRICE_FILTER']['tickSize'])
        step_size = float(filters['LOT_SIZE']['stepSize'])

        # ✅ fallback if MARKET order has no price
        if price is None:
            try:
                mark_data = client.futures_mark_price(symbol=symbol)
                price = float(mark_data['markPrice'])
                logger.info(f"[PrecisionFix] Using mark price for {symbol}: {price}")
            except Exception as e:
                logger.warning(f"[PrecisionFix] Failed to fetch mark price for {symbol}: {e}, using 0")
                price = 0.0

        price = math.floor(float(price) / tick_size) * tick_size if price else 0.0
        qty = math.floor(float(qty) / step_size) * step_size
        return round(qty, 6), round(price, 2) if price else (round(qty, 6), None)

    except Exception as e:
        logging.warning(f"[PrecisionFix] Fallback normalization for {symbol}: {e}")
        return round(qty or 0, 6), round(float(price or 0), 2)


def get_symbol_specific_precision(symbol: str) -> tuple[int, int]:
    """
    Get symbol-specific precision for quantity and price.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        
    Returns:
        Tuple of (qty_precision, price_precision)
    """
    symbol_upper = symbol.upper()
    if symbol_upper.startswith("BTC"):
        return (3, 2)  # qty precision = 3, price = 2
    elif symbol_upper.startswith("BNB"):
        return (4, 2)  # qty precision = 4, price = 2
    else:
        # Default precision
        return (3, 2)


def safe_qty(symbol: str, qty: float) -> float:
    """
    Safely round quantity to symbol-specific precision to prevent "Precision is over the maximum" errors.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        qty: Quantity to round
        
    Returns:
        Rounded quantity according to symbol precision
    """
    symbol_upper = symbol.upper()
    if symbol_upper.startswith("BTC"):
        return round(qty, 3)
    elif symbol_upper.startswith("BNB"):
        return round(qty, 4)
    else:
        # Default to 3 decimal places
        return round(qty, 3)

# Initialize logging
logger = logging.getLogger("order_manager")

# ============================================================================
# ORDER RESTRICTIONS & THROTTLING
# ============================================================================

def _get_env_float(name: str, default: float) -> float:
    """Safely get float from environment"""
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default


def _get_env_int(name: str, default: int) -> int:
    """Safely get int from environment"""
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default


def _get_allowed_symbols() -> set:
    """Get set of allowed trading symbols from settings"""
    return settings.parsed_allowed_symbols


def _get_trade_log_path() -> str:
    """Get trade log file path from settings"""
    return settings.trade_log_path

# In-memory state for reversal/holding period protection
LAST_TRADE_TIME: dict[str, float] = {}
LAST_TRADE_SIDE: dict[str, str] = {}
REVERSAL_COOLDOWN_UNTIL: dict[str, float] = {}

# In-memory state for tracking active agents and their signals
ACTIVE_AGENT_SIGNALS: dict[str, dict] = {}

# In-memory state for tracking current position side per symbol
CURRENT_POSITION_SIDE: dict[str, str] = {}

# Log debouncing: Track last log time per symbol to prevent log spam
_last_position_exists_log: dict[str, float] = {}
_log_debounce_interval = 60  # Log once per minute


def _append_order_log(
    agent_id: str,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    leverage: int,
    status: str,
    message: str = "",
    order_id: str = ""
) -> None:
    """Append order attempt to trades_log.csv"""
    path = _get_trade_log_path()
    header = ["time", "agent_id", "symbol", "side", "qty", "entry_price", "exit_price", "pnl", "status", "message", "order_id"]
    row = [
        time.time(),
        agent_id or "system",
        symbol,
        side,
        f"{qty:.8f}",
        f"{price:.8f}",
        "",
        "",
        status,
        message,
        order_id
    ]
    
    try:
        exists = os.path.exists(path)
        with open(path, "a", newline="") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(header)
            writer.writerow(row)
    except Exception as e:
        logger.warning(f"Failed to write order log: {e}")


def _count_daily_orders() -> int:
    """
    Count orders with status OPENED in trades_log.csv for today.
    Only counts orders from the last 12 hours to avoid counting stale test entries.
    """
    path = settings.trade_log_path
    if not os.path.exists(path):
        return 0
    
    today = datetime.utcnow().date()
    count = 0
    # Only count orders from last 12 hours to exclude old test entries
    cutoff_time = time.time() - (12 * 60 * 60)
    
    try:
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = float(row.get("time", "0"))
                    # Only count if:
                    # 1. Date matches today
                    # 2. Timestamp is within last 12 hours (filters stale test entries)
                    # 3. Status is OPENED
                    if (datetime.utcfromtimestamp(ts).date() == today and 
                        ts >= cutoff_time and
                        (row.get("status") or "").upper() == "OPENED"):
                        count += 1
                except Exception:
                    continue
    except Exception:
        return 0
    
    return count


def _get_open_positions_count(client: Client) -> int:
    """Count current open positions across all symbols"""
    try:
        positions = _retryable_futures_position_information(client)
        return sum(1 for p in positions if abs(float(p.get("positionAmt", 0))) > 0)
    except Exception:
        return 0


def _get_symbol_min_notional(client: Client, symbol: str) -> float:
    """Get minimum notional value for a symbol using BinanceGuard"""
    try:
        guard = BinanceGuard(client)
        filters = guard.get_symbol_filters(symbol)
        return filters.get('minNotional', 5.0)
    except Exception:
        return 5.0  # Default to $5 if error


def can_place_order(client: Client, symbol: str, qty: float, leverage: int, agent_id: str = "system", tp_pct: float = 2.0, sl_pct: float = 1.0, side: str = "BUY") -> tuple[bool, str, float, float, float]:
    """
    Check if order can be placed based on pre-trade checks (risk management rules):
    
    1. Symbol allowed (ALLOWED_SYMBOLS)
    2. Max open trades not exceeded (MAX_OPEN_TRADES)
    3. Max daily orders not exceeded (MAX_DAILY_ORDERS)
    4. Minimum notional requirement (≥ $5)
    5. Basic leverage and quantity validation
    
    Note: Full margin validation now happens post-trade for reactive risk management.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol (BTCUSDT format)
        qty: Order quantity
        leverage: Order leverage
        agent_id: Agent identifier for logging
        tp_pct: Take profit percentage
        sl_pct: Stop loss percentage
        side: Position side ('BUY' for long, 'SELL' for short)
        
    Returns:
        Tuple of (can_place: bool, reason: str, adjusted_qty: float, tp_price: float, sl_price: float)
    """
    binance_symbol = symbol.replace("/", "").upper()
    
    # Initialize adjusted_qty with the original qty
    adjusted_qty = qty
    
    # 1. Check allowed symbols using settings
    allowed = settings.parsed_allowed_symbols
    if binance_symbol not in allowed:
        return False, f"Symbol {binance_symbol} not in ALLOWED_SYMBOLS list", adjusted_qty, 0.0, 0.0
    
    # 2. Check max open trades
    max_open = _get_env_int("MAX_OPEN_TRADES", 4)
    current_open = _get_open_positions_count(client)
    if current_open >= max_open:
        return False, f"Max open trades ({max_open}) reached (current: {current_open})", adjusted_qty, 0.0, 0.0
    
    # 3. Check max daily orders
    max_daily = _get_env_int("MAX_DAILY_ORDERS", 10)
    daily_count = _count_daily_orders()
    if daily_count >= max_daily:
        return False, f"Max daily orders ({max_daily}) reached (today: {daily_count})", adjusted_qty, 0.0, 0.0
    
    # 4. Get current price
    try:
        # Add 0.3s async-safe delay before fetching ticker
        time.sleep(0.3)
        
        # Use the corrected _retryable_futures_symbol_ticker function with improved error handling
        try:
            price = _retryable_futures_symbol_ticker(client, binance_symbol)
            # Add type safety check
            if not isinstance(price, (int, float)):
                raise TypeError(f"[OrderManager] Invalid ticker value: {price}")
            logger.info(f"[OrderManager] Live ticker for {binance_symbol} fetched successfully: {price}")
        except Exception as e:
            logger.error(f"[OrderManager] Skipping {binance_symbol} due to ticker fetch failure: {e}")
            # Clear cached state to avoid false cooldown
            price = 0.0
            # Release symbol lock since we're not proceeding with the order
            release_position_lock(binance_symbol, success=False)
            return False, f"Could not fetch price for {binance_symbol}", adjusted_qty, 0.0, 0.0
    except Exception:
        price = 0.0
    
    if price <= 0:
        return False, f"Could not fetch price for {binance_symbol}", adjusted_qty, 0.0, 0.0
    
    # 5. Calculate notional value
    notional_value = qty * price
    
    # 6. Check minimum notional requirement ($5 for Binance Futures)
    min_notional = _get_symbol_min_notional(client, binance_symbol)
    if notional_value < min_notional:
        # Try to adjust quantity to meet minimum notional
        min_qty = min_notional / price
        adjusted_qty = max(qty, min_qty)
        adjusted_notional = adjusted_qty * price
        
        if adjusted_notional >= min_notional:
            # Recalculate with adjusted quantity
            notional_value = adjusted_notional
            logger.info(f"Adjusted qty from {qty:.8f} to {adjusted_qty:.8f} to meet min notional ${min_notional}")
        else:
            return False, f"Order notional (${notional_value:.2f}) below minimum (${min_notional})", adjusted_qty, 0.0, 0.0
    
    # 7. Calculate TP/SL prices based on position side
    # FIXED: Use side parameter to correctly calculate TP/SL for SHORT positions
    normalized_side = side.upper() if side else "BUY"
    if normalized_side == "BUY":  # Long position
        # For LONG: TP above entry, SL below entry
        tp_price = price * (1 + tp_pct/100) if tp_pct > 0 else 0.0
        sl_price = price * (1 - sl_pct/100) if sl_pct > 0 else 0.0
    else:  # SHORT position
        # For SHORT: TP below entry (profit when price drops), SL above entry (loss when price rises)
        tp_price = price * (1 - tp_pct/100) if tp_pct > 0 else 0.0
        sl_price = price * (1 + sl_pct/100) if sl_pct > 0 else 0.0
    
    return True, "OK", adjusted_qty, tp_price, sl_price


def check_post_trade_risk(client: Client, agent_id: str, symbol: str, qty: float, leverage: int, filled_qty: float, avg_price: float) -> Dict[str, Any]:
    """
    Perform post-trade risk evaluation to check if the executed position exceeds risk limits.
    
    Args:
        client: Binance futures client
        agent_id: Agent identifier for logging
        symbol: Trading symbol
        qty: Original requested quantity
        leverage: Order leverage
        filled_qty: Actual filled quantity
        avg_price: Average entry price
        
    Returns:
        Dict with risk evaluation results
    """
    try:
        logger.info(f"[RiskPostCheck] Executed order OK. Checking post-trade exposure...")
        
        # Get account balance
        try:
            balances = _retryable_futures_account_balance(client)
            usdt_balance = 0.0
            for b in balances:
                if b["asset"] == "USDT":
                    usdt_balance = float(b["balance"])
                    break
        except Exception:
            usdt_balance = 0.0
        
        if usdt_balance <= 0:
            logger.warning(f"[RiskPostCheck] Could not fetch account balance for risk check")
            return {"action": "continue", "reason": "balance_unavailable"}
        
        # Calculate actual margin used
        notional_value = filled_qty * avg_price
        actual_margin = notional_value / leverage
        
        # Check against max margin per trade
        max_margin = settings.max_margin_per_trade
        min_margin = settings.MIN_MARGIN_PER_TRADE
        
        logger.info(f"[RiskPostCheck] Position analysis - Notional: ${notional_value:.2f}, Margin: ${actual_margin:.2f} (Min=${min_margin}, Max=${max_margin})")
        
        # Check if margin exceeds limits
        if actual_margin > max_margin:
            logger.warning(f"[RiskPostCheck] Margin ${actual_margin:.2f} exceeds max limit ${max_margin:.2f}")
            # Calculate reduction factor to bring within limits
            reduction_factor = max_margin / actual_margin
            reduced_qty = filled_qty * reduction_factor
            
            return {
                "action": "schedule_partial_close", 
                "reason": "margin_exceeded",
                "original_qty": filled_qty,
                "reduced_qty": reduced_qty,
                "reduction_factor": reduction_factor,
                "excess_margin": actual_margin - max_margin
            }
        
        # Check risk percentage vs balance
        risk_pct = 30.0  # Use 30% as intended
        max_risk_amount = usdt_balance * (risk_pct / 100)
        max_risk_per_trade_usd = getattr(settings, 'max_risk_per_trade_usd', 600.0)
        max_risk_amount = min(max_risk_amount, max_risk_per_trade_usd)
        
        if actual_margin > max_risk_amount:
            logger.warning(f"[RiskPostCheck] Risk ${actual_margin:.2f} exceeds limit ${max_risk_amount:.2f}")
            # Calculate reduction factor to bring within limits
            reduction_factor = max_risk_amount / actual_margin
            reduced_qty = filled_qty * reduction_factor
            
            return {
                "action": "schedule_partial_close", 
                "reason": "risk_exceeded",
                "original_qty": filled_qty,
                "reduced_qty": reduced_qty,
                "reduction_factor": reduction_factor,
                "excess_risk": actual_margin - max_risk_amount
            }
        
        logger.info(f"[RiskPostCheck] Exposure within limits - continuing normally")
        return {"action": "continue", "reason": "within_limits"}
        
    except Exception as e:
        logger.error(f"[RiskPostCheck] Error during post-trade risk evaluation: {e}")
        return {"action": "continue", "reason": "evaluation_error"}


def schedule_partial_close(symbol: str, side: str, excess_qty: float, agent_id: str = "system") -> bool:
    """
    Schedule and execute a partial close for positions that exceed risk limits.
    
    Args:
        symbol: Trading symbol
        side: Position side ('BUY' to close long, 'SELL' to close short)
        excess_qty: Quantity to close
        agent_id: Agent identifier for logging
        
    Returns:
        bool: True if scheduled and executed successfully
    """
    try:
        # Apply symbol-specific precision rounding
        safe_quantity = safe_qty(symbol, excess_qty)
        
        # Check minimum quantity
        MIN_QTY_MAP = {"BTCUSDT": 0.001, "BNBUSDT": 0.0001}
        min_qty = MIN_QTY_MAP.get(symbol, 0.001)
        if safe_quantity < min_qty:
            logger.warning(f"[RiskPostCheck] Skipping partial close: quantity {safe_quantity} below minimum {min_qty} for {symbol}")
            return False
        
        logger.info(f"[RiskPostCheck] Executing partial close: {side} {safe_quantity:.6f} {symbol}")
        
        # Execute the partial close immediately
        client = get_futures_client()
        if not client:
            logger.error(f"[RiskPostCheck] Failed to get client for partial close")
            return False
            
        # Place reduce-only market order for the excess quantity
        close_params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": safe_quantity,
            "reduceOnly": "true"
        }
        
        close_response = _retryable_futures_create_order(client, **close_params)
        close_order_id = str(close_response.get("orderId", "N/A"))
        
        logger.info(f"[RiskPostCheck] Partial close executed successfully: Order ID {close_order_id}")
        
        # Send Telegram notification
        if TELEGRAM_ENABLED:
            telegram_msg = (
                f"⚖️ PARTIAL POSITION REDUCTION\n"
                f"Symbol: {symbol}\n"
                f"Side: {side}\n"
                f"Quantity: {excess_qty:.6f}\n"
                f"Order ID: {close_order_id}"
            )
            send_message(telegram_msg)
        
        return True
    except Exception as e:
        logger.error(f"[RiskPostCheck] Failed to execute partial close: {e}")
        return False


def check_existing_position(client: Client, symbol: str) -> Optional[Dict[str, Any]]:
    """
    Check if there's an existing position for a symbol.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol (BTCUSDT format)
        
    Returns:
        Position dict if exists, None otherwise
    """
    try:
        positions = _retryable_futures_position_information(client, symbol=symbol)
        for pos in positions:
            if abs(float(pos.get("positionAmt", 0))) > 0:
                return pos
        return None
    except Exception as e:
        logger.error(f"Error checking existing position for {symbol}: {e}")
        return None


def monitor_positions(client: Client):
    """
    Monitor open positions and auto-close when TP/SL reached.
    This is a fallback mechanism in case the main trade_manager fails.
    """
    try:
        positions = client.futures_position_information()
        
        for position in positions:
            pos_amt = float(position.get("positionAmt", 0))
            if pos_amt == 0:
                continue
                
            symbol = position.get("symbol", "")
            entry_price = float(position.get("entryPrice", 0))
            if entry_price == 0:
                continue
            
            # Get current mark price
            try:
                mark_price_data = client.futures_mark_price(symbol=symbol)
                mark_price = float(mark_price_data.get("markPrice", 0))
            except Exception:
                continue
            
            # Calculate P&L percentage
            if pos_amt > 0:  # Long position
                pnl_pct = ((mark_price - entry_price) / entry_price) * 100
            else:  # Short position
                pnl_pct = ((entry_price - mark_price) / entry_price) * 100
            
            # Check TP/SL levels
            tp_level = _get_env_float("TAKE_PROFIT_PERCENT", 2.0)
            sl_level = _get_env_float("STOP_LOSS_PERCENT", 1.0)
            
            close_position = False
            close_reason = ""
            
            if pnl_pct >= tp_level:
                close_position = True
                close_reason = f"TP reached ({pnl_pct:.2f}%)"
            elif pnl_pct <= -sl_level:
                close_position = True
                close_reason = f"SL reached ({pnl_pct:.2f}%)"
            
            if close_position:
                # Apply symbol-specific precision rounding
                safe_quantity = safe_qty(symbol, abs(pos_amt))
                
                # Check minimum quantity
                MIN_QTY_MAP = {"BTCUSDT": 0.001, "BNBUSDT": 0.0001}
                min_qty = MIN_QTY_MAP.get(symbol, 0.001)
                if safe_quantity < min_qty:
                    logger.warning(f"[Monitor] Skipping position close: quantity {safe_quantity} below minimum {min_qty} for {symbol}")
                else:
                    # Close position
                    side = 'SELL' if pos_amt > 0 else 'BUY'
                    close_params = {
                        "symbol": symbol,
                        "side": side,
                        "type": "MARKET",
                        "quantity": safe_quantity,
                        "reduceOnly": "true"
                    }
                    close_response = client.futures_create_order(**close_params)
                    close_order_id = str(close_response.get("orderId", ""))
                    
                    logger.info(f"✅ Position closed {symbol}: {side} {safe_quantity:.8f} | {close_reason} | ID: {close_order_id}")
                    
                    # Send Telegram notification
                    if TELEGRAM_ENABLED:
                        telegram_msg = (
                            f"🔒 POSITION CLOSED\n"
                            f"Symbol: {symbol}\n"
                            f"Side: {side}\n"
                            f"Quantity: {safe_quantity:.6f}\n"
                            f"Reason: {close_reason}\n"
                            f"Order ID: {close_order_id}"
                        )
                        send_message(telegram_msg)
                
    except Exception as e:
        logger.error(f"Error monitoring positions: {e}")


def place_futures_order(
    symbol: str,
    side: str,
    qty: float,
    price: Optional[float] = None,
    leverage: int = 5,
    agent_id: str = "system",
    order_type: str = "MARKET",
    reduce_only: bool = False,
    skip_position_check: bool = False,
    allow_position_scaling: bool = False,
    max_position_multiplier: float = 1.5,
    tp_pct: float = 0.0,  # 0 means no TP/SL
    sl_pct: float = 0.0
) -> Dict[str, Any]:
    """
    Place a futures order with comprehensive safety checks and TP/SL support.
    
    Args:
        symbol: Trading symbol (BTC/USDT format)
        side: Order side ('BUY' or 'SELL')
        qty: Order quantity
        price: Order price (None for market orders)
        leverage: Leverage to use (1-125)
        agent_id: Agent identifier for logging
        order_type: Order type ('MARKET' or 'LIMIT')
        reduce_only: If True, only reduce existing position
        skip_position_check: If True, skip existing position check
        allow_position_scaling: If True, allow adding to existing positions in same direction
        max_position_multiplier: Maximum multiplier for position scaling
        tp_pct: Take profit percentage (0 = no TP)
        sl_pct: Stop loss percentage (0 = no SL)
        
    Returns:
        Dict with order status and details
    """
    logger.info(f"[OrderManager] 🚀 place_futures_order ENTRY: {symbol} {side} qty={qty} leverage={leverage} tp={tp_pct}% sl={sl_pct}%")
    
    # Get futures client
    logger.info(f"[OrderManager] Getting futures client...")
    try:
        client = get_futures_client()
        logger.info(f"[OrderManager] ✅ Futures client retrieved: {client is not None}")
    except Exception as e:
        logger.error(f"[OrderManager] ❌ Error getting futures client: {e}")
        import traceback
        logger.error(traceback.format_exc())
        client = None
    if not client:
        error_msg = "Futures client not initialized"
        logger.error(error_msg)
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "leverage": leverage,
            "status": "error",
            "message": error_msg
        }
    
    # Normalize symbol format
    logger.info(f"[OrderManager] Normalizing symbol: {symbol}")
    binance_symbol = symbol.replace("/", "").upper()
    normalized_side = side.upper()
    normalized_order_type = order_type.upper()
    original_qty = qty
    logger.info(f"[OrderManager] Symbol normalized: {binance_symbol}, side: {normalized_side}")
    
    # FIXED: Add debounce to order conflict handler (2-3s delay before checking)
    if not reduce_only and not skip_position_check:
        logger.info(f"[OrderManager] Checking position lock for {binance_symbol}...")
        # Add small debounce before checking positions (prevents false skips)
        _order_debounce_cache = getattr(place_futures_order, '_debounce_cache', {})
        now = time.time()
        debounce_key = f"{binance_symbol}_{normalized_side}"
        debounce_interval = 2.5  # 2.5 seconds
        
        if debounce_key in _order_debounce_cache:
            last_check_time = _order_debounce_cache[debounce_key]
            if (now - last_check_time) < debounce_interval:
                # Within debounce window - skip the check temporarily
                logger.debug(f"[Debounce] {binance_symbol} check debounced ({debounce_interval - (now - last_check_time):.1f}s remaining)")
        else:
            _order_debounce_cache[debounce_key] = now
            place_futures_order._debounce_cache = _order_debounce_cache
        
        # REMOVED: Position lock check - was causing hangs. Binance handles duplicate position prevention.
        # Just proceed with order placement
    
    # Get symbol-specific precision
    qty_precision, price_precision = get_symbol_specific_precision(binance_symbol)
    
    # Step -1: Enforce minimum holding and reversal cooldown (using settings)
    try:
        now_ts = time.time()
        min_holding = settings.min_holding_period
        reversal_cooldown = settings.reversal_cooldown_sec  # Use the new configurable cooldown

        last_ts = LAST_TRADE_TIME.get(binance_symbol, 0)
        cooldown_until = REVERSAL_COOLDOWN_UNTIL.get(binance_symbol, 0)

        # Check if we're in reversal cooldown
        if cooldown_until and now_ts < cooldown_until:
            # Check if we should override the cooldown based on signal strength
            should_override = False
            override_reason = ""
            
            # Check if majority of agents flip direction
            if binance_symbol in ACTIVE_AGENT_SIGNALS:
                signals = ACTIVE_AGENT_SIGNALS[binance_symbol]
                total_signals = len(signals)
                if total_signals > 0:
                    buy_signals = sum(1 for sig in signals.values() if sig.get('side', '').upper() == 'BUY')
                    sell_signals = sum(1 for sig in signals.values() if sig.get('side', '').upper() == 'SELL')
                    
                    # Check if majority flips direction
                    if (normalized_side == 'BUY' and sell_signals > buy_signals and 
                        (sell_signals / total_signals) > 0.5):
                        should_override = True
                        override_reason = f"Majority flip: {sell_signals}/{total_signals} agents flipped to BUY"
                    elif (normalized_side == 'SELL' and buy_signals > sell_signals and 
                          (buy_signals / total_signals) > 0.5):
                        should_override = True
                        override_reason = f"Majority flip: {buy_signals}/{total_signals} agents flipped to SELL"
            
            # If we should override, allow the trade
            if should_override:
                logger.info(f"[OrderManager] 🔁 Reversal override activated for {binance_symbol}: {override_reason}")
                # Clear the cooldown
                REVERSAL_COOLDOWN_UNTIL[binance_symbol] = 0
            else:
                # Otherwise, enforce the cooldown
                remaining = int(cooldown_until - now_ts)
                warning_msg = f"In reversal cooldown for {binance_symbol} ({remaining}s remaining)"
                logger.warning(f"[OrderManager] ⚠️ {warning_msg}")
                # Release symbol lock since we're not proceeding with the order
                release_position_lock(binance_symbol, success=False)
                return {
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "price": price,
                    "leverage": leverage,
                    "status": "skipped",
                    "message": warning_msg
                }

        # Enforce minimum holding period between any trades on same symbol
        if min_holding and last_ts and (now_ts - last_ts) < min_holding:
            remaining = int(min_holding - (now_ts - last_ts))
            warning_msg = f"Minimum holding period not met for {binance_symbol} ({remaining}s remaining)"
            logger.warning(warning_msg)
            # Release symbol lock since we're not proceeding with the order
            release_position_lock(binance_symbol, success=False)
            return {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "leverage": leverage,
                "status": "skipped",
                "message": warning_msg
            }
    except Exception:
        # If any error in protection logic, proceed without blocking
        # Release symbol lock since we're not proceeding with the order
        release_position_lock(binance_symbol, success=False)
        pass
    
    # Validate inputs
    if normalized_side not in ["BUY", "SELL"]:
        error_msg = f"Invalid side: {side} (must be BUY or SELL)"
        logger.error(error_msg)
        # Release symbol lock since we're not proceeding with the order
        release_position_lock(binance_symbol, success=False)
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "leverage": leverage,
            "status": "error",
            "message": error_msg
        }
        
    if qty <= 0:
        error_msg = f"Invalid quantity: {qty} (must be > 0)"
        logger.error(error_msg)
        # Release symbol lock since we're not proceeding with the order
        release_position_lock(binance_symbol, success=False)
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "leverage": leverage,
            "status": "error",
            "message": error_msg
        }
    
    # Validate order type
    if normalized_order_type not in ["MARKET", "LIMIT"]:
        error_msg = f"Invalid order type: {order_type} (must be MARKET or LIMIT)"
        logger.error(error_msg)
        # Release symbol lock since we're not proceeding with the order
        release_position_lock(binance_symbol, success=False)
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "leverage": leverage,
            "status": "error",
            "message": error_msg
        }
    
    # Step 0: Check order restrictions with TP/SL calculation
    # For reduce_only orders, skip TP/SL calculation
    tp_price: float = 0.0
    sl_price: float = 0.0
    adjusted_qty = qty
    
    if not reduce_only:
        # For entry orders, calculate TP/SL but don't attach yet
        # Calculate TP/SL prices for logging purposes only using precise math
        if tp_pct > 0 or sl_pct > 0:
            try:
                # Add 0.3s async-safe delay after order placement
                time.sleep(0.3)
                
                # Use the corrected _retryable_futures_symbol_ticker function with improved error handling
                try:
                    mark_price = _retryable_futures_symbol_ticker(client, binance_symbol)
                    logger.info(f"[OrderManager] Live ticker for {binance_symbol} fetched successfully: {mark_price}")
                except Exception as e:
                    logger.error(f"[OrderManager] Skipping {binance_symbol} due to ticker fetch failure: {e}")
                    # Clear cached state to avoid false cooldown
                    tp_price = 0.0
                    sl_price = 0.0
                    mark_price = 0.0
                    # Release symbol lock since we're not proceeding with the order
                    release_position_lock(binance_symbol, success=False)
                    return {
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                        "price": price,
                        "leverage": leverage,
                        "status": "error",
                        "message": f"Could not fetch price for {binance_symbol}"
                    }
                
                tp_price_calc = 0.0
                sl_price_calc = 0.0
                
                if mark_price > 0:
                    # FIXED: Correct TP/SL price calculation for both LONG and SHORT
                    # For LONG: TP above entry, SL below entry
                    # For SHORT: TP below entry, SL above entry
                    if normalized_side == "BUY":  # Long position
                        tp_price_calc = mark_price * (1 + tp_pct / 100)  # Above entry
                        sl_price_calc = mark_price * (1 - sl_pct / 100)  # Below entry
                    else:  # SHORT position
                        tp_price_calc = mark_price * (1 - tp_pct / 100)  # Below entry (profit when price drops)
                        sl_price_calc = mark_price * (1 + sl_pct / 100)  # Above entry (loss when price rises)
                
                # Normalize prices and ensure they are valid floats
                tp_price_norm, _ = normalize(binance_symbol, tp_price_calc)
                sl_price_norm, _ = normalize(binance_symbol, sl_price_calc)
                
                # Ensure we have valid float values (fallback to 0.0 if None)
                tp_price = float(tp_price_norm) if tp_price_norm is not None else 0.0
                sl_price = float(sl_price_norm) if sl_price_norm is not None else 0.0

                logger.info(f"[TPSL] Calculated TP@{tp_price} SL@{sl_price} for {binance_symbol}")
            except Exception as e:
                logger.warning(f"Could not calculate TP/SL prices for {binance_symbol}: {e}")
                tp_price = 0.0
                sl_price = 0.0
    
    # Step 1: Check for existing position (unless skipped or reduce_only)
    # Keep existing position checks as they are part of pre-trade validation
    if not skip_position_check and not reduce_only:
        existing_position = check_existing_position(client, binance_symbol)
        if existing_position:
            position_amt = float(existing_position.get('positionAmt', 0))
            position_side = 'long' if position_amt > 0 else 'short'
            requested_side = 'long' if normalized_side == 'BUY' else 'short'
            
            # Check if position scaling is allowed
            if allow_position_scaling and position_side == requested_side:
                # Calculate total position if we scale in
                total_position_qty = abs(position_amt) + qty
                max_allowed_qty = qty * max_position_multiplier
                
                if total_position_qty <= max_allowed_qty:
                    logger.info(
                        f"📈 Scaling into {binance_symbol} position: "
                        f"current={abs(position_amt):.4f}, adding={qty:.4f}, "
                        f"total={total_position_qty:.4f} (max={max_allowed_qty:.4f})"
                    )
                    # Allow the order to proceed
                else:
                    warning_msg = (
                        f"⚠️  Position scaling limit reached for {binance_symbol}: "
                        f"total would be {total_position_qty:.4f} > max {max_allowed_qty:.4f}"
                    )
                    logger.warning(warning_msg)
                    # Release symbol lock since we're not proceeding with the order
                    release_position_lock(binance_symbol, success=False)
                    return {
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                        "price": price,
                        "leverage": leverage,
                        "status": "skipped",
                        "message": warning_msg,
                        "existing_position": existing_position
                    }
            else:
                # Position exists and scaling not allowed, or opposite direction
                # Implement auto-reversal logic as requested
                if position_side != requested_side:
                    logger.info(f"[OrderManager] 🔁 Auto-closing {position_side.upper()} for {binance_symbol} before opening {requested_side.upper()}...")
                    
                    # Close existing position
                    close_side = 'SELL' if position_side == 'long' else 'BUY'
                    close_params = {
                        "symbol": binance_symbol,
                        "side": close_side,
                        "type": "MARKET",
                        "quantity": abs(position_amt),
                        "reduceOnly": "true"
                    }
                    
                    try:
                        close_response = client.futures_create_order(**close_params)
                        close_order_id = str(close_response.get("orderId", ""))
                        logger.info(f"[OrderManager] ✅ Auto-closed existing {position_side} position for {binance_symbol} | ID: {close_order_id}")
                        
                        # Update current position side tracking
                        CURRENT_POSITION_SIDE[binance_symbol] = 'NONE'
                        
                        # Send Telegram notification for auto-close
                        if TELEGRAM_ENABLED:
                            telegram_msg = (
                                f"🔁 AUTO-REVERSAL\n"
                                f"Symbol: {binance_symbol}\n"
                                f"Closed: {position_side.upper()} position\n"
                                f"Order ID: {close_order_id}"
                            )
                            send_message(telegram_msg)
                    except Exception as e:
                        logger.error(f"[OrderManager] Failed to auto-close existing position for {binance_symbol}: {e}")
                        # Release symbol lock since we're not proceeding with the order
                        release_position_lock(binance_symbol, success=False)
                        return {
                            "symbol": symbol,
                            "side": side,
                            "qty": qty,
                            "price": price,
                            "leverage": leverage,
                            "status": "error",
                            "message": f"Failed to auto-close existing position: {e}"
                        }
                    
                    # FIXED: Wait for position closure to be confirmed by Binance (prevents race condition)
                    time.sleep(0.3)  # 300ms delay for Binance to process the close order
                    
                    # Verify position is closed by checking one more time
                    try:
                        verify_positions = client.futures_position_information(symbol=binance_symbol)
                        position_still_exists = False
                        for pos in verify_positions:
                            if pos.get("symbol") == binance_symbol:
                                pos_amt = float(pos.get("positionAmt", 0))
                                if abs(pos_amt) > 0:
                                    position_still_exists = True
                                    logger.warning(f"[OrderManager] ⚠️ Position still exists after auto-close for {binance_symbol}, waiting longer...")
                                    time.sleep(0.5)  # Additional wait if position still exists
                                    break
                        
                        if position_still_exists:
                            # Position still exists after auto-close - this shouldn't happen but handle it gracefully
                            logger.error(f"[OrderManager] ❌ Failed to verify position closure for {binance_symbol}, skipping new order")
                            release_position_lock(binance_symbol, success=False)
                            return {
                                "symbol": symbol,
                                "side": side,
                                "qty": qty,
                                "price": price,
                                "leverage": leverage,
                                "status": "error",
                                "message": "Position closure verification failed"
                            }
                    except Exception as verify_error:
                        logger.warning(f"[OrderManager] Could not verify position closure: {verify_error}, proceeding anyway")
                    
                    # FIXED: Cleanup TP/SL orders from closed position (prevents dangling orders)
                    try:
                        cancelled_count = cleanup_open_orders(client, binance_symbol)
                        if cancelled_count > 0:
                            logger.info(f"[Auto-Reversal] ✅ Cancelled {cancelled_count} TP/SL orders for closed {position_side.upper()} position")
                    except Exception as cleanup_error:
                        logger.warning(f"[Auto-Reversal] Could not cleanup orders: {cleanup_error}")
                    
                    # Update last trade time and side (will be updated again after new order is placed)
                    LAST_TRADE_TIME[binance_symbol] = time.time()
                    LAST_TRADE_SIDE[binance_symbol] = requested_side.upper()
                    
                    # Clear position side tracking temporarily (will be set after new order)
                    CURRENT_POSITION_SIDE[binance_symbol] = 'NONE'
                    
                    # FIXED: Continue with order placement instead of returning early
                    # The opposite position is now closed, so we can proceed to place the new order
                    logger.info(f"[OrderManager] ✅ Opposite position closed, proceeding to place new {requested_side.upper()} order")
                    # Don't release lock or return - continue to Step 2 (can_place_order check) and Step 3 (order placement)
    
    # Step 2: Check if order can be placed (risk management rules)
    can_place, reason, adjusted_qty, tp_price, sl_price = can_place_order(
        client,
        binance_symbol,
        adjusted_qty,
        leverage,
        agent_id,
        tp_pct,
        sl_pct,
        side=normalized_side
    )
    if not can_place:
        logger.warning(f"[OrderManager] Order rejected: {reason}")
        # Log rejection to CSV
        log_error("order_manager", agent_id, binance_symbol, "order_rejection", reason,
                 f"Order rejected during validation: side={side}, qty={qty}, leverage={leverage}", "", 0)
        # Release symbol lock since we're not proceeding with the order
        release_position_lock(binance_symbol, success=False)
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "leverage": leverage,
            "status": "skipped",
            "message": reason
        }
    
    # Step 2: Adjust precision using symbol-specific precision
    try:
        # Use BinanceGuard for precision adjustment with symbol-specific settings
        guard = BinanceGuard(client)
        adjusted_qty = guard.quantize_quantity(binance_symbol, qty)
        adjusted_price = guard.quantize_price(binance_symbol, price) if price is not None else None
        
        # Ensure we still have a valid quantity after precision adjustment
        if adjusted_qty <= 0:
            error_msg = f"Adjusted quantity is invalid: {adjusted_qty}"
            logger.error(error_msg)
            # Log error to CSV
            log_error("order_manager", agent_id, binance_symbol, "precision_error", error_msg,
                     f"Quantity precision adjustment failed: original={qty}, adjusted={adjusted_qty}", "", 0)
            # Release symbol lock since we're not proceeding with the order
            release_position_lock(binance_symbol, success=False)
            return {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "leverage": leverage,
                "status": "error",
                "message": error_msg
            }
            
        # Apply symbol-specific precision rounding
        qty_precision, price_precision = get_symbol_specific_precision(binance_symbol)
        adjusted_qty = round(adjusted_qty, qty_precision)
        if adjusted_price is not None:
            adjusted_price = round(adjusted_price, price_precision)
            
    except Exception as e:
        error_msg = f"Precision adjustment failed for {binance_symbol}: {e}"
        logger.error(error_msg)
        # Release symbol lock since we're not proceeding with the order
        release_position_lock(binance_symbol, success=False)
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "leverage": leverage,
            "status": "error",
            "message": error_msg
        }
    
    # Step 3: Set leverage
    if not reduce_only:
        set_leverage(client, binance_symbol, leverage)
    
    # Step 4: Place the order
    try:
        order_params = {
            "symbol": binance_symbol,
            "side": normalized_side,
            "type": normalized_order_type,
            "quantity": adjusted_qty,
        }
        
        # Add price for LIMIT orders
        if normalized_order_type == "LIMIT":
            if adjusted_price is None:
                error_msg = "LIMIT orders require a price"
                logger.error(error_msg)
                # Release symbol lock since we're not proceeding with the order
                release_position_lock(binance_symbol, success=False)
                return {
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "price": price,
                    "leverage": leverage,
                    "status": "error",
                    "message": error_msg
                }
            order_params["price"] = adjusted_price
            order_params["timeInForce"] = "GTC"
        
        # Add reduce_only parameter
        if reduce_only:
            order_params["reduceOnly"] = "true"
        
        # === [ApexPatch2025-10-31] Precision Normalizer ===
        # Normalize qty and price to Binance futures precision limits
        logger.debug(f"[OrderExecution] Normalizing precision for {binance_symbol}...")
        try:
            qty, price = normalize_order_precision(client, binance_symbol, adjusted_qty, adjusted_price)
            logger.debug(f"[OrderExecution] Precision normalized: qty={qty}, price={price}")
        except Exception as e:
            logger.error(f"[OrderExecution] Precision normalization failed: {e}")
            release_position_lock(binance_symbol, success=False)
            return {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "leverage": leverage,
                "status": "error",
                "message": f"Precision normalization failed: {e}"
            }
        
        order_params["quantity"] = qty
        if "price" in order_params:
            order_params["price"] = price
        
        # Execute order
        logger.info(f"[OrderExecution] Creating {normalized_side} order for {binance_symbol}: qty={qty}, price={price}")
        logger.debug(f"[OrderExecution] Order params: {order_params}")
        
        try:
            # Execute order with retry wrapper (has built-in timeout via retry limits)
            order_response = _retryable_futures_create_order(client, **order_params)
            
            if order_response is None:
                raise Exception("Order creation returned None response")
                
            logger.info(f"[OrderExecution] ✅ Order created: {order_response.get('orderId', 'N/A')}")
        except Exception as e:
            logger.error(f"[OrderExecution] ❌ Order creation failed for {binance_symbol}: {e}")
            import traceback
            logger.error(f"[OrderExecution] Full traceback:\n{traceback.format_exc()}")
            release_position_lock(binance_symbol, success=False)
            raise
        
        # Parse response
        order_id = str(order_response.get("orderId", "N/A"))
        filled_qty = float(order_response.get("executedQty", adjusted_qty))
        avg_price = float(order_response.get("avgPrice", adjusted_price or 0))
        order_status = order_response.get("status", "UNKNOWN")
        
        # Confirm order fill
        confirmed_order = confirm_order_fill(client, binance_symbol, order_id)
        if confirmed_order:
            filled_qty = float(confirmed_order.get("executedQty", filled_qty))
            avg_price = float(confirmed_order.get("avgPrice", avg_price))
        
        # Log successful order placement
        logger.info(f"[OrderPlaced] {binance_symbol} {normalized_side} {filled_qty:.{qty_precision}f} @ {avg_price:.{price_precision}f} (Lev {leverage}x)")
        
        # Place TP/SL orders if specified (AFTER position confirmation to avoid race condition)
        tp_order_id = None
        sl_order_id = None
        if tp_price > 0 or sl_price > 0:
            # CRITICAL FIX: Wait for position confirmation before placing TP/SL
            # This fixes BTC SL attach race condition where Binance hasn't synced position yet
            if not reduce_only:  # Only wait for new positions, not closes
                position_confirmed = wait_for_position_confirmation(
                    client, binance_symbol, normalized_side, max_wait_seconds=2.0, poll_interval=0.2
                )
                if not position_confirmed:
                    logger.warning(f"[TP/SL] Position confirmation timeout for {binance_symbol}, attempting TP/SL anyway...")
                else:
                    logger.info(f"[TP/SL] Position confirmed for {binance_symbol}, proceeding with TP/SL attachment")
            
            tp_order_id, sl_order_id = place_take_profit_and_stop_loss(
                client, binance_symbol, normalized_side, filled_qty, tp_price, sl_price, agent_id, leverage=leverage
            )
            
            # STRENGTHENED DUAL-LEG VERIFICATION: Require both TP and SL to be confirmed
            # This ensures no false positives where only one leg exists
            if tp_order_id and sl_order_id:
                # DEBUG: Log both calculated prices AND trigger prices used
                # Note: tp_price/sl_price are the calculated prices, but actual triggers may differ due to safety margins
                logger.info(f"[TP/SL] ✅ TP/SL successfully attached for {binance_symbol}")
                logger.info(f"[TP/SL]   Calculated: TP={tp_price:.{price_precision}f}, SL={sl_price:.{price_precision}f}")
                logger.info(f"[TP/SL]   Order IDs: TP={tp_order_id[:8]}, SL={sl_order_id[:8]}")
                logger.debug(f"[TP/SL]   Note: Actual trigger prices may differ due to safety margins (see [TPSL-Debug] logs)")
            elif tp_order_id:
                logger.warning(f"[TP/SL] ⚠️ Only TP attached → TP={tp_price:.{price_precision}f} (ID: {tp_order_id[:8]}), SL missing - will retry via SentinelAgent")
                # Set flag for SentinelAgent to pick up missing SL
                sl_order_id = None  # Ensure we know SL is missing
            elif sl_order_id:
                logger.warning(f"[TP/SL] ⚠️ Only SL attached → SL={sl_price:.{price_precision}f} (ID: {sl_order_id[:8]}), TP missing - will retry via SentinelAgent")
                # Set flag for SentinelAgent to pick up missing TP
                tp_order_id = None  # Ensure we know TP is missing
            else:
                logger.error(f"[TP/SL] ❌ Both TP and SL failed to attach for {binance_symbol} - will retry via SentinelAgent")

        # === [ApexPatch2025-10-31] Post-Trade Risk Management ===
        # Perform risk evaluation after order execution and TP/SL placement
        risk_result = {"action": "not_applicable"}  # Initialize with default value
        if not reduce_only and not skip_position_check:
            logger.info(f"[RiskPostCheck] Executed order OK. Checking exposure...")
            risk_result = check_post_trade_risk(
                client, agent_id, binance_symbol, qty, leverage, filled_qty, avg_price
            )
            
            if risk_result["action"] == "schedule_partial_close":
                logger.warning(f"[RiskPostCheck] Exposure exceeds limit — scheduling partial close.")
                excess_qty = filled_qty - risk_result["reduced_qty"]
                close_side = 'SELL' if normalized_side == 'BUY' else 'BUY'
                
                # Schedule partial close for the excess quantity
                schedule_partial_close(binance_symbol, close_side, excess_qty, agent_id)
                
                # Log the risk adjustment
                logger.info(
                    f"[RiskPostCheck] Scheduled reduction: {excess_qty:.6f} of {filled_qty:.6f} "
                    f"({risk_result['reduction_factor']:.2%} reduction) due to {risk_result['reason']}"
                )
            elif risk_result["action"] == "continue":
                logger.info(f"[RiskPostCheck] Position within risk limits - continuing normally")

        # Log SUCCESS to CSV
        _append_order_log(
            agent_id=agent_id,
            symbol=binance_symbol,
            side=normalized_side,
            qty=adjusted_qty,
            price=avg_price,
            leverage=leverage,
            status="OPENED",
            message=f"Order {order_id} filled",
            order_id=order_id
        )
        
        # Update last trade state for holding period/hysteresis
        try:
            LAST_TRADE_TIME[binance_symbol] = time.time()
            LAST_TRADE_SIDE[binance_symbol] = normalized_side
        except Exception:
            pass
        
        # Add specific logging for successful closes
        if reduce_only and agent_id != "system":  # This is likely a close order
            logger.info(f"[ApexPatch2025-10-30] ✅ Auto-closed {normalized_side} position @ {avg_price:.4f}")
        
        # Add specific logging for successful closes
        if reduce_only and skip_position_check:  # This is likely a close order
            logger.info(f"[OrderManager] ✅ Auto-closed {normalized_side} position @ {avg_price:.4f}")
            # Update current position side tracking
            CURRENT_POSITION_SIDE[binance_symbol] = 'NONE'
        else:
            # Update current position side tracking for new positions
            CURRENT_POSITION_SIDE[binance_symbol] = normalized_side
        
        # Release symbol lock since order was successful
        release_position_lock(binance_symbol, success=True)
        
        # Prepare result with risk management information
        result = {
            "symbol": symbol,
            "side": side.lower(),
            "qty": filled_qty,
            "price": avg_price,
            "leverage": leverage,
            "status": "success",
            "order_id": order_id,
            "order_status": order_status,
            "tp_order_id": tp_order_id,
            "sl_order_id": sl_order_id,
            "message": f"Order {order_id} placed successfully"
        }
        
        # Add risk management information if applicable
        if not reduce_only and not skip_position_check and risk_result.get("action") == "schedule_partial_close":
            result["risk_action"] = "partial_close_executed"
            reduced_qty = float(risk_result.get("reduced_qty", filled_qty))
            result["excess_qty"] = filled_qty - reduced_qty
            result["reduction_reason"] = risk_result.get("reason", "unknown")
        
        return result
        
    except BinanceAPIException as e:
        error_msg = f"Binance API error: {e.message} (code: {e.code})"
        logger.error(f"[OrderManager] ❌ Order failed for {binance_symbol}: {error_msg}")
        
        # Log error to CSV
        log_error("order_manager", agent_id, binance_symbol, "binance_api_error", error_msg,
                 f"Binance API exception: side={side}, qty={qty}, leverage={leverage}, code={e.code}", "", 0)
        
        # Release symbol lock since order failed
        release_position_lock(binance_symbol, success=False)
        
        # Get symbol precision for logging
        qty_precision, price_precision = get_symbol_precision(client, binance_symbol) if 'client' in locals() else (3, 2)
        
        # Send Telegram notification for order error
        if TELEGRAM_ENABLED:
            telegram_msg = (
                f"❌ ORDER FAILED\n"
                f"Symbol: {binance_symbol}\n"
                f"Side: {normalized_side}\n"
                f"Quantity: {adjusted_qty:.{qty_precision}f}\n"
                f"Error: {error_msg}"
            )
            send_message(telegram_msg)
        
        # Log ERROR to CSV
        _append_order_log(
            agent_id=agent_id,
            symbol=binance_symbol,
            side=normalized_side,
            qty=adjusted_qty,
            price=(adjusted_price or 0.0),
            leverage=leverage,
            status="ERROR",
            message=error_msg
        )
        
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "leverage": leverage,
            "status": "error",
            "message": error_msg
        }
    except Exception as e:
        error_msg = f"Order execution failed: {str(e)}"
        logger.error(f"[OrderManager] ❌ Order failed for {binance_symbol}: {error_msg}", exc_info=True)
        
        # Log error to CSV
        log_error("order_manager", agent_id, binance_symbol, "order_execution_exception", error_msg,
                 f"Order execution exception: side={side}, qty={qty}, leverage={leverage}", "", 0)
        
        # Release symbol lock since order failed
        release_position_lock(binance_symbol, success=False)
        
        # Get symbol precision for logging
        qty_precision, price_precision = get_symbol_precision(client, binance_symbol) if 'client' in locals() else (3, 2)
        
        # Send Telegram notification for order error
        if TELEGRAM_ENABLED:
            telegram_msg = (
                f"❌ ORDER FAILED\n"
                f"Symbol: {binance_symbol}\n"
                f"Side: {normalized_side}\n"
                f"Quantity: {adjusted_qty:.{qty_precision}f}\n"
                f"Error: {error_msg}"
            )
            send_message(telegram_msg)
        
        # Log ERROR to CSV
        _append_order_log(
            agent_id=agent_id,
            symbol=binance_symbol,
            side=normalized_side,
            qty=adjusted_qty,
            price=(adjusted_price or 0.0),
            leverage=leverage,
            status="ERROR",
            message=error_msg
        )
        
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "leverage": leverage,
            "status": "error",
            "message": error_msg
        }


def close_position(symbol: str, side: str, qty: float, max_retries: int = 3, forced_event: bool = False) -> Dict[str, Any]:
    """
    Close a position with reduce-only order with retry mechanism.
    
    Args:
        symbol: Trading symbol (BTC/USDT format)
        side: Close side ('BUY' to close short, 'SELL' to close long)
        qty: Quantity to close
        max_retries: Maximum number of retry attempts
        forced_event: If True, bypass minimum holding period
        
    Returns:
        Dict with close result details
    """
    # Apply symbol-specific precision rounding
    binance_symbol = symbol.replace('/', '').upper()
    safe_quantity = safe_qty(binance_symbol, qty)
    
    # Check minimum quantity
    MIN_QTY_MAP = {"BTCUSDT": 0.001, "BNBUSDT": 0.0001}
    min_qty = MIN_QTY_MAP.get(binance_symbol, 0.001)
    if safe_quantity < min_qty:
        logger.warning(f"[OrderManager] Skipping close: quantity {safe_quantity} below minimum {min_qty} for {binance_symbol}")
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "status": "skipped",
            "message": f"Quantity {safe_quantity} below minimum {min_qty}"
        }
    
    last_exception = None
    client = get_futures_client()
    
    # Bypass minimum holding period for forced events (risk management, cleanup)
    skip_position_check = forced_event
    
    for attempt in range(max_retries):
        try:
            result = place_futures_order(
                symbol=symbol,
                side=side,
                qty=safe_quantity,
                leverage=1,  # Use leverage 1 for closing
                order_type="MARKET",
                reduce_only=True,
                skip_position_check=skip_position_check
            )
            
            # If successful, cleanup any dangling orders and return the result
            if result.get('status') in ['success', 'skipped']:
                # Cleanup any dangling TP/SL orders after position close
                if client:
                    cancelled_count = cleanup_open_orders(client, symbol.replace('/', '').upper())
                    if cancelled_count > 0:
                        logger.info(f"[Cleanup] Cancelled {cancelled_count} dangling orders for {symbol} after position close.")
                return result
            
            # Log the failure but continue to retry
            logger.warning(f"[OrderManager] ⚠️ Close position attempt {attempt + 1} failed: {result.get('message', 'Unknown error')}")
            last_exception = result.get('message', 'Unknown error')
            
        except Exception as e:
            logger.warning(f"[OrderManager] ⚠️ Close position attempt {attempt + 1} failed with exception: {e}")
            last_exception = str(e)
        
        # Wait before retrying (100ms delay)
        if attempt < max_retries - 1:  # Don't wait after the last attempt
            time.sleep(0.1)
    
    # If we get here, all retries failed
    logger.error(f"[OrderManager] ❌ Failed to close position after {max_retries} attempts: {last_exception}")
    return {
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "status": "error",
        "message": f"Failed to close position after {max_retries} attempts: {last_exception}"
    }


def get_current_position(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get current position for a symbol.
    
    Args:
        symbol: Trading symbol (BTC/USDT format)
        
    Returns:
        Position dict if exists, None otherwise
    """
    try:
        client = get_futures_client()
        if not client:
            return None
            
        binance_symbol = symbol.replace("/", "").upper()
        positions = _retryable_futures_position_information(client, symbol=binance_symbol)
        
        for position in positions:
            if position.get("symbol") == binance_symbol:
                position_amt = float(position.get("positionAmt", 0))
                if position_amt != 0:
                    return position
        return None
    except Exception as e:
        logger.error(f"Error getting current position for {symbol}: {e}")
        return None


def set_leverage(client: Client, symbol: str, leverage: int) -> bool:
    """
    Set leverage for a symbol.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol (BTCUSDT format)
        leverage: Leverage to set (1-125)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Cap leverage at maximum allowed
        max_leverage = getattr(settings, 'max_leverage', 125)
        capped_leverage = min(leverage, max_leverage)
        
        _retryable_futures_change_leverage(client, symbol=symbol, leverage=capped_leverage)
        logger.info(f"✅ Leverage set to {capped_leverage}x for {symbol}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to set leverage for {symbol}: {e}")
        return False


def confirm_order_fill(client: Client, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
    """
    Confirm that an order has been filled and get the filled details.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        order_id: Order ID to confirm
        
    Returns:
        Order details dict if filled, None otherwise
    """
    try:
        order = _retryable_futures_get_order(client, symbol=symbol, orderId=order_id)
        status = order.get("status", "")
        
        # Check if order is filled or partially filled
        if status in ["FILLED", "PARTIALLY_FILLED"]:
            return order
        elif status == "NEW":
            # Order is still open, wait a bit and try again
            time.sleep(0.1)
            order = _retryable_futures_get_order(client, symbol=symbol, orderId=order_id)
            status = order.get("status", "")
            if status in ["FILLED", "PARTIALLY_FILLED"]:
                return order
        return None
    except Exception as e:
        logger.warning(f"Error confirming order fill for {symbol} order {order_id}: {e}")
        return None


def wait_for_position_confirmation(client: Client, symbol: str, expected_side: str, max_wait_seconds: float = 2.0, poll_interval: float = 0.2) -> bool:
    """
    Wait for Binance to recognize the new position after order execution.
    This fixes the race condition where TP/SL orders fail because position isn't synced yet.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        expected_side: Expected position side ('BUY' for long, 'SELL' for short)
        max_wait_seconds: Maximum time to wait (default 2.0 seconds)
        poll_interval: How often to check (default 0.2 seconds = 200ms)
        
    Returns:
        True if position confirmed, False if timeout
    """
    start_time = time.time()
    expected_position_amt_sign = 1.0 if expected_side.upper() == "BUY" else -1.0
    
    while (time.time() - start_time) < max_wait_seconds:
        try:
            positions = _retryable_futures_position_information(client, symbol=symbol)
            for pos in positions:
                position_amt = float(pos.get("positionAmt", 0))
                
                # Check if position exists and matches expected direction
                if abs(position_amt) > 0:
                    # Check direction matches (same sign)
                    if (position_amt > 0 and expected_position_amt_sign > 0) or \
                       (position_amt < 0 and expected_position_amt_sign < 0):
                        logger.info(f"[PositionConfirm] Position confirmed for {symbol}: {position_amt}")
                        return True
            
            # Position not ready yet, wait and retry
            time.sleep(poll_interval)
            
        except Exception as e:
            logger.warning(f"[PositionConfirm] Error checking position for {symbol}: {e}")
            time.sleep(poll_interval)
    
    logger.warning(f"[PositionConfirm] Timeout waiting for position confirmation for {symbol} after {max_wait_seconds}s")
    return False


def place_take_profit_and_stop_loss(client: Client, symbol: str, side: str, qty: float, tp_price: float, sl_price: float, agent_id: str = "system", leverage: int = 2) -> tuple[Optional[str], Optional[str]]:
    """
    Place take profit and stop loss orders for a position.
    
    FIXED: Includes hash-based deduplication to prevent duplicate orders.
    COMPREHENSIVE: Handles all edge cases and validation scenarios.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        side: Position side ('BUY' or 'SELL')
        qty: Position quantity
        tp_price: Take profit price
        sl_price: Stop loss price
        agent_id: Agent identifier for logging
        leverage: Leverage used (1-125)
        
    Returns:
        Tuple of (tp_order_id, sl_order_id) or (None, None) if failed
    """
    tp_order_id = None
    sl_order_id = None
    
    # ===== COMPREHENSIVE INPUT VALIDATION =====
    # 1. Client validation
    if not client:
        logger.error(f"[TPSL] ❌ Invalid client (symbol not yet validated)")
        return None, None
    
    # 2. Symbol validation
    if not symbol or not isinstance(symbol, str):
        logger.error(f"[TPSL] ❌ Invalid symbol: {symbol}")
        return None, None
    
    # Normalize symbol format
    binance_symbol = symbol.replace("/", "").upper() if "/" in symbol else symbol.upper()
    if not binance_symbol or len(binance_symbol) < 4:
        logger.error(f"[TPSL] ❌ Invalid symbol format: {symbol} -> {binance_symbol}")
        return None, None
    
    # 3. Side validation
    if not side or not isinstance(side, str):
        logger.error(f"[TPSL] ❌ Invalid side for {binance_symbol}: {side}")
        return None, None
    
    normalized_side = side.upper()
    if normalized_side not in ["BUY", "SELL"]:
        logger.error(f"[TPSL] ❌ Invalid side value for {binance_symbol}: {side} (must be BUY or SELL)")
        return None, None
    
    is_long = normalized_side == "BUY"
    
    # 4. Quantity validation
    if not isinstance(qty, (int, float)) or qty <= 0:
        logger.error(f"[TPSL] ❌ Invalid quantity for {binance_symbol}: {qty} (must be > 0)")
        return None, None
    
    if qty > 1000000:  # Sanity check: prevent unreasonably large quantities
        logger.error(f"[TPSL] ❌ Quantity too large for {binance_symbol}: {qty} (max 1,000,000)")
        return None, None
    
    # 5. Leverage validation
    if not isinstance(leverage, int) or leverage < 1 or leverage > 125:
        logger.warning(f"[TPSL] ⚠️ Invalid leverage for {binance_symbol}: {leverage}, using default 2x")
        leverage = 2
    
    # 6. TP/SL price validation
    # Check for valid numeric values
    if not isinstance(tp_price, (int, float)) or not isinstance(sl_price, (int, float)):
        logger.error(f"[TPSL] ❌ Invalid TP/SL prices for {binance_symbol}: TP={tp_price}, SL={sl_price} (must be numeric)")
        return None, None
    
    # Check for negative or zero prices
    if tp_price < 0 or sl_price < 0:
        logger.error(f"[TPSL] ❌ Negative TP/SL prices for {binance_symbol}: TP={tp_price}, SL={sl_price}")
        return None, None
    
    # Check if both TP and SL are zero (no TP/SL to place)
    if tp_price == 0 and sl_price == 0:
        logger.info(f"[TPSL] No TP/SL to place for {binance_symbol} (both are 0)")
        return None, None
    
    # Get current mark price for validation
    try:
        mark_price_data = client.futures_mark_price(symbol=binance_symbol)
        mark_price = float(mark_price_data.get("markPrice", 0))
    except Exception as e:
        logger.warning(f"[TPSL] Could not fetch mark price for {binance_symbol}: {e}, using fallback")
        mark_price = tp_price if tp_price > 0 else sl_price if sl_price > 0 else 0
    
    if mark_price <= 0:
        logger.error(f"[TPSL] ❌ Invalid mark price for {binance_symbol}: {mark_price}")
        return None, None
    
    # 7. Validate TP/SL direction logic
    # For LONG: TP should be above entry/mark, SL should be below
    # For SHORT: TP should be below entry/mark, SL should be above
    if is_long:
        if tp_price > 0 and tp_price < mark_price:
            logger.error(f"[TPSL] ❌ Invalid LONG TP for {binance_symbol}: TP={tp_price} < Mark={mark_price} (TP must be above entry for LONG)")
            return None, None
        if sl_price > 0 and sl_price > mark_price:
            logger.error(f"[TPSL] ❌ Invalid LONG SL for {binance_symbol}: SL={sl_price} > Mark={mark_price} (SL must be below entry for LONG)")
            return None, None
    else:  # SHORT
        if tp_price > 0 and tp_price > mark_price:
            logger.error(f"[TPSL] ❌ Invalid SHORT TP for {binance_symbol}: TP={tp_price} > Mark={mark_price} (TP must be below entry for SHORT)")
            return None, None
        if sl_price > 0 and sl_price < mark_price:
            logger.error(f"[TPSL] ❌ Invalid SHORT SL for {binance_symbol}: SL={sl_price} < Mark={mark_price} (SL must be above entry for SHORT)")
            return None, None
    
    # 8. Check if TP/SL are too close to mark price (immediate trigger risk)
    try:
        guard = BinanceGuard(client)
        filters = guard.get_symbol_filters(binance_symbol)
        tick_size = filters.get('tickSize', 0.01)
        min_safety_distance = tick_size * 3  # At least 3 ticks away
        
        if tp_price > 0:
            distance = abs(tp_price - mark_price)
            if distance < min_safety_distance:
                logger.warning(f"[TPSL] ⚠️ TP too close to mark for {binance_symbol}: TP={tp_price}, Mark={mark_price}, Distance={distance:.8f} (min={min_safety_distance:.8f})")
                # Adjust TP to safe distance
                if is_long:
                    tp_price = mark_price + min_safety_distance
                else:
                    tp_price = mark_price - min_safety_distance
                logger.info(f"[TPSL] Adjusted TP to {tp_price:.8f} for safety")
        
        if sl_price > 0:
            distance = abs(sl_price - mark_price)
            if distance < min_safety_distance:
                logger.warning(f"[TPSL] ⚠️ SL too close to mark for {binance_symbol}: SL={sl_price}, Mark={mark_price}, Distance={distance:.8f} (min={min_safety_distance:.8f})")
                # Adjust SL to safe distance
                if is_long:
                    sl_price = mark_price - min_safety_distance
                else:
                    sl_price = mark_price + min_safety_distance
                logger.info(f"[TPSL] Adjusted SL to {sl_price:.8f} for safety")
    except Exception as e:
        logger.warning(f"[TPSL] Could not validate TP/SL distance for {binance_symbol}: {e}")
        # Continue anyway - safety margin will be applied later
    
    # 9. Check if TP and SL are on wrong sides (crossed orders)
    if tp_price > 0 and sl_price > 0:
        if is_long:
            if tp_price <= sl_price:
                logger.error(f"[TPSL] ❌ Crossed TP/SL for LONG {binance_symbol}: TP={tp_price} <= SL={sl_price} (TP must be > SL for LONG)")
                return None, None
        else:  # SHORT
            if tp_price >= sl_price:
                logger.error(f"[TPSL] ❌ Crossed TP/SL for SHORT {binance_symbol}: TP={tp_price} >= SL={sl_price} (TP must be < SL for SHORT)")
                return None, None
    
    # FIXED: Hash-based TP/SL deduplication to prevent duplicate orders
    try:
        from core.trade_state_manager import generate_tpsl_hash, is_tpsl_duplicate, register_tpsl_order
        tpsl_hash = generate_tpsl_hash(binance_symbol, normalized_side, tp_price, sl_price)
        
        if is_tpsl_duplicate(binance_symbol, tpsl_hash):
            logger.info(f"[TPSL Dedupe] Skipping duplicate TP/SL for {binance_symbol} (hash: {tpsl_hash[:20]}...)")
            # Still return existing orders if found
            try:
                existing_orders = _retryable_futures_get_open_orders(client, symbol=binance_symbol)
                for o in existing_orders:
                    if o['type'] == 'TAKE_PROFIT_MARKET' and (o.get('closePosition') or o.get('reduceOnly')):
                        tp_order_id = str(o.get('orderId', ''))
                    if o['type'] == 'STOP_MARKET' and (o.get('closePosition') or o.get('reduceOnly')):
                        sl_order_id = str(o.get('orderId', ''))
                if tp_order_id and sl_order_id:
                    return tp_order_id, sl_order_id
            except Exception:
                pass
            return None, None  # Duplicate, skip
    except ImportError:
        pass  # Fallback if module not available
    
    # Initialize flags for existing orders
    has_tp_order = False
    has_sl_order = False
    
    # STRENGTHENED: Check for existing TP/SL orders from Binance (not just memory)
    # This fixes BNB margin errors from redundant re-attach attempts
    try:
        existing_orders = _retryable_futures_get_open_orders(client, symbol=binance_symbol)
        
        # DUAL-LEG VERIFICATION: Check TP and SL separately
        has_tp_order = any(
            o['type'] == 'TAKE_PROFIT_MARKET' and 
            (o.get('closePosition') == True or o.get('reduceOnly') == True)
            for o in existing_orders
        )
        has_sl_order = any(
            o['type'] == 'STOP_MARKET' and 
            (o.get('closePosition') == True or o.get('reduceOnly') == True)
            for o in existing_orders
        )
        
        if has_tp_order and has_sl_order:
            logger.info(f"[TPSL] ✅ Both TP and SL already attached for {binance_symbol}, skipping re-attach.")
            # Return the existing order IDs if we can find them
            for o in existing_orders:
                if o['type'] == 'TAKE_PROFIT_MARKET' and (o.get('closePosition') or o.get('reduceOnly')):
                    tp_order_id = str(o.get('orderId', ''))
                if o['type'] == 'STOP_MARKET' and (o.get('closePosition') or o.get('reduceOnly')):
                    sl_order_id = str(o.get('orderId', ''))
            return tp_order_id, sl_order_id
        elif has_tp_order or has_sl_order:
            logger.info(f"[TPSL] ⚠️ Partial TP/SL found for {binance_symbol} - TP: {has_tp_order}, SL: {has_sl_order}. Will attach missing leg(s).")
            # Continue to attach missing leg(s)
    except Exception as e:
        logger.warning(f"[TPSL] Error checking existing orders for {binance_symbol}: {e}")
        # Continue anyway - better to try than skip
    
    # MARGIN VALIDATION: Check available margin before placing TP/SL orders
    # This prevents -2019 "Margin insufficient" errors
    try:
        account_balance = _retryable_futures_account_balance(client)
        available_margin = 0.0
        for b in account_balance:
            if b["asset"] == "USDT":
                available_margin = float(b.get("availableBalance", 0))
                break
        
        # ENHANCED: Calculate approximate margin requirement for TP/SL orders
        # With leverage, approximate margin needed = (qty * price) / leverage
        # For safety, estimate at current mark price
        try:
            mark_price_data = client.futures_mark_price(symbol=binance_symbol)
            margin_mark_price = float(mark_price_data.get("markPrice", 0))
            estimated_margin_required = (qty * margin_mark_price) / max(leverage, 1) if margin_mark_price > 0 else 0
        except Exception:
            estimated_margin_required = 0
        
        # Skip reattach if margin is insufficient (prevent -2019 retry storms)
        if available_margin < estimated_margin_required * 0.1:  # Need at least 10% buffer
            logger.warning(f"[TPSL] ⚠️ Skipped TP/SL attach for {binance_symbol}: insufficient margin (available=${available_margin:.2f}, required≈${estimated_margin_required:.2f})")
            return None, None  # Skip and log - no retries
        
        if available_margin < 1.0:  # Less than $1 free margin might indicate issues
            logger.warning(f"[TPSL] ⚠️ Low available margin (${available_margin:.2f}) for {binance_symbol} - may cause margin errors")
        
        logger.debug(f"[TPSL] Available margin: ${available_margin:.2f} for {binance_symbol} (estimated required: ${estimated_margin_required:.2f})")
    except Exception as e:
        logger.warning(f"[TPSL] Could not check margin for {binance_symbol}: {e}")
        # Continue anyway - margin check is advisory
    
    # Get symbol filters for precision
    # Try to reuse tick_size from validation if available
    tick_size = None
    step_size = 0.001
    try:
        guard = BinanceGuard(client)
        filters = guard.get_symbol_filters(binance_symbol)
        tick_size = filters.get('tickSize', 0.01)
        step_size = filters.get('stepSize', 0.001)
    except Exception:
        tick_size = 0.01  # Default fallback
        step_size = 0.001  # Default fallback
    
    # Ensure we have tick_size for subsequent operations
    if tick_size is None or tick_size <= 0:
        tick_size = 0.01  # Safe default
    
    # Determine order sides and types for TP/SL based on position side
    # (is_long already calculated during validation above)
    tp_type, sl_type = "TAKE_PROFIT_MARKET", "STOP_MARKET"
    if is_long:  # Long position
        tp_side, sl_side = "SELL", "SELL"
    else:  # Short position
        tp_side, sl_side = "BUY", "BUY"
    
    # Mark price already fetched during validation, reuse it
    # (fallback is already handled in validation section)
    
    # Import rounding functions
    from core.exchange_filters import round_tick, apply_safety_margin
    
    # Calculate trigger prices with proper direction and rounding
    if is_long:
        # For long positions:
        # TP trigger = entry * (1 + tp_pct) - should be >= entry
        # SL trigger = entry * (1 - sl_pct) - should be <= entry
        tp_trigger = round_tick(tp_price, tick_size)
        sl_trigger = round_tick(sl_price, tick_size)
    else:
        # For short positions:
        # TP trigger = entry * (1 - tp_pct) - should be <= entry
        # SL trigger = entry * (1 + sl_pct) - should be >= entry
        tp_trigger = round_tick(tp_price, tick_size)
        sl_trigger = round_tick(sl_price, tick_size)
    
    # DEBUG: Log before safety margin adjustment
    logger.debug(f"[TPSL-Debug] Before safety margin - tp_price={tp_price:.2f}, sl_price={sl_price:.2f}, mark_price={mark_price:.2f}, is_long={is_long}")
    logger.debug(f"[TPSL-Debug] Before safety margin - tp_trigger={tp_trigger:.2f}, sl_trigger={sl_trigger:.2f}")
    
    # Apply safety margins to prevent immediate trigger
    tp_trigger = apply_safety_margin(tp_trigger, mark_price, tick_size, is_tp=True, is_long=is_long)
    sl_trigger = apply_safety_margin(sl_trigger, mark_price, tick_size, is_tp=False, is_long=is_long)
    
    # DEBUG: Log after safety margin adjustment
    logger.info(f"[TPSL-Debug] After safety margin - tp_trigger={tp_trigger:.2f}, sl_trigger={sl_trigger:.2f} (is_long={is_long}, side={side})")
    
    # PRECISION FIX: Normalize trigger prices to exact Binance precision (fixes -1111 error)
    # Binance requires stopPrice to match tickSize exactly, not just be rounded
    try:
        # Calculate price precision from tick_size (e.g., 0.01 = 2 decimals, 0.001 = 3 decimals)
        tick_str = str(tick_size).rstrip('0')
        if '.' in tick_str:
            price_precision = len(tick_str.split('.')[-1])
        else:
            price_precision = 0
        
        # Normalize using floor division to ensure exact tick alignment
        tp_trigger = math.floor(tp_trigger / tick_size) * tick_size
        sl_trigger = math.floor(sl_trigger / tick_size) * tick_size
        
        # Round to appropriate decimal places to remove floating-point artifacts
        tp_trigger = round(tp_trigger, price_precision)
        sl_trigger = round(sl_trigger, price_precision)
        
        logger.debug(f"[PrecisionFix] Normalized triggers for {symbol}: TP={tp_trigger}, SL={sl_trigger} (tick_size={tick_size}, precision={price_precision})")
    except Exception as e:
        logger.warning(f"[PrecisionFix] Failed to normalize trigger prices for {symbol}: {e}, using fallback rounding")
        # Fallback: simple rounding to 2 decimal places (safe for BTC/BNB)
        tp_trigger = round(tp_trigger, 2)
        sl_trigger = round(sl_trigger, 2)
    
    # Use closePosition mode by default (preferred for TP/SL)
    use_close_position = True
    
    # PRECISION FIX: Normalize quantity for reduceOnly fallback mode
    # This prevents precision errors when closePosition fails and we fall back to reduceOnly
    normalized_qty = safe_qty(symbol, qty)
    
    # Determine which legs need to be placed (skip if already exists)
    need_tp = tp_price > 0 and not has_tp_order
    need_sl = sl_price > 0 and not has_sl_order
    
    # Place TP order with correct parameters (only if missing)
    if need_tp:
        try:
            # Try with closePosition first
            tp_params = {
                "symbol": binance_symbol,
                "side": tp_side,
                "type": tp_type,
                "stopPrice": tp_trigger,
                "closePosition": True,
                "workingType": "MARK_PRICE",
                "priceProtect": False
            }
            
            tp_response = _retryable_futures_create_order(client, **tp_params)
            tp_order_id = str(tp_response.get("orderId", ""))
            logger.info(f"✅ TP order placed for {binance_symbol}: {tp_side} {tp_type} @ {tp_trigger} | ID: {tp_order_id}")
            logger.debug(f"[TPSL-Debug] TP order details - calculated_tp_price={tp_price:.2f}, actual_trigger={tp_trigger:.2f}, mark_price={mark_price:.2f}")
        except (BinanceAPIException, Exception) as e:
            # ENHANCED ERROR HANDLING: Use binance_error_handler for proper error mapping
            from core.binance_error_handler import handle_binance_error
            
            error_handler = handle_binance_error(e, context=f"place_tp_{binance_symbol}", symbol=binance_symbol)
            
            # Handle based on error handler recommendations
            if error_handler["action"] == "fallback" and error_handler.get("fallback_mode") == "reduceOnly":
                # Fallback to reduceOnly mode
                logger.warning(f"[TPSL] Retrying TP order for {binance_symbol} with reduceOnly instead of closePosition")
                try:
                    tp_params = {
                        "symbol": binance_symbol,
                        "side": tp_side,
                        "type": tp_type,
                        "stopPrice": tp_trigger,
                        "quantity": normalized_qty,  # ✅ Use normalized quantity to prevent precision errors
                        "reduceOnly": True,
                        "workingType": "MARK_PRICE",
                        "priceProtect": False
                    }
                    tp_response = _retryable_futures_create_order(client, **tp_params)
                    tp_order_id = str(tp_response.get("orderId", ""))
                    logger.info(f"✅ TP order placed for {binance_symbol}: {tp_side} {tp_type} @ {tp_trigger} | ID: {tp_order_id}")
                    use_close_position = False  # Switch to reduceOnly mode for SL as well
                except Exception as e2:
                    logger.error(f"❌ Failed to place TP order for {binance_symbol} with reduceOnly: {e2}")
            elif error_handler["action"] == "skip":
                # Skip (e.g., -2019 margin insufficient, -4164 duplicate)
                if error_handler.get("treat_as_success"):
                    logger.info(f"[TPSL] TP order for {binance_symbol} already exists (treated as success)")
                    # Try to find existing TP order ID
                    try:
                        existing_orders = _retryable_futures_get_open_orders(client, symbol=binance_symbol)
                        for o in existing_orders:
                            if o['type'] == 'TAKE_PROFIT_MARKET' and (o.get('closePosition') or o.get('reduceOnly')):
                                tp_order_id = str(o.get('orderId', ''))
                                break
                    except Exception:
                        pass
            else:
                # Fail or other actions
                logger.error(f"❌ Failed to place TP order for {binance_symbol}: {error_handler['message']}")
    
    # Place SL order with correct parameters (only if missing)
    if need_sl:
        try:
            if use_close_position:
                # Use closePosition mode
                sl_params = {
                    "symbol": binance_symbol,
                    "side": sl_side,
                    "type": sl_type,
                    "stopPrice": sl_trigger,
                    "closePosition": True,
                    "workingType": "MARK_PRICE",
                    "priceProtect": False
                }
            else:
                # Use reduceOnly mode
                sl_params = {
                    "symbol": binance_symbol,
                    "side": sl_side,
                    "type": sl_type,
                    "stopPrice": sl_trigger,
                    "quantity": normalized_qty,  # ✅ Use normalized quantity to prevent precision errors
                    "reduceOnly": True,
                    "workingType": "MARK_PRICE",
                    "priceProtect": False
                }
            
            sl_response = _retryable_futures_create_order(client, **sl_params)
            sl_order_id = str(sl_response.get("orderId", ""))
            logger.info(f"✅ SL order placed for {binance_symbol}: {sl_side} {sl_type} @ {sl_trigger} | ID: {sl_order_id}")
            logger.debug(f"[TPSL-Debug] SL order details - calculated_sl_price={sl_price:.2f}, actual_trigger={sl_trigger:.2f}, mark_price={mark_price:.2f}")
            
            # Register TP/SL hash after successful placement
            if tp_order_id and sl_order_id:
                try:
                    from core.trade_state_manager import register_tpsl_order
                    register_tpsl_order(symbol, tpsl_hash)
                except ImportError:
                    pass
        except (BinanceAPIException, Exception) as e:
            # ENHANCED ERROR HANDLING: Use binance_error_handler for proper error mapping
            from core.binance_error_handler import handle_binance_error
            
            error_handler = handle_binance_error(e, context=f"place_sl_{binance_symbol}", symbol=binance_symbol)
            
            # Handle based on error handler recommendations
            if error_handler["action"] == "fallback" and error_handler.get("fallback_mode") == "reduceOnly":
                # Fallback to reduceOnly mode
                logger.warning(f"[TPSL] Retrying SL order for {binance_symbol} with reduceOnly")
                try:
                    sl_params = {
                        "symbol": binance_symbol,
                        "side": sl_side,
                        "type": sl_type,
                        "stopPrice": sl_trigger,
                        "quantity": normalized_qty,  # ✅ Use normalized quantity to prevent precision errors
                        "reduceOnly": True,
                        "workingType": "MARK_PRICE",
                        "priceProtect": False
                    }
                    sl_response = _retryable_futures_create_order(client, **sl_params)
                    sl_order_id = str(sl_response.get("orderId", ""))
                    logger.info(f"✅ SL order placed for {binance_symbol}: {sl_side} {sl_type} @ {sl_trigger} | ID: {sl_order_id}")
                except Exception as e2:
                    logger.error(f"❌ Failed to place SL order for {binance_symbol} with reduceOnly: {e2}")
            elif error_handler["action"] == "skip":
                # Skip (e.g., -2019 margin insufficient, -4164 duplicate)
                if error_handler.get("treat_as_success"):
                    logger.info(f"[TPSL] SL order for {binance_symbol} already exists (treated as success)")
                    # Try to find existing SL order ID
                    try:
                        existing_orders = _retryable_futures_get_open_orders(client, symbol=binance_symbol)
                        for o in existing_orders:
                            if o['type'] == 'STOP_MARKET' and (o.get('closePosition') or o.get('reduceOnly')):
                                sl_order_id = str(o.get('orderId', ''))
                                break
                    except Exception:
                        pass
            else:
                # Fail or other actions
                logger.error(f"❌ Failed to place SL order for {binance_symbol}: {error_handler['message']}")
    
    # STRENGTHENED VERIFICATION: Verify both TP and SL legs separately from Binance
    try:
        # Re-check open orders from Binance to verify both legs
        open_orders = _retryable_futures_get_open_orders(client, symbol=binance_symbol)
        
        # Check TP separately
        verified_tp_exists = any(
            o['type'] == 'TAKE_PROFIT_MARKET' and 
            (o.get('closePosition') == True or o.get('reduceOnly') == True)
            for o in open_orders
        )
        
        # Check SL separately  
        verified_sl_exists = any(
            o['type'] == 'STOP_MARKET' and 
            (o.get('closePosition') == True or o.get('reduceOnly') == True)
            for o in open_orders
        )
            
        # Dual-leg status logging
        if verified_tp_exists and verified_sl_exists:
            logger.info(f"[TPSL] ✅ VERIFIED: Both TP and SL attached for {binance_symbol}")
        elif verified_tp_exists:
            logger.warning(f"[TPSL] ⚠️ VERIFIED: Only TP attached for {binance_symbol} - SL missing!")
        elif verified_sl_exists:
            logger.warning(f"[TPSL] ⚠️ VERIFIED: Only SL attached for {binance_symbol} - TP missing!")
        else:
            logger.error(f"[TPSL] ❌ VERIFIED: Neither TP nor SL attached for {binance_symbol}")
            
        # Update return values with verified IDs
        if verified_tp_exists and not tp_order_id:
            for o in open_orders:
                if o['type'] == 'TAKE_PROFIT_MARKET' and (o.get('closePosition') or o.get('reduceOnly')):
                    tp_order_id = str(o.get('orderId', ''))
        
        if verified_sl_exists and not sl_order_id:
            for o in open_orders:
                if o['type'] == 'STOP_MARKET' and (o.get('closePosition') or o.get('reduceOnly')):
                    sl_order_id = str(o.get('orderId', ''))
                    
    except Exception as e:
        logger.warning(f"[TPSL] Could not verify orders for {binance_symbol}: {e}")
    
    # Send Telegram notification for TP/SL placement
    if TELEGRAM_ENABLED and (tp_order_id or sl_order_id):
        telegram_msg = (
            f"🎯 TP/SL ATTACHED\n"
            f"Symbol: {symbol}\n"
            f"TP: {tp_trigger if tp_order_id else 'N/A'}\n"
            f"SL: {sl_trigger if sl_order_id else 'N/A'}\n"
            f"TP ID: {tp_order_id or 'N/A'}\n"
            f"SL ID: {sl_order_id or 'N/A'}"
        )
        send_message(telegram_msg)
    
    return tp_order_id, sl_order_id


def cleanup_open_orders(client: Client, symbol: str) -> int:
    """
    Cancel all open orders for a symbol.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        
    Returns:
        Number of orders cancelled
    """
    try:
        # Get all open orders for the symbol
        open_orders = _retryable_futures_get_open_orders(client, symbol=symbol)
        
        cancelled_count = 0
        for order in open_orders:
            order_id = order.get("orderId")
            if order_id:
                try:
                    _retryable_futures_cancel_order(client, symbol=symbol, orderId=order_id)
                    cancelled_count += 1
                    logger.info(f"✅ Cancelled order {order_id} for {symbol}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to cancel order {order_id} for {symbol}: {e}")
        
        return cancelled_count
    except Exception as e:
        logger.error(f"Error cleaning up open orders for {symbol}: {e}")
        return 0


def get_symbol_precision(client: Client, symbol: str) -> tuple[int, int]:
    """
    Get symbol precision for quantity and price from Binance.
    
    Args:
        client: Binance futures client
        symbol: Trading symbol
        
    Returns:
        Tuple of (qty_precision, price_precision)
    """
    try:
        info = client.futures_exchange_info()
        symbol_info = next((s for s in info['symbols'] if s['symbol'] == symbol), None)
        if not symbol_info:
            return (3, 2)  # Default precision
            
        filters = {f['filterType']: f for f in symbol_info['filters']}
        
        # Get quantity precision from LOT_SIZE filter
        lot_size = filters.get('LOT_SIZE', {})
        step_size = float(lot_size.get('stepSize', '0.001'))
        qty_precision = max(0, -int(math.floor(math.log10(step_size))))
        
        # Get price precision from PRICE_FILTER filter
        price_filter = filters.get('PRICE_FILTER', {})
        tick_size = float(price_filter.get('tickSize', '0.01'))
        price_precision = max(0, -int(math.floor(math.log10(tick_size))))
        
        return (qty_precision, price_precision)
    except Exception:
        return (3, 2)  # Default precision


def update_active_agent_signals(symbol: str, agent_id: str, signal: str, confidence: float) -> None:
    """
    Update active agent signals for a symbol.
    
    Args:
        symbol: Trading symbol
        agent_id: Agent identifier
        signal: Trading signal ('buy', 'sell', 'hold')
        confidence: Confidence level (0.0-1.0)
    """
    binance_symbol = symbol.replace("/", "").upper()
    
    if binance_symbol not in ACTIVE_AGENT_SIGNALS:
        ACTIVE_AGENT_SIGNALS[binance_symbol] = {}
    
    # Store the signal and confidence for this agent
    ACTIVE_AGENT_SIGNALS[binance_symbol][agent_id] = {
        'side': signal.upper(),
        'confidence': confidence,
        'timestamp': time.time()
    }
    
    # Clean up old signals (older than 1 hour)
    current_time = time.time()
    expired_agents = [
        agent for agent, data in ACTIVE_AGENT_SIGNALS[binance_symbol].items()
        if current_time - data['timestamp'] > 3600
    ]
    
    for agent in expired_agents:
        del ACTIVE_AGENT_SIGNALS[binance_symbol][agent]


def calculate_tp_sl_triggers(is_long: bool, entry: float, tp_pct: float, sl_pct: float) -> tuple[float, float]:
    """
    Calculate TP and SL trigger prices based on position direction.
    
    Args:
        is_long: True for long position, False for short
        entry: Entry price
        tp_pct: Take profit percentage (as decimal, e.g. 0.005 for 0.5%)
        sl_pct: Stop loss percentage (as decimal, e.g. 0.003 for 0.3%)
        
    Returns:
        Tuple of (tp_trigger, sl_trigger)
    """
    if is_long:
        # For long positions:
        # TP trigger = entry * (1 + tp_pct)
        # SL trigger = entry * (1 - sl_pct)
        tp_trigger = entry * (1 + tp_pct)
        sl_trigger = entry * (1 - sl_pct)
    else:
        # For short positions:
        # TP trigger = entry * (1 - tp_pct)
        # SL trigger = entry * (1 + sl_pct)
        tp_trigger = entry * (1 - tp_pct)
        sl_trigger = entry * (1 + sl_pct)
    
    return tp_trigger, sl_trigger
