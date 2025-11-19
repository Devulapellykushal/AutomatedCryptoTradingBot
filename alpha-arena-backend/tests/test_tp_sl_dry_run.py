"""
Unit tests for TP/SL dry-run functionality
"""

import unittest
from core.order_manager import calculate_tp_sl_triggers

class TestTPSLDryRun(unittest.TestCase):
    
    def test_long_position_calculations(self):
        """Test TP/SL calculations for long positions"""
        # Long position
        is_long = True
        entry = 50000.0  # BTC entry price
        tp_pct = 0.005   # 0.5%
        sl_pct = 0.003   # 0.3%
        
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(is_long, entry, tp_pct, sl_pct)
        
        # For long positions:
        # TP should be higher than entry (profit target)
        self.assertGreater(tp_trigger, entry)
        # SL should be lower than entry (stop loss)
        self.assertLess(sl_trigger, entry)
        
        # Verify exact calculations
        expected_tp = entry * (1 + tp_pct)  # 50000 * 1.005 = 50250
        expected_sl = entry * (1 - sl_pct)  # 50000 * 0.997 = 49850
        
        self.assertAlmostEqual(tp_trigger, expected_tp, places=2)
        self.assertAlmostEqual(sl_trigger, expected_sl, places=2)
        
        # Verify the percentage differences
        tp_pct_diff = (tp_trigger - entry) / entry
        sl_pct_diff = (entry - sl_trigger) / entry
        
        self.assertAlmostEqual(tp_pct_diff, tp_pct, places=6)
        self.assertAlmostEqual(sl_pct_diff, sl_pct, places=6)
    
    def test_short_position_calculations(self):
        """Test TP/SL calculations for short positions"""
        # Short position
        is_long = False
        entry = 50000.0  # BTC entry price
        tp_pct = 0.005   # 0.5%
        sl_pct = 0.003   # 0.3%
        
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(is_long, entry, tp_pct, sl_pct)
        
        # For short positions:
        # TP should be lower than entry (profit target)
        self.assertLess(tp_trigger, entry)
        # SL should be higher than entry (stop loss)
        self.assertGreater(sl_trigger, entry)
        
        # Verify exact calculations
        expected_tp = entry * (1 - tp_pct)  # 50000 * 0.995 = 49750
        expected_sl = entry * (1 + sl_pct)  # 50000 * 1.003 = 50150
        
        self.assertAlmostEqual(tp_trigger, expected_tp, places=2)
        self.assertAlmostEqual(sl_trigger, expected_sl, places=2)
        
        # Verify the percentage differences
        tp_pct_diff = (entry - tp_trigger) / entry
        sl_pct_diff = (sl_trigger - entry) / entry
        
        self.assertAlmostEqual(tp_pct_diff, tp_pct, places=6)
        self.assertAlmostEqual(sl_pct_diff, sl_pct, places=6)
    
    def test_edge_cases(self):
        """Test edge cases for TP/SL calculations"""
        # Test with zero percentages
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(True, 50000.0, 0.0, 0.0)
        self.assertEqual(tp_trigger, 50000.0)
        self.assertEqual(sl_trigger, 50000.0)
        
        # Test with very small percentages
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(True, 50000.0, 0.0001, 0.0001)
        self.assertAlmostEqual(tp_trigger, 50005.0, places=1)
        self.assertAlmostEqual(sl_trigger, 49995.0, places=1)
        
        # Test with larger percentages
        tp_trigger, sl_trigger = calculate_tp_sl_triggers(True, 50000.0, 0.05, 0.02)
        self.assertAlmostEqual(tp_trigger, 52500.0, places=1)
        self.assertAlmostEqual(sl_trigger, 49000.0, places=1)

if __name__ == '__main__':
    unittest.main()