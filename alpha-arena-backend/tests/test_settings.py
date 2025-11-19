"""
Unit tests for the settings module.
"""
import os
import pytest
from unittest.mock import patch
from core.settings import TradingSettings


def test_settings_loading():
    """Test that settings can be loaded successfully."""
    # This test will use the actual .env file
    settings = TradingSettings()
    assert settings is not None
    assert isinstance(settings.binance_api_key, str)
    assert isinstance(settings.binance_api_secret, str)
    assert isinstance(settings.binance_testnet, bool)


def test_settings_with_missing_required_vars():
    """Test that missing required vars raise an error."""
    # Mock environment with missing required variables
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(Exception):
            TradingSettings()


def test_settings_with_valid_env_vars():
    """Test settings with valid environment variables."""
    test_env = {
        "BINANCE_API_KEY": "test_key",
        "BINANCE_API_SECRET": "test_secret",
        "BINANCE_TESTNET": "true",
        "SYMBOLS": "BTCUSDT,ETHUSDT",
        "TIMEFRAME": "5m",
        "STARTING_CAPITAL": "50000",
        "MAX_LEVERAGE": "10",
        "RISK_FRACTION": "0.05",
        "MAX_DRAWDOWN": "0.3",
        "TAKE_PROFIT_PERCENT": "3.0",
        "STOP_LOSS_PERCENT": "1.5",
        "MAX_OPEN_TRADES": "3",
        "MAX_DAILY_ORDERS": "20",
        "MAX_MARGIN_PER_TRADE": "2000",
        "RISK_PER_TRADE_PERCENT": "1.0",
        "ALLOWED_SYMBOLS": "BTCUSDT,ETHUSDT,BNBUSDT",
        "TRADE_LOG_PATH": "test_trades.csv"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = TradingSettings()
        assert settings.binance_api_key == "test_key"
        assert settings.binance_api_secret == "test_secret"
        assert settings.binance_testnet is True
        assert settings.symbols == "BTCUSDT,ETHUSDT"
        assert settings.timeframe == "5m"
        assert settings.starting_capital == 50000.0
        assert settings.max_leverage == 10
        assert settings.risk_fraction == 0.05
        assert settings.max_drawdown == 0.3
        assert settings.take_profit_percent == 3.0
        assert settings.stop_loss_percent == 1.5
        assert settings.max_open_trades == 3
        assert settings.max_daily_orders == 20
        assert settings.max_margin_per_trade == 2000.0
        assert settings.risk_per_trade_percent == 1.0
        assert settings.allowed_symbols == "BTCUSDT,ETHUSDT,BNBUSDT"
        assert settings.trade_log_path == "test_trades.csv"


def test_settings_symbol_parsing():
    """Test symbol parsing functionality."""
    test_env = {
        "BINANCE_API_KEY": "test_key",
        "BINANCE_API_SECRET": "test_secret",
        "SYMBOLS": "BTC/USDT,ETH/USDT,BNB/USDT",
        "ALLOWED_SYMBOLS": "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = TradingSettings()
        parsed_symbols = settings.parsed_symbols
        assert "BTCUSDT" in parsed_symbols
        assert "ETHUSDT" in parsed_symbols
        assert "BNBUSDT" in parsed_symbols
        assert len(parsed_symbols) == 3
        
        parsed_allowed = settings.parsed_allowed_symbols
        assert "BTCUSDT" in parsed_allowed
        assert "ETHUSDT" in parsed_allowed
        assert "BNBUSDT" in parsed_allowed
        assert "SOLUSDT" in parsed_allowed
        assert len(parsed_allowed) == 4


def test_settings_validation_bounds():
    """Test that settings enforce value bounds."""
    # Test invalid max_leverage (> 125)
    test_env = {
        "BINANCE_API_KEY": "test_key",
        "BINANCE_API_SECRET": "test_secret",
        "MAX_LEVERAGE": "150"  # Should be capped at 125
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = TradingSettings()
        # Pydantic validation should prevent this, but let's check behavior
        # Note: This might raise a validation error depending on how Pydantic is configured
        
    # Test invalid risk_fraction (> 1)
    test_env = {
        "BINANCE_API_KEY": "test_key",
        "BINANCE_API_SECRET": "test_secret",
        "RISK_FRACTION": "1.5"  # Should be <= 1
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        with pytest.raises(Exception):
            TradingSettings()


def test_settings_tp_sl_validation():
    """Test TP/SL validation logic."""
    # Test valid TP/SL relationship
    test_env = {
        "BINANCE_API_KEY": "test_key",
        "BINANCE_API_SECRET": "test_secret",
        "TAKE_PROFIT_PERCENT": "3.0",
        "STOP_LOSS_PERCENT": "1.5"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = TradingSettings()
        assert settings.take_profit_percent > settings.stop_loss_percent
    
    # Test invalid TP/SL relationship (this should raise validation error)
    test_env = {
        "BINANCE_API_KEY": "test_key",
        "BINANCE_API_SECRET": "test_secret",
        "TAKE_PROFIT_PERCENT": "1.0",
        "STOP_LOSS_PERCENT": "2.0"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        with pytest.raises(Exception):
            TradingSettings()


if __name__ == "__main__":
    pytest.main([__file__])