import pandas as pd
import time
import numpy as np
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Position:
    symbol: str
    side: str  # 'long' or 'short'
    qty: float
    entry_price: float
    entry_time: float
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

class Portfolio:
    def __init__(self, agent_id: str, capital: float = 10000):
        self.agent_id = agent_id
        self.equity = capital
        self.cash = capital
        self.initial_capital = capital
        self.peak_equity = capital
        self.max_drawdown = 0.0
        self.positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        self.history = pd.DataFrame(columns=[
            "timestamp", "symbol", "side", "qty", "entry_price", 
            "exit_price", "pnl", "pnl_pct", "duration_sec", "equity"
        ])
        self.equity_track = [(time.time(), capital)]

    def open_position(self, symbol: str, side: str, qty: float, price: float) -> bool:
        """
        Open a new position
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            side: 'long' or 'short'
            qty: Position size in base currency
            price: Entry price
            
        Returns:
            bool: True if position opened successfully, False otherwise
        """
        if symbol in self.positions:
            print(f"⚠️  Position for {symbol} already exists")
            return False
            
        if side not in ['long', 'short']:
            print(f"❌ Invalid position side: {side}")
            return False
            
        # For simplicity, we're not tracking margin/leverage here
        # In a real system, you'd want to track margin requirements
        self.positions[symbol] = Position(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=price,
            entry_time=time.time()
        )
        return True

    def close_position(self, symbol: str, price: float) -> Optional[Tuple[float, float]]:
        """
        Close an existing position and update equity
        
        Args:
            symbol: Symbol of the position to close
            price: Exit price
            
        Returns:
            Tuple of (pnl, pnl_pct) or None if no position exists
        """
        if symbol not in self.positions:
            print(f"⚠️  No open position for {symbol} to close")
            return None
            
        pos = self.positions.pop(symbol)
        now = time.time()
        
        # Calculate P&L
        if pos.side == 'long':
            pnl = (price - pos.entry_price) * pos.qty
        else:  # short
            pnl = (pos.entry_price - price) * pos.qty
            
        pnl_pct = (pnl / (pos.entry_price * pos.qty)) * 100
        
        # Update position with exit info
        pos.exit_price = price
        pos.exit_time = now
        pos.pnl = pnl
        pos.pnl_pct = pnl_pct
        
        # Update portfolio
        self.equity += pnl
        self.cash += pnl + (pos.entry_price * pos.qty)  # Return initial margin + P&L
        self.peak_equity = max(self.peak_equity, self.equity)
        self.max_drawdown = max(self.max_drawdown, self.get_drawdown())
        
        # Log to history
        self.closed_positions.append(pos)
        self.equity_track.append((now, self.equity))
        
        # Add to trade history
        self.history.loc[len(self.history)] = [
            now, 
            symbol, 
            pos.side, 
            pos.qty, 
            pos.entry_price, 
            price, 
            pnl, 
            pnl_pct, 
            now - pos.entry_time,
            self.equity
        ]
        
        return pnl, pnl_pct

    def get_open_positions(self) -> Dict[str, Position]:
        """
        Get all open positions
        
        Returns:
            Dict of {symbol: Position} for all open positions
        """
        return self.positions.copy()
    
    def has_position(self, symbol: str) -> bool:
        """
        Check if there's an open position for a symbol
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            
        Returns:
            bool: True if position exists, False otherwise
        """
        return symbol in self.positions
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get an open position by symbol
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Position object if found, None otherwise
        """
        return self.positions.get(symbol)
    
    def get_drawdown(self) -> float:
        """
        Calculate current drawdown from peak equity
        
        Returns:
            float: Drawdown as a percentage (0-100)
        """
        if len(self.equity_track) < 2:
            return 0.0
            
        # Extract just the equity values (second element of each tuple)
        equity_values = [entry[1] for entry in self.equity_track]
        peak = max(equity_values) if equity_values else 0.0
        current = self.equity
        
        if peak <= 0:
            return 0.0
            
        drawdown = (1 - current / peak) * 100
        return max(0.0, min(100.0, drawdown))  # Ensure result is between 0 and 100
    
    def get_total_return(self) -> float:
        """Calculate total return percentage"""
        return ((self.equity - self.initial_capital) / self.initial_capital) * 100
    
    def get_stats(self) -> Dict:
        """
        Get portfolio performance statistics
        
        Returns:
            Dict containing various performance metrics
        """
        total_return = (self.equity - self.initial_capital) / self.initial_capital * 100
        win_rate = 0
        avg_win = 0
        avg_loss = 0
        
        if not self.history.empty:
            wins = self.history[self.history['pnl'] > 0]
            losses = self.history[self.history['pnl'] < 0]
            
            win_rate = len(wins) / len(self.history) * 100 if len(self.history) > 0 else 0
            avg_win = wins['pnl'].mean() if not wins.empty else 0
            avg_loss = abs(losses['pnl'].mean()) if not losses.empty else 0
        
        return {
            'equity': self.equity,
            'cash': self.cash,
            'total_return': total_return,
            'drawdown': self.get_drawdown(),
            'max_drawdown': self.max_drawdown,
            'total_trades': len(self.history),
            'win_rate': win_rate,
            'profit_factor': (avg_win / avg_loss) if avg_loss != 0 else float('inf'),
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'positions': len(self.positions)
        }
        
    def calculate_sharpe_ratio(self, risk_free_rate: float = 0.0, period: str = 'daily') -> float:
        """
        Calculate Sharpe ratio for the portfolio
        
        Args:
            risk_free_rate: Annual risk-free rate (default: 0.0)
            period: Time period of returns ('daily', 'hourly', etc.)
            
        Returns:
            float: Sharpe ratio (annualized)
        """
        if len(self.equity_track) < 2:
            return 0.0
            
        # Calculate daily returns
        returns = []
        for i in range(1, len(self.equity_track)):
            prev_equity = self.equity_track[i-1][1]
            curr_equity = self.equity_track[i][1]
            returns.append((curr_equity - prev_equity) / prev_equity)
            
        if not returns:
            return 0.0
            
        # Convert to numpy array for calculations
        returns = np.array(returns)
        
        # Calculate annualization factor based on period
        if period == 'daily':
            trading_days = 252  # Typical number of trading days in a year
            ann_factor = np.sqrt(trading_days)
        elif period == 'hourly':
            trading_hours = 252 * 24  # 24/7 market
            ann_factor = np.sqrt(trading_hours)
        else:
            ann_factor = 1.0
        
        # Calculate Sharpe ratio
        excess_returns = returns - (risk_free_rate / ann_factor)
        if np.std(excess_returns) == 0:
            return 0.0
            
        return (np.mean(excess_returns) / np.std(excess_returns)) * ann_factor
