"""
Trading Orchestrator - Main Control Loop
Implements the complete trading flow with rule-based → ML → LLM pipeline
"""

import os
import time
import logging
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np

from core.data_engine import fetch_ohlcv
from core.signal_engine import compute_indicators, get_feature_summary
from core.ai_agent import decide
from core.coordinator_agent import coordinate
from core.signal_arbitrator import arbitrate_signals, check_signal_conflict
from core.risk_engine import position_size, daily_loss_tracker, check_drawdown
from core.portfolio import Portfolio
from core.storage import log_trade, log_equity
from core.order_manager import place_futures_order, close_position, get_current_position
from core.trading_engine import get_account_summary
from core.settings import settings
from core.csv_logger import log_decision, log_trade as csv_log_trade, log_error, log_learning, flush_all_csvs, force_flush_all
from hackathon_config import (
    CAPITAL, MAX_LEVERAGE, MAX_DRAWDOWN, TRADE_RISK,
    DAILY_LOSS_LIMIT, MIN_POSITION_SIZE
)

logger = logging.getLogger("orchestrator")

# Use paper_trading setting from settings instead of MODE environment variable
USE_PAPER_TRADING = settings.paper_trading


class TradingOrchestrator:
    """
    Main trading orchestrator that implements the complete pipeline:
    Data → Features → Rule-Based → ML → LLM → Risk Check → Execute
    
    Optimizations:
    - Shared data cache per symbol (reduces redundant API calls)
    - Centralized capital pool management
    - Efficient multi-agent coordination
    """
    
    def __init__(self, agent_configs: Dict[str, Any], portfolios: Dict[str, Portfolio]):
        self.agent_configs = agent_configs
        self.portfolios = portfolios
        self.iteration = 0
        self.equity_history = {agent_id: [] for agent_id in agent_configs.keys()}
        
        # Data cache: {symbol: {'data': df, 'timestamp': time, 'features_computed': bool}}
        self.data_cache = {}
        self.cache_ttl = 30  # Cache validity in seconds - reduced for faster ATR sync every cycle
        
        # Reversal cooldown tracking: {symbol: {"side": "BUY/SELL", "time": timestamp}}
        self.last_trade_meta = {}
        
        logger.info(f"Orchestrator initialized with {len(agent_configs)} agents")
        
    def _calculate_dynamic_tp_sl(self, atr: float, price: float, confidence: float) -> tuple[float, float]:
        """Calculate TP/SL based on volatility and confidence with sane bounds."""
        try:
            vol_ratio = (atr / price) * 100 if price > 0 else 0
            base_tp = settings.base_tp_percent
            base_sl = settings.base_sl_percent
            min_tp = settings.min_tp_percent
            max_tp = settings.max_tp_percent
            min_sl = settings.min_sl_percent
            max_sl = settings.max_sl_percent

            vol_multiplier = min(max(vol_ratio / 0.5, 0.5), 3.0)
            conf_multiplier = max(0.5, min(1.0, confidence)) * 0.5 + 0.5

            tp_pct = base_tp * vol_multiplier * conf_multiplier
            sl_pct = base_sl * vol_multiplier * conf_multiplier

            tp_pct = max(min(tp_pct, max_tp), min_tp)
            sl_pct = max(min(sl_pct, max_sl), min_sl)
            return tp_pct, sl_pct
        except Exception:
            return float(os.getenv("TAKE_PROFIT_PERCENT", 2.0)), float(os.getenv("STOP_LOSS_PERCENT", 1.0))
    
    def _calculate_symbol_specific_tp_sl(self, symbol: str, atr: float, price: float) -> tuple[float, float]:
        """Calculate symbol-specific TP/SL based on ATR with bounds checking."""
        try:
            # Normalize symbol name
            normalized_symbol = symbol.replace("/", "").upper()
            
            # Calculate TP/SL based on symbol and ATR
            if normalized_symbol.startswith("BTC"):
                # BTC: TP = 2.0 × ATR, SL = 1.0 × ATR
                tp_pct = 2.0 * (atr / price) * 100
                sl_pct = 1.0 * (atr / price) * 100
            elif normalized_symbol.startswith("BNB"):
                # BNB: TP = 1.5 × ATR, SL = 0.7 × ATR
                tp_pct = 1.5 * (atr / price) * 100
                sl_pct = 0.7 * (atr / price) * 100
            else:
                # Default fallback
                tp_pct = 2.0 * (atr / price) * 100
                sl_pct = 1.0 * (atr / price) * 100
            
            # Read from settings
            min_tp = settings.min_tp_percent
            max_tp = settings.max_tp_percent
            min_sl = settings.min_sl_percent
            max_sl = settings.max_sl_percent
            
            # Clamp TP/SL between min and max bounds
            tp = min(max(tp_pct, min_tp), max_tp)
            sl = min(max(sl_pct, min_sl), max_sl)
            
            # Log the bounded result
            logger.info(f"🎯 Final TP/SL set for {symbol}: TP={tp:.2f}%, SL={sl:.2f}%")
            
            return tp, sl
        except Exception as e:
            logger.warning(f"Failed to calculate symbol-specific TP/SL for {symbol}: {e}")
            # Fallback to default values
            return float(os.getenv("TAKE_PROFIT_PERCENT", 2.0)), float(os.getenv("STOP_LOSS_PERCENT", 1.0))

    def _get_cached_data(self, symbol: str, timeframe: str = "3m", force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        Get cached market data if still valid, otherwise fetch fresh.
        ATR is calculated fresh every cycle for accurate position sizing and signals.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe for data
            force_refresh: If True, bypass cache and fetch fresh data (for ATR sync every cycle)
        """
        cache_key = f"{symbol}_{timeframe}"
        current_time = time.time()
        
        # ATR SYNC FIX: Force refresh for trading decisions to ensure ATR is always current
        # This fixes "BTC slow reaction" by ensuring ATR updates every cycle
        if not force_refresh and cache_key in self.data_cache:
            cache_entry = self.data_cache[cache_key]
            # Reduce cache validity to ensure fresh ATR every cycle
            if current_time - cache_entry['timestamp'] < self.cache_ttl:
                # For critical indicators like ATR, always use fresh data if cache is > 10 seconds old
                cache_age = current_time - cache_entry['timestamp']
                if cache_age > 10:  # If cache is older than 10 seconds, refresh for accuracy
                    logger.debug(f"[ATR-Sync] Cache age {cache_age:.1f}s > 10s for {symbol}, refreshing for fresh ATR")
                    force_refresh = True
                else:
                    logger.debug(f"Using cached data for {symbol} ({timeframe})")
                    return cache_entry['data']
        
        # Fetch fresh data (always for force_refresh or expired cache)
        df = fetch_ohlcv(symbol, timeframe=timeframe, limit=200)
        if not df.empty and len(df) >= 50:
            df = compute_indicators(df)  # ATR is calculated here
            self.data_cache[cache_key] = {
                'data': df,
                'timestamp': current_time,
                'features_computed': True
            }
            logger.debug(f"Fetched and cached fresh data for {symbol} ({timeframe}) with updated ATR")
            return df
        
        return pd.DataFrame()
        
    def run_cycle(self, symbols: list = ['BTC/USDT', 'BNB/USDT']) -> Dict[str, Any]:
        """
        Run one complete trading cycle
        
        Returns:
            Dictionary with cycle statistics
        """
        self.iteration += 1
        cycle_stats = {
            'iteration': self.iteration,
            'timestamp': time.time(),
            'trades_executed': 0,
            'signals_generated': 0,
            'agents_active': 0
        }
        
        # Monitor positions for TP/SL hits (fallback mechanism)
        self._monitor_positions()
        
        # Header already printed in main.py, so we skip it here
        
        # FIXED: Collect all agent signals first, then arbitrate per symbol before executing
        # Initialize pending signals tracker if not exists
        if not hasattr(self, '_pending_signals'):
            self._pending_signals = {}
        
        # Process each agent and collect signals
        agent_results = {}
        for agent_id, config in self.agent_configs.items():
            try:
                result = self._process_agent(agent_id, config)
                agent_results[agent_id] = result
                
                if result['signal'] != 'hold':
                    cycle_stats['signals_generated'] += 1
                    # Store signal for arbitration
                    symbol = config.get('symbol', 'UNKNOWN')
                    if symbol not in self._pending_signals:
                        self._pending_signals[symbol] = []
                    
                    # Store all non-hold signals for arbitration (even if not yet executed)
                    # This allows arbitration to prevent conflicting trades before execution
                    if result['signal'] != 'hold':
                        self._pending_signals[symbol].append({
                            "agent_id": agent_id,
                            "signal": result['signal'],
                            "confidence": result.get('confidence', 0.0),
                            "reasoning": result.get('reasoning', ''),
                            "agent_style": config.get('style', 'unknown'),
                            "time": time.time(),
                            "executed": result.get('executed', False)
                        })
                
                if result['executed']:
                    cycle_stats['trades_executed'] += 1
                if result['active']:
                    cycle_stats['agents_active'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing agent {agent_id}: {e}", exc_info=True)
                print(f"  ⚠️  [{agent_id}] Error: {e}")
                # Log error to CSV
                log_error("orchestrator", agent_id, "", "exception", str(e), f"Error in agent processing", "", 0)
        
        # FIXED: Arbitrate signals per symbol after all agents processed
        # Check for conflicting signals and arbitrate before execution
        for symbol in list(self._pending_signals.keys()):
            signals = self._pending_signals[symbol]
            
            # Filter to only signals that passed initial checks (not rejected early)
            valid_signals = [s for s in signals if s.get('executed') or any(
                agent_results.get(aid, {}).get('signal') == s.get('signal') and 
                agent_results.get(aid, {}).get('reason') != 'rejected'
                for aid in self.agent_configs.keys()
                if self.agent_configs.get(aid, {}).get('symbol') == symbol
            )]
            
            if len(valid_signals) > 1:
                # Multiple agents have signals - arbitrate
                final_signal, arbitrated_conf, arbitration_reason = arbitrate_signals(symbol, valid_signals, time.time())
                logger.info(f"[SignalArbitrator] {symbol}: {arbitration_reason} → Final: {final_signal.upper()}")
                
                # Note: This is informational - actual execution prevention happens via cooldown checks
                # Future enhancement: could cancel conflicting orders here
        
        # Clear pending signals after arbitration (will be rebuilt next cycle)
        self._pending_signals = {}
        
        # FIXED: Log equity curve to CSV for persistence and analytics
        try:
            import csv
            import os
            equity_log_path = "logs/equity_curve.csv"
            equity_header = ["timestamp", "cycle", "agent_id", "equity", "equity_change", "equity_change_pct"]
            
            # Log equity for each agent
            for agent_id, portfolio in self.portfolios.items():
                equity = portfolio.equity
                
                # Calculate equity change
                prev_equity = getattr(self, '_last_equity', {}).get(agent_id, equity)
                equity_change = equity - prev_equity
                equity_change_pct = ((equity - prev_equity) / prev_equity * 100) if prev_equity > 0 else 0.0
                
                # Track last equity
                if not hasattr(self, '_last_equity'):
                    self._last_equity = {}
                self._last_equity[agent_id] = equity
                
                # Append to CSV
                os.makedirs("logs", exist_ok=True)
                file_exists = os.path.exists(equity_log_path)
                with open(equity_log_path, "a", newline="") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(equity_header)
                    writer.writerow([
                        time.time(),
                        self.iteration,
                        agent_id,
                        f"{equity:.2f}",
                        f"{equity_change:.2f}",
                        f"{equity_change_pct:.4f}"
                    ])
        except Exception as e:
            logger.warning(f"Failed to log equity curve: {e}")
        
        # FIXED: Daily equity reconciliation (every 10 cycles)
        if self.iteration % 10 == 0:  # Every 10 cycles
            try:
                from core.equity_reconciliation import daily_reconciliation
                from core.binance_client import get_futures_client
                
                client = get_futures_client()
                if client:
                    daily_reconciliation(client)
                    logger.debug(f"✅ Equity reconciliation completed (cycle {self.iteration})")
            except ImportError:
                logger.debug("Equity reconciliation module not available (optional)")
            except Exception as e:
                logger.warning(f"Failed equity reconciliation: {e}")
        
        # FIXED: Self-optimization (every 100 cycles)
        if self.iteration % 100 == 0:  # Every 100 cycles
            try:
                # Check if self-optimization is enabled
                self_optimize = settings.self_optimize or os.getenv('SELF_OPTIMIZE', 'False').lower() == 'true'
                if self_optimize:
                    from core.self_optimizer import optimize_agent_weights
                    
                    # Only optimize if agent_metrics.csv exists (from recent backtest)
                    metrics_file = "logs/backtest_results/agent_metrics.csv"
                    if os.path.exists(metrics_file):
                        logger.info(f"🧠 Running self-optimization (cycle {self.iteration})")
                        print(f"\n🧠 SELF-OPTIMIZATION TRIGGERED (Cycle {self.iteration})")
                        
                        new_weights = optimize_agent_weights(
                            metrics_file=metrics_file,
                            configs_dir="agents_config",
                            apply_changes=True,
                            min_weight=0.7,
                            max_weight=1.3
                        )
                        
                        if new_weights:
                            # Reload agent configs to get updated weights (will be picked up next cycle)
                            logger.info(f"✅ Agent weights updated - will reload configs next cycle")
                            print(f"✅ Agent weights updated successfully (will apply next cycle)")
                    else:
                        logger.debug(f"Skipping self-optimization: {metrics_file} not found")
            except ImportError:
                logger.debug("Self-optimizer module not available (optional)")
            except Exception as e:
                logger.warning(f"Failed self-optimization: {e}")
        
        # Flush CSV buffers every 5-10 cycles (performance optimization)
        flush_all_csvs()
        
        # Display cycle summary
        self._print_cycle_summary(cycle_stats)
        
        # Send dashboard update to API server
        try:
            dashboard_data = self.get_dashboard_data()
            # Add null guard
            if dashboard_data and isinstance(dashboard_data, dict):
                # Try to import and update API server
                try:
                    from api_server import update_dashboard_data
                    update_dashboard_data(dashboard_data)
                except ImportError:
                    # API server not running
                    pass
            else:
                logger.info("Dashboard data is None or not a dict, skipping update")
        except Exception as e:
            logger.warning(f"Could not update dashboard: {e}")
        
        return cycle_stats
    
    def _monitor_positions(self):
        """Monitor open positions and close when TP/SL reached (fallback mechanism)"""
        try:
            from core.order_manager import monitor_positions
            from core.binance_client import get_futures_client
            
            client = get_futures_client()
            if client:
                monitor_positions(client)
        except Exception as e:
            logger.warning(f"Position monitoring failed: {e}")
    
    def _process_agent(self, agent_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single agent through the complete pipeline
        
        Pipeline:
        1. Fetch market data
        2. Generate 40+ features
        3. Get AI decision (rule-based → ML → LLM)
        4. Coordinator meta-decision
        5. Risk management checks
        6. Execute trade (if MODE=live)
        7. Log and track
        
        Returns:
            Dictionary with processing results
        """
        portfolio = self.portfolios[agent_id]
        symbol = config.get('symbol', 'BNB/USDT')
        
        result = {
            'signal': 'hold',
            'executed': False,
            'active': False,
            'reason': None
        }
        
        # === STEP 1: SAFETY CHECKS ===
        portfolio_equity = portfolio.equity
        print(f"\n  🤖 Agent: {agent_id[:20]} │ Symbol: {symbol}")
        print(f"     💰 Current Equity: ${portfolio_equity:,.2f}")
        
        # GLOBAL KILL-SWITCH: Comprehensive safety check (daily loss, consecutive losses, API lag, PnL < -2%)
        allowed, kill_switch_reason = daily_loss_tracker.check_kill_switch_triggers(agent_id, portfolio_equity)
        if not allowed:
            result['reason'] = kill_switch_reason
            print(f"     ⛔ TRADING HALTED: {kill_switch_reason.replace('_', ' ').title()}")
            # Log decision rejection
            log_decision(agent_id, symbol, "hold", 0.0, f"Kill switch: {kill_switch_reason}", "rejected", 
                        kill_switch_reason, last_price if 'last_price' in locals() else 0.0, 
                        atr if 'atr' in locals() else 0.0, "", 0.0, False, "", 0.0, 1, "", "", 0.0, False)
            return result
        
        # CIRCUIT BREAKER: Check for extreme market conditions (news/spikes)
        # FIXED: Get price data BEFORE circuit breaker check to avoid uninitialized variable
        binance_symbol = symbol.replace("/", "").upper()
        try:
            from core.circuit_breaker import check_circuit_breaker, is_entry_paused
            from core.binance_client import get_futures_client
            
            client = get_futures_client()
            if client:
                # FIXED: Initialize last_price early for circuit breaker logging
                try:
                    ticker = client.futures_symbol_ticker(symbol=binance_symbol)
                    last_price = float(ticker.get('price', 0)) if ticker else 0.0
                except Exception:
                    last_price = 0.0
                
                should_pause, pause_reason, pause_until = check_circuit_breaker(client, binance_symbol)
                if should_pause:
                    result['reason'] = 'circuit_breaker_active'
                    remaining = int(pause_until - time.time()) if pause_until else 0
                    print(f"     ⏸️  ENTRY PAUSED: {pause_reason}")
                    print(f"        Circuit breaker active ({remaining//60}m {remaining%60}s remaining)")
                    # Log decision rejection
                    log_decision(agent_id, symbol, trading_signal if 'trading_signal' in locals() else "hold", 
                                confidence if 'confidence' in locals() else 0.0,
                                reasoning if 'reasoning' in locals() else "", "rejected", 
                                f"Circuit breaker: {pause_reason}", last_price, 0.0, "", 0.0, True, pause_reason, 
                                0.0, 1, "", "", 0.0, False)
                    return result
                
                # Also check if already paused
                if is_entry_paused(binance_symbol):
                    from core.circuit_breaker import get_circuit_breaker_status
                    status = get_circuit_breaker_status(binance_symbol)
                    if status:
                        result['reason'] = 'circuit_breaker_active'
                        remaining = status['remaining_seconds']
                        print(f"     ⏸️  ENTRY PAUSED: {status['reason']} ({remaining//60}m {remaining%60}s remaining)")
                        return result
        except Exception as e:
            logger.warning(f"Failed to check circuit breaker: {e}")
        
        result['active'] = True
        
        # === STEP 2: FETCH MARKET DATA ===
        df = self._get_cached_data(symbol, timeframe="3m", force_refresh=False)
        if df is None or df.empty or len(df) < 50:
            result['reason'] = 'insufficient_data'
            print(f"     ⚠️  Insufficient market data (need at least 50 candles)")
            # Log decision rejection
            log_decision(agent_id, symbol, "hold", 0.0, "Insufficient market data", "rejected", 
                        "insufficient_data", 0.0, 0.0, "", 0.0, False, "", 0.0, 1, "", "", 0.0, False)
            return result
        
        last_price = df['c'].iloc[-1]
        atr = df['atr'].iloc[-1] if 'atr' in df.columns else last_price * 0.02
        feature_count = len(df.columns)
        
        print(f"     📊 Market Data: Price=${last_price:,.2f} │ ATR=${atr:.2f} │ Features={feature_count}")
        
        # Step 3: AI Decision Pipeline (Rule-based → ML → LLM)
        decision = decide(symbol, df, config)
        raw_confidence = decision.get('confidence', 0.0)
        trading_signal = decision.get('signal', 'hold')
        reasoning = decision.get('reasoning', 'AI analysis indicates trade opportunity')
        strategy_used = decision.get('strategy_used', config.get('style', 'unknown'))
        
        # FIXED: Confidence normalization based on recent accuracy
        # Note: volatility_regime is set later in the code, so we'll use a default here
        confidence = raw_confidence  # Initialize with raw confidence
        
        try:
            from core.confidence_normalizer import normalize_confidence, record_decision
            
            # Get volatility regime if available (set later in code flow)
            vol_regime = "NORMAL"  # Default
            if 'volatility_regime' in locals():
                vol_regime = volatility_regime
            
            confidence = normalize_confidence(agent_id, raw_confidence, symbol, vol_regime)
            
            # Record decision for accuracy tracking
            if trading_signal != 'hold':
                record_decision(agent_id, trading_signal, raw_confidence)
            
            if confidence != raw_confidence:
                print(f"     📊 Confidence normalized: {raw_confidence:.1%} → {confidence:.1%}")
        except ImportError:
            confidence = raw_confidence  # Fallback if module not available
        
        result['signal'] = trading_signal
        
        # Update active agent signals for reversal cooldown logic
        try:
            from core.order_manager import update_active_agent_signals
            update_active_agent_signals(symbol, agent_id, trading_signal, confidence)
        except Exception as e:
            logger.warning(f"Failed to update active agent signals: {e}")
        
        # === STEP 3: AI DECISION ===
        if trading_signal != 'hold':
            emoji = "🟢" if trading_signal == 'long' else "🔴"
            signal_name = "BUY (LONG)" if trading_signal == 'long' else "SELL (SHORT)"
            print(f"     {emoji} AI Signal: {signal_name}")
            print(f"        Confidence: {confidence:.1%} │ Reason: {reasoning[:60]}...")
        else:
            print(f"     ⏸️  AI Signal: HOLD (no trading opportunity detected)")
            # Log hold decision
            log_decision(agent_id, symbol, "hold", confidence, reasoning, "hold", "", 
                        last_price, atr, "", 0.0, False, "", 0.0, 1, "", "", 0.0, True)
            return result
        
        # Step 4: Check confidence threshold with dynamic logic + volatility regime awareness
        # Allow environment to enforce a minimum floor without breaking per-agent configs
        min_conf_env = settings.min_confidence
        
        # Implement dynamic confidence threshold logic
        base_min_confidence = max(config.get('min_confidence', 0.65), min_conf_env)
        
        # VOLATILITY REGIME AWARENESS: Adjust confidence based on market volatility
        # Uses both market_analysis (simple) and regime_engine (dual-ATR) for comprehensive analysis
        try:
            from core.market_analysis import classify_volatility_regime, get_volatility_adjusted_confidence
            from core.regime_engine import get_regime_analysis
            from core.binance_client import get_futures_client
            
            client = get_futures_client()
            if client:
                binance_symbol = symbol.replace("/", "").upper()
                
                # Try dual-ATR regime analysis first (more sophisticated)
                regime_analysis = get_regime_analysis(client, binance_symbol)
                if regime_analysis:
                    regime = regime_analysis.get("regime", "NORMAL")
                    volatility_ratio = regime_analysis.get("volatility_ratio", 1.0)
                    atr_fast = regime_analysis.get("atr_fast", 0)
                    atr_slow = regime_analysis.get("atr_slow", 0)
                    
                    # Display regime information in user-friendly format
                    regime_emoji = {"EXTREME": "🔥", "HIGH": "⚡", "NORMAL": "📊", "LOW": "🌊"}
                    emoji = regime_emoji.get(regime, "📊")
                    print(f"     {emoji} Volatility Regime: {regime} (VR={volatility_ratio:.2f})")
                    if regime != "NORMAL":
                        print(f"        ATR Fast={atr_fast:.2f} │ ATR Slow={atr_slow:.2f} │ Ratio={volatility_ratio:.2f}")
                    
                    # Adjust confidence based on dual-ATR regime
                    if regime == "LOW":
                        base_min_confidence *= 1.05  # Increase threshold in low volatility
                    elif regime == "HIGH":
                        base_min_confidence *= 0.97  # Decrease threshold in high volatility
                    elif regime == "EXTREME":
                        base_min_confidence *= 1.10  # Significantly increase in extreme volatility
                else:
                    # Fallback to simple volatility classification
                    regime = classify_volatility_regime(binance_symbol, client)
                    base_min_confidence = get_volatility_adjusted_confidence(base_min_confidence, regime)
                    print(f"     📊 Volatility: {regime} (simple classification)")
        except Exception as e:
            logger.warning(f"Failed to apply volatility regime adjustment: {e}")
        
        # Check if dynamic confidence is enabled
        dynamic_confidence = settings.dynamic_confidence
        
        if dynamic_confidence:
            # Check if there's an existing position for this symbol
            existing_position = None
            try:
                from core.order_manager import get_current_position
                existing_position = get_current_position(symbol)
            except Exception:
                pass
            
            # If no open position, use temporary threshold
            if existing_position is None:
                min_confidence = 0.68  # Temporary threshold
            else:
                min_confidence = base_min_confidence  # Keep original threshold
        else:
            min_confidence = base_min_confidence
        
        # === STEP 4: CONFIDENCE CHECK ===
        print(f"     ✅ Confidence Check: {confidence:.1%} >= {min_confidence:.1%} required")
        
        # Initialize volatility regime info for logging (will be populated later)
        volatility_regime = ""
        volatility_ratio = 0.0
        circuit_breaker_active = False
        circuit_breaker_reason = ""
        regime_info = None
        
        if trading_signal == 'hold' or confidence < min_confidence:
            if trading_signal != 'hold':
                result['reason'] = 'low_confidence'
                print(f"     ⏸️  REJECTED: Confidence too low ({confidence:.1%} < {min_confidence:.1%})")
                # Log decision rejection with full context
                log_decision(agent_id, symbol, trading_signal, confidence, reasoning, "rejected",
                            f"Confidence too low: {confidence:.1%} < {min_confidence:.1%}", last_price, atr,
                            volatility_regime, volatility_ratio, circuit_breaker_active, circuit_breaker_reason,
                            0.0, 1, "", "", min_confidence, False)
            return result
        
        # === STEP 5: Signal will be arbitrated after all agents processed (see run_cycle)
        # For now, store signal metadata for later arbitration
        
        # === STEP 5.5: RISK ADJUSTMENTS ===
        meta_decision = coordinate({agent_id: config})
        adjustment = meta_decision.get('adjustment', 1.0)
        
        # CORRELATION FILTER: Reduce position size if BTC/BNB are highly correlated
        correlation_adjustment = 1.0
        try:
            from core.market_analysis import get_correlation_adjustment
            from core.binance_client import get_futures_client
            
            client = get_futures_client()
            if client:
                binance_symbol = symbol.replace("/", "").upper()
                # Check correlation if this is BNB and BTC might be open, or vice versa
                if "BNB" in binance_symbol:
                    correlation_adjustment = get_correlation_adjustment("BTCUSDT", binance_symbol, client, correlation_threshold=0.8)
                    if correlation_adjustment < 1.0:
                        print(f"     🔗 Correlation Filter: High BTC/BNB correlation detected → reducing size to {correlation_adjustment:.0%}")
        except Exception as e:
            logger.warning(f"Failed to apply correlation filter: {e}")
        
        # REGIME-BASED ADJUSTMENT: Apply volatility regime analysis for position sizing
        regime_adjustment = 1.0
        regime_info = None
        try:
            from core.regime_engine import get_regime_analysis
            from core.binance_client import get_futures_client
            
            client = get_futures_client()
            if client:
                binance_symbol = symbol.replace("/", "").upper()
                regime_info = get_regime_analysis(client, binance_symbol)
                
                if regime_info:
                    regime = regime_info.get("regime", "NORMAL")
                    regime_adjustments = regime_info.get("adjustments", {})
                    regime_adjustment = regime_adjustments.get("size_multiplier", 1.0)
                    
                    # Skip entry if regime requires it
                    if regime_adjustments.get("skip_entry", False):
                        result['reason'] = f'regime_skip_{regime.lower()}'
                        print(f"     ⏸️  REJECTED: {regime} volatility regime detected (too risky to enter)")
                        # Log decision rejection
                        volatility_regime = regime
                        volatility_ratio = regime_analysis.get("volatility_ratio", 0.0)
                        log_decision(agent_id, symbol, trading_signal, confidence, reasoning, "rejected",
                                    f"Regime skip: {regime} volatility", last_price, atr, volatility_regime,
                                    volatility_ratio, False, "", 0.0, leverage if 'leverage' in locals() else 1,
                                    "", "", min_confidence if 'min_confidence' in locals() else 0.0, True)
                        return result
                    
                    # Store regime info for logging
                    volatility_regime = regime
                    volatility_ratio = regime_analysis.get("volatility_ratio", 0.0)
                    
                    if regime_adjustment != 1.0:
                        print(f"     ⚡ Regime Adjustment: {regime} volatility → reducing size to {regime_adjustment:.0%}")
        except Exception as e:
            logger.warning(f"Failed to apply regime analysis: {e}")
        
        # Combine all adjustments: coordinator + correlation + regime
        final_adjustment = adjustment * correlation_adjustment * regime_adjustment
        
        # === STEP 6: POSITION SIZING ===
        # FIXED: Adaptive leverage based on volatility (instead of static 2x)
        base_leverage = int(decision.get('leverage', 2))
        
        # Adaptive leverage: 1x in LOW vol, 2x in NORMAL, 3x in HIGH (max 3x for safety)
        if 'volatility_regime' in locals() and volatility_regime:
            if volatility_regime == "LOW":
                leverage = min(base_leverage, 1)  # Conservative in low vol
            elif volatility_regime == "HIGH":
                leverage = min(base_leverage, 3)  # Slightly higher in high vol (but capped)
            elif volatility_regime == "EXTREME":
                leverage = min(base_leverage, 1)  # Very conservative in extreme
            else:
                leverage = min(base_leverage, 2)  # Normal = 2x
        else:
            leverage = min(base_leverage, MAX_LEVERAGE)
        
        leverage = max(1, leverage)  # Minimum 1x
        
        # FIXED: Leverage Governor - Auto-reduce after loss streak (max 3x, reduce by 1x per 2 losses)
        try:
            loss_streak = daily_loss_tracker.consecutive_losses.get(agent_id, 0)
            if loss_streak >= 2:
                # Reduce leverage after 2 consecutive losses
                leverage_reduction = min(loss_streak // 2, 2)  # Max reduction of 2x
                leverage = max(1, leverage - leverage_reduction)
                if leverage_reduction > 0:
                    print(f"     🛡️  Leverage Governor: Reduced to {leverage}x after {loss_streak} consecutive losses")
        except Exception as e:
            logger.warning(f"Failed to check leverage governor: {e}")
        
        # Enforce absolute max of 3x
        leverage = min(leverage, 3)
        
        # FIXED: Position stacking check - max 3 positions per symbol
        try:
            from core.binance_client import get_futures_client
            client = get_futures_client()
            if client:
                positions = client.futures_position_information()
                symbol_positions = [p for p in positions if p.get('symbol') == binance_symbol and abs(float(p.get('positionAmt', 0))) > 0]
                
                if len(symbol_positions) >= 3:
                    result['reason'] = 'position_stacking_limit'
                    print(f"     ⏸️  REJECTED: Maximum positions per symbol reached (3/3)")
                    log_decision(agent_id, symbol, trading_signal, confidence, reasoning, "rejected",
                                f"Position stacking limit: {len(symbol_positions)}/3 positions for {symbol}",
                                last_price, atr, volatility_regime if 'volatility_regime' in locals() else "", 
                                volatility_ratio if 'volatility_ratio' in locals() else 0.0, 
                                circuit_breaker_active if 'circuit_breaker_active' in locals() else False,
                                circuit_breaker_reason if 'circuit_breaker_reason' in locals() else "", 
                                qty if 'qty' in locals() else 0.0, leverage, "", "", min_confidence, True)
                    return result
        except Exception as e:
            logger.warning(f"Failed to check position stacking: {e}")
        
        # Calculate base position size
        qty = position_size(
            portfolio.equity,
            last_price,
            atr,
            TRADE_RISK,
            leverage,
            final_adjustment  # Use combined adjustment (coordinator + correlation + regime)
        )
        
        if qty <= 0 or qty < MIN_POSITION_SIZE:
            result['reason'] = 'position_too_small'
            print(f"     ⏸️  REJECTED: Position size too small (${qty * last_price:.2f} below minimum)")
            # Log decision rejection
            adjustments_str = f"coordinator:{adjustment:.2f},correlation:{correlation_adjustment:.2f},regime:{regime_adjustment:.2f}"
            log_decision(agent_id, symbol, trading_signal, confidence, reasoning, "rejected",
                        f"Position size too small: ${qty * last_price:.2f} < ${MIN_POSITION_SIZE * last_price:.2f}",
                        last_price, atr, volatility_regime, volatility_ratio, circuit_breaker_active,
                        circuit_breaker_reason, qty, leverage, "", adjustments_str, min_confidence, True)
            return result
        
        # Calculate position details for display
        position_value = qty * last_price
        margin_required = position_value / leverage
        risk_amount = margin_required  # Risk = margin (for 2.5% of equity)
        
        print(f"     💼 Position Size Calculation:")
        print(f"        Quantity: {qty:.6f} {symbol.split('/')[0]}")
        print(f"        Position Value: ${position_value:,.2f}")
        print(f"        Margin Required: ${margin_required:,.2f} (with {leverage}x leverage)")
        print(f"        Risk Amount: ${risk_amount:,.2f} ({risk_amount/portfolio_equity*100:.1f}% of equity)")
        if final_adjustment != 1.0:
            print(f"        Adjustments Applied: {final_adjustment:.1%} of base size")
        
        # === STEP 7: ADDITIONAL SAFETY CHECKS ===
        self.equity_history[agent_id].append(portfolio.equity)
        if len(self.equity_history[agent_id]) > 100:
            equity_series = pd.Series(self.equity_history[agent_id])
            if not check_drawdown(equity_series, MAX_DRAWDOWN):
                result['reason'] = 'max_drawdown_exceeded'
                print(f"     ⛔ REJECTED: Maximum drawdown exceeded (trading halted for safety)")
                # Log decision rejection
                adjustments_str = f"coordinator:{adjustment:.2f},correlation:{correlation_adjustment:.2f},regime:{regime_adjustment:.2f}"
                log_decision(agent_id, symbol, trading_signal, confidence, reasoning, "rejected",
                            "Maximum drawdown exceeded", last_price, atr, volatility_regime, volatility_ratio,
                            circuit_breaker_active, circuit_breaker_reason, qty, leverage, "", adjustments_str,
                            min_confidence, True)
                return result
        
        # REMOVED: Same-direction cooldown is redundant - order_manager already handles position checks
        # The position check in order_manager prevents duplicate entries when positions exist
        # If position is closed, allow new entries immediately (no artificial delays)
        
        # Simplified: Only apply reversal cooldown if there's an actual open position
        # This prevents rapid direction flips when a position is still open
        from core.order_manager import get_current_position
        current_position = get_current_position(symbol)
        binance_symbol = symbol.replace("/", "").upper()
        meta = self.last_trade_meta.get(binance_symbol)
        normalized_signal = "BUY" if trading_signal == "long" else "SELL"
        
        if meta and current_position:
            # Position exists - apply short reversal cooldown to prevent rapid flips
            now = time.time()
            last_time = meta.get("time", 0)
            last_side = meta.get("side", "")
            cooldown_period = float(settings.reversal_cooldown_period)
            
            if last_side and last_side != normalized_signal:
                elapsed = now - last_time
                if elapsed < cooldown_period:
                    remaining = int(cooldown_period - elapsed)
                    result['reason'] = 'reversal_cooldown_active'
                    print(f"     ⏸️  REJECTED: Reversal cooldown active ({remaining}s remaining) - position still open")
                    adjustments_str = f"coordinator:{adjustment:.2f},correlation:{correlation_adjustment:.2f},regime:{regime_adjustment:.2f}"
                    log_decision(agent_id, symbol, trading_signal, confidence, reasoning, "rejected",
                                f"Reversal cooldown active ({remaining}s remaining)", last_price, atr, volatility_regime,
                                volatility_ratio, circuit_breaker_active, circuit_breaker_reason, qty, leverage, "",
                                adjustments_str, min_confidence, True)
                    return result
        
        print(f"     ✅ All safety checks passed")
        
        # Log successful decision (about to execute) with full context
        adjustments_str = f"coordinator:{adjustment:.2f},correlation:{correlation_adjustment:.2f},regime:{regime_adjustment:.2f}"
        risk_factors_str = f"position_value:${position_value:.2f},margin:${margin_required:.2f},risk_pct:{risk_amount/portfolio_equity*100:.2f}%"
        log_decision(agent_id, symbol, trading_signal, confidence, reasoning, "executed", "",
                    last_price, atr, volatility_regime, volatility_ratio, circuit_breaker_active,
                    circuit_breaker_reason, qty, leverage, risk_factors_str, adjustments_str,
                    min_confidence, True)
        
        # === STEP 8: EXECUTE TRADE ===
        signal_name = "BUY (LONG)" if trading_signal == 'long' else "SELL (SHORT)"
        print(f"     🚀 Executing {signal_name} order...")
        
        # Initialize timestamp for trade metadata
        now = time.time()
        
        if not USE_PAPER_TRADING:
            # LIVE FUTURES TRADING
            executed = self._execute_live_trade(
                agent_id, portfolio, symbol, trading_signal,
                qty, leverage, last_price, atr, confidence, decision
            )
            
            # Update last trade metadata if trade was successful
            if executed:
                self.last_trade_meta[binance_symbol] = {"side": normalized_signal, "time": now}
                print(f"     ✅ ORDER EXECUTED: {signal_name} {qty:.6f} {symbol.split('/')[0]} @ ${last_price:,.2f}")
                print(f"        TP/SL orders attached automatically")
            else:
                print(f"     ❌ Order execution failed (check logs for details)")
            
            result['executed'] = executed
        else:
            # PAPER TRADING (Simulation)
            executed = self._execute_paper_trade(
                agent_id, portfolio, symbol, trading_signal,
                qty, last_price, confidence, decision
            )
            
            # Update last trade metadata if trade was successful
            if executed:
                self.last_trade_meta[binance_symbol] = {"side": normalized_signal, "time": now}
                print(f"     ✅ PAPER TRADE: {signal_name} {qty:.6f} {symbol.split('/')[0]} @ ${last_price:,.2f} (simulated)")
            
            result['executed'] = executed
        
        return result
    
    def _execute_live_trade(
        self, agent_id: str, portfolio: Portfolio, symbol: str,
        signal: str, qty: float, leverage: int, price: float, atr: float,
        confidence: float, decision: Dict
    ) -> bool:
        """Execute live trade on Binance Futures Testnet using order_manager with TP/SL"""
        side = 'buy' if signal == 'long' else 'sell'
        
        try:
            # Get TP/SL percentages from environment or compute dynamically
            if (os.getenv("DYNAMIC_TP_SL", "false").lower() == "true"):
                # Use symbol-specific TP/SL calculation
                tp_pct, sl_pct = self._calculate_symbol_specific_tp_sl(symbol, atr, price)
            else:
                tp_pct = float(os.getenv("TAKE_PROFIT_PERCENT", 2.0))
                sl_pct = float(os.getenv("STOP_LOSS_PERCENT", 1.0))
            
            # Place live futures order using unified order_manager with TP/SL
            logger.info(f"[Orchestrator] About to call place_futures_order: {symbol} {side} qty={qty} tp={tp_pct}% sl={sl_pct}%")
            order = place_futures_order(
                symbol=symbol,
                side=side,
                qty=qty,
                leverage=leverage,
                order_type="MARKET",
                agent_id=agent_id,
                tp_pct=tp_pct,
                sl_pct=sl_pct
            )
            logger.info(f"[Orchestrator] place_futures_order returned: status={order.get('status')}")
            
            # Check order status
            if order.get('status') == 'error':
                error_msg = order.get('message', 'Unknown error')
                print(f"     ❌ Order failed: {error_msg[:50]}")
                # Log error to CSV
                log_error("orchestrator", agent_id, symbol, "order_execution_error", error_msg,
                         f"Order execution failed: side={side}, qty={qty}, leverage={leverage}", "", 0)
                return False
            
            if order.get('status') == 'skipped':
                skip_reason = order.get('message', 'Unknown reason')
                print(f"     ⏭️ Skipped: {skip_reason[:50]}")
                # Log skipped decision
                log_decision(agent_id, symbol, signal, confidence, decision.get('reasoning', ''), "skipped",
                            skip_reason, price, atr, "", 0.0, False, "", qty, leverage, "", "", 0.0, False)
                return False
            
            # Extract order details
            entry_price = float(order.get('price', price))
            filled_qty = float(order.get('qty', qty))
            order_id = order.get('order_id', 'N/A')
            tp_order_id = order.get('tp_order_id', 'N/A')
            sl_order_id = order.get('sl_order_id', 'N/A')
            
            agent_str = agent_id[:15].ljust(15)
            signal_str = signal.upper().ljust(5)
            # Handle missing order IDs safely
            tp_id = tp_order_id if tp_order_id else 'N/A'
            sl_id = sl_order_id if sl_order_id else 'N/A'
            tp_display = tp_id[:8] if tp_id != 'N/A' and tp_id else 'N/A'
            sl_display = sl_id[:8] if sl_id != 'N/A' and sl_id else 'N/A'
            tp_sl_info = f" TP: {tp_display} SL: {sl_display}"
            print(f"     ✅ [{agent_str}] LIVE {signal_str} {filled_qty:.4f} @ ${entry_price:.2f} (Lev: {leverage}x, ID: {order_id}){tp_sl_info}")
            
            # Update portfolio for tracking
            portfolio.open_position(symbol, signal, filled_qty, entry_price)
            
            # FIXED: Set trade state to OPEN
            try:
                from core.trade_state_manager import set_trade_state, reset_trade_state
                binance_symbol = symbol.replace("/", "").upper()
                reset_trade_state(binance_symbol)  # Clear any old state
                set_trade_state(binance_symbol, "OPEN")
            except ImportError:
                pass
            
            # Update last trade metadata
            binance_symbol = symbol.replace("/", "").upper()
            self.last_trade_meta[binance_symbol] = {"side": signal.upper(), "time": time.time()}
            
            # Log the trade to database (keep for compatibility)
            log_trade(
                agent_id, symbol, signal, filled_qty,
                entry_price, entry_price, 0.0,  # PnL calculated on close
                confidence, decision.get('reasoning', '')
            )
            log_equity(agent_id, portfolio.equity)
            
            # Log to CSV with full context
            reasoning = decision.get('reasoning', '')
            strategy_used = decision.get('strategy_used', 'unknown')
            csv_log_trade(
                agent_id=agent_id,
                symbol=symbol,
                side=signal.upper(),
                qty=filled_qty,
                entry_price=entry_price,
                status="OPENED",
                message=f"Order {order_id} filled",
                order_id=str(order_id),
                confidence=confidence,
                reasoning=reasoning,
                leverage=leverage,
                volatility_regime="",  # Will be populated if available
                tp_percent=tp_pct,
                sl_percent=sl_pct,
                strategy_used=strategy_used
            )
            
            # Store decision metadata in a simple cache for later retrieval (for learning bridge)
            # Key format: symbol_agent_id_entry_price
            try:
                from core.learning_bridge import _decision_cache
                cache_key = f"{symbol.replace('/', '')}_{agent_id}_{entry_price:.2f}"
                _decision_cache[cache_key] = {
                    "timestamp": time.time(),
                    "signal": signal,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "strategy_used": strategy_used,
                    "agent_id": agent_id
                }
            except Exception:
                pass  # Cache is optional
            
            return True
            
        except Exception as e:
            logger.error(f"Live order error for {agent_id}: {e}", exc_info=True)
            print(f"     ❌ Live order failed: {str(e)[:50]}")
            return False
    
    def _execute_paper_trade(
        self, agent_id: str, portfolio: Portfolio, symbol: str,
        signal: str, qty: float, price: float,
        confidence: float, decision: Dict
    ) -> bool:
        """Execute simulated paper trade"""
        try:
            # Open position
            portfolio.open_position(symbol, signal, qty, price)
            agent_str = agent_id[:15].ljust(15)
            signal_str = signal.upper().ljust(5)
            print(f"     📝 [{agent_str}] PAPER {signal_str} {qty:.4f} @ ${price:.2f}")
            
            # Update last trade metadata
            binance_symbol = symbol.replace("/", "").upper()
            self.last_trade_meta[binance_symbol] = {"side": signal.upper(), "time": time.time()}
            
            # Simulate price movement
            import random
            price_change = random.uniform(-0.002, 0.003) if signal == 'long' else random.uniform(-0.003, 0.002)
            new_price = price * (1 + price_change)
            
            # Close position and calculate P&L
            result = portfolio.close_position(symbol, new_price)
            if result:
                pnl, pnl_pct = result
                
                # FIXED: Record outcome for confidence normalization (paper trades)
                try:
                    from core.confidence_normalizer import record_outcome
                    # Determine if decision was correct
                    was_correct = (pnl > 0 and signal == "long") or (pnl < 0 and signal == "short")
                    record_outcome(agent_id, was_correct)
                except ImportError:
                    pass
                
                # Log trade
                log_trade(
                    agent_id, symbol, signal, qty,
                    price, new_price, pnl,
                    confidence, decision.get('reasoning', '')
                )
                log_equity(agent_id, portfolio.equity)
                
                # Display result
                emoji = "💚" if pnl > 0 else "💔"
                print(f"     {emoji} Closed | P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%) | Equity: ${portfolio.equity:.2f}")
                
            return True
            
        except Exception as e:
            logger.error(f"Paper trade error for {agent_id}: {e}", exc_info=True)
            print(f"     ❌ Paper trade failed: {str(e)[:50]}")
            return False
    
    def _print_cycle_summary(self, stats: Dict[str, Any]):
        """Print cycle summary with current positions and profits"""
        # Calculate portfolio metrics
        total_equity = sum(p.equity for p in self.portfolios.values())
        total_pnl = total_equity - (CAPITAL * len(self.portfolios))
        pnl_pct = (total_pnl / (CAPITAL * len(self.portfolios))) * 100 if len(self.portfolios) > 0 else 0
        
        # --- Live Position Summary (Binance Futures) ---
        try:
            from core.binance_client import get_futures_client
            client = get_futures_client()
            if client:
                positions = client.futures_position_information()

                print("\n📊 LIVE POSITION SUMMARY")
                print("Symbol      Side   Qty        Entry        Mark        PnL(USDT)   ROI(%)     Lev  Margin")
                print("─────────────────────────────────────────────────────────────────────────────────────────────")

                for p in positions:
                    qty = float(p["positionAmt"])
                    if qty == 0:
                        continue

                    entry = float(p["entryPrice"])
                    mark = float(p["markPrice"])
                    pnl = float(p["unRealizedProfit"])
                    side = "LONG" if qty > 0 else "SHORT"
                    roi = (pnl / (abs(qty) * entry)) * 100 if entry != 0 else 0
                    
                    # Get actual leverage - calculate from notional and isolated margin
                    leverage = p.get("leverage", None)
                    if leverage is None or leverage == "":
                        # Calculate leverage from position notional and isolated margin
                        notional = abs(float(p.get("notional", 0)))
                        isolated_margin = float(p.get("isolatedMargin", 0))
                        if isolated_margin > 0 and notional > 0:
                            calculated_leverage = notional / isolated_margin
                            leverage = f"{calculated_leverage:.1f}"
                        else:
                            # Fallback to known leverage from settings (we use 2x)
                            from core.settings import settings
                            leverage = f"{settings.max_leverage}"
                    
                    # Ensure leverage is a string for display
                    if isinstance(leverage, (int, float)):
                        leverage = f"{int(leverage)}"
                    
                    margin_type = p.get("marginType", "Cross")
                    if margin_type == "":
                        margin_type = "Cross"

                    print(f"{p['symbol']:<10} {side:<5} {abs(qty):<10.4f} {entry:<12.2f} {mark:<12.2f} "
                          f"{pnl:<10.2f} ({roi:+.2f}%)     {leverage}x  {margin_type}")

                print("─────────────────────────────────────────────────────────────────────────────────────────────\n")
        except Exception as e:
            logger.error(f"⚠️ Failed to fetch live position summary: {e}")
        
        # Log PnL summary every 10 cycles
        if self.iteration % 10 == 0:
            logger.info(f"[Orchestrator] 📊 PnL Summary - Cycle #{self.iteration}: Total Equity=${total_equity:,.2f}, Total PnL=${total_pnl:+.2f} ({pnl_pct:+.2f}%)")
        
        print(f"\n┌─" + "─"*76 + "─┐")
        print("│ 📈 CYCLE SUMMARY" + " "*62 + "│")
        print("├─" + "─"*76 + "─┤")
        print(f"│ Active Agents: {stats['agents_active']}/{len(self.agent_configs)}" + " "*(63-len(str(stats['agents_active']))-len(str(len(self.agent_configs)))) + "│")
        print(f"│ Signals Generated: {stats['signals_generated']}" + " "*(60-len(str(stats['signals_generated']))) + "│")
        print(f"│ Trades Executed: {stats['trades_executed']}" + " "*(62-len(str(stats['trades_executed']))) + "│")
        print("└─" + "─"*76 + "─┘")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get current dashboard data with full position details"""
        from core.binance_client import get_full_balance, get_futures_client
        from core.binance_client import is_testnet_mode
        from core.settings import settings
        
        # Get balance
        try:
            balance = get_full_balance()
        except Exception as e:
            print(f"⚠️  Could not fetch balance: {e}")
            balance = {"total": CAPITAL, "free": CAPITAL, "used": 0.0}
        
        # Calculate total portfolio metrics
        total_equity = sum(p.equity for p in self.portfolios.values())
        total_pnl = total_equity - (CAPITAL * len(self.portfolios))
        total_pnl_pct = (total_pnl / (CAPITAL * len(self.portfolios))) * 100 if len(self.portfolios) > 0 else 0
        
        # Collect agent data with P&L
        agents_data = []
        for agent_id, portfolio in self.portfolios.items():
            agent_config = self.agent_configs.get(agent_id, {})
            agent_initial = CAPITAL
            agent_pnl = portfolio.equity - agent_initial
            agent_pnl_pct = (agent_pnl / agent_initial) * 100 if agent_initial > 0 else 0
            
            # Count positions for this agent
            agent_positions_count = len(portfolio.get_open_positions())
            
            agents_data.append({
                "agent_id": agent_id,
                "symbol": agent_config.get("symbol", "N/A"),
                "style": agent_config.get("style", "unknown"),
                "equity": portfolio.equity,
                "pnl": agent_pnl,
                "pnl_pct": agent_pnl_pct,
                "positions": agent_positions_count
            })
        
        # Get open positions from Binance
        open_positions = []
        try:
            client = get_futures_client()
            if client:
                positions = client.futures_position_information()
                for p in positions:
                    qty = float(p["positionAmt"])
                    if qty == 0:
                        continue
                    
                    entry = float(p["entryPrice"])
                    pnl = float(p["unRealizedProfit"])
                    side = "LONG" if qty > 0 else "SHORT"
                    
                    open_positions.append({
                        "symbol": p['symbol'],
                        "side": side,
                        "size": abs(qty),
                        "entry": entry,
                        "pnl": pnl
                    })
        except Exception as e:
            logger.warning(f"Could not fetch positions for dashboard: {e}")
        
        # Determine mode
        mode = "paper" if settings.paper_trading else "live"
        if is_testnet_mode():
            mode = "live"  # Testnet is still "live" demo trading
        
        # Return complete dashboard data
        return {
            "iteration": self.iteration,
            "agents": agents_data,
            "total_equity": total_equity,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "mode": mode,
            "balance": balance,
            "open_positions": open_positions,
            "last_update": time.strftime('%Y-%m-%dT%H:%M:%S')
        }
