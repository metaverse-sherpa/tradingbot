"""
Telegram Trading Bot - Main Entry Point

This module serves as the primary initialization script for the application. It bootstraps the
python-telegram-bot application, sets up error handlers, registers routing handlers, and crucially,
launches the core background asynchronous trading engines (`sync_engine`, `signal_engine`, `alpaca_equities_engine`).

Architecture Overview:
- The bot runs entirely within the `asyncio` event loop provided by the `python-telegram-bot` ApplicationBuilder.
- It leverages Telegram's `post_init` and `post_stop` hooks to safely spin up and tear down long-running 
  API connection tasks (e.g., CCXT web sockets or REST polling) without blocking the main thread.
- Upon a fatal crash, it uses a synchronous requests fallback to alert the Super Admin to bypass 
  the event loop if it becomes entirely compromised.
"""

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
from bot.engines import (
    sync_engine,
    signal_engine,
    alpaca_equities_engine,
    alpaca_fractional_monitor_engine,
    premium_expiration_engine,
    daily_stock_email_engine,
    daily_crypto_email_engine,
    weekly_stock_email_engine,
    weekly_crypto_email_engine,
    theory_trades_resolution_engine
)
from bot.handlers.system import error_handler

# Backward compatibility imports for downstream charting/audit scripts
from bot.ui.keyboards import get_nav_buttons

async def post_init(application):
    """
    Hook executed after the bot application is initialized but before it starts polling.
    
    Responsibilities:
    1. Register the standard Telegram Command Menu for the UI.
    2. Dispatch a deployment success notification to the Super Admin (reading git history).
    3. Spawn the core trading background loops as concurrent asyncio tasks.
    """
    # Set the bot's command menu (the button in the bottom left of Telegram)
    await application.bot.set_my_commands([
        ("opentrades", "🛰 View live active positions"),
        ("list", "📜 List last 10 closed trades"),
        ("stats", "📊 View account performance"),
        ("balance", "💰 Check available USDT balance"),
        ("help", "❓ Get help & command guide"),
        ("settings", "⚙️ Bot settings & privacy"),
        ("docs", "📖 View user manual & tutorials"),
        ("contact", "🤝 Contact @metaverse_sherpa"),
        ("reset", "🔄 Reconfigure API keys"),
    ])

    # 🚀 Notify Overlord of Deployment Success
    try:
        import subprocess
        from datetime import datetime
        from bot.ui.keyboards import escape_md_v2
        
        # Fetch the latest 3 commit messages for the changelog
        try:
            changelog = subprocess.check_output(['git', 'log', '-n', '3', '--pretty=format:• %s (%ar)']).decode('utf-8')
        except Exception as git_err:
            logger.error(f"Failed to fetch changelog via git: {git_err}")
            changelog = "• New deployment (Audit Trail Unavailable)"
            
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now_v2 = escape_md_v2(now)
        changelog_v2 = escape_md_v2(changelog)
        msg = (
            "🚀 *Deployment Success*\n\n"
            "The MetaverseSherpa Trading Bot has been upgraded and is now online\\.\n\n"
            f"🕒 *Timestamp:* `{now_v2}`\n\n"
            "📜 *Recent Fixes:* \n" + changelog_v2 + "\n\n"
            "🔬 *What to Test Next:*\n"
            "• Verify 'Close Trade' tactical confirmation on /opentrades\n"
            "• Audit the new 'Glass Progress Bar' for layout overlap\n"
            "• Confirm Blofin Tutorial deep\\_link delivers PDF correctly"
        )
        await application.bot.send_message(
            chat_id=SUPER_ADMIN_ID,
            text=msg,
            parse_mode="MarkdownV2"
        )
        logger.info("Sent startup deployment notification to Super Admin.")
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")

    # Spawn the background loop engines under python-telegram-bot's loop context.
    # By storing these tasks in `bot_data`, we can gracefully cancel them in the `post_stop` hook.
    task1 = asyncio.create_task(sync_engine(application))
    task2 = asyncio.create_task(signal_engine(application))
    task3 = asyncio.create_task(alpaca_equities_engine(application))
    task4 = asyncio.create_task(alpaca_fractional_monitor_engine(application))
    task5 = asyncio.create_task(premium_expiration_engine(application))
    task6_1 = asyncio.create_task(daily_stock_email_engine(application))
    task6_2 = asyncio.create_task(daily_crypto_email_engine(application))
    task6_3 = asyncio.create_task(weekly_stock_email_engine(application))
    task6_4 = asyncio.create_task(weekly_crypto_email_engine(application))
    task7 = asyncio.create_task(theory_trades_resolution_engine(application))
    
    # Store references to prevent garbage collection
    application.bot_data["bg_tasks"] = [
        task1, task2, task3, task4, task5,
        task6_1, task6_2, task6_3, task6_4,
        task7
    ]


async def post_stop(application):
    """
    Hook executed when the application receives a shutdown signal (SIGINT/SIGTERM).
    Gracefully cancels background engines to release TCP sockets safely and prevent 
    dangling tasks from holding ports or generating messy traceback errors on exit.
    """
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

def main():
    """
    Main application runner. 
    Bootstraps the database, configures the Telegram Application instance, attaches background hooks, 
    and initiates the long-polling loop. Also includes a hard fail-safe to alert admins on fatal loops.
    """
    try:
        # Ensure database table exists before allowing any bot interactions
        database.init_db()

        # Initialize Bot Application with the post_init and post_stop hooks
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).post_stop(post_stop).build()
        app.add_error_handler(error_handler)
        
        # Register all command handlers and callback query handlers
        register_handlers(app)
        
        logger.info("Starting Telegram Bot Polling...")
        app.run_polling(bootstrap_retries=5)
    except Exception as e:
        # Gracefully handle event loop closure artifact during shutdown under Python 3.12+
        if isinstance(e, RuntimeError) and "no running event loop" in str(e):
            logger.info("Event loop was closed/stopped during shutdown cleanup.")
            sys.exit(0)
            
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

# Force restart to apply Alpaca schema migrations
