"""
Unit tests for TP/SL exit logic.
"""
from unittest.mock import Mock, patch
from core.order_manager import place_take_profit_and_stop_loss


def test_tp_sl_inequality_validation():
    """Test TP/SL inequality validation for long positions."""
    mock_client = Mock()
    
    # Mock the BinanceGuard methods
    with patch('core.binance_guard.BinanceGuard.quantize_quantity', side_effect=lambda symbol, qty: round(qty, 6)), \
         patch('core.binance_guard.BinanceGuard.quantize_price', side_effect=lambda symbol, price: round(price, 2)):
        
        # Test valid TP/SL for long position (SL < TP)
        tp_order_id, sl_order_id = place_take_profit_and_stop_loss(
            mock_client, "BTCUSDT", "BUY", 0.1, 50000.0, 49000.0, "test_agent"
        )
        # Should not raise an exception
        
        # Test invalid TP/SL for long position (SL >= TP) - should be auto-adjusted
        tp_order_id, sl_order_id = place_take_profit_and_stop_loss(
            mock_client, "BTCUSDT", "BUY", 0.1, 49000.0, 50000.0, "test_agent"
        )
        # Should auto-adjust and not raise an exception


def test_tp_sl_inequality_validation_short():
    """Test TP/SL inequality validation for short positions."""
    mock_client = Mock()
    
    # Mock the BinanceGuard methods
    with patch('core.binance_guard.BinanceGuard.quantize_quantity', side_effect=lambda symbol, qty: round(qty, 6)), \
         patch('core.binance_guard.BinanceGuard.quantize_price', side_effect=lambda symbol, price: round(price, 2)):
        
        # Test valid TP/SL for short position (TP < SL)
        tp_order_id, sl_order_id = place_take_profit_and_stop_loss(
            mock_client, "BTCUSDT", "SELL", 0.1, 49000.0, 50000.0, "test_agent"
        )
        # Should not raise an exception
        
        # Test invalid TP/SL for short position (TP >= SL) - should be auto-adjusted
        tp_order_id, sl_order_id = place_take_profit_and_stop_loss(
            mock_client, "BTCUSDT", "SELL", 0.1, 50000.0, 49000.0, "test_agent"
        )
        # Should auto-adjust and not raise an exception


if __name__ == "__main__":
    # Run the tests
    test_tp_sl_inequality_validation()
    test_tp_sl_inequality_validation_short()
    print("All TP/SL tests passed!")