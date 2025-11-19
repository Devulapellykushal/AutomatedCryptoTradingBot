"""
Kushal Hackathon Configuration
Central config for the trading competition
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Competition Parameters
CAPITAL = float(os.getenv("STARTING_CAPITAL", 10000))
MAX_LEVERAGE = 5
MAX_DRAWDOWN = 0.4
TRADE_RISK = 0.1  # 10% of capital per trade
DAILY_LOSS_LIMIT = 0.05  # 5% daily loss limit
RUN_DURATION_DAYS = 14
REFRESH_INTERVAL_SEC = 60

# Risk Rules
DISQUALIFICATION_DRAWDOWN = 0.4
DISQUALIFICATION_LEVERAGE = 5

# Scoring Weights
METRIC_WEIGHTS = {
    "return": 0.6,
    "sharpe": 0.4
}

# Agent Configuration
AGENTS_CONFIG_DIR = "agents_config"

# Data Settings
DEFAULT_TIMEFRAME = "3m"
DEFAULT_LIMIT = 200

# LLM Settings
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.4
COORDINATOR_TEMPERATURE = 0.2

# Trading Rules
MIN_POSITION_SIZE = 0.0001  # Lowered from 0.001 to 0.0001
SLIPPAGE = 0.001  # 0.1% slippage simulation

def load_symbols():
    """
    Load and filter trading symbols from .env based on ALLOWED_SYMBOLS.
    Only returns symbols that are both in SYMBOLS and ALLOWED_SYMBOLS.
    
    Returns:
        list: Filtered list of allowed trading pairs (e.g., ["BTC/USDT", "BNB/USDT"])
    """
    symbols_str = os.getenv("SYMBOLS", "")
    allowed_str = os.getenv("ALLOWED_SYMBOLS", "")

    # Parse SYMBOLS from .env
    env_symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
    
    # Parse ALLOWED_SYMBOLS from .env (normalize to non-slash format)
    allowed_symbols = [s.strip().upper() for s in allowed_str.split(",") if s.strip()]

    # Filter symbols: only include if in ALLOWED_SYMBOLS
    filtered = []
    for sym in env_symbols:
        # Normalize symbol for comparison (remove slash)
        clean = sym.replace("/", "").upper()
        if clean in allowed_symbols:
            filtered.append(sym)
        else:
            print(f"⏩ Skipping {sym} (not in ALLOWED_SYMBOLS)")

    # Default to BTC/USDT if nothing valid found
    if not filtered:
        print("⚠️  No valid symbols found in .env, defaulting to BTC/USDT")
        filtered = ["BTC/USDT"]
    else:
        print(f"✅ Active trading symbols: {', '.join(filtered)}")

    return filtered

# Logging
LOG_DIR = "logs"
LOG_LEVEL = "INFO"

# Database
DB_DIR = "db"
MAIN_DB = f"{DB_DIR}/arena.db"
LEADERBOARD_DB = f"{DB_DIR}/leaderboard.db"
THOUGHTS_FILE = f"{DB_DIR}/thoughts.json"

def get_config():
    """Return current configuration as dict"""
    return {
        "capital": CAPITAL,
        "max_leverage": MAX_LEVERAGE,
        "max_drawdown": MAX_DRAWDOWN,
        "trade_risk": TRADE_RISK,
        "refresh_interval": REFRESH_INTERVAL_SEC,
        "disqualification_drawdown": DISQUALIFICATION_DRAWDOWN,
        "disqualification_leverage": DISQUALIFICATION_LEVERAGE
    }