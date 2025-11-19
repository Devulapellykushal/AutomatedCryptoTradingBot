"""
Utility script to view the current leaderboard without running the competition
"""
from core.judge import get_leaderboard, print_leaderboard
import sys

if __name__ == "__main__":
    try:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
        print_leaderboard()
        
        # Also print raw data
        df = get_leaderboard(limit)
        if len(df) > 0:
            print("\n📋 Raw Data:")
            print(df.to_string(index=False))
    except Exception as e:
        print(f"Error: {e}")
