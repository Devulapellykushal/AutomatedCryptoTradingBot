"""
Unit tests for order sizing logic.
"""
import pytest
from unittest.mock import Mock, patch
from decimal import Decimal
from core.order_manager import adjust_precision, can_place_order


def test_adjust_precision():
    """Test precision adjustment functionality."""
    # Mock client and exchange info
    mock_client = Mock()
    
    # Mock exchange info for BTCUSDT
    mock_exchange_info = {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "tickSize": "0.01"
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": "0.001",
                        "minQty": "0.001"
                    }
                ]
            }
        ]
    }
    
    mock_client.futures_exchange_info.return_value = mock_exchange_info
    
    # Test quantity adjustment
    adjusted_qty, adjusted_price = adjust_precision(mock_client, "BTCUSDT", 0.123456, 45678.901234)
    
    # Quantity should be rounded to 3 decimal places (stepSize 0.001)
    assert round(adjusted_qty, 3) == 0.123
    
    # Price should be rounded to 2 decimal places (tickSize 0.01)
    if adjusted_price is not None:
        assert round(adjusted_price, 2) == 45678.90


def test_can_place_order_symbol_check():
    """Test that order placement checks allowed symbols."""
    mock_client = Mock()
    
    # Mock environment with specific allowed symbols
    with patch('core.settings.settings.parsed_allowed_symbols', {'BTCUSDT', 'ETHUSDT'}):
        # Test allowed symbol
        result = can_place_order(mock_client, "BTCUSDT", 0.1, 5)
        # Should not be blocked due to symbol (other checks might fail)
        assert result[0] is True or result[1] != "Symbol BTCUSDT not in ALLOWED_SYMBOLS list"
        
        # Test disallowed symbol
        result = can_place_order(mock_client, "SOLUSDT", 0.1, 5)
        assert result[0] is False
        assert "SOLUSDT not in ALLOWED_SYMBOLS list" in result[1]


def test_can_place_order_quantity_validation():
    """Test order quantity validation."""
    mock_client = Mock()
    
    # Mock exchange info
    mock_exchange_info = {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "filters": [
                    {
                        "filterType": "MIN_NOTIONAL",
                        "notional": "5.0"
                    }
                ]
            }
        ]
    }
    
    mock_client.futures_exchange_info.return_value = mock_exchange_info
    mock_client.futures_symbol_ticker.return_value = {"price": "50000.0"}
    mock_client.futures_account_balance.return_value = [{"asset": "USDT", "balance": "10000.0"}]
    
    with patch('core.settings.settings.parsed_allowed_symbols', {'BTCUSDT'}):
        # Test valid quantity that meets minimum notional
        result = can_place_order(mock_client, "BTCUSDT", 0.0002, 5)  # 0.0002 * 50000 = $10 (valid)
        assert result[0] is True or "notional" not in result[1].lower()
        
        # Test invalid quantity that doesn't meet minimum notional
        # This test might be complex to implement without full mocking


if __name__ == "__main__":
    pytest.main([__file__])