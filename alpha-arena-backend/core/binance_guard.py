"""
Binance Guard Module for the trading bot.
Fetches exchange filters, validates API permissions, validates leverage,
and verifies symbol existence before trading.
"""
import logging
from typing import Dict, Any, Optional, Tuple
from binance.client import Client
from binance.exceptions import BinanceAPIException
from core.settings import settings

logger = logging.getLogger(__name__)


class BinanceGuard:
    """Binance guard for validating exchange constraints and API permissions."""
    
    def __init__(self, client: Client):
        """
        Initialize Binance guard with a client.
        
        Args:
            client: Binance client instance
        """
        self.client = client
        self._symbol_filters_cache: Dict[str, Dict[str, Any]] = {}
    
    def validate_api_permissions(self) -> bool:
        """
        Validate API permissions (canTrade).
        
        Returns:
            True if API has trading permissions, False otherwise
        """
        try:
            account_info = self.client.futures_account()
            can_trade = account_info.get('canTrade', False)
            if not can_trade:
                logger.error("❌ API key does not have trading permissions")
                return False
            logger.info("✅ API key has trading permissions")
            return True
        except BinanceAPIException as e:
            logger.error(f"❌ Failed to validate API permissions: {e.message}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error validating API permissions: {e}")
            return False
    
    def get_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch exchange filters for a symbol (minQty, stepSize, minNotional, etc.).
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Dictionary with symbol filters
        """
        # Return cached filters if available
        if symbol in self._symbol_filters_cache:
            return self._symbol_filters_cache[symbol]
        
        try:
            exchange_info = self.client.futures_exchange_info()
            symbol_info = None
            
            for s in exchange_info.get('symbols', []):
                if s.get('symbol') == symbol:
                    symbol_info = s
                    break
            
            if not symbol_info:
                raise ValueError(f"Symbol {symbol} not found in exchange info")
            
            filters = {}
            for f in symbol_info.get('filters', []):
                filter_type = f.get('filterType')
                if filter_type == 'PRICE_FILTER':
                    filters.update({
                        'minPrice': float(f.get('minPrice', 0)),
                        'maxPrice': float(f.get('maxPrice', 0)),
                        'tickSize': float(f.get('tickSize', 0))
                    })
                elif filter_type == 'LOT_SIZE':
                    filters.update({
                        'minQty': float(f.get('minQty', 0)),
                        'maxQty': float(f.get('maxQty', 0)),
                        'stepSize': float(f.get('stepSize', 0))
                    })
                elif filter_type == 'MIN_NOTIONAL':
                    filters.update({
                        'minNotional': float(f.get('notional', 0))
                    })
                elif filter_type == 'MARKET_LOT_SIZE':
                    filters.update({
                        'marketMinQty': float(f.get('minQty', 0)),
                        'marketMaxQty': float(f.get('maxQty', 0)),
                        'marketStepSize': float(f.get('stepSize', 0))
                    })
            
            # Cache the filters
            self._symbol_filters_cache[symbol] = filters
            return filters
            
        except Exception as e:
            logger.error(f"Failed to get symbol filters for {symbol}: {e}")
            # Return default filters
            return {
                'minPrice': 0.0,
                'maxPrice': 0.0,
                'tickSize': 0.01,
                'minQty': 0.001,
                'maxQty': 1000.0,
                'stepSize': 0.001,
                'minNotional': 5.0,
                'marketMinQty': 0.001,
                'marketMaxQty': 1000.0,
                'marketStepSize': 0.001
            }
    
    def validate_symbol_exists(self, symbol: str) -> bool:
        """
        Ping and verify symbol existence before trading.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            True if symbol exists, False otherwise
        """
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            if ticker and 'symbol' in ticker and ticker['symbol'] == symbol:
                logger.info(f"✅ Symbol {symbol} exists and is available for trading")
                return True
            else:
                logger.error(f"❌ Symbol {symbol} not found or not available")
                return False
        except BinanceAPIException as e:
            if e.code == -1121:  # Invalid symbol
                logger.error(f"❌ Symbol {symbol} does not exist: {e.message}")
                return False
            else:
                logger.error(f"❌ Error checking symbol {symbol}: {e.message}")
                return False
        except Exception as e:
            logger.error(f"❌ Unexpected error checking symbol {symbol}: {e}")
            return False
    
    def get_max_leverage(self, symbol: str) -> int:
        """
        Get maximum leverage allowed for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Maximum leverage for the symbol
        """
        try:
            # Get leverage bracket info
            brackets = self.client.futures_leverage_bracket(symbol=symbol)
            if brackets and isinstance(brackets, list) and len(brackets) > 0:
                # Get the first bracket which typically has the max leverage
                max_leverage = brackets[0].get('initialLeverage', 1)
                return int(max_leverage)
            else:
                # Default to 1 if we can't determine
                return 1
        except Exception as e:
            logger.warning(f"Could not fetch max leverage for {symbol}: {e}. Using default of 1.")
            return 1
    
    def validate_leverage(self, symbol: str, requested_leverage: int) -> Tuple[bool, int]:
        """
        Validate leverage is within exchange limits.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            requested_leverage: Requested leverage
            
        Returns:
            Tuple of (is_valid, actual_leverage)
        """
        try:
            max_leverage = self.get_max_leverage(symbol)
            actual_leverage = min(requested_leverage, max_leverage, settings.max_leverage)
            
            if actual_leverage < requested_leverage:
                logger.warning(
                    f"⚠️  Requested leverage {requested_leverage}x exceeds max allowed "
                    f"{max_leverage}x for {symbol}. Using {actual_leverage}x instead."
                )
            
            return True, actual_leverage
        except Exception as e:
            logger.error(f"Error validating leverage for {symbol}: {e}")
            return False, 1
    
    def quantize_quantity(self, symbol: str, quantity: float, use_market_lot_size: bool = False) -> float:
        """
        Quantize quantity according to symbol's stepSize.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            quantity: Quantity to quantize
            use_market_lot_size: Whether to use market lot size instead of regular lot size
            
        Returns:
            Quantized quantity
        """
        filters = self.get_symbol_filters(symbol)
        
        if use_market_lot_size:
            step_size = filters.get('marketStepSize', 0.001)
        else:
            step_size = filters.get('stepSize', 0.001)
        
        # Convert to integer based on step size
        step_precision = len(str(step_size).split('.')[-1].rstrip('0')) if '.' in str(step_size) else 0
        multiplier = 10 ** step_precision
        quantized_qty = round(quantity * multiplier) / multiplier
        
        # Ensure it's a multiple of stepSize
        quantized_qty = round(quantized_qty / step_size) * step_size
        
        # Apply min/max limits
        min_qty = filters.get('minQty', 0) if not use_market_lot_size else filters.get('marketMinQty', 0)
        max_qty = filters.get('maxQty', float('inf')) if not use_market_lot_size else filters.get('marketMaxQty', float('inf'))
        
        quantized_qty = max(min_qty, min(quantized_qty, max_qty))
        
        return quantized_qty
    
    def quantize_price(self, symbol: str, price: float) -> float:
        """
        Quantize price according to symbol's tickSize.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            price: Price to quantize
            
        Returns:
            Quantized price
        """
        filters = self.get_symbol_filters(symbol)
        tick_size = filters.get('tickSize', 0.01)
        
        # Convert to integer based on tick size
        tick_precision = len(str(tick_size).split('.')[-1].rstrip('0')) if '.' in str(tick_size) else 0
        multiplier = 10 ** tick_precision
        quantized_price = round(price * multiplier) / multiplier
        
        # Ensure it's a multiple of tickSize
        quantized_price = round(quantized_price / tick_size) * tick_size
        
        return quantized_price
    
    def validate_order_params(
        self, 
        symbol: str, 
        quantity: float, 
        price: Optional[float] = None,
        leverage: int = 1
    ) -> Tuple[bool, str, float, Optional[float]]:
        """
        Validate order parameters against exchange rules.
        
        Args:
            symbol: Trading symbol
            quantity: Order quantity
            price: Order price (optional)
            leverage: Leverage to use
            
        Returns:
            Tuple of (is_valid, message, quantized_quantity, quantized_price)
        """
        try:
            # Validate symbol exists
            if not self.validate_symbol_exists(symbol):
                return False, f"Symbol {symbol} does not exist", quantity, price
            
            # Validate leverage
            is_valid_leverage, actual_leverage = self.validate_leverage(symbol, leverage)
            if not is_valid_leverage:
                return False, f"Invalid leverage for {symbol}", quantity, price
            
            # Quantize quantity
            quantized_qty = self.quantize_quantity(symbol, quantity)
            
            # Check minimum quantity
            filters = self.get_symbol_filters(symbol)
            min_qty = filters.get('minQty', 0.001)
            if quantized_qty < min_qty:
                return False, f"Quantity {quantized_qty} is below minimum {min_qty}", quantized_qty, price
            
            # Quantize price if provided
            quantized_price = None
            if price is not None:
                quantized_price = self.quantize_price(symbol, price)
                min_price = filters.get('minPrice', 0)
                max_price = filters.get('maxPrice', float('inf'))
                if quantized_price < min_price or quantized_price > max_price:
                    return False, f"Price {quantized_price} is outside allowed range [{min_price}, {max_price}]", quantized_qty, quantized_price
            
            # Check notional value
            notional_value = quantized_qty * (quantized_price or price or 0)
            min_notional = filters.get('minNotional', 5.0)
            if notional_value > 0 and notional_value < min_notional:
                return False, f"Notional value ${notional_value:.2f} is below minimum ${min_notional}", quantized_qty, quantized_price
            
            return True, "OK", quantized_qty, quantized_price
            
        except Exception as e:
            logger.error(f"Error validating order params for {symbol}: {e}")
            return False, f"Validation error: {e}", quantity, price
    
    def run_all_checks(self, symbol: str, leverage: int = 1) -> bool:
        """
        Run all guard checks for a symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage to validate
            
        Returns:
            True if all checks pass, False otherwise
        """
        logger.info(f"Running Binance guard checks for {symbol}...")
        
        # Validate API permissions
        if not self.validate_api_permissions():
            return False
        
        # Validate symbol exists
        if not self.validate_symbol_exists(symbol):
            return False
        
        # Validate leverage
        is_valid, actual_leverage = self.validate_leverage(symbol, leverage)
        if not is_valid:
            return False
        
        # Log symbol filters for debugging
        filters = self.get_symbol_filters(symbol)
        logger.info(f"Symbol {symbol} filters: {filters}")
        
        logger.info(f"✅ All Binance guard checks passed for {symbol}")
        return True


def create_binance_guard(client: Client) -> BinanceGuard:
    """
    Create a BinanceGuard instance.
    
    Args:
        client: Binance client instance
        
    Returns:
        BinanceGuard instance
    """
    return BinanceGuard(client)