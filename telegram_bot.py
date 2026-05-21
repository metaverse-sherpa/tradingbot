import sys
import os
import asyncio
from telegram.ext import ApplicationBuilder

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Load config and core logger
from bot.config import TELEGRAM_TOKEN, SUPER_ADMIN_ID, logger
import database
from bot.handlers import register_handlers
from bot.engines import sync_engine, signal_engine, alpaca_equities_engine

# Backward compatibility imports for downstream charting/audit scripts
from bot.ui.keyboards import get_nav_buttons

async def post_init(application):
    # Spawn the background loop engines under python-telegram-bot's loop context
    task1 = asyncio.create_task(sync_engine(application))
    task2 = asyncio.create_task(signal_engine(application))
    task3 = asyncio.create_task(alpaca_equities_engine(application))
    application.bot_data['bg_tasks'] = [task1, task2, task3]

async def post_stop(application):
    """Gracefully cancel background engines to release TCP sockets safely."""
    logger.info("Gracefully shutting down background engines...")
    bg_tasks = application.bot_data.get('bg_tasks', [])
    for task in bg_tasks:
        task.cancel()
        
    if bg_tasks:
        # Wait for them to cancel, triggering CCXT finally/__aexit__ blocks
        await asyncio.gather(*bg_tasks, return_exceptions=True)
    
    # Give aiohttp a small buffer to sweep the unclosed connectors
    await asyncio.sleep(0.5)
    logger.info("Background engines shut down.")

async def error_handler(update, context):
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)

def main():
    try:
        # Ensure database table exists
        database.init_db()

        # Initialize Bot Application with the post_init and post_stop hooks
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).post_stop(post_stop).build()
        app.add_error_handler(error_handler)
        
        # Register all command handlers and callback query handlers
        register_handlers(app)
        
        logger.info("Starting Telegram Bot Polling...")
        app.run_polling()
    except Exception as e:
        import traceback
        import requests
        err_msg = f"🚨 *FATAL BOT CRASH*\n\nThe Cyber-Sherpa has fallen! 🏔️\n\n*Error:* `{str(e)}`"
        try:
            tb = traceback.format_exc()
            # Send to Super Admin via simple HTTP request to bypass complex bot setup
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": SUPER_ADMIN_ID,
                "text": f"{err_msg}\n\n*Traceback:*\n```\n{tb[:3500]}\n```",
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=10)
        except:
            pass
        logger.critical(f"FATAL ERROR: {e}\n{traceback.format_exc()}")
        raise e

if __name__ == "__main__":
    main()
