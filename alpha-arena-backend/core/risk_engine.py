import numpy as np
import time
import math
import os
import logging
from typing import Dict, List, Optional
from collections import deque

class DailyLossTracker:
    """Track daily losses, API lag, consecutive losses, and halt trading if limits exceeded"""
    
    def __init__(self, max_daily_loss_pct: float = 0.05):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.daily_starting_equity: Dict[str, float] = {}
        self.daily_current_equity: Dict[str, float] = {}
        self.trading_halted: Dict[str, bool] = {}
        self.last_reset_day: Dict[str, int] = {}
        
        # Global Kill-Switch enhancements
        self.consecutive_losses: Dict[str, int] = {}  # Track consecutive losing trades
        self.api_lag_times: Dict[str, deque] = {}  # Track API response times per agent
        self.trade_history: Dict[str, List[bool]] = {}  # Track win/loss history (True=win, False=loss)
        self.max_consecutive_losses = 3  # Halt after 3 consecutive losses
        self.max_api_lag_seconds = 5.0  # Halt if API lag > 5 seconds
        self.api_lag_window = 10  # Track last 10 API calls
        
    def reset_if_new_day(self, agent_id: str):
        """Reset tracker if it's a new trading day"""
        from datetime import datetime
        current_day = datetime.now().day
        
        if agent_id not in self.last_reset_day or self.last_reset_day[agent_id] != current_day:
            self.last_reset_day[agent_id] = current_day
            self.trading_halted[agent_id] = False
            print(f"📅 [{agent_id}] New trading day - daily loss limit reset")
            
    def initialize_agent(self, agent_id: str, starting_equity: float):
        """Initialize tracking for an agent"""
        self.reset_if_new_day(agent_id)
        if agent_id not in self.daily_starting_equity:
            self.daily_starting_equity[agent_id] = starting_equity
            self.daily_current_equity[agent_id] = starting_equity
            self.trading_halted[agent_id] = False
            print(f"✅ [{agent_id}] Daily loss tracker initialized: ${starting_equity:.2f}")
    
    def update_equity(self, agent_id: str, current_equity: float):
        """Update current equity and check loss limit"""
        self.reset_if_new_day(agent_id)
        
        if agent_id not in self.daily_starting_equity:
            self.initialize_agent(agent_id, current_equity)
            return
            
        self.daily_current_equity[agent_id] = current_equity
        
    def record_api_lag(self, agent_id: str, lag_seconds: float):
        """Record API lag time for monitoring"""
        if agent_id not in self.api_lag_times:
            self.api_lag_times[agent_id] = deque(maxlen=self.api_lag_window)
        self.api_lag_times[agent_id].append(lag_seconds)
        
        # Check if lag exceeds threshold
        avg_lag = sum(self.api_lag_times[agent_id]) / len(self.api_lag_times[agent_id])
        if avg_lag > self.max_api_lag_seconds:
            self.trading_halted[agent_id] = True
            logging.error(f"🚨 [{agent_id}] API LAG EXCEEDED: {avg_lag:.2f}s (max: {self.max_api_lag_seconds}s)")
            logging.error(f"🛑 [{agent_id}] Trading HALTED due to API instability")
    
    def record_trade_outcome(self, agent_id: str, is_win: bool):
        """Record trade outcome (win/loss) for consecutive loss tracking"""
        if agent_id not in self.trade_history:
            self.trade_history[agent_id] = []
            self.consecutive_losses[agent_id] = 0
        
        self.trade_history[agent_id].append(is_win)
        # Keep only last 20 trades
        if len(self.trade_history[agent_id]) > 20:
            self.trade_history[agent_id] = self.trade_history[agent_id][-20:]
        
        # Update consecutive losses
        if is_win:
            self.consecutive_losses[agent_id] = 0
        else:
            self.consecutive_losses[agent_id] += 1
            
            # Check consecutive loss limit
            if self.consecutive_losses[agent_id] >= self.max_consecutive_losses:
                self.trading_halted[agent_id] = True
                logging.error(f"🚨 [{agent_id}] CONSECUTIVE LOSSES EXCEEDED: {self.consecutive_losses[agent_id]} (max: {self.max_consecutive_losses})")
                logging.error(f"🛑 [{agent_id}] Trading HALTED due to consecutive losses")
    
    def check_kill_switch_triggers(self, agent_id: str, current_equity: float) -> tuple[bool, Optional[str]]:
        """
        Comprehensive kill-switch check for all safety triggers
        
        Returns:
            (allowed, reason): (True if trading allowed, None if allowed, reason string if halted)
        """
        # Check daily loss limit
        if not self.check_daily_loss_limit(agent_id, current_equity):
            return False, "daily_loss_limit_exceeded"
        
        # Check consecutive losses
        if agent_id in self.consecutive_losses and self.consecutive_losses[agent_id] >= self.max_consecutive_losses:
            if not self.trading_halted.get(agent_id, False):
                self.trading_halted[agent_id] = True
            return False, f"consecutive_losses_{self.consecutive_losses[agent_id]}"
        
        # Check API lag
        if agent_id in self.api_lag_times and len(self.api_lag_times[agent_id]) > 0:
            avg_lag = sum(self.api_lag_times[agent_id]) / len(self.api_lag_times[agent_id])
            if avg_lag > self.max_api_lag_seconds:
                if not self.trading_halted.get(agent_id, False):
                    self.trading_halted[agent_id] = True
                return False, f"api_lag_{avg_lag:.2f}s"
        
        # Check daily PnL < -2%
        daily_pnl_pct = self.get_daily_pnl_pct(agent_id, current_equity)
        if daily_pnl_pct < -2.0:
            if not self.trading_halted.get(agent_id, False):
                self.trading_halted[agent_id] = True
                logging.error(f"🚨 [{agent_id}] Daily PnL < -2%: {daily_pnl_pct:.2f}%")
            return False, f"daily_pnl_below_-2%_{daily_pnl_pct:.2f}%"
        
        return True, None
        
    def check_daily_loss_limit(self, agent_id: str, current_equity: float) -> bool:
        """Check if daily loss limit exceeded
        
        Returns:
            bool: True if trading allowed, False if halted
        """
        self.reset_if_new_day(agent_id)
        self.update_equity(agent_id, current_equity)
        
        if agent_id not in self.daily_starting_equity:
            return True
            
        starting = self.daily_starting_equity[agent_id]
        current = current_equity
        
        if starting <= 0:
            return True
            
        loss_pct = (starting - current) / starting
        
        if loss_pct >= self.max_daily_loss_pct and not self.trading_halted[agent_id]:
            self.trading_halted[agent_id] = True
            print(f"🚨 [{agent_id}] DAILY LOSS LIMIT EXCEEDED: {loss_pct*100:.2f}% (max: {self.max_daily_loss_pct*100:.1f}%)")
            print(f"🛑 [{agent_id}] Trading HALTED for today")
            return False
            
        return not self.trading_halted.get(agent_id, False)
    
    def is_trading_allowed(self, agent_id: str) -> bool:
        """Check if trading is allowed for agent"""
        self.reset_if_new_day(agent_id)
        return not self.trading_halted.get(agent_id, False)
    
    def get_daily_pnl(self, agent_id: str, current_equity: float) -> float:
        """Get current daily P&L"""
        if agent_id not in self.daily_starting_equity:
            return 0.0
        return current_equity - self.daily_starting_equity[agent_id]
    
    def get_daily_pnl_pct(self, agent_id: str, current_equity: float) -> float:
        """Get current daily P&L percentage"""
        if agent_id not in self.daily_starting_equity or self.daily_starting_equity[agent_id] <= 0:
            return 0.0
        return ((current_equity - self.daily_starting_equity[agent_id]) / self.daily_starting_equity[agent_id]) * 100

