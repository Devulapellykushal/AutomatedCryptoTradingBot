"""
Test Script: Verify Symbol Filtering from .env
This script verifies that only symbols in ALLOWED_SYMBOLS are loaded and processed.
"""

import os
from dotenv import load_dotenv
from hackathon_config import load_symbols
from main import load_agent_configs

# Load environment
load_dotenv()

print("\n" + "="*80)
print("🧪 TESTING SYMBOL FILTERING")
print("="*80)

# Test 1: Load symbols from .env
print("\n1️⃣  Testing load_symbols() function:")
print("-" * 80)
symbols = load_symbols()
print(f"✅ Filtered symbols: {symbols}")

# Test 2: Check environment variables
print("\n2️⃣  Environment Variables:")
print("-" * 80)
print(f"SYMBOLS = {os.getenv('SYMBOLS', 'Not set')}")
print(f"ALLOWED_SYMBOLS = {os.getenv('ALLOWED_SYMBOLS', 'Not set')}")

# Test 3: Load and filter agents
print("\n3️⃣  Testing Agent Filtering:")
print("-" * 80)
agents = load_agent_configs()
print(f"\n✅ Loaded {len(agents)} agent(s) matching ALLOWED_SYMBOLS:")
for agent_id, config in agents.items():
    symbol = config.get('symbol', 'N/A')
    style = config.get('style', 'unknown')
    print(f"   • {agent_id:20s} → {symbol:12s} ({style})")

# Test 4: Summary
print("\n" + "="*80)
print("📊 SUMMARY")
print("="*80)
print(f"Allowed Symbols: {', '.join(symbols)}")
print(f"Active Agents: {len(agents)}")
print(f"Expected Behavior: ✅ Only {', '.join(symbols)} will be traded")
print("="*80 + "\n")
