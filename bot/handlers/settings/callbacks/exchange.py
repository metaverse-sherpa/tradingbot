import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database
from bot.ui.keyboards import safe_edit_text

logger = logging.getLogger(__name__)

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

async def handle_exchange_callback(query, update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id: int) -> bool:
    """
    Handles callbacks related to Alpaca brokerage account linking with explicit Paper/Live selection.
    Returns True if the callback was handled, False otherwise.
    """
    
    if query.data in ["switch_exchange_prompt", "set_alpaca_prompt"]:
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("📝 Alpaca Paper Trading (Simulated)", callback_data="set_alpaca_mode_paper")],
            [InlineKeyboardButton("💵 Alpaca Live Trading (Real Capital)", callback_data="set_alpaca_mode_live")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]
        ]
        await safe_edit_text(
            update, context,
            "🦙 *Link Your Alpaca Brokerage Account*\n\n"
            "Metaverse Sherpa connects exclusively to **Alpaca Markets** to execute algorithmic stock strategies.\n\n"
            "Please explicitly select your desired trading environment:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    if query.data == "set_alpaca_mode_paper":
        await query.answer()
        context.user_data['alpaca_endpoint'] = "https://paper-api.alpaca.markets"
        context.user_data['setup_step'] = 102
        guide = (
            "📝 *Alpaca Paper Trading Setup (Simulated)*\n\n"
            "Endpoint: `https://paper-api.alpaca.markets`\n\n"
            "1️⃣ Go to your **Alpaca Dashboard** and ensure **Paper Trading** is selected.\n"
            "2️⃣ Generate an API Key in the API Keys section on the right.\n\n"
            "Please paste your **Alpaca API Key ID** (e.g. `PK...`) below:"
        )
        await safe_edit_text(update, context, guide)
        return True

    if query.data == "set_alpaca_mode_live":
        await query.answer()
        context.user_data['alpaca_endpoint'] = "https://api.alpaca.markets"
        context.user_data['setup_step'] = 102
        guide = (
            "💵 *Alpaca Live Trading Setup (Real Capital)*\n\n"
            "Endpoint: `https://api.alpaca.markets`\n\n"
            "⚠️ *Warning*: Live orders will execute with real capital in your Alpaca brokerage account.\n\n"
            "1️⃣ Go to your **Alpaca Dashboard** and switch to **Live Brokerage**.\n"
            "2️⃣ Generate an API Key under the Live API Keys section.\n\n"
            "Please paste your **Alpaca API Key ID** (e.g. `AK...`) below:"
        )
        await safe_edit_text(update, context, guide)
        return True

    return False
