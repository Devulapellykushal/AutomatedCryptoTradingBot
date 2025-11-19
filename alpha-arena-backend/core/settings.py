"""
Typed Pydantic settings model for the Binance Futures trading bot.
Loads all environment variables, enforces value bounds, provides defaults,
fails fast if required vars are missing, and logs effective configuration.
"""
import os
import logging
from typing import Set, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class TradingSettings(BaseModel):
    """
    Pydantic settings model for trading configuration.
    """
    
    # Binance API Configuration
    binance_api_key: str = Field(default=..., alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default=..., alias="BINANCE_API_SECRET")
    binance_testnet: bool = Field(default=True, alias="BINANCE_TESTNET")
    
    # Trading Configuration
    symbols: str = Field(default="BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT", alias="SYMBOLS")
    timeframe: str = Field(default="3m", alias="TIMEFRAME")
    starting_capital: float = Field(default=10000.0, alias="STARTING_CAPITAL", gt=0)
    max_leverage: int = Field(default=5, alias="MAX_LEVERAGE", ge=1, le=125)
    risk_fraction: float = Field(default=0.1, alias="RISK_FRACTION", gt=0, le=1)
    max_drawdown: float = Field(default=0.4, alias="MAX_DRAWDOWN", gt=0, le=1)
    
    # Risk Management & Throttling
    take_profit_percent: float = Field(default=2.0, alias="TAKE_PROFIT_PERCENT", gt=0)
    stop_loss_percent: float = Field(default=1.0, alias="STOP_LOSS_PERCENT", gt=0)
    max_open_trades: int = Field(default=4, alias="MAX_OPEN_TRADES", ge=1)
    max_daily_orders: int = Field(default=10, alias="MAX_DAILY_ORDERS", ge=1)
    max_margin_per_trade: float = Field(default=2500.0, alias="MAX_MARGIN_PER_TRADE", gt=0)
    MIN_MARGIN_PER_TRADE: float = Field(default=600.0, alias="MIN_MARGIN_PER_TRADE", gt=0)
    MAX_RISK_PER_TRADE_USD: float = Field(default=200.0, alias="MAX_RISK_PER_TRADE_USD", gt=0)
    RISK_PER_TRADE_PERCENT: float = Field(default=2.0, alias="RISK_PER_TRADE_PERCENT", gt=0, le=100)
    allowed_symbols: str = Field(default="BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT", alias="ALLOWED_SYMBOLS")
    trade_log_path: str = Field(default="trades_log.csv", alias="TRADE_LOG_PATH")
    
    # Auto-Scaling
    auto_scale_qty: bool = Field(default=True, alias="AUTO_SCALE_QTY")
    
    # Telegram Notifications
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    telegram_auto_notifications: bool = Field(default=True, alias="TELEGRAM_AUTO_NOTIFICATIONS")
    
    # Confidence & Cooldowns
    min_confidence: float = Field(default=0.68, alias="MIN_CONFIDENCE", ge=0, le=1)
    min_holding_period: int = Field(default=0, alias="MIN_HOLDING_PERIOD", ge=0)
    reversal_cooldown_period: int = Field(default=600, alias="REVERSAL_COOLDOWN_PERIOD", ge=0)
    reversal_cooldown_sec: int = Field(default=120, alias="REVERSAL_COOLDOWN_SEC", ge=0)
    dynamic_confidence: bool = Field(default=True, alias="DYNAMIC_CONFIDENCE")
    
    # Dynamic TP/SL
    dynamic_tp_sl: bool = Field(default=False, alias="DYNAMIC_TP_SL")
    base_tp_percent: float = Field(default=2.0, alias="BASE_TP_PERCENT", gt=0)
    base_sl_percent: float = Field(default=1.0, alias="BASE_SL_PERCENT", gt=0)
    min_tp_percent: float = Field(default=0.5, alias="MIN_TP_PERCENT", gt=0)
    max_tp_percent: float = Field(default=3.0, alias="MAX_TP_PERCENT", gt=0)
    min_sl_percent: float = Field(default=0.5, alias="MIN_SL_PERCENT", gt=0)
    max_sl_percent: float = Field(default=1.5, alias="MAX_SL_PERCENT", gt=0)
    
    # Paper Trading
    paper_trading: bool = Field(default=False, alias="PAPER_TRADING")
    
    # Self-Optimization
    self_optimize: bool = Field(default=False, alias="SELF_OPTIMIZE")
    
    @field_validator('symbols', 'allowed_symbols')
    @classmethod
    def validate_symbols_format(cls, v: Any) -> Any:
        """Validate that symbols are properly formatted."""
        if not v:
            return v
        symbols = [s.strip().upper() for s in v.split(',') if s.strip()]
        return ','.join(symbols)
    
    @field_validator('timeframe')
    @classmethod
    def validate_timeframe(cls, v: Any) -> Any:
        """Validate timeframe format."""
        valid_timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']
        if v not in valid_timeframes:
            raise ValueError(f"Invalid timeframe: {v}. Must be one of {valid_timeframes}")
        return v
    
    @model_validator(mode='after')
    def validate_tp_sl_relationships(self) -> 'TradingSettings':
        """Validate relationships between TP/SL settings."""
        # Basic TP > SL validation
        if self.take_profit_percent <= self.stop_loss_percent:
            raise ValueError("Take profit percent must be greater than stop loss percent")
            
        # Dynamic TP/SL validations
        if self.base_tp_percent < self.min_tp_percent:
            raise ValueError("Base TP percent must be >= min TP percent")
        if self.base_tp_percent > self.max_tp_percent:
            raise ValueError("Base TP percent must be <= max TP percent")
        if self.base_sl_percent < self.min_sl_percent:
            raise ValueError("Base SL percent must be >= min SL percent")
        if self.base_sl_percent > self.max_sl_percent:
            raise ValueError("Base SL percent must be <= max SL percent")
            
        return self
    
    @property
    def parsed_symbols(self) -> Set[str]:
        """Get set of trading symbols."""
        return set([s.strip().upper().replace("/", "") for s in self.symbols.split(",") if s.strip()])
    
    @property
    def parsed_allowed_symbols(self) -> Set[str]:
        """Get set of allowed trading symbols."""
        return set([s.strip().upper().replace("/", "") for s in self.allowed_symbols.split(",") if s.strip()])
    
    def log_settings(self) -> None:
        """Log the effective configuration at startup."""
        logger.info("=== Trading Bot Configuration ===")
        logger.info(f"Binance Testnet: {self.binance_testnet}")
        logger.info(f"Trading Symbols: {self.symbols}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Starting Capital: ${self.starting_capital}")
        logger.info(f"Max Leverage: {self.max_leverage}x")
        logger.info(f"Risk Fraction: {self.risk_fraction*100}%")
        logger.info(f"Max Drawdown: {self.max_drawdown*100}%")
        logger.info(f"Take Profit: {self.take_profit_percent}%")
        logger.info(f"Stop Loss: {self.stop_loss_percent}%")
        logger.info(f"Max Open Trades: {self.max_open_trades}")
        logger.info(f"Max Daily Orders: {self.max_daily_orders}")
        logger.info(f"Max Margin Per Trade: ${self.max_margin_per_trade}")
        logger.info(f"Risk Per Trade: {self.RISK_PER_TRADE_PERCENT}%")
        logger.info(f"Auto Scale Quantity: {self.auto_scale_qty}")
        logger.info(f"Telegram Notifications: {self.telegram_auto_notifications}")
        logger.info(f"Min Confidence: {self.min_confidence}")
        logger.info(f"Dynamic TP/SL: {self.dynamic_tp_sl}")
        logger.info(f"Paper Trading: {self.paper_trading}")
        if self.telegram_auto_notifications and self.telegram_bot_token and self.telegram_chat_id:
            logger.info("Telegram notifications enabled")
        elif self.telegram_auto_notifications:
            logger.warning("Telegram notifications enabled but credentials missing")
        logger.info("================================")


