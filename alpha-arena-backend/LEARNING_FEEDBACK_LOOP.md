# Learning Feedback Loop - How CSV Logs Feed Into Future Decisions

## ✅ Answer: **YES**, the next cycles' orders WILL take CSV logs as references!

The bot now has a complete feedback loop: **Decision → Execute → Outcome → Learn → Better Decision**

---

## How It Works

### 1. **When a Trade Opens** (Cycle N)
- AI agent makes a decision based on:
  - Current market data
  - Technical indicators
  - **Recent performance from `learning_memory.json`** ← This uses past outcomes!
- Decision is logged to `decisions_log.csv`
- Decision metadata is cached in memory for fast retrieval

### 2. **When a Trade Closes** (Cycle N + X)
- Trade outcome is logged to `trades_log.csv`
- **`learning_bridge.py` automatically:**
  - Finds the original decision from CSV logs or cache
  - Links outcome (PnL, exit reason) to decision (signal, confidence, reasoning)
  - Updates `learning_memory.json` with the complete picture

### 3. **Next Cycle** (Cycle N + Y)
- AI agent calls `get_recent_performance(symbol, hours=24)` 
- This reads from `learning_memory.json` (which was updated from CSV logs)
- **The LLM prompt includes:**
  ```
  Recent Performance for {symbol}:
  - LONG trend_following (Conf: 0.75) -> PnL: +$125.50 (+2.51%)
  - SHORT mean_reversion (Conf: 0.68) -> PnL: -$45.20 (-0.90%)
  ```
- AI considers this when making new decisions

---

## Data Flow Diagram

```
┌─────────────────┐
│   Cycle N       │
│  AI Decides     │ ──► decisions_log.csv
│  (uses past     │
│   performance)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Trade Executed │ ──► trades_log.csv
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Trade Closes  │ ──► trades_log.csv (close record)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ learning_bridge │ ──► Links decision → outcome
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│learning_memory  │ ←─ Updates with decision+outcome
│    .json        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Cycle N+1     │
│  AI Reads Past  │ ←─ Reads learning_memory.json
│  Performance    │
└─────────────────┘
```

---

## Files Involved

1. **`core/learning_bridge.py`** (NEW)
   - Connects CSV logs to learning system
   - `find_matching_decision()` - Retrieves original decision when trade closes
   - `update_learning_from_csv_logs()` - Updates learning memory from CSV data

2. **`core/learning_memory.py`**
   - Stores decision → outcome pairs
   - `get_recent_performance()` - Returns last 24h performance for AI prompts

3. **`core/ai_agent.py`** (Line 106)
   - Calls `get_recent_performance()` before making decisions
   - Includes past performance in LLM prompt

4. **`core/trade_manager.py`** (Updated)
   - When trades close, automatically calls `update_learning_from_csv_logs()`

5. **`core/orchestrator.py`** (Updated)
   - Caches decision metadata when trades open for fast retrieval

---

## What Gets Learned

For each closed trade, the system learns:
- ✅ Which strategy worked (`strategy_used`)
- ✅ How accurate confidence was (`confidence_accuracy`)
- ✅ What market conditions led to win/loss
- ✅ Exit reason (TP vs SL) and context
- ✅ PnL and percentage returns

This data is used in future cycles to:
- ⚠️ **Avoid repeating failed strategies** in similar conditions
- ✅ **Boost confidence** when strategies match successful patterns
- 📊 **Adjust position sizing** based on historical performance
- 🎯 **Improve exit timing** based on past outcomes

---

## Verification

You can verify it's working by:

1. **Check learning memory:**
   ```bash
   cat db/learning_memory.json
   ```

2. **Check logs for feedback updates:**
   ```
   ✅ Learning updated: BTCUSDT WIN (PnL: +125.50) → Future decisions will use this
   ```

3. **Watch AI prompts:**
   - The LLM prompt will show "Recent Performance for {symbol}" section
   - This comes from `learning_memory.json` which was updated from CSV logs

---

## Summary

✅ **YES** - CSV logs feed into future decisions automatically!

The bot learns from every trade and uses that knowledge to make better decisions in the next cycles. The CSV logs (`decisions_log.csv`, `trades_log.csv`, `learning_log.csv`) are all connected to the learning system (`learning_memory.json`), which the AI agent reads before making new decisions.

**You don't need to do anything** - it happens automatically! 🚀

