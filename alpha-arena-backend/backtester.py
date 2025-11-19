#!/usr/bin/env python3
"""
Standalone CLI entry point for backtester
Usage: python3 backtester.py --symbol BTCUSDT --timeframe 3m --start "2024-10-01" --end "2024-11-01"
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.backtester import main

if __name__ == "__main__":
    main()