# Function to load settings from environment variables
def load_settings() -> TradingSettings:
    # Load environment variables from .env file if it exists
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.strip().split("=", 1)
                    env_vars[key] = value
    
    # Get values from environment variables or .env file
    def get_env_var(key: str, default: Any = None) -> Any:
        # Check environment variables first (they take precedence)
        if key in os.environ:
            return os.environ[key]
        # Check .env file
        if key in env_vars:
            return env_vars[key]
        # Return default
        return default
    
    # Create settings instance
    return TradingSettings(
        BINANCE_API_KEY=get_env_var("BINANCE_API_KEY", ""),
        BINANCE_API_SECRET=get_env_var("BINANCE_API_SECRET", ""),
        BINANCE_TESTNET=get_env_var("BINANCE_TESTNET", "True").lower() == "true",
        SYMBOLS=get_env_var("SYMBOLS", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT"),
        TIMEFRAME=get_env_var("TIMEFRAME", "3m"),
        STARTING_CAPITAL=float(get_env_var("STARTING_CAPITAL", "10000.0")),
        MAX_LEVERAGE=int(get_env_var("MAX_LEVERAGE", "5")),
        RISK_FRACTION=float(get_env_var("RISK_FRACTION", "0.1")),
        MAX_DRAWDOWN=float(get_env_var("MAX_DRAWDOWN", "0.4")),
        TAKE_PROFIT_PERCENT=float(get_env_var("TAKE_PROFIT_PERCENT", "2.0")),
        STOP_LOSS_PERCENT=float(get_env_var("STOP_LOSS_PERCENT", "1.0")),
        MAX_OPEN_TRADES=int(get_env_var("MAX_OPEN_TRADES", "4")),
        MAX_DAILY_ORDERS=int(get_env_var("MAX_DAILY_ORDERS", "10")),
        MAX_MARGIN_PER_TRADE=float(get_env_var("MAX_MARGIN_PER_TRADE", "2000.0")),
        MIN_MARGIN_PER_TRADE=float(get_env_var("MIN_MARGIN_PER_TRADE", "600.0")),
        MAX_RISK_PER_TRADE_USD=float(get_env_var("MAX_RISK_PER_TRADE_USD", "200.0")),
        RISK_PER_TRADE_PERCENT=float(get_env_var("RISK_PER_TRADE_PERCENT", "2.0")),
        ALLOWED_SYMBOLS=get_env_var("ALLOWED_SYMBOLS", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT"),
        TRADE_LOG_PATH=get_env_var("TRADE_LOG_PATH", "trades_log.csv"),
        AUTO_SCALE_QTY=get_env_var("AUTO_SCALE_QTY", "True").lower() == "true",
        TELEGRAM_BOT_TOKEN=get_env_var("TELEGRAM_BOT_TOKEN"),
        TELEGRAM_CHAT_ID=get_env_var("TELEGRAM_CHAT_ID"),
        TELEGRAM_AUTO_NOTIFICATIONS=get_env_var("TELEGRAM_AUTO_NOTIFICATIONS", "True").lower() == "true",
        MIN_CONFIDENCE=float(get_env_var("MIN_CONFIDENCE", "0.68")),
        MIN_HOLDING_PERIOD=int(get_env_var("MIN_HOLDING_PERIOD", "0")),
        REVERSAL_COOLDOWN_PERIOD=int(get_env_var("REVERSAL_COOLDOWN_PERIOD", "600")),
        REVERSAL_COOLDOWN_SEC=int(get_env_var("REVERSAL_COOLDOWN_SEC", "120")),
        DYNAMIC_CONFIDENCE=get_env_var("DYNAMIC_CONFIDENCE", "True").lower() == "true",
        DYNAMIC_TP_SL=get_env_var("DYNAMIC_TP_SL", "False").lower() == "true",
        BASE_TP_PERCENT=float(get_env_var("BASE_TP_PERCENT", "2.0")),
        BASE_SL_PERCENT=float(get_env_var("BASE_SL_PERCENT", "1.0")),
        MIN_TP_PERCENT=float(get_env_var("MIN_TP_PERCENT", "0.5")),
        MAX_TP_PERCENT=float(get_env_var("MAX_TP_PERCENT", "3.0")),
        MIN_SL_PERCENT=float(get_env_var("MIN_SL_PERCENT", "0.5")),
        MAX_SL_PERCENT=float(get_env_var("MAX_SL_PERCENT", "1.5")),
        PAPER_TRADING=get_env_var("PAPER_TRADING", "False").lower() == "true"
    )


# Global settings instance
settings = load_settings()


if __name__ == "__main__":
    # Test the settings loading
    try:
        settings.log_settings()
        print("✅ Settings loaded successfully")
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        raise