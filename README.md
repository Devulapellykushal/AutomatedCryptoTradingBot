# 🚀 Kushal Automated Crypto Trading Bot

A professional AI-powered cryptocurrency trading bot with multi-agent system, live Binance Futures execution, and comprehensive trading strategies.

## 📁 Project Structure

```
AutomatedCryptoTradingBot/
├── alpha-arena-backend/    # Backend trading engine
│   ├── core/                # Core trading modules
│   ├── agents_config/       # Trading agent configurations
│   ├── db/                  # Database files (gitignored)
│   ├── logs/                # Log files (gitignored)
│   └── README.md            # Backend documentation
│
├── frontend/                # React frontend dashboard
│   └── README.md            # Frontend documentation
│
└── MarkdownFiles/           # Project documentation
```

## 🚀 Quick Start

### Backend Setup

1. Navigate to the backend directory:
```bash
cd alpha-arena-backend
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your API keys
```

4. Run setup check:
```bash
python setup_check.py
```

5. Start trading:
```bash
python run_fullstack.py
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start development server:
```bash
npm run dev
```

## ✨ Features

- **Multi-Agent Trading System** - Multiple AI agents with different strategies
- **Live Binance Futures Trading** - Real-time order execution
- **5 Professional Strategies** - Trend Following, Mean Reversion, Breakout, MACD, Multi-Timeframe
- **45+ Technical Indicators** - Comprehensive market analysis
- **Risk Management** - Position sizing, stop-loss, daily limits
- **Adaptive Learning** - Performance tracking and optimization
- **Real-time Dashboard** - Live monitoring and analytics
- **Telegram Integration** - Notifications and command control

## 📚 Documentation

- [Backend README](alpha-arena-backend/README.md) - Complete backend documentation
- [Frontend README](frontend/README.md) - Frontend setup and usage
- [Project Structure](MarkdownFiles/PROJECT_STRUCTURE_FINAL.md) - Detailed project structure
- [Codebase Audit](MarkdownFiles/CODEBASE_AUDIT_FINAL.md) - System verification report

## 🔒 Security

- All `.env` files are gitignored
- Database files are not tracked
- Log files are excluded from version control
- Sensitive trading data is not committed

## 📝 License

This project is for educational and research purposes.

## 🤝 Contributing

Please ensure all sensitive files are properly gitignored before committing.

