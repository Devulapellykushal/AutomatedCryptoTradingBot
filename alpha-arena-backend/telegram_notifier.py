"""
Telegram Notifier for Apex Neural Trading Bot
Sends trade alerts, system warnings, and summaries to Telegram
Also handles interactive commands from users
"""
import os
import logging
from typing import Optional, Any, Dict, List
from dotenv import load_dotenv
import asyncio
import threading
import time

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Suppress noisy telegram logs
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)

# Load Telegram credentials from environment
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# Check if automatic notifications are enabled
TELEGRAM_AUTO_NOTIFICATIONS = os.getenv("TELEGRAM_AUTO_NOTIFICATIONS", "false").lower() == "true"

# Initialize bot if credentials are available
bot: Optional[Any] = None
application: Optional[Any] = None
command_handlers: Dict[str, Any] = {}
# Flag to track if initial message has been sent
initial_message_sent = False

def _init_telegram_bot():
    """Initialize Telegram bot safely"""
    global bot, application
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("ℹ️ Telegram credentials not found in .env (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
        return
    
    try:
        # Use importlib to avoid linter issues
        import importlib
        telegram_module = importlib.import_module("telegram")
        ext_module = importlib.import_module("telegram.ext")
        
        # Get classes dynamically
        Bot = getattr(telegram_module, "Bot")
        Application = getattr(ext_module, "Application")
        CommandHandler = getattr(ext_module, "CommandHandler")
        
        bot = Bot(token=BOT_TOKEN)
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Register command handlers
        _register_command_handlers()
        
        logger.info("✅ Telegram bot initialized successfully")
    except ImportError:
        logger.info("ℹ️ Telegram library not available")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize Telegram bot: {e}")
        bot = None
        application = None

def _register_command_handlers():
    """Register command handlers for the bot"""
    global application
    if not application:
        return
    
    try:
        import importlib
        ext_module = importlib.import_module("telegram.ext")
        CommandHandler = getattr(ext_module, "CommandHandler")
        
        # Register all command handlers
        application.add_handler(CommandHandler("start", _handle_start))
        application.add_handler(CommandHandler("help", _handle_help))
        application.add_handler(CommandHandler("status", _handle_status))
        application.add_handler(CommandHandler("balance", _handle_balance))
        application.add_handler(CommandHandler("positions", _handle_positions))
        application.add_handler(CommandHandler("close", _handle_close))
        application.add_handler(CommandHandler("closeall", _handle_close_all))
        
        logger.info("✅ Telegram command handlers registered")
    except Exception as e:
        logger.warning(f"⚠️ Failed to register command handlers: {e}")

# Security function to check if user is authorized
async def _is_authorized(update: Any) -> bool:
    """Check if the user is authorized to use the bot"""
    if not CHAT_ID:
        return False
    
    try:
        user_id = str(update.message.from_user.id)
        authorized_id = str(CHAT_ID)
        return user_id == authorized_id
    except Exception as e:
        logger.warning(f"⚠️ Error checking authorization: {e}")
        return False

# Command handler functions
async def _handle_start(update: Any, context: Any):
    """Handle /start command"""
    # Check authorization
    if not await _is_authorized(update):
        await update.message.reply_text("❌ Unauthorized access. Only the bot creator can use this bot.")
        return
    
    welcome_msg = (
        "🤖 Welcome to Apex Neural Trading Bot!\n\n"
        "I'm your trading assistant that provides on-demand information "
        "and allows you to control your trading bot directly from Telegram.\n\n"
        "Use /help to see available commands."
    )
    await update.message.reply_text(welcome_msg)

async def _handle_help(update: Any, context: Any):
    """Handle /help command"""
    # Check authorization
    if not await _is_authorized(update):
        await update.message.reply_text("❌ Unauthorized access. Only the bot creator can use this bot.")
        return
    
    help_msg = (
        "🤖 Available Commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/status - Show bot status and system info\n"
        "/balance - Show account balance\n"
        "/positions - Show open positions\n"
        "/close <symbol> - Close position for a symbol (e.g., /close BTCUSDT)\n"
        "/closeall - Close all open positions\n"
        "\n⚠️ Use commands with caution as they affect real trading positions!"
    )
    await update.message.reply_text(help_msg)

async def _handle_status(update: Any, context: Any):
    """Handle /status command"""
    # Check authorization
    if not await _is_authorized(update):
        await update.message.reply_text("❌ Unauthorized access. Only the bot creator can use this bot.")
        return
    
    try:
        # Import required modules
        import importlib
        main_module = importlib.import_module("main")
        
        # Get system info
        status_msg = "📊 Bot Status\n\n"
        
        # Get trading mode
        mode = getattr(main_module, "TRADING_MODE", "unknown")
        status_msg += f"Mode: {mode.upper()}\n"
        
        # Get connection status
        try:
            test_results = main_module.test_connections()
            conn_status = "✅ Connected" if test_results.get("futures_connection", False) else "❌ Disconnected"
            status_msg += f"Connection: {conn_status}\n"
        except Exception as e:
            status_msg += f"Connection: ❓ Unknown ({str(e)})\n"
        
        # Get system time
        status_msg += f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        await update.message.reply_text(status_msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting status: {str(e)}")

async def _handle_balance(update: Any, context: Any):
    """Handle /balance command"""
    # Check authorization
    if not await _is_authorized(update):
        await update.message.reply_text("❌ Unauthorized access. Only the bot creator can use this bot.")
        return
    
    try:
        import importlib
        trading_engine = importlib.import_module("core.trading_engine")
        
        balance_info = trading_engine.get_futures_balance()
        
        balance_msg = "💰 Account Balance\n\n"
        balance_msg += f"Total: ${balance_info.get('total', 0):,.2f}\n"
        balance_msg += f"Free: ${balance_info.get('free', 0):,.2f}\n"
        balance_msg += f"Used: ${balance_info.get('used', 0):,.2f}\n"
        
        await update.message.reply_text(balance_msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting balance: {str(e)}")

async def _handle_positions(update: Any, context: Any):
    """Handle /positions command"""
    # Check authorization
    if not await _is_authorized(update):
        await update.message.reply_text("❌ Unauthorized access. Only the bot creator can use this bot.")
        return
    
    try:
        import importlib
        trading_engine = importlib.import_module("core.trading_engine")
        
        account_summary = trading_engine.get_account_summary()
        
        if "error" in account_summary:
            await update.message.reply_text(f"❌ Error: {account_summary['error']}")
            return
        
        positions = account_summary.get('open_positions', [])
        
        if not positions:
            await update.message.reply_text("📭 No open positions")
            return
        
        pos_msg = "📊 Open Positions\n\n"
        for pos in positions:
            symbol = pos.get('symbol', 'N/A')
            amount = float(pos.get('positionAmt', 0))
            entry_price = float(pos.get('entryPrice', 0))
            pnl = float(pos.get('unRealizedProfit', 0))
            
            side = "🟢 LONG" if amount > 0 else "🔴 SHORT" if amount < 0 else "N/A"
            amount = abs(amount)
            
            pos_msg += f"{symbol}\n"
            pos_msg += f"  {side}\n"
            pos_msg += f"  Amount: {amount:.6f}\n"
            pos_msg += f"  Entry: ${entry_price:.2f}\n"
            pos_msg += f"  PnL: ${pnl:+.2f}\n\n"
        
        await update.message.reply_text(pos_msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting positions: {str(e)}")

async def _handle_close(update: Any, context: Any):
    """Handle /close command"""
    # Check authorization
    if not await _is_authorized(update):
        await update.message.reply_text("❌ Unauthorized access. Only the bot creator can use this bot.")
        return
    
    try:
        if not context.args:
            await update.message.reply_text("❌ Please specify a symbol. Usage: /close <symbol>")
            return
        
        symbol = context.args[0].upper()
        
        # Validate symbol format
        if not symbol.endswith('USDT'):
            await update.message.reply_text("❌ Invalid symbol format. Use format like BTCUSDT")
            return
        
        importlib = __import__('importlib')
        trading_engine = importlib.import_module("core.trading_engine")
        
        # Get current position
        position = trading_engine.get_futures_position(symbol)
        
        if not position:
            await update.message.reply_text(f"📭 No open position for {symbol}")
            return
        
        # Determine close side
        amount = float(position.get('positionAmt', 0))
        if amount > 0:
            side = 'SELL'
        elif amount < 0:
            side = 'BUY'
        else:
            await update.message.reply_text(f"📭 No open position for {symbol}")
            return
        
        # Close position
        result = trading_engine.close_futures_position(
            symbol=symbol,
            side=side.lower(),
            amount=abs(amount)
        )
        
        if 'error' in result:
            await update.message.reply_text(f"❌ Error closing position: {result['error']}")
            return
        
        close_msg = (
            f"✅ Position Closed\n\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Amount: {abs(amount):.6f}\n"
            f"Order ID: {result.get('orderId', 'N/A')}"
        )
        
        await update.message.reply_text(close_msg)
        
        # Send notification to main chat
        if str(update.message.from_user.id) != str(CHAT_ID):
            send_message(close_msg)
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error closing position: {str(e)}")

async def _handle_close_all(update: Any, context: Any):
    """Handle /closeall command"""
    # Check authorization
    if not await _is_authorized(update):
        await update.message.reply_text("❌ Unauthorized access. Only the bot creator can use this bot.")
        return
    
    try:
        confirm_text = " ".join(context.args).lower() if context.args else ""
        
        if confirm_text != "confirm":
            await update.message.reply_text(
                "⚠️ Please confirm by typing: /closeall confirm\n\n"
                "This will close ALL open positions!"
            )
            return
        
        importlib = __import__('importlib')
        trading_engine = importlib.import_module("core.trading_engine")
        
        # Get all positions
        account_summary = trading_engine.get_account_summary()
        positions = account_summary.get('open_positions', [])
        
        if not positions:
            await update.message.reply_text("📭 No open positions to close")
            return
        
        closed_count = 0
        errors = []
        
        for pos in positions:
            try:
                symbol = pos.get('symbol', '')
                amount = float(pos.get('positionAmt', 0))
                
                if amount == 0:
                    continue
                
                # Determine close side
                side = 'SELL' if amount > 0 else 'BUY'
                
                # Close position
                result = trading_engine.close_futures_position(
                    symbol=symbol,
                    side=side.lower(),
                    amount=abs(amount)
                )
                
                if 'error' not in result:
                    closed_count += 1
                else:
                    errors.append(f"{symbol}: {result['error']}")
                    
            except Exception as e:
                errors.append(f"{pos.get('symbol', 'N/A')}: {str(e)}")
        
        # Prepare response
        if closed_count > 0:
            close_msg = f"✅ Closed {closed_count} position(s)"
            if errors:
                close_msg += f"\n\n⚠️ Errors:\n" + "\n".join(errors[:3])  # Limit to first 3 errors
                if len(errors) > 3:
                    close_msg += f"\n... and {len(errors) - 3} more"
        else:
            close_msg = "❌ No positions were closed"
            if errors:
                close_msg += f"\n\nErrors:\n" + "\n".join(errors[:5])
        
        await update.message.reply_text(close_msg)
        
        # Send notification to main chat
        if str(update.message.from_user.id) != str(CHAT_ID):
            send_message(close_msg)
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error closing positions: {str(e)}")

def start_telegram_bot():
    """Start the Telegram bot in a separate thread"""
    global application
    if not application:
        logger.warning("Telegram bot not initialized")
        return
    
    def run_bot():
        try:
            # Run the bot until stopped
            if application:
                application.run_polling(stop_signals=None)
        except Exception as e:
            logger.error(f"Error running Telegram bot: {e}")
    
    # Start bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("✅ Telegram bot started in background thread")

def send_initial_message():
    """Send initial welcome message with commands when bot starts"""
    global initial_message_sent
    if initial_message_sent:
        return False
    
    if not bot or not CHAT_ID:
        logger.debug("Telegram not configured, skipping initial message")
        return False
    
    try:
        initial_msg = (
            "🚀 Apex Neural Trading Bot Started!\n\n"
            "Available Commands:\n"
            "/start - Start the bot\n"
            "/help - Show detailed help\n"
            "/status - Show bot status\n"
            "/balance - Show account balance\n"
            "/positions - Show open positions\n"
            "/close <symbol> - Close a position\n"
            "/closeall - Close all positions\n\n"
            "ℹ️ All other notifications are disabled. Use commands to get information."
        )
        
        # Use importlib to avoid linter issues
        import importlib
        asyncio = importlib.import_module("asyncio")
        
        # Handle both async and sync contexts
        try:
            # Try to get running event loop
            loop = asyncio.get_running_loop()
            # If we're in an async context, create task
            task = loop.create_task(bot.send_message(chat_id=CHAT_ID, text=initial_msg))
            logger.info("📩 Initial Telegram welcome message queued")
        except RuntimeError:
            # No event loop running, run synchronously
            asyncio.run(bot.send_message(chat_id=CHAT_ID, text=initial_msg))
            logger.info("📩 Initial Telegram welcome message sent")
        
        initial_message_sent = True
        return True
            
    except Exception as e:
        logger.warning(f"⚠️ Failed to send initial Telegram message: {e}")
        return False

def send_message(text: str) -> bool:
    """
    Send a Telegram message from backend (for command responses)
    
    Args:
        text: Message to send
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    if not bot or not CHAT_ID:
        logger.debug("Telegram not configured, skipping message")
        return False
    
    try:
        # Use importlib to avoid linter issues
        import importlib
        asyncio = importlib.import_module("asyncio")
        
        # Handle both async and sync contexts
        try:
            # Try to get running event loop
            loop = asyncio.get_running_loop()
            # If we're in an async context, create task
            task = loop.create_task(bot.send_message(chat_id=CHAT_ID, text=text))
            logger.info(f"📩 Telegram command response queued: {text[:50]}...")
            return True
        except RuntimeError:
            # No event loop running, run synchronously
            asyncio.run(bot.send_message(chat_id=CHAT_ID, text=text))
            logger.info(f"📩 Telegram command response sent: {text[:50]}...")
            return True
            
    except Exception as e:
        logger.warning(f"⚠️ Telegram send failed: {e}")
        return False

def send_auto_notification(text: str) -> bool:
    """
    Send an automatic Telegram notification (only if enabled)
    
    Args:
        text: Message to send
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    # Only send automatic notifications if enabled
    if not TELEGRAM_AUTO_NOTIFICATIONS:
        logger.debug("Automatic Telegram notifications disabled, skipping message")
        return False
    
    return send_message(text)

# Test function to verify Telegram integration
def test_telegram() -> bool:
    """Test Telegram integration by sending a test message"""
    if not bot or not CHAT_ID:
        print("❌ Telegram not configured. Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return False
    
    try:
        send_message("✅ Telegram integration test successful! Apex Neural Trading Bot is ready.")
        print("✅ Telegram test message sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Telegram test failed: {e}")
        return False

# Initialize the bot when module is imported
_init_telegram_bot()

# Start the bot if credentials are available
if bot and application:
    start_telegram_bot()