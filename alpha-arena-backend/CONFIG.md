# Trading Bot Configuration

This document describes all configuration variables used by the Binance Futures trading bot.

## Binance API Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BINANCE_API_KEY` | Binance API key | None | ✅ |
| `BINANCE_API_SECRET` | Binance API secret | None | ✅ |
| `BINANCE_TESTNET` | Use testnet instead of live trading | `true` | ✅ |

## Trading Configuration

| Variable | Description | Default | Range | Required |
|----------|-------------|---------|-------|----------|
| `SYMBOLS` | Comma-separated list of trading symbols | `BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT` | Any valid Binance Futures symbols | ✅ |
| `TIMEFRAME` | Candle timeframe for analysis | `3m` | `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M` | ✅ |
| `STARTING_CAPITAL` | Starting capital in USDT | `10000.0` | > 0 | ✅ |
| `MAX_LEVERAGE` | Maximum leverage allowed | `5` | 1-125 | ✅ |
| `RISK_FRACTION` | Fraction of capital to risk per trade | `0.1` | 0-1 | ✅ |
| `MAX_DRAWDOWN` | Maximum allowed drawdown | `0.4` | 0-1 | ✅ |

## Risk Management & Throttling

| Variable | Description | Default | Range | Required |
|----------|-------------|---------|-------|----------|
| `TAKE_PROFIT_PERCENT` | Take profit percentage | `2.0` | > 0 | ✅ |
| `STOP_LOSS_PERCENT` | Stop loss percentage | `1.0` | > 0 | ✅ |
| `MAX_OPEN_TRADES` | Maximum number of concurrent open trades | `4` | ≥ 1 | ✅ |
| `MAX_DAILY_ORDERS` | Maximum number of orders per day | `10` | ≥ 1 | ✅ |
| `MAX_MARGIN_PER_TRADE` | Maximum margin per trade in USDT | `1000.0` | > 0 | ✅ |
| `RISK_PER_TRADE_PERCENT` | Risk percentage per trade | `2.0` | 0-100 | ✅ |
| `ALLOWED_SYMBOLS` | Comma-separated list of allowed symbols | `BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT` | Any valid Binance Futures symbols | ✅ |
| `TRADE_LOG_PATH` | Path to trade log CSV file | `trades_log.csv` | Valid file path | ✅ |

## Auto-Scaling

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AUTO_SCALE_QTY` | Automatically scale quantity based on risk | `true` | ✅ |

## Telegram Notifications

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for notifications | None | ❌ |
| `TELEGRAM_CHAT_ID` | Telegram chat ID for notifications | None | ❌ |
| `TELEGRAM_AUTO_NOTIFICATIONS` | Enable automatic Telegram notifications | `true` | ✅ |

## Confidence & Cooldowns

| Variable | Description | Default | Range | Required |
|----------|-------------|---------|-------|----------|
| `MIN_CONFIDENCE` | Minimum confidence level for trades | `0.75` | 0-1 | ✅ |
| `MIN_HOLDING_PERIOD` | Minimum holding period in seconds | `0` | ≥ 0 | ✅ |
| `REVERSAL_COOLDOWN_PERIOD` | Cooldown period after position reversal in seconds | `0` | ≥ 0 | ✅ |

## Dynamic TP/SL

| Variable | Description | Default | Range | Required |
|----------|-------------|---------|-------|----------|
| `DYNAMIC_TP_SL` | Enable dynamic take profit and stop loss | `false` | boolean | ✅ |
| `BASE_TP_PERCENT` | Base take profit percentage | `2.0` | > 0 | ✅ |
| `BASE_SL_PERCENT` | Base stop loss percentage | `1.0` | > 0 | ✅ |
| `MIN_TP_PERCENT` | Minimum take profit percentage | `1.5` | > 0 | ✅ |
| `MAX_TP_PERCENT` | Maximum take profit percentage | `8.0` | > 0 | ✅ |
| `MIN_SL_PERCENT` | Minimum stop loss percentage | `0.5` | > 0 | ✅ |
| `MAX_SL_PERCENT` | Maximum stop loss percentage | `4.0` | > 0 | ✅ |

## Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your values:
   ```bash
   nano .env
   ```

3. Make sure to set `BINANCE_TESTNET=false` when you're ready for live trading.

## Security Notes

- Never commit your `.env` file to version control
- Keep your API keys secure and limit their permissions to only what's needed
- Use testnet for development and testing
- Regularly rotate your API keys