# TP/SL Order Fix Summary

## Issues Fixed

1. **Binance Futures TP/SL order types & triggers**:
   - Fixed incorrect order types and parameters that caused "Order would immediately trigger" errors
   - Implemented correct Futures TP/SL types with proper parameters:
     - `TAKE_PROFIT_MARKET` with `reduceOnly=True`, `closePosition=True`, `workingType="MARK_PRICE"`
     - `STOP_MARKET` with `reduceOnly=True`, `closePosition=True`, `workingType="MARK_PRICE"`

2. **Side & close semantics**:
   - Implemented correct side/closePosition logic:
     - When closing SHORT: side="BUY"
     - When closing LONG: side="SELL"
     - Always set reduceOnly=True and closePosition=True

3. **Symbol precision & tick/step rounding**:
   - Created exchange_filters.py helper module for exchange filters and rounding
   - Implemented proper rounding using tickSize and stepSize from exchange filters
   - Added safety margin to prevent immediate trigger errors

4. **Reattach logic (LiveMonitor/Sentinel)**:
   - Updated Sentinel agent to properly verify attached orders
   - Added reattach functionality for missing TP/SL orders
   - Improved logging and verification of order types

5. **Unit tests**:
   - Created comprehensive unit tests for TP/SL calculations
   - Added dry-run function validation tests

## Key Changes Made

### 1. order_manager.py
- Fixed `place_take_profit_and_stop_loss` function with correct Binance Futures parameters
- Added proper rounding using tickSize from exchange filters
- Implemented safety margins to prevent immediate trigger errors
- Added verification of placed orders

### 2. sentinel_agent.py
- Enhanced `check_position_health` to properly verify TP/SL orders
- Added `reattach_missing_tpsl` function to reattach missing orders
- Improved logging for order verification

### 3. exchange_filters.py (new file)
- Created helper module for exchange filters and rounding
- Implemented `round_tick`, `round_step`, and `apply_safety_margin` functions
- Added caching for symbol filters

### 4. test_tp_sl_dry_run.py (new file)
- Created unit tests for TP/SL dry-run functionality
- Added tests for long/short position calculations
- Included edge case testing

## How the -2021 Error is Prevented

The "Order would immediately trigger" (-2021) error is now prevented by:

1. **Correct Order Parameters**: Using the proper order types (`TAKE_PROFIT_MARKET`, `STOP_MARKET`) with correct parameters (`reduceOnly=True`, `closePosition=True`, `workingType="MARK_PRICE"`)

2. **Proper Price Calculation**: Calculating trigger prices with the correct direction:
   - LONG TP: entry * (1 + tpP)
   - LONG SL: entry * (1 - slP)
   - SHORT TP: entry * (1 - tpP)
   - SHORT SL: entry * (1 + slP)

3. **Precision Rounding**: Applying proper rounding using tickSize from exchange filters

4. **Safety Margins**: Ensuring a minimum distance (2 ticks) between trigger prices and current mark price to prevent immediate triggering

5. **Order Verification**: Verifying that orders were placed correctly after submission

## Verification

After these changes, the system should:
- ✅ Place TP/SL successfully on first attempt (no -2021 errors)
- ✅ Sentinel stops warning "Missing TP/SL"
- ✅ Open orders show one STOP_MARKET + one TAKE_PROFIT_MARKET with closePosition=true for each active position