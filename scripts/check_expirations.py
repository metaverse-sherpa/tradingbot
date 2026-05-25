import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("CheckExpirations")

# Ensure projects directory is in path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path.append(project_root)

# Load explicit .env path
dotenv_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path=dotenv_path)

import database

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN not found in environment!")
    sys.exit(1)

async def run_expiration_check():
    logger.info("⏳ Starting Premium Expiration Check...")
    database.init_db()
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    expired_users = database.get_expired_unnotified_users()
    if not expired_users:
        logger.info("✅ No new expirations to notify.")
        return

    logger.info(f"📬 Found {len(expired_users)} users whose premium expired. Sending alerts...")
    
    msg = (
        "⚠️ *Your Premium Access Has Expired!*\n\n"
        "Your Metaverse Sherpa autopilot has been paused, and live trade execution is no longer active for your account.\n\n"
        "However, you will continue to receive free trading signals directly in Telegram!\n\n"
        "To reactivate auto-trading across all your assets and return to autopilot mode, please renew your Premium Access by typing /settings or /premium."
    )
    
    for chat_id in expired_users:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown"
            )
            database.set_premium_expired_notified(chat_id, True)
            logger.info(f"Notified {chat_id} of expiration.")
        except Exception as e:
            logger.error(f"Failed to send expiration notice to {chat_id}: {e}")
            
    logger.info("✅ Expiration check complete!")

if __name__ == "__main__":
    asyncio.run(run_expiration_check())