# Global daily loss tracker instance
daily_loss_tracker = DailyLossTracker(max_daily_loss_pct=0.05)

def position_size(equity, price, atr, risk_fraction, leverage, symbol, adjust=1.0):
    """
    Calculate position size based on risk parameters.
    
    ENHANCEMENT: Now uses equity-based dynamic scaling (0.5% of current equity).
    This ensures risk scales with account growth/shrinkage.
    """
    # Import settings to get the new risk parameters
    from core.settings import settings
    import logging
    
    # EQUITY-BASED SCALING: Use dynamic risk percentage based on current equity
    # Use actual RISK_FRACTION from settings (allow 2.5% as per requirements)
    # Cap at 3% maximum for safety, but allow full 2.5% if configured
    dynamic_risk_pct = min(risk_fraction, 0.03)  # Cap at 3% for safety
    if equity > 0:
        # Ensure minimum 0.1% risk for proper position sizing (removed restrictive 0.3% minimum)
        dynamic_risk_pct = max(dynamic_risk_pct, 0.001)  # Minimum 0.1% of equity
    
    # Calculate raw intended margin using dynamic risk percentage
    risk_amt = equity * dynamic_risk_pct * adjust
    
    # Cap the risk amount by the maximum allowed risk per trade (from settings)
    max_risk_per_trade = getattr(settings, 'MAX_RISK_PER_TRADE_USD', 125.0)  # Default $125 for 2.5% of $5k
    risk_amt = min(risk_amt, max_risk_per_trade)
    
    # === [ApexPatch2025-10-31] Refactored Quantity Calculation ===
    # Apply margin clamping logic before calculating quantity
    max_margin = settings.max_margin_per_trade
    min_margin = settings.MIN_MARGIN_PER_TRADE
    
    # Compute the raw intended margin
    raw_margin = risk_amt
    
    # Clamp margin between configured limits
    clamped_margin = max(min_margin, min(max_margin, raw_margin))
    
    # Compute quantity using clamped margin
    stop_distance = atr
    # Use MAX_LEVERAGE from settings (should be 2x from .env)
    max_lev = getattr(settings, 'max_leverage', 2)
    capped_leverage = min(leverage, max_lev)
    qty = (clamped_margin * capped_leverage) / price
    
    # Log the decision clearly
    logging.info(f"[QtyCalc] Final margin = ${clamped_margin:.2f} | leverage = {capped_leverage}x | qty = {qty:.6f}")
    
    # Ensure we respect Binance's minQty
    MIN_QTY_MAP = {"BTCUSDT": 0.001, "BNBUSDT": 0.1}
    min_qty = MIN_QTY_MAP.get(symbol, 0)
    
    if qty < min_qty:
        logging.warning(f"[QtyCalc] Qty {qty:.6f} < minQty {min_qty}, adjusting to {min_qty}")
        qty = min_qty
    
    # Optional - Add safety enforcement for Binance minimum notional
    MIN_NOTIONAL_USD = 10.0  # Increased from 5.0 to 10.0 to prevent micro orders
    if qty * price < MIN_NOTIONAL_USD:
        logging.warning(f"[RiskPostCheck] Skipping partial close: notional value ${qty * price:.2f} below minimum ${MIN_NOTIONAL_USD}")
        return 0  # Return 0 to skip the trade
    
    return qty

def check_drawdown(equity_series, max_dd=0.4):
    """Check if drawdown exceeds maximum threshold"""
    peak = np.maximum.accumulate(equity_series)
    dd = (peak - equity_series)/peak
    return dd.max() < max_dd