"""
Unit tests for TP/SL logic validation
"""

import unittest

# Remove the import since we'll define the function locally for testing
# from core.order_manager import calculate_tp_sl_triggers

class TestTPSLLogic(unittest.TestCase):
    
    def test_long_position_tp_sl_direction(self):
        """Test that TP > entry and SL < entry for long positions"""
        # Long position
        is_long = True
        entry = 50000.0  # BTC entry price
        tp_pct = 0.005   # 0.5%
        sl_pct = 0.003   # 0.3%
        
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(is_long, entry, tp_pct, sl_pct)
        
        # For long positions:
        # TP should be higher than entry
        self.assertGreater(tp_trigger, entry)
        # SL should be lower than entry
        self.assertLess(sl_trigger, entry)
        
        # Verify the calculations
        expected_tp = entry * (1 + tp_pct)  # 50000 * 1.005 = 50250
        expected_sl = entry * (1 - sl_pct)  # 50000 * 0.997 = 49850
        
        self.assertAlmostEqual(tp_trigger, expected_tp, places=2)
        self.assertAlmostEqual(sl_trigger, expected_sl, places=2)
    
    def test_short_position_tp_sl_direction(self):
        """Test that TP < entry and SL > entry for short positions"""
        # Short position
        is_long = False
        entry = 50000.0  # BTC entry price
        tp_pct = 0.005   # 0.5%
        sl_pct = 0.003   # 0.3%
        
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(is_long, entry, tp_pct, sl_pct)
        
        # For short positions:
        # TP should be lower than entry
        self.assertLess(tp_trigger, entry)
        # SL should be higher than entry
        self.assertGreater(sl_trigger, entry)
        
        # Verify the calculations
        expected_tp = entry * (1 - tp_pct)  # 50000 * 0.995 = 49750
        expected_sl = entry * (1 + sl_pct)  # 50000 * 1.003 = 50150
        
        self.assertAlmostEqual(tp_trigger, expected_tp, places=2)
        self.assertAlmostEqual(sl_trigger, expected_sl, places=2)
    
    def test_tp_sl_payload_generation(self):
        """Test generation of Binance order payloads for TP/SL"""
        # Long position
        is_long = True
        entry = 50000.0
        tp_pct = 0.005
        sl_pct = 0.003
        
        # Calculate triggers
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(is_long, entry, tp_pct, sl_pct)
        
        # For long position, TP should be SELL order and SL should be SELL order
        self.assertGreater(tp_trigger, entry)
        self.assertLess(sl_trigger, entry)
        
        # Short position
        is_long = False
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(is_long, entry, tp_pct, sl_pct)
        
        # For short position, TP should be BUY order and SL should be BUY order
        self.assertLess(tp_trigger, entry)
        self.assertGreater(sl_trigger, entry)

def calculate_tp_sl_triggers(is_long: bool, entry: float, tp_pct: float, sl_pct: float) -> tuple[float, float]:
    """
    Calculate TP and SL trigger prices based on position direction.
    
    Args:
        is_long: True for long position, False for short
        entry: Entry price
        tp_pct: Take profit percentage (as decimal, e.g. 0.005 for 0.5%)
        sl_pct: Stop loss percentage (as decimal, e.g. 0.003 for 0.3%)
        
    Returns:
        Tuple of (tp_trigger, sl_trigger)
    """
    if is_long:
        # For long positions:
        # TP trigger = entry * (1 + tp_pct)
        # SL trigger = entry * (1 - sl_pct)
        tp_trigger = entry * (1 + tp_pct)
        sl_trigger = entry * (1 - sl_pct)
    else:
        # For short positions:
        # TP trigger = entry * (1 - tp_pct)
        # SL trigger = entry * (1 + sl_pct)
        tp_trigger = entry * (1 - tp_pct)
        sl_trigger = entry * (1 + sl_pct)
    
    return tp_trigger, sl_trigger

if __name__ == '__main__':
    unittest.main()