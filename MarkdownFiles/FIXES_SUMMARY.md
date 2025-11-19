# Trading System Fixes Summary

## 1. Precision-Safe Rounding Wrapper

### Added `safe_qty` function in `order_manager.py`:
- Implements symbol-specific precision rounding to prevent "Precision is over the maximum" errors
- BTC: 3 decimal places for quantity
- BNB: 4 decimal places for quantity
- Default: 3 decimal places for other symbols

## 2. LiveMonitor Improvements

### Updated `trade_manager.py`:
- Added debounce mechanism to prevent re-attachment within 5 seconds
- Added precision error checking to skip re-attachment if last error was precision-related
- Added global state tracking for last attach times and errors

## 3. Risk Engine Fixes

### Updated `risk_engine.py`:
- Fixed risk calculation to use intended 30% equity risk instead of 1%
- Updated maximum risk per trade from $200 to $600

### Updated `order_manager.py`:
- Updated post-trade risk logic to use 30% equity risk limit
- Updated maximum risk per trade to $600

## 4. Leverage Configuration Fixes

### Updated `ai_agent.py`:
- Replaced hardcoded leverage values (3, 5) with settings-based values
- Added import for settings module
- Fixed leverage calculation to use `settings.max_leverage`

## 5. Minimum Holding Period Bypass

### Updated `order_manager.py`:
- Added `forced_event` parameter to `close_position` function
- Added bypass for minimum holding period when `forced_event=True`
- Added symbol-specific precision rounding to `close_position` and `schedule_partial_close`
- Added minimum quantity checks

## 6. Retry Mechanism Improvements

### Updated `retry_wrapper.py`:
- Added short-circuit logic for precision errors
- Skip retries when "Precision is over" error is detected

## 7. Sentinel Agent (Optional Add-on)

### Created `sentinel_agent.py`:
- Background monitoring thread that runs every 5 minutes
- Checks position health including TP/SL presence and PnL drift
- Alerts on Telegram if issues are detected
- Monitors for missing TP/SL orders
- Monitors for excessive drawdown (> 2%)

### Updated `main.py`:
- Added sentinel agent to startup process
- Added sentinel agent to shutdown cleanup
- Added sentinel agent to signal handler

## Files Modified:

1. `core/order_manager.py` - Added safe_qty function, updated close_position and schedule_partial_close
2. `core/risk_engine.py` - Fixed risk calculation parameters
3. `core/ai_agent.py` - Fixed leverage configuration
4. `core/trade_manager.py` - Added debounce and precision error checking to LiveMonitor
5. `core/retry_wrapper.py` - Added short-circuit for precision errors
6. `core/sentinel_agent.py` - New file for optional position health monitoring
7. `main.py` - Added sentinel agent to startup/shutdown processes

## Expected Behavior After Fixes:

| Cycle | Symbol    | Behavior                                                | Status |
| ----- | --------- | ------------------------------------------------------- | ------ |
| 1     | BNB Short | Executes cleanly @ ~1.14 qty, TP/SL placed, no retries   | ✅     |
| 2     | BTC Long  | Executes 0.011 qty, 0.5 % TP / 0.3 % SL applied          | ✅     |
| 3–10  | Both      | Post-trade risk check runs silently (no false warnings)  | ✅     |
| All   |           | LiveMonitor only logs once every 3–5 s, not spam         | ✅     |
| All   |           | TP/SL hit logs cleanly: `[Close] SL @ 10745 | PnL -0.30 USDT` | ✅ |

## Additional Benefits:

1. **Reduced API calls** - Debounce mechanism prevents unnecessary re-attachments
2. **Improved reliability** - Short-circuit for precision errors prevents useless retries
3. **Better error handling** - More precise error messages and handling
4. **Enhanced monitoring** - Sentinel agent provides additional oversight
5. **Consistent precision** - All order quantities are properly rounded
6. **Proper risk management** - Correct risk percentages applied