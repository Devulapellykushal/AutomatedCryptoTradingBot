"""
Logging system for Kushal
Provides structured logging to files and console
"""
import logging
import os
from datetime import datetime
from hackathon_config import LOG_DIR

os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Setup logger with file and console handlers"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # File handler
    log_file = os.path.join(LOG_DIR, f"{name}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_format = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
    file_handler.setFormatter(file_format)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_format = logging.Formatter('[%(name)s] %(message)s')
    console_handler.setFormatter(console_format)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Create loggers for different components
trading_logger = setup_logger("trading")
coordinator_logger = setup_logger("coordinator")
error_logger = setup_logger("errors")

def log_trade_decision(agent_id: str, symbol: str, signal: str, confidence: float, 
                      leverage: float, reasoning: str = ""):
    """Log trading decision"""
    trading_logger.info(
        f"{agent_id} | {symbol} | Signal={signal} | Conf={confidence:.2f} | "
        f"Lev={leverage}x | {reasoning}"
    )

def log_execution(agent_id: str, symbol: str, side: str, qty: float, 
                 entry: float, exit: float, pnl: float):
    """Log trade execution"""
    emoji = "🟢" if pnl > 0 else "🔴"
    trading_logger.info(
        f"{emoji} {agent_id} | {symbol} | {side.upper()} | Qty={qty:.4f} | "
        f"Entry={entry:.2f} | Exit={exit:.2f} | PnL={pnl:+.2f}"
    )

def log_meta_decision(mode: str, reason: str, adjustment: float):
    """Log coordinator meta-decision"""
    coordinator_logger.info(
        f"Mode={mode.upper()} | Reason={reason} | Adjustment={adjustment:.2f}"
    )

def log_error(component: str, error: Exception):
    """Log errors"""
    error_logger.error(f"{component}: {str(error)}", exc_info=True)
