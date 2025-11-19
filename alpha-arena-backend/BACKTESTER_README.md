# 🧪 Backtesting & Self-Optimization Modules

This document explains how to use the new **Backtesting Engine** and **Self-Optimization** modules in Kushal.

---

## 📊 **Backtesting Engine**

The backtesting module (`core/backtester.py`) allows you to replay historical market data and test your trading strategies without risking real capital.

### **Features:**
- ✅ Replays historical OHLCV data (from CSV or Binance API)
- ✅ Uses the **exact same agent logic** as live trading
- ✅ Simulates TP/SL, partial closes, and trailing stops
- ✅ Calculates performance metrics (Sharpe ratio, win rate, drawdown)
- ✅ Exports results to CSV for analysis

### **Usage:**

#### **1. Run Backtest from Command Line:**

```bash
cd alpha-arena-backend

# Basic backtest
python3 backtester.py \
  --symbol BTC/USDT \
  --timeframe 3m \
  --start "2024-10-01" \
  --end "2024-11-01"

# Using CSV file instead of API
python3 backtester.py \
  --symbol BTC/USDT \
  --timeframe 3m \
  --start "2024-10-01" \
  --end "2024-11-01" \
  --csv data/historical_btc.csv

# Custom capital and output directory
python3 backtester.py \
  --symbol BTC/USDT \
  --timeframe 3m \
  --start "2024-10-01" \
  --end "2024-11-01" \
  --capital 5000 \
  --output-dir logs/my_backtest
```

#### **2. Programmatic Usage:**

```python
from core.backtester import BacktestEngine, load_agent_configs, summarize_backtest

# Load agent configs
agent_configs = load_agent_configs(symbols=['BTC/USDT'])

# Initialize engine
engine = BacktestEngine(agent_configs, initial_capital=10000)

# Load historical data (from API)
df = engine.load_historical_data(
    symbol='BTC/USDT',
    timeframe='3m',
    start_date='2024-10-01',
    end_date='2024-11-01'
)

# Run backtest
results = engine.run_backtest(df)

# Calculate metrics
metrics = engine.calculate_metrics()

# Save results
engine.save_results()

# Display summary
summarize_backtest(metrics)
```

### **Output Files:**

After running a backtest, you'll find these files in `logs/backtest_results/`:

1. **`backtest_trades.csv`** - All executed trades with full details:
   - Entry/exit prices, PnL, duration
   - Agent ID, confidence, reasoning
   - Exit reason (TP, SL, PARTIAL_CLOSE, etc.)

2. **`backtest_equity_curve.csv`** - Equity over time:
   - Timestamp, cycle number
   - Total equity, equity change, equity change %

3. **`agent_metrics.csv`** - Performance metrics per agent:
   - Total trades, win rate, profit factor
   - Sharpe ratio, max drawdown
   - Total PnL, average PnL

### **Command Line Arguments:**

```
--symbol        Trading pair (e.g., BTC/USDT or BTCUSDT)
--timeframe     Candle timeframe (1m, 3m, 15m, 1h, etc.)
--start         Start date (YYYY-MM-DD)
--end           End date (YYYY-MM-DD)
--csv           Optional: Path to CSV file (if provided, loads from file)
--capital       Initial capital (default: from config)
--output-dir    Output directory (default: logs/backtest_results)
```

---

## 🧠 **Self-Optimization Engine**

The self-optimization module (`core/self_optimizer.py`) automatically adjusts agent weights based on their recent performance (Sharpe ratio, win rate, profit factor).

### **Features:**
- ✅ Reads performance metrics from backtest results
- ✅ Calculates performance scores (Sharpe, win rate, profit factor)
- ✅ Updates agent config JSON files with new weights
- ✅ Safeguards: min weight (0.7), max weight (1.3)
- ✅ Logs optimization history to CSV

### **Usage:**

#### **1. Enable in `.env` File:**

```env
# Enable self-optimization (runs every 100 cycles in live mode)
SELF_OPTIMIZE=True
```

#### **2. Manual Run (CLI):**

```bash
# Optimize based on latest backtest results
python3 -m core.self_optimizer

# Dry-run (calculate without applying)
python3 -m core.self_optimizer --dry-run

# Custom metrics file
python3 -m core.self_optimizer \
  --metrics-file logs/backtest_results/agent_metrics.csv \
  --configs-dir agents_config
```

#### **3. Programmatic Usage:**

```python
from core.self_optimizer import optimize_agent_weights

# Optimize agent weights
new_weights = optimize_agent_weights(
    metrics_file="logs/backtest_results/agent_metrics.csv",
    configs_dir="agents_config",
    apply_changes=True,
    min_weight=0.7,
    max_weight=1.3
)

print(f"Updated weights: {new_weights}")
```

### **How It Works:**

1. **Reads Metrics** - Loads `agent_metrics.csv` from backtest results
2. **Calculates Performance Score** - Combines:
   - Sharpe ratio (40% weight)
   - Win rate (35% weight)
   - Profit factor (25% weight)
