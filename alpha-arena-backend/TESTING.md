# Alpha-Arena Safety Test Suite

## Overview

This test suite verifies that all recent fixes have been properly implemented in the trading system:

1. Precision Guard - Prevents "Precision is over the maximum" errors
2. Duplicate Position Guard - Prevents same-direction duplicate trades
3. Cooldown Logic - Enforces holding periods between trades
4. Post-Trade Exposure - Ensures margin limits are respected
5. Monitor Interval - Verifies LiveMonitor polling rate

## Prerequisites

1. Python 3.8+
2. Virtual environment activated
3. Binance Testnet API keys configured in `.env`
4. All dependencies installed via `pip install -r requirements.txt`

## How to Run

```bash
# Navigate to the project directory
cd alpha-arena-backend

# Run the test suite
python test_safety_suite.py
```

## Expected Output

When all fixes are properly implemented, you should see output similar to:

```
2025-10-31 10:30:15,987 - INFO - Connected to Binance Futures ✅

=== [TEST 1] Precision Guard ===
2025-10-31 10:30:15,988 - INFO - Safe quantity returned: 0.0005
2025-10-31 10:30:15,988 - INFO - [PASS] Small qty correctly rounded or blocked

=== [TEST 2] Duplicate Position Guard ===
2025-10-31 10:30:15,989 - INFO - Safe quantity for normal order: 0.01
2025-10-31 10:30:15,989 - INFO - [PASS] Duplicate entry guard logic verified

=== [TEST 3] Cooldown Logic ===
2025-10-31 10:30:15,990 - INFO - Min holding period: 60s
2025-10-31 10:30:15,990 - INFO - Reversal cooldown: 600s
2025-10-31 10:30:15,990 - INFO - [PASS] Cooldown settings loaded correctly

=== [TEST 4] Post-Trade Exposure ===
2025-10-31 10:30:15,991 - INFO - Calculated qty: 0.033333
2025-10-31 10:30:15,991 - INFO - Margin: $500.00
2025-10-31 10:30:15,991 - INFO - [PASS] Exposure within limits

=== [TEST 5] LiveMonitor Interval ===
2025-10-31 10:30:15,992 - INFO - [PASS] LiveMonitor interval set to 5 seconds (verified in main.py)

2025-10-31 10:30:15,992 - INFO - 
All tests completed ✅
```

## Test Descriptions

### Test 1: Precision Guard
Verifies that the `safe_qty` function properly rounds quantities to symbol-specific precision and prevents sub-minQty orders.

### Test 2: Duplicate Position Guard
Checks that the system prevents duplicate entries in the same direction for a symbol.

### Test 3: Cooldown Logic
Validates that cooldown settings are properly loaded and enforced.

### Test 4: Post-Trade Exposure
Ensures that position sizing calculations respect margin limits (MIN_MARGIN_PER_TRADE and MAX_MARGIN_PER_TRADE).

### Test 5: Monitor Interval
Confirms that the LiveMonitor polling interval has been set to 5 seconds to reduce API load.

## Troubleshooting

If you encounter errors:

1. **Binance connection failed**: Check your `.env` file for correct API keys and Testnet settings
2. **Import errors**: Make sure you're running from the `alpha-arena-backend` directory
3. **Permission errors**: Ensure your API keys have Futures trading permissions

## Manual Verification

In addition to running this test suite, you can manually verify the fixes by:

1. Checking the LiveMonitor interval in `main.py` (should be 5 seconds)
2. Verifying the `safe_qty` function in `core/order_manager.py`
3. Confirming margin limits in `core/settings.py`
4. Checking cooldown settings in `core/settings.py`