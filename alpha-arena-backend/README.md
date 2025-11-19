# 🚀 Kushal AI Trading Bot

Professional AI-powered cryptocurrency trading bot with multi-agent system, live Binance Futures execution, and 5 proven trading strategies.

---

## ✨ Features

- ✅ **5 Professional Trading Strategies** (Trend Following, Mean Reversion, Breakout, MACD Momentum, Multi-Timeframe)
- ✅ **45+ Technical Indicators** (RSI, MACD, Bollinger Bands, ATR, EMA, etc.)
- ✅ **AI-Powered Decisions** (GPT-4o-mini integration with strategy validation)
- ✅ **Live Futures Trading** (Binance USDT-M Futures Demo Trading with leverage)
- ✅ **Multi-Agent System** (Multiple AI agents with different strategies)
- ✅ **Risk Management** (Position sizing, stop-loss, daily limits, drawdown protection)
- ✅ **Real-time Dashboard** (Live performance tracking and logging)
- ✅ **Paper Trading Mode** (Safe simulation for testing)
- ✅ **Adaptive Learning** (Performance tracking and strategy optimization)
- ✅ **Strategy Analytics** (Performance analysis and recommendations)
- ✅ **LLM Memory Introspection** (API endpoint to view AI memory and context)
- ✅ **Telegram Notifications & Commands** (On-demand alerts and interactive control)

---

## 🎯 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` and set your Futures Demo API keys:
```bash
# Binance Futures Demo Trading Configuration
BINANCE_MODE=demo
BINANCE_ACCOUNT_TYPES=usdm
BINANCE_API_KEY=your_demo_key
BINANCE_SECRET_KEY=your_demo_secret

# OpenAI API
OPENAI_API_KEY=your_openai_key

# Trading Mode
MODE=live  # 'live' for real demo orders, 'paper' for simulation
SYMBOLS=BTC/USDT,BNB/USDT
TIMEFRAME=3m
```

**Get Futures Demo Keys:**
1. Visit: https://www.binance.com/en/futures/demo
2. Login to your Binance account
3. Navigate to Futures Demo Trading
4. Generate API keys (Settings → API Management)
5. Enable "Futures Trading" permission