3. **Converts to Weights** - Maps performance score to weight (0.7-1.3 range)
4. **Updates Configs** - Modifies agent JSON files:
   ```json
   {
     "agent_id": "BTC_Momentum",
     "base_weight": 1.12,  // Updated
     "performance_multiplier": 1.12,  // Updated
     "final_weight": 1.12,  // Updated
     "last_optimization": "2024-11-01T12:00:00"
   }
   ```
5. **Logs History** - Saves to `logs/self_optimization_history.csv`

### **Weight Calculation Logic:**

- **Score 0.0** → Weight 0.7 (poor performance, reduce influence)
- **Score 0.5** → Weight 1.0 (neutral/average performance)
- **Score 1.0** → Weight 1.3 (excellent performance, increase influence)

Safeguards prevent weights from going below 0.7 or above 1.3.

---

## 🔄 **Integration with Live Trading**

### **Automatic Self-Optimization:**

When `SELF_OPTIMIZE=True` in `.env`, the orchestrator will:

1. **Every 100 cycles**, check if `logs/backtest_results/agent_metrics.csv` exists
2. If found, run self-optimization and update agent weights
3. Log the changes to `logs/self_optimization_history.csv`
4. Send Telegram notification (if enabled)

### **Workflow:**

```
1. Run backtest → Generate agent_metrics.csv
2. Enable SELF_OPTIMIZE=True in .env
3. Start live trading → Weights auto-update every 100 cycles
4. Re-run backtest → Compare improved Sharpe ratio
```

---

## 📈 **Example Workflow**

### **Step 1: Run Backtest**

```bash
python3 backtester.py \
  --symbol BTC/USDT \
  --timeframe 3m \
  --start "2024-10-01" \
  --end "2024-11-01"
```

**Output:**
```
📊 BACKTEST SUMMARY
================================================================================

🎯 OVERALL PERFORMANCE:
   Total Trades: 47
   Total PnL: $+342.50
   Overall Win Rate: 68.1%
   Average Sharpe Ratio: 1.85

📈 PER-AGENT METRICS:
Agent ID                    Trades   Win %    PnL          Sharpe     Max DD
--------------------------------------------------------------------------------
BTC_Momentum                12       75.0%    $+156.20     2.10      5.2%
BTC_Trend                   15       66.7%    $+124.80     1.95      6.1%
BTC_Reversion               10       60.0%    $+61.50      1.42      8.5%
BTC_Breakout                10       70.0%    $+0.00       1.20      12.3%
```

### **Step 2: Optimize Weights**

```bash
python3 -m core.self_optimizer
```

**Output:**
```
🧠 SELF-OPTIMIZATION ENGINE
================================================================================
✅ Loaded metrics for 4 agents
✅ Loaded 4 agent configs

📊 WEIGHT ADJUSTMENTS:
Agent ID                        Old Weight   New Weight   Change       Sharpe
--------------------------------------------------------------------------------
BTC_Momentum                    1.00         1.23         +0.23 (+23.0%)   2.10
BTC_Trend                       1.00         1.18         +0.18 (+18.0%)   1.95
BTC_Reversion                   1.00         0.95         -0.05 (-5.0%)    1.42
BTC_Breakout                    1.00         0.84         -0.16 (-16.0%)   1.20

💾 Applying weight updates to config files...
  ✅ Updated BTC_Momentum: weight 1.00 → 1.23 (multiplier: 1.23)
  ✅ Updated BTC_Trend: weight 1.00 → 1.18 (multiplier: 1.18)
  ✅ Updated BTC_Reversion: weight 1.00 → 0.95 (multiplier: 0.95)
  ✅ Updated BTC_Breakout: weight 1.00 → 0.84 (multiplier: 0.84)
✅ Updated 4 agent configs
💾 Logged optimization history to logs/self_optimization_history.csv
```

### **Step 3: Re-run Backtest (Verify Improvement)**

```bash
python3 backtester.py \
  --symbol BTC/USDT \
  --timeframe 3m \
  --start "2024-11-01" \
  --end "2024-12-01"
```

Compare Sharpe ratio improvement! 🚀

---

## 🔧 **Troubleshooting**

### **Issue: "No agent configs found"**

**Solution:** Ensure your agent configs are in `agents_config/` and match the symbol format (e.g., `BTC/USDT`).

### **Issue: "Metrics file not found"**

**Solution:** Run a backtest first to generate `logs/backtest_results/agent_metrics.csv`.

### **Issue: "No historical data fetched"**

**Solution:** 
- Check Binance API connection
- Verify date range is valid
- Try using `--csv` option with a local CSV file

### **Issue: Import errors**

**Solution:** Ensure all dependencies are installed:
```bash
pip install pandas numpy
```

---

## 📚 **Additional Resources**

- **Backtester Code:** `core/backtester.py`
- **Self-Optimizer Code:** `core/self_optimizer.py`
- **Output Directory:** `logs/backtest_results/`
- **Optimization History:** `logs/self_optimization_history.csv`

---

## 🎯 **Best Practices**

1. **Run backtests regularly** to validate strategy performance
2. **Compare metrics** before and after optimization
3. **Use dry-run mode** first to preview weight changes
4. **Monitor optimization history** to track weight evolution
5. **Re-run backtests** after optimization to verify improvement

Happy backtesting! 🚀

