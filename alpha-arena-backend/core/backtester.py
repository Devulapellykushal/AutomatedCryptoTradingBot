#!/usr/bin/env python3
"""
Backtesting Engine for Kushal Trading System
Replays historical OHLCV data and simulates agent trading decisions
"""

import os
import sys
import pandas as pd
import numpy as np
import time
import json
import argparse
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_engine import fetch_ohlcv
from core.signal_engine import compute_indicators
from core.ai_agent import decide
from core.coordinator_agent import coordinate
from core.signal_arbitrator import arbitrate_signals
from core.risk_engine import position_size, daily_loss_tracker
from core.portfolio import Portfolio
from core.regime_engine import get_regime_analysis
from core.market_analysis import get_correlation_adjustment
from core.circuit_breaker import check_circuit_breaker
from hackathon_config import CAPITAL, load_symbols, TRADE_RISK
from core.settings import settings

# Create logs directory structure
LOGS_DIR = Path("logs/backtest_results")
LOGS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class BacktestPosition:
    """Represents an open position in backtesting"""
    symbol: str
    side: str  # 'long' or 'short'
    qty: float
    entry_price: float
    entry_time: float
    entry_timestamp: pd.Timestamp
    tp_price: float
    sl_price: float
    leverage: int = 1
    partial_close_executed: bool = False
    breakeven_sl_updated: bool = False
    agent_id: str = ""
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class BacktestTrade:
    """Represents a completed trade"""
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    entry_time: float
    exit_time: float
    entry_timestamp: pd.Timestamp
    exit_timestamp: pd.Timestamp
    pnl: float
    pnl_pct: float
    duration_seconds: float
    agent_id: str
    confidence: float
    reasoning: str
    exit_reason: str  # 'TP', 'SL', 'PARTIAL_CLOSE', 'BREAKEVEN_SL'
    leverage: int = 1


class BacktestEngine:
    """Main backtesting engine that replays historical data"""
    
    def __init__(self, agent_configs: Dict[str, Dict], initial_capital: float = CAPITAL):
        self.agent_configs = agent_configs
        self.initial_capital = initial_capital
        self.portfolios: Dict[str, Portfolio] = {}
        self.positions: Dict[str, Dict[str, BacktestPosition]] = {}  # {agent_id: {symbol: position}}
        self.closed_trades: List[BacktestTrade] = []
        self.equity_curve: List[Dict] = []
        self.cycle_count = 0
        
        # Initialize portfolios for each agent
        for agent_id in agent_configs.keys():
            self.portfolios[agent_id] = Portfolio(agent_id=agent_id, capital=initial_capital)
            self.positions[agent_id] = {}
            daily_loss_tracker.initialize_agent(agent_id, initial_capital)
    
    def load_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        from_csv: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Load historical OHLCV data from CSV or Binance API
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '3m', '15m', '1h')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            from_csv: Optional path to CSV file (if provided, loads from file)
            
        Returns:
            DataFrame with OHLCV data
        """
        if from_csv and os.path.exists(from_csv):
            # Load from CSV
            print(f"📂 Loading historical data from CSV: {from_csv}")
            df = pd.read_csv(from_csv)
            # Ensure timestamp column exists
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            elif 'time' in df.columns:
                df['timestamp'] = pd.to_datetime(df['time'])
                df = df.rename(columns={'time': 'timestamp'})
            else:
                raise ValueError("CSV must contain 'timestamp' or 'time' column")
            
            # Ensure required columns exist
            required_cols = ['o', 'h', 'l', 'c', 'v']
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                raise ValueError(f"CSV missing required columns: {missing}")
            
            # Filter by date range
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            df = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)]
            
            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            print(f"✅ Loaded {len(df)} candles from CSV")
            return df
        
        # Load from Binance API
        print(f"📡 Fetching historical data from Binance: {symbol} ({timeframe})")
        print(f"   Date range: {start_date} to {end_date}")
        
        # Binance API limits: max 1000 candles per request
        # We'll need to batch requests for longer periods
        all_data = []
        current_date = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        from binance.client import Client
        from core.binance_client import get_data_client, initialize_binance_clients
        
        # Initialize Binance clients first (required before fetching data)
        init_result = initialize_binance_clients()
        if not init_result.get('futures', False):
            raise ConnectionError(
                "Failed to initialize Binance API client. "
                "Please check:\n"
                "1. BINANCE_API_KEY and BINANCE_API_SECRET in .env\n"
                "2. Network connection\n"
                "3. Or use --csv option to load from CSV file"
            )
        
        client = get_data_client()
        if client is None:
            raise ConnectionError(
                "Failed to connect to Binance API. "
                "Please check:\n"
                "1. BINANCE_API_KEY and BINANCE_API_SECRET in .env\n"
                "2. Network connection\n"
                "3. Or use --csv option to load from CSV file"
            )
        
        binance_symbol = symbol.replace("/", "").upper()
        timeframe_map = {
            "1m": Client.KLINE_INTERVAL_1MINUTE,
            "3m": Client.KLINE_INTERVAL_3MINUTE,
            "5m": Client.KLINE_INTERVAL_5MINUTE,
            "15m": Client.KLINE_INTERVAL_15MINUTE,
            "30m": Client.KLINE_INTERVAL_30MINUTE,
            "1h": Client.KLINE_INTERVAL_1HOUR,
            "2h": Client.KLINE_INTERVAL_2HOUR,
            "4h": Client.KLINE_INTERVAL_4HOUR,
            "6h": Client.KLINE_INTERVAL_6HOUR,
            "8h": Client.KLINE_INTERVAL_8HOUR,
            "12h": Client.KLINE_INTERVAL_12HOUR,
            "1d": Client.KLINE_INTERVAL_1DAY,
        }
        
        interval = timeframe_map.get(timeframe, Client.KLINE_INTERVAL_3MINUTE)
        
        # Calculate timeframe duration in minutes
        tf_minutes = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360,
            "8h": 480, "12h": 720, "1d": 1440
        }.get(timeframe, 3)
        
        # Fetch in batches (1000 candles max per request)
        max_candles_per_request = 1000
        batch_duration = max_candles_per_request * tf_minutes
        
        while current_date < end:
            batch_end = min(current_date + timedelta(minutes=batch_duration), end)
            
            try:
                klines = client.futures_historical_klines(
                    symbol=binance_symbol,
                    interval=interval,
                    start_str=current_date.strftime('%Y-%m-%d %H:%M:%S'),
                    end_str=batch_end.strftime('%Y-%m-%d %H:%M:%S'),
                    limit=max_candles_per_request
                )
                
                if klines:
                    for k in klines:
                        all_data.append({
                            'timestamp': pd.to_datetime(k[0], unit='ms'),
                            'o': float(k[1]),
                            'h': float(k[2]),
                            'l': float(k[3]),
                            'c': float(k[4]),
                            'v': float(k[5])
                        })
                
                current_date = batch_end
                time.sleep(0.2)  # Rate limit protection
                
            except Exception as e:
                print(f"⚠️  Error fetching batch {current_date}: {e}")
                current_date = batch_end
        
        if not all_data:
            raise ValueError("No historical data fetched from Binance")
        
        df = pd.DataFrame(all_data)
        df = df.sort_values('timestamp').reset_index(drop=True)
        df = df.drop_duplicates(subset=['timestamp']).reset_index(drop=True)
        
        print(f"✅ Fetched {len(df)} candles from Binance API")
        return df
    
    def simulate_order_execution(
        self,
        agent_id: str,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        tp_pct: float,
        sl_pct: float,
        leverage: int,
        confidence: float,
        reasoning: str,
        timestamp: pd.Timestamp
    ) -> bool:
        """
        Simulate order execution (opens a position)
        
        Returns:
            True if order executed, False otherwise
        """
        # Check if agent already has position in this symbol
        if symbol in self.positions[agent_id]:
            return False  # Skip duplicate entry
        
        # Calculate TP/SL prices
        if side.lower() == 'long':
            tp_price = price * (1 + tp_pct / 100)
            sl_price = price * (1 - sl_pct / 100)
        else:  # short
            tp_price = price * (1 - tp_pct / 100)
            sl_price = price * (1 + sl_pct / 100)
        
        # Create position
        position = BacktestPosition(
            symbol=symbol,
            side=side.lower(),
            qty=qty,
            entry_price=price,
            entry_time=time.time(),
            entry_timestamp=timestamp,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage,
            agent_id=agent_id,
            confidence=confidence,
            reasoning=reasoning
        )
        
        self.positions[agent_id][symbol] = position
        
        # Update portfolio equity (subtract margin)
        portfolio = self.portfolios[agent_id]
        margin_used = (qty * price) / leverage
        portfolio.equity -= margin_used
        
        return True
    
    def check_exit_conditions(
        self,
        agent_id: str,
        symbol: str,
        current_candle: pd.Series,
        timestamp: pd.Timestamp
    ) -> Optional[BacktestTrade]:
        """
        Check if position should be closed (TP/SL hit, partial close, etc.)
        
        Returns:
            BacktestTrade if position closed, None otherwise
        """
        if symbol not in self.positions[agent_id]:
            return None
        
        position = self.positions[agent_id][symbol]
        portfolio = self.portfolios[agent_id]
        
        # Get current price (use close of current candle)
        current_price = current_candle['c']
        high = current_candle['h']
        low = current_candle['l']
        
        exit_reason = None
        exit_price = current_price
        
        # Check TP/SL hits
        if position.side == 'long':
            # Long position
            if low <= position.sl_price:
                # Stop loss hit
                exit_reason = 'SL'
                exit_price = position.sl_price  # Use SL price, not low
            elif high >= position.tp_price:
                # Take profit hit
                exit_reason = 'TP'
                exit_price = position.tp_price  # Use TP price, not high
            elif current_price >= position.entry_price * 1.003 and not position.partial_close_executed:
                # Partial close at +0.3% ROI (25% of position)
                exit_reason = 'PARTIAL_CLOSE'
                exit_price = current_price
            elif position.partial_close_executed and not position.breakeven_sl_updated:
                # Move SL to breakeven after partial close
                position.sl_price = position.entry_price
                position.breakeven_sl_updated = True
                return None  # Don't close, just update SL
        else:  # short
            if high >= position.sl_price:
                # Stop loss hit (for shorts, SL is above entry)
                exit_reason = 'SL'
                exit_price = position.sl_price
            elif low <= position.tp_price:
                # Take profit hit (for shorts, TP is below entry)
                exit_reason = 'TP'
                exit_price = position.tp_price
            elif current_price <= position.entry_price * 0.997 and not position.partial_close_executed:
                # Partial close at +0.3% ROI (for shorts, price drops)
                exit_reason = 'PARTIAL_CLOSE'
                exit_price = current_price
            elif position.partial_close_executed and not position.breakeven_sl_updated:
                # Move SL to breakeven after partial close
                position.sl_price = position.entry_price
                position.breakeven_sl_updated = True
                return None
        
        if exit_reason:
            # Close position
            if exit_reason == 'PARTIAL_CLOSE':
                # Partial close: close 25%, keep 75%
                close_qty = position.qty * 0.25
                position.qty *= 0.75  # Reduce position size
                position.partial_close_executed = True
                
                # Calculate PnL for partial close
                if position.side == 'long':
                    partial_pnl = (exit_price - position.entry_price) * close_qty
                else:
                    partial_pnl = (position.entry_price - exit_price) * close_qty
                
                # Update portfolio equity (add back margin + profit)
                margin_returned = (close_qty * position.entry_price) / position.leverage
                portfolio.equity += margin_returned + partial_pnl
                
                # Create trade record for partial close
                trade = BacktestTrade(
                    symbol=symbol,
                    side=position.side,
                    qty=close_qty,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    entry_time=position.entry_time,
                    exit_time=time.time(),
                    entry_timestamp=position.entry_timestamp,
                    exit_timestamp=timestamp,
                    pnl=partial_pnl,
                    pnl_pct=(partial_pnl / (position.entry_price * close_qty)) * 100,
                    duration_seconds=(timestamp - position.entry_timestamp).total_seconds(),
                    agent_id=agent_id,
                    confidence=position.confidence,
                    reasoning=position.reasoning,
                    exit_reason=exit_reason,
                    leverage=position.leverage
                )
                
                self.closed_trades.append(trade)
                return None  # Don't close full position, just record partial
            else:
                # Full close (TP or SL)
                close_qty = position.qty
                
                # Calculate PnL
                if position.side == 'long':
                    pnl = (exit_price - position.entry_price) * close_qty
                else:
                    pnl = (position.entry_price - exit_price) * close_qty
                
                # Update portfolio equity
                margin_returned = (close_qty * position.entry_price) / position.leverage
                portfolio.equity += margin_returned + pnl
                
                # Create trade record
                trade = BacktestTrade(
                    symbol=symbol,
                    side=position.side,
                    qty=close_qty,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    entry_time=position.entry_time,
                    exit_time=time.time(),
                    entry_timestamp=position.entry_timestamp,
                    exit_timestamp=timestamp,
                    pnl=pnl,
                    pnl_pct=(pnl / (position.entry_price * close_qty)) * 100,
                    duration_seconds=(timestamp - position.entry_timestamp).total_seconds(),
                    agent_id=agent_id,
                    confidence=position.confidence,
                    reasoning=position.reasoning,
                    exit_reason=exit_reason,
                    leverage=position.leverage
                )
                
                # Remove position
                del self.positions[agent_id][symbol]
                self.closed_trades.append(trade)
                
                # Record outcome for learning
                daily_loss_tracker.record_trade_outcome(agent_id, pnl > 0)
                
                return trade
        
        return None
    
    def process_cycle(self, df: pd.DataFrame, cycle_idx: int) -> Dict[str, Any]:
        """
        Process one trading cycle (one candle)
        
        Args:
            df: Full historical DataFrame
            cycle_idx: Index of current candle
            
        Returns:
            Dictionary with cycle results
        """
        self.cycle_count += 1
        
        if cycle_idx >= len(df):
            return {'processed': False}
        
        current_candle = df.iloc[cycle_idx]
        timestamp = current_candle['timestamp']
        
        # Need historical data up to current candle
        historical_df = df.iloc[:cycle_idx + 1].copy()
        
        if len(historical_df) < 50:
            return {'processed': False, 'reason': 'insufficient_data'}  # Need at least 50 candles for indicators
        
        # Compute indicators
        historical_df = compute_indicators(historical_df)
        current_data = historical_df.iloc[-1]
        
        # First, check exit conditions for all open positions
        for agent_id in list(self.positions.keys()):
            for symbol in list(self.positions[agent_id].keys()):
                closed_trade = self.check_exit_conditions(agent_id, symbol, current_data, timestamp)
                if closed_trade:
                    print(f"  [{agent_id}] {symbol} {closed_trade.exit_reason} @ {closed_trade.exit_price:.2f} | PnL: {closed_trade.pnl:+.2f} ({closed_trade.pnl_pct:+.2f}%)")
        
        # Process each agent for new entries
        trades_executed = 0
        
        for agent_id, config in self.agent_configs.items():
            symbol = config.get('symbol', 'BTC/USDT')
            portfolio = self.portfolios[agent_id]
            
            # Skip if agent already has position in this symbol
            if symbol in self.positions[agent_id]:
                continue
            
            # Check kill-switch
            allowed, reason = daily_loss_tracker.check_kill_switch_triggers(agent_id, portfolio.equity)
            if not allowed:
                continue
            
            try:
                # Get AI decision using same pipeline as live trading
                decision = decide(symbol, historical_df, config)
                
                trading_signal = decision.get('signal', 'hold')
                if trading_signal == 'hold':
                    continue
                
                confidence = decision.get('confidence', 0.5)
                
                # Check confidence threshold
                min_confidence = settings.min_confidence
                if confidence < min_confidence:
                    continue
                
                # Get coordinator adjustment (same way as orchestrator)
                # Note: coordinate() expects agent_configs dict, not individual params
                meta_decision = coordinate({agent_id: config})
                adjustment = meta_decision.get('adjustment', 1.0)
                final_confidence = confidence  # Use raw confidence (coordinate doesn't modify it)
                
                # Check circuit breaker (simplified for backtesting)
                # Skip regime analysis for backtesting (uses API which is slow and not needed for historical data)
                # Regime analysis is primarily for live trading volatility monitoring
                
                # Calculate position size
                atr = current_data.get('atr', 0.0)
                if atr == 0:
                    atr = (current_data['h'] - current_data['l']) * 0.01  # Fallback
                
                current_price = current_data['c']
                
                # Determine leverage (adaptive based on volatility regime)
                leverage = decision.get('leverage', 2)
                
                # Use same position sizing logic as live trading
                # Signature: position_size(equity, price, atr, risk_fraction, leverage, symbol, adjust=1.0)
                qty = position_size(
                    portfolio.equity,     # equity (positional)
                    current_price,        # price (positional)
                    atr,                  # atr (positional)
                    TRADE_RISK,           # risk_fraction (positional)
                    leverage,             # leverage (positional)
                    symbol,               # symbol (positional)
                    adjust=adjustment     # adjust (keyword, optional)
                )
                
                if qty <= 0:
                    continue
                
                # Calculate TP/SL (use ATR-based dynamic TP/SL)
                tp_pct, sl_pct = self._calculate_dynamic_tp_sl(
                    symbol=symbol,
                    atr=atr,
                    price=current_price
                )
                
                # Execute simulated order (leverage already determined above)
                executed = self.simulate_order_execution(
                    agent_id=agent_id,
                    symbol=symbol,
                    side='long' if trading_signal == 'long' else 'short',
                    qty=qty,
                    price=current_price,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    leverage=leverage,
                    confidence=final_confidence,
                    reasoning=decision.get('reasoning', ''),
                    timestamp=timestamp
                )
                
                if executed:
                    trades_executed += 1
                    print(f"  [{agent_id}] {trading_signal.upper()} {symbol} @ {current_price:.2f} | Qty: {qty:.4f} | Confidence: {final_confidence:.1%}")
                
            except Exception as e:
                print(f"  ⚠️  Error processing {agent_id}: {e}")
                continue
        
        # Update equity curve
        total_equity = sum(p.equity for p in self.portfolios.values())
        self.equity_curve.append({
            'timestamp': timestamp,
            'cycle': self.cycle_count,
            'total_equity': total_equity,
            'equity_change': total_equity - self.initial_capital,
            'equity_change_pct': ((total_equity - self.initial_capital) / self.initial_capital) * 100
        })
        
        # Update daily loss tracker
        for agent_id, portfolio in self.portfolios.items():
            daily_loss_tracker.update_equity(agent_id, portfolio.equity)
        
        return {
            'processed': True,
            'trades_executed': trades_executed,
            'timestamp': timestamp
        }
    
    def _calculate_dynamic_tp_sl(self, symbol: str, atr: float, price: float) -> Tuple[float, float]:
        """Calculate dynamic TP/SL based on ATR (same logic as orchestrator)"""
        try:
            normalized_symbol = symbol.replace("/", "").upper()
            
            if normalized_symbol.startswith("BTC"):
                tp_pct = 2.0 * (atr / price) * 100
                sl_pct = 1.0 * (atr / price) * 100
            elif normalized_symbol.startswith("BNB"):
                tp_pct = 1.5 * (atr / price) * 100
                sl_pct = 0.7 * (atr / price) * 100
            else:
                tp_pct = 2.0 * (atr / price) * 100
                sl_pct = 1.0 * (atr / price) * 100
            
            # Apply clamps
            tp_pct = max(0.5, min(tp_pct, 5.0))  # 0.5% to 5%
            sl_pct = max(0.3, min(sl_pct, 2.0))  # 0.3% to 2%
            
            return tp_pct, sl_pct
        except:
            return 2.0, 1.0  # Default fallback
    
    def run_backtest(
        self,
        df: pd.DataFrame,
        progress_interval: int = 100
    ) -> Dict[str, Any]:
        """
        Run complete backtest on historical data
        
        Args:
            df: Historical OHLCV DataFrame
            progress_interval: Print progress every N cycles
            
        Returns:
            Dictionary with backtest results
        """
        print(f"\n🚀 Starting backtest on {len(df)} candles...")
        print(f"   Initial Capital: ${self.initial_capital:,.2f}")
        print(f"   Agents: {len(self.agent_configs)}\n")
        
        total_cycles = len(df)
        processed_cycles = 0
        
        for i in range(50, total_cycles):  # Start from 50 to have enough data for indicators
            if i % progress_interval == 0:
                progress = (i / total_cycles) * 100
                print(f"📊 Progress: {i}/{total_cycles} ({progress:.1f}%) | Trades: {len(self.closed_trades)}")
            
            result = self.process_cycle(df, i)
            if result.get('processed'):
                processed_cycles += 1
        
        # Close any remaining open positions at the end
        final_price = df.iloc[-1]['c']
        final_timestamp = df.iloc[-1]['timestamp']
        
        for agent_id in list(self.positions.keys()):
            for symbol in list(self.positions[agent_id].keys()):
                position = self.positions[agent_id][symbol]
                portfolio = self.portfolios[agent_id]
                
                # Calculate final PnL
                if position.side == 'long':
                    pnl = (final_price - position.entry_price) * position.qty
                else:
                    pnl = (position.entry_price - final_price) * position.qty
                
                margin_returned = (position.qty * position.entry_price) / position.leverage
                portfolio.equity += margin_returned + pnl
                
                trade = BacktestTrade(
                    symbol=symbol,
                    side=position.side,
                    qty=position.qty,
                    entry_price=position.entry_price,
                    exit_price=final_price,
                    entry_time=position.entry_time,
                    exit_time=time.time(),
                    entry_timestamp=position.entry_timestamp,
                    exit_timestamp=final_timestamp,
                    pnl=pnl,
                    pnl_pct=(pnl / (position.entry_price * position.qty)) * 100,
                    duration_seconds=(final_timestamp - position.entry_timestamp).total_seconds(),
                    agent_id=agent_id,
                    confidence=position.confidence,
                    reasoning=position.reasoning,
                    exit_reason='END_OF_BACKTEST',
                    leverage=position.leverage
                )
                
                self.closed_trades.append(trade)
        
        print(f"\n✅ Backtest complete!")
        print(f"   Processed: {processed_cycles} cycles")
        print(f"   Total Trades: {len(self.closed_trades)}")
        
        return {
            'total_cycles': processed_cycles,
            'total_trades': len(self.closed_trades),
            'trades': self.closed_trades,
            'equity_curve': self.equity_curve,
            'final_equity': sum(p.equity for p in self.portfolios.values())
        }
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """Calculate performance metrics for each agent"""
        metrics = {}
        
        for agent_id, portfolio in self.portfolios.items():
            agent_trades = [t for t in self.closed_trades if t.agent_id == agent_id]
            
            if not agent_trades:
                metrics[agent_id] = {
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'profit_factor': 0.0,
                    'sharpe_ratio': 0.0,
                    'max_drawdown': 0.0,
                    'total_pnl': 0.0,
                    'avg_pnl': 0.0
                }
                continue
            
            wins = [t for t in agent_trades if t.pnl > 0]
            losses = [t for t in agent_trades if t.pnl < 0]
            
            total_pnl = sum(t.pnl for t in agent_trades)
            win_rate = len(wins) / len(agent_trades) if agent_trades else 0.0
            
            gross_profit = sum(t.pnl for t in wins) if wins else 0.0
            gross_loss = abs(sum(t.pnl for t in losses)) if losses else 1.0  # Avoid division by zero
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
            
            # Calculate Sharpe ratio (annualized)
            returns = [t.pnl_pct / 100 for t in agent_trades]  # Convert to decimal
            if len(returns) > 1 and np.std(returns) > 0:
                sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252)  # Annualized (assuming daily-ish trades)
            else:
                sharpe = 0.0
            
            # Calculate max drawdown
            equity_values = [self.initial_capital]
            for trade in agent_trades:
                equity_values.append(equity_values[-1] + trade.pnl)
            
            peak = equity_values[0]
            max_dd = 0.0
            for equity in equity_values:
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
            
            metrics[agent_id] = {
                'total_trades': len(agent_trades),
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'sharpe_ratio': sharpe,
                'max_drawdown': max_dd,
                'total_pnl': total_pnl,
                'avg_pnl': total_pnl / len(agent_trades) if agent_trades else 0.0,
                'final_equity': portfolio.equity
            }
        
        return metrics
    
    def save_results(self, output_dir: Path = LOGS_DIR):
        """Save backtest results to CSV files"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save trades
        if self.closed_trades:
            trades_df = pd.DataFrame([
                {
                    'timestamp': t.exit_timestamp,
                    'agent_id': t.agent_id,
                    'symbol': t.symbol,
                    'side': t.side,
                    'qty': t.qty,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'pnl': t.pnl,
                    'pnl_pct': t.pnl_pct,
                    'duration_seconds': t.duration_seconds,
                    'confidence': t.confidence,
                    'reasoning': t.reasoning,
                    'exit_reason': t.exit_reason,
                    'leverage': t.leverage
                }
                for t in self.closed_trades
            ])
            trades_df.to_csv(output_dir / 'backtest_trades.csv', index=False)
            print(f"💾 Saved {len(trades_df)} trades to {output_dir / 'backtest_trades.csv'}")
        
        # Save equity curve
        if self.equity_curve:
            equity_df = pd.DataFrame(self.equity_curve)
            equity_df.to_csv(output_dir / 'backtest_equity_curve.csv', index=False)
            print(f"💾 Saved equity curve to {output_dir / 'backtest_equity_curve.csv'}")
        
        # Save agent metrics
        metrics = self.calculate_metrics()
        metrics_df = pd.DataFrame([
            {
                'agent_id': agent_id,
                **metrics[agent_id]
            }
            for agent_id in metrics.keys()
        ])
        metrics_df.to_csv(output_dir / 'agent_metrics.csv', index=False)
        print(f"💾 Saved agent metrics to {output_dir / 'agent_metrics.csv'}")
        
        return metrics


def summarize_backtest(metrics: Dict[str, Any]) -> None:
    """
    Display comprehensive backtest summary
    
    Args:
        metrics: Dictionary of agent metrics from calculate_metrics()
    """
    print("\n" + "="*80)
    print("📊 BACKTEST SUMMARY")
    print("="*80)
    
    total_trades = sum(m['total_trades'] for m in metrics.values())
    total_pnl = sum(m['total_pnl'] for m in metrics.values())
    
    print(f"\n🎯 OVERALL PERFORMANCE:")
    print(f"   Total Trades: {total_trades}")
    print(f"   Total PnL: ${total_pnl:+,.2f}")
    
    if total_trades > 0:
        overall_win_rate = sum(m['win_rate'] * m['total_trades'] for m in metrics.values()) / total_trades
        print(f"   Overall Win Rate: {overall_win_rate:.1%}")
        
        # Weighted average Sharpe
        total_sharpe = sum(m['sharpe_ratio'] * m['total_trades'] for m in metrics.values() if m['total_trades'] > 0)
        if total_trades > 0:
            avg_sharpe = total_sharpe / total_trades
            print(f"   Average Sharpe Ratio: {avg_sharpe:.2f}")
    
    print(f"\n📈 PER-AGENT METRICS:")
    print(f"{'Agent ID':<25} {'Trades':<8} {'Win %':<8} {'PnL':<12} {'Sharpe':<10} {'Max DD':<10}")
    print("-" * 80)
    
    for agent_id, m in sorted(metrics.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
        print(f"{agent_id:<25} {m['total_trades']:<8} {m['win_rate']*100:>6.1f}% ${m['total_pnl']:>+10.2f} {m['sharpe_ratio']:>9.2f} {m['max_drawdown']*100:>9.1f}%")
    
    print("="*80 + "\n")


def load_agent_configs(symbols: Optional[List[str]] = None) -> Dict[str, Dict]:
    """
    Load agent configurations, optionally filtered by symbols
    
    Args:
        symbols: List of symbols to filter by (e.g., ['BTC/USDT'])
        
    Returns:
        Dictionary of agent_id -> agent_config
    """
    import json
    from pathlib import Path
    
    agent_configs = {}
    config_dir = Path("agents_config")
    
    if not config_dir.exists():
        raise FileNotFoundError(f"Agents config directory not found: {config_dir}")
    
    for config_file in config_dir.glob("*.json"):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            agent_id = config.get('agent_id')
            symbol = config.get('symbol')
            
            if agent_id and symbol:
                if symbols is None or symbol in symbols:
                    agent_configs[agent_id] = config
        except Exception as e:
            print(f"⚠️  Error loading {config_file}: {e}")
    
    return agent_configs


def main():
    """CLI entry point for backtester"""
    parser = argparse.ArgumentParser(description='Kushal Backtesting Engine')
    parser.add_argument('--symbol', type=str, required=True, help='Trading pair (e.g., BTC/USDT or BTCUSDT)')
    parser.add_argument('--timeframe', type=str, default='3m', help='Timeframe (1m, 3m, 15m, 1h, etc.)')
    parser.add_argument('--start', type=str, required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--csv', type=str, help='Optional: Load from CSV file instead of Binance API')
    parser.add_argument('--capital', type=float, default=CAPITAL, help='Initial capital (default: from config)')
    parser.add_argument('--output-dir', type=str, default='logs/backtest_results', help='Output directory for results')
    
    args = parser.parse_args()
    
    # Normalize symbol format (accept both BTC/USDT and BTCUSDT)
    if "/" in args.symbol:
        symbol_with_slash = args.symbol  # Already has slash
    else:
        # Convert BTCUSDT to BTC/USDT
        symbol_with_slash = f"{args.symbol[:-4]}/{args.symbol[-4:]}"
    
    # Load agent configs for the specified symbol
    agent_configs = load_agent_configs(symbols=[symbol_with_slash])
    
    if not agent_configs:
        print(f"❌ No agent configs found for symbol {symbol_with_slash}")
        return
    
    print(f"✅ Loaded {len(agent_configs)} agent configs for {symbol_with_slash}")
    
    # Initialize backtest engine
    engine = BacktestEngine(agent_configs, initial_capital=args.capital)
    
    # Load historical data
    try:
        df = engine.load_historical_data(
            symbol=symbol_with_slash,
            timeframe=args.timeframe,
            start_date=args.start,
            end_date=args.end,
            from_csv=args.csv
        )
        
        if df.empty:
            print("❌ No historical data loaded")
            return
        
        # Run backtest
        results = engine.run_backtest(df)
        
        # Calculate metrics
        metrics = engine.calculate_metrics()
        
        # Save results
        output_dir = Path(args.output_dir)
        engine.save_results(output_dir)
        
        # Display summary
        summarize_backtest(metrics)
        
        print(f"✅ Backtest complete! Results saved to {output_dir}")
        
    except Exception as e:
        print(f"❌ Error running backtest: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