### 3. Configure Telegram Notifications & Commands (Optional)
To control your bot via Telegram:
1. Create a Telegram bot by messaging [@BotFather](https://t.me/BotFather)
2. Use the `/newbot` command to create a bot
3. Copy the bot token provided
4. Message your new bot to start a chat
5. Get your chat ID using a bot like [@userinfobot](https://t.me/userinfobot) or [@getmyid_bot](https://t.me/getmyid_bot)
6. Add to `.env`:
```bash
# Telegram Notifications & Commands
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_AUTO_NOTIFICATIONS=false  # Set to true to enable automatic notifications
```

### 4. Run Setup Check
```bash
python setup_check.py
```

### 5. Test Demo Setup (Recommended)
```bash
python -c "from core.binance_client import test_demo_connection; test_demo_connection()"
```

### 6. Start Trading
```bash
python run_fullstack.py
```

---

## 📁 Project Structure

```
alpha-arena-backend/
├── core/                      # Core trading system
│   ├── ai_agent.py           # AI decision making (GPT-4o-mini)
│   ├── strategies.py         # 5 professional trading strategies
│   ├── signal_engine.py      # 45+ technical indicators
│   ├── data_engine.py        # Market data fetching
│   ├── trading_engine.py     # Live order execution
│   ├── risk_engine.py        # Risk management
│   ├── portfolio.py          # Position tracking
│   ├── orchestrator.py       # Main trading pipeline
│   ├── binance_client.py     # Binance connection manager
│   ├── coordinator_agent.py  # Multi-agent coordination
│   ├── storage.py            # Database logging
│   ├── learning_memory.py    # Adaptive learning system
│   ├── strategy_analytics.py # Strategy performance analysis
│   ├── order_manager.py      # Order placement and management
│   ├── trade_manager.py      # TP/SL management
│   └── judge.py              # Performance evaluation
│
├── agents_config/            # Agent strategy configurations
│   ├── neuraquant.json       # Mean reversion agent
│   ├── bnbswing.json         # Trend following agent
│   ├── bnbbreakout.json      # Breakout agent
│   ├── bnbrevert.json        # Mean reversion agent
│   └── bnbscalp.json         # MACD momentum agent
│
├── db/                       # Database files
│   ├── arena.db              # Trade history
│   ├── leaderboard.db        # Performance rankings
│   ├── thoughts.json         # AI reasoning logs
│   └── learning_memory.json  # Adaptive learning data
│
├── logs/                     # Log files
│   ├── trading.log           # Trading activity
│   ├── errors.log            # Error logs
│   └── coordinator.log       # Agent coordination logs
│
├── main.py                   # Main entry point
├── api_server.py             # FastAPI server with WebSocket
├── telegram_notifier.py      # Telegram notification and command system
├── hackathon_config.py       # Global configuration
├── view_learning_analytics.py # Learning analytics viewer
├── .env                      # Environment variables (not in git)
├── .env.example              # Environment template
└── requirements.txt          # Python dependencies
```

---

## 🎮 Trading Strategies

### 1. Trend Following (Most Reliable)
- **Best for:** Strong trending markets
- **Entry:** Price > EMA20, MACD bullish, RSI 40-70
- **Agent:** BNB_Momentum

### 2. Mean Reversion (Range Trading)
- **Best for:** Sideways/ranging markets
- **Entry:** RSI < 30 or > 70, Price at Bollinger Bands
- **Agent:** NeuraQuant, BNB_Reversion

### 3. Breakout (High Momentum)
- **Best for:** Volatile markets with big moves
- **Entry:** Price breaks Bollinger Bands + high volume
- **Agent:** BNB_Breakout

### 4. MACD Momentum (Trend Changes)
- **Best for:** Catching trend reversals
- **Entry:** MACD crossover + histogram confirmation
- **Agent:** BNB_Scalper

### 5. Multi-Timeframe (Professional)
- **Best for:** High-probability confirmed setups
- **Entry:** All timeframes aligned (short/med/long)
- **Agent:** (Can be configured)

---

## 🔔 Telegram Notifications & Commands

The bot provides on-demand information and control through Telegram commands.

### Interactive Commands:
- `/start` - Start the bot and receive welcome message
- `/help` - Show detailed help with all available commands
- `/status` - Show bot status and system information
- `/balance` - Show your account balance
- `/positions` - Show all currently open positions
- `/close <symbol>` - Close a specific position (e.g., `/close BTCUSDT`)
- `/closeall confirm` - Close all open positions (requires confirmation)

### Notification Policy:
- **Initial Message**: When the bot starts, it sends one welcome message listing all available commands
- **On-Demand Only**: All other notifications are disabled by default
- **No Automatic Alerts**: No trade execution, position closure, or system event notifications
- **Optional Auto-Notifications**: Set `TELEGRAM_AUTO_NOTIFICATIONS=true` to enable automatic notifications

### Setup:
1. Create a new Telegram bot by messaging [@BotFather](https://t.me/BotFather)
2. Use the `/newbot` command to create a bot
3. Copy the bot token provided
4. Message your new bot to start a chat
5. Get your chat ID using a bot like [@userinfobot](https://t.me/userinfobot) or [@getmyid_bot](https://t.me/getmyid_bot)
6. Add these to your `.env` file:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_AUTO_NOTIFICATIONS=false  # Set to true for automatic notifications
```

### Test:
```bash
python test_telegram.py
```

### Security Notes:
⚠️ **Use commands with caution** as they can affect real trading positions!
- Only users with the correct chat ID can send commands to the bot
- The `/closeall` command requires explicit confirmation to prevent accidental mass closures

---

## 🤖 Adaptive Learning System

The Kushal bot now features an adaptive learning system that tracks strategy performance and optimizes decision-making over time.

### Features:
- **Performance Tracking:** Records all trades with PnL, confidence accuracy, and strategy used
- **Strategy Analytics:** Analyzes win rates, profitability, and confidence accuracy for each strategy
- **Adaptive Weighting:** Automatically adjusts strategy weights based on recent performance
- **Recommendations:** Provides actionable insights for strategy optimization

### View Learning Analytics:
```bash
# View all performance data and recommendations
python view_learning_analytics.py --all

# View recent trades
python view_learning_analytics.py --recent

# View strategy recommendations
python view_learning_analytics.py --recommendations

# View raw learning data
python view_learning_analytics.py --raw
```

---

## 🔍 LLM Memory Introspection

You can actively query the LLM's memory and context through the API:

### REST API Endpoint:
```bash
# Get current LLM memory and context
curl http://localhost:8000/api/llm/memory
```

### WebSocket Support:
```javascript
// Connect to WebSocket and request LLM memory
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onopen = () => {
  ws.send(JSON.stringify({type: 'get_llm_memory'}));
};
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'llm_memory') {
    console.log('LLM Memory:', data.data);
  }
};
```

### API Response Structure:
```json
{
  "success": true,
  "thoughts": {
    "BTC/USDT": {
      "signal": "hold",
      "confidence": 0.3,
      "reasoning": "Market is in neutral zone...",
      "strategy_used": "mean_reversion"
    }
  },
  "learning_memory": {
    "BTC/USDT": [
      {
        "timestamp": 1761731111.3491058,
        "decision": { /* AI decision */ },
        "outcome": { /* Trade outcome */ },
        "performance": { /* Performance metrics */ }
      }
    ]
  },
  "timestamp": "2025-10-29T15:29:38.616085"
}
```

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# Binance Configuration
BINANCE_TESTNET=true           # Use testnet (true) or mainnet (false)
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret

# Trading Mode
MODE=live                      # 'live' = real orders, 'paper' = simulation

# Capital & Risk
STARTING_CAPITAL=10000         # Starting capital per agent
MAX_LEVERAGE=5                 # Maximum leverage allowed
RISK_FRACTION=0.10             # 10% risk per trade
MAX_DRAWDOWN=0.40              # 40% max drawdown before halt

# OpenAI
OPENAI_API_KEY=your_key

# Telegram Notifications & Commands
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_AUTO_NOTIFICATIONS=false  # Set to true for automatic notifications
```

### Agent Configuration (agents_config/*.json)

```json
{
  "agent_id": "MyAgent",
  "symbol": "BNB/USDT",
  "style": "trend_following",  # or: mean_reversion, breakout, macd_momentum
  "model": "gpt-4o-mini",
  "parameters": {
    "leverage_max": 5,
    "confidence_threshold": 0.65
  }
}
```

---

## 🔒 Risk Management

- **Position Sizing:** Max 10% of capital per trade
- **Leverage Control:** 1x-5x (configurable per agent)
- **Stop Loss:** Automatic (1.5x ATR)
- **Take Profit:** Automatic (2.5x ATR)
- **Daily Loss Limit:** Trading halts after 5% daily loss
- **Max Drawdown:** System shutdown if equity drops 40%

---

## 📊 Monitoring

### Real-time Dashboard
```
📊 ITERATION 25 - 2025-10-28 23:30:00
================================================================================
  🟢 [BNB_Momentum] LONG signal | BNB/USDT | Confidence: 0.85
      Strategy: Trend Following BUY: Price $632.40 > EMA20 $628.50...
```

## 🧪 Testing

### Run the existing test suite:

```bash
python -m pytest tests/ -v
```

### Run the new stability test suite:

```bash
python test_final_stability.py
```

This comprehensive test suite verifies all the safety features implemented for stable, consistent compounding.

## 🛡️ Safety Features

The trading bot includes comprehensive safety features to ensure stable operation:

1. **Precision Safety Net** - Prevents "Precision is over the maximum" errors
2. **RiskPostCheck Protection** - Rejects micro orders below minimum notional value
3. **Re-Attach Spam Guard** - Prevents excessive TP/SL re-attachment attempts
4. **Multi-Agent Conflict Guard** - Prevents multiple agents from entering the same symbol
5. **Proper TP/SL Ratios** - Uses minimum recommended ratios (1.0% TP / 0.6% SL)
6. **Cooldown & Reversal Safety** - Unified cooldown mechanism for conflict prevention
7. **Fee & Margin Alignment** - Fee-aware calculations for accurate PnL tracking
8. **ATR Validation & TP/SL Drift** - Caching mechanism to prevent TP/SL drift
9. **Log Optimization** - Structured logging with appropriate level filtering
10. **Additional Safeties** - Timeout watchdog, auto-close positions, heartbeat logging

For detailed implementation of these safety features, see [STABILITY_SAFETY_IMPLEMENTATION.md](STABILITY_SAFETY_IMPLEMENTATION.md).
