# TP/SL Order Fixes - Round 2

## Issues Fixed

1. **Mutually Exclusive Parameters**: Removed the use of both `reduceOnly=True` and `closePosition=True` which are mutually exclusive
2. **Parameter 'reduceonly' sent when not required** (APIError -1106): Implemented fallback logic to automatically retry with alternate mode
3. **Improved Order Verification**: Enhanced verification logic to check for either `closePosition` or `reduceOnly`

## Key Changes Made

### 1. order_manager.py - place_take_profit_and_stop_loss function
- **Removed mutually exclusive parameters**: Now uses either `closePosition=True` OR `reduceOnly=True` + `quantity`
- **Added fallback logic**: If order fails with -1106 error, automatically retries with the alternate mode
- **Consistent parameters**: Always sets `workingType="MARK_PRICE"` and omits `timeInForce` for market triggers
- **Improved verification**: Checks for either `closePosition` or `reduceOnly` in verification

### 2. sentinel_agent.py - check_position_health and reattach_missing_tpsl functions
- **Enhanced verification**: Checks for orders with either `closePosition` or `reduceOnly` flags
- **Improved logging**: Now shows "✅ TP/SL successfully attached for SYMBOL" when successful
- **Better error handling**: More descriptive error messages

## How the -1106 Error is Prevented

The "Parameter 'reduceonly' sent when not required" (-1106) error is now prevented by:

1. **Mutually Exclusive Parameters**: Only sending either `closePosition=True` OR `reduceOnly=True` + `quantity`, never both
2. **Fallback Logic**: If an order fails with -1106 error, automatically retrying with the alternate mode
3. **Consistent Order Types**: Using proper Futures TP/SL types with correct side logic:
   - For closing LONG: side="SELL"
   - For closing SHORT: side="BUY"

## Verification

After these changes, the system should:
- ✅ Place TP/SL successfully for BTCUSDT and BNBUSDT
- ✅ No more APIError -1106 errors
- ✅ Sentinel logs "✅ TP/SL successfully attached for BTCUSDT" and "✅ TP/SL successfully attached for BNBUSDT"
- ✅ No retries triggered when orders are placed correctly the first time

## Implementation Details

### Order Placement Logic
```
# Preferred mode (default)
payload = dict(
    symbol=symbol,
    side=side,
    type=order_type,
    stopPrice=stop_price,
    closePosition=True,
    workingType="MARK_PRICE"
)

# Fallback mode (if -1106 error occurs)
payload = dict(
    symbol=symbol,
    side=side,
    type=order_type,
    stopPrice=stop_price,
    quantity=qty,
    reduceOnly=True,
    workingType="MARK_PRICE"
)
```

### Fallback Mechanism
1. Try placing order with `closePosition=True` first (preferred method)
2. If -1106 error occurs, retry with `reduceOnly=True` + `quantity`
3. Use the successful mode for both TP and SL orders for consistency
4. Log success/failure appropriately

This implementation ensures compatibility with different Binance Futures configurations while maintaining robust error handling.