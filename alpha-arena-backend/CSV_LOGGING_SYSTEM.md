# 📊 Comprehensive CSV Logging System

## Overview
All trading decisions, errors, trades, and learning data are now logged to structured CSV files. Buffered writes ensure optimal performance (flushed every 7 cycles).

---

## 📁 CSV Files Created

### 1. `logs/decisions_log.csv`
**All decisions (executed, rejected, skipped, hold)**
- Every agent decision with full context
- Rejection reasons
- Market conditions at decision time
- Confidence levels and thresholds

**Columns:**
```
timestamp, agent_id, symbol, signal, confidence, reasoning, status, 
rejection_reason, market_price, atr, volatility_regime, volatility_ratio,
circuit_breaker_active, circuit_breaker_reason, position_size_calculated,
leverage, risk_factors, adjustments_applied, min_confidence_required,
confidence_check_passed
```

### 2. `logs/trades_log.csv` (Enhanced)
**All trades with full context**
- Entry and exit prices
- PnL and PnL%
- Exit reasons (TP/SL/MANUAL)
- Market conditions at entry/exit
- Strategy used
- Hold duration

**Columns:**
```
time, agent_id, symbol, side, qty, entry_price, exit_price, pnl, pnl_pct,
status, message, order_id, confidence, reasoning, leverage, volatility_regime,
tp_percent, sl_percent, exit_reason, price_action_exit, market_conditions_exit,
strategy_used, hold_duration_sec
```

### 3. `logs/errors_log.csv` (New)
**Structured error tracking**
- Component where error occurred
- Error type and message
- Context and resolution
- Retry attempts

**Columns:**
```
timestamp, component, agent_id, symbol, error_type, error_message,
context, resolution, retry_count, order_id
```

### 4. `logs/learning_log.csv` (New)
**Decision → Outcome mapping for ML/learning**
- Decision details
- Outcome (win/loss/breakeven)
- PnL and confidence accuracy
- Lessons learned
- Market conditions

**Columns:**
```
timestamp, agent_id, symbol, decision_signal, decision_confidence,
decision_reasoning, outcome_status, outcome_pnl, outcome_pnl_pct,
exit_reason, strategy_used, market_conditions_entry, market_conditions_exit,
confidence_accuracy, lesson_learned, hold_duration_sec
```

---

## ⚡ Performance Optimization

### Buffered Writes
- All logs are buffered in memory
- Flushed to disk **every 7 cycles** (between 5-10 as requested)
- No blocking I/O during trading execution
- Automatic flush on shutdown

### Flush Points
1. **Every 7 cycles** in `run_cycle()` → `flush_all_csvs()`
2. **On shutdown** → `force_flush_all()` in signal handler

---

## 🔍 What Gets Logged

### ✅ Decisions Logged
- **Hold decisions** (AI signals hold)
- **Rejected decisions** with reasons:
  - Low confidence
  - Circuit breaker active
  - Regime skip (EXTREME/LOW volatility)
  - Position too small
  - Max drawdown exceeded
  - Reversal cooldown
  - Kill switch triggers
- **Executed decisions** (passed all checks)
- **Skipped decisions** (order manager rejections)

### ✅ Errors Logged
- Binance API errors
- Order execution exceptions
- Precision errors
- Order rejections during validation
- Component-level exceptions

### ✅ Trades Logged
- Order opens (with TP/SL attached)
- Trade closes (with exit reasons)
- PnL calculations
- Market conditions at entry/exit

### ✅ Learning Data
- Decision → Outcome pairs
- Confidence accuracy
- Strategy effectiveness
- Lessons learned

---

## 📍 Integration Points

### `core/orchestrator.py`
- Logs all decisions at rejection points
- Logs executed decisions before trade
- Logs trade execution results
- Flushes CSV buffers every cycle

### `core/order_manager.py`
- Logs order rejections
- Logs Binance API errors
- Logs precision errors

### `core/trade_manager.py`
- Enhanced trade close logging
- Exit reasons and PnL details

### `main.py`
- Force flush on shutdown

---

## 📊 How to Use the Logs

### View Recent Decisions
```bash
tail -n 50 logs/decisions_log.csv
```

### Analyze Rejection Reasons
```bash
grep "rejected" logs/decisions_log.csv | cut -d',' -f8 | sort | uniq -c
```

### View All Errors
```bash
cat logs/errors_log.csv
```

### Calculate Win Rate
```python
import pandas as pd
df = pd.read_csv('logs/trades_log.csv')
wins = df[df['pnl'] > 0]
win_rate = len(wins) / len(df) * 100
print(f"Win Rate: {win_rate:.2f}%")
```

### Analyze Strategy Performance
```python
import pandas as pd
df = pd.read_csv('logs/learning_log.csv')
strategy_perf = df.groupby('strategy_used')['outcome_pnl'].agg(['mean', 'count', 'sum'])
print(strategy_perf)
```

---

## 🎯 Benefits

1. **Complete Audit Trail**: Every decision, error, and trade is logged
2. **Performance**: Buffered writes don't slow down trading
3. **Easy Analysis**: CSV format works with Excel, Python pandas, etc.
4. **Learning**: Decision → Outcome mapping enables ML improvements
5. **Debugging**: Structured errors help identify issues quickly
6. **Compliance**: Full trading history for review

---

## 🔧 Configuration

CSV files are automatically created in `logs/` directory:
- `decisions_log.csv`
- `trades_log.csv`
- `errors_log.csv`
- `learning_log.csv`

Flush interval: **7 cycles** (configurable in `csv_logger.py` line 31)

---

## ✅ Verification

After running the bot, check:
1. CSV files are created in `logs/` directory
2. Data appears after every 7 cycles
3. All decisions are logged (even rejections)
4. Errors are captured with context
5. Trades have full context (entry/exit reasons)

---

**Status**: ✅ Fully Implemented and Integrated

