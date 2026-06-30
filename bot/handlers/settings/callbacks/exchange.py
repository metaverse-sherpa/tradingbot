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
    Handles callbacks related to exchange selection and setup guides.
    Returns True if the callback was handled, False otherwise.
    """
    
    if query.data == "send_blofin_guide":
        await query.answer("📥 Sending Blofin Guide...")
        pdf_path = os.path.join(BASE_DIR, "tutorials", "MetaverseSherpa Blofin API Setup.pdf")
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as doc:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=doc,
                    caption="🏔️ *Blofin API Setup Guide*\nFollow these steps to link your account securely.",
                    parse_mode="Markdown"
                )
        else:
            await query.message.reply_text("❌ Guide not found on server. Please contact @metaverse_sherpa.")
        return True

    if query.data == "switch_exchange_prompt":
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("🏔️ Blofin", callback_data="setex_blofin")],
            [InlineKeyboardButton("🔶 Binance", callback_data="setex_binance")],
            [InlineKeyboardButton("💠 MEXC", callback_data="setex_mexc")],
            [InlineKeyboardButton("🔷 Bitget", callback_data="setex_bitget")],
            [InlineKeyboardButton("🟦 BingX", callback_data="setex_bingx")],
            [InlineKeyboardButton("🪙 Coinbase Advanced", callback_data="setex_coinbase")],
            [InlineKeyboardButton("🦙 Alpaca Stocks", callback_data="setex_alpaca")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]
        ]
        await safe_edit_text(
            update, context,
            "🌍 *Select Your Exchange*\n\n"
            "Which exchange would you like to link to the Metaverse Sherpa?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    if query.data.startswith("setex_"):
        exchange_id = query.data.split("_")[1]
        context.user_data['exchange_id'] = exchange_id
        await query.answer()
        
        warning_text = ""
        if not user or not database.is_premium(user):
            warning_text = "⚠️ *Note:* You can configure your exchange settings now, but live auto-trading will only activate once you sign up for /premium.\n\n"
        
        if exchange_id == 'alpaca':
            context.user_data['setup_step'] = 101
            guide = (
                "🦙 *Alpaca API Setup*\n\n"
                "To connect your Alpaca Stock account, we will prompt you for your Endpoint Base URL, Key ID, and Secret Key sequentially.\n\n"
                "1️⃣ Please paste your **Alpaca API Endpoint Base URL** below:\n"
                "• Paper Trading: `https://paper-api.alpaca.markets`\n"
                "• Live Trading: `https://api.alpaca.markets`"
            )
            await safe_edit_text(update, context, f"{warning_text}{guide}")
            return True

        context.user_data['setup_step'] = 1
        if exchange_id == 'binance':
            guide = (
                "🔶 *Binance API Setup*\n\n"
                "1️⃣ Go to **API Management** on Binance.\n"
                "2️⃣ Create a 'System Generated' Key.\n"
                "3️⃣ Click 'Edit Restrictions' -> **'Enable Futures'**.\n"
                "4️⃣ **Security**: You MUST whitelist the VPS IP for Futures trading.\n\n"
                "Please paste your **Binance API Key** below:"
            )
        elif exchange_id == 'mexc':
            guide = (
                "💠 *MEXC API Setup*\n\n"
                "⚠️ *Requirement*: You MUST complete **Primary KYC** on MEXC to use Futures API keys.\n\n"
                "1️⃣ Go to **API Management** on MEXC.\n"
                "2️⃣ Create Key with **'Futures'** permissions.\n"
                "3️⃣ (Optional) Whitelist the VPS IP to avoid key expiration.\n\n"
                "Please paste your **MEXC API Key** below:"
            )
        elif exchange_id == 'bitget':
            guide = (
                "🔷 *Bitget API Setup*\n\n"
                "1️⃣ Go to **API Management** on Bitget.\n"
                "2️⃣ Create Key -> Enable **'Futures Trading'**.\n"
                "3️⃣ Note your passphrase for the final step.\n"
                "4️⃣ (Optional) Whitelist the VPS IP for security.\n\n"
                "Please paste your **Bitget API Key** below:"
            )
        elif exchange_id == 'bingx':
            guide = (
                "🟦 *BingX API Setup*\n\n"
                "1️⃣ Go to **API Management** on BingX.\n"
                "2️⃣ Create Key -> Enable **'Perpetual Futures Trading'**.\n"
                "3️⃣ (Optional) Whitelist the VPS IP for security.\n\n"
                "Please paste your **BingX API Key** below:"
            )
        elif exchange_id == 'coinbase':
            guide = (
                "🪙 *Coinbase Advanced API Setup*\n\n"
                "1️⃣ Go to the **Coinbase Developer Platform (CDP)**.\n"
                "2️⃣ Create a new API Key.\n"
                "3️⃣ Grant **'Advanced Trade (Trade & Read)'** permissions.\n"
                "4️⃣ Note that Coinbase US futures leverage is set by margin requirements rather than a direct multiplier.\n\n"
                "Please paste your **Coinbase API Key Name** (e.g. `organizations/123/apiKeys/abc-123`):"
            )
        else:
            guide = (
                "🏔️ *Blofin API Setup*\n\n"
                "1️⃣ Go to **API Management** on Blofin.\n"
                "2️⃣ Create Key with **'Read'** & **'Trade'** permissions.\n"
                "3️⃣ Note your passphrase for the final step.\n"
                "4️⃣ Do **not** bind the VPS IP during setup.\n\n"
                "Please paste your **Blofin API Key** below:"
            )
            
        await safe_edit_text(update, context, f"{warning_text}{guide}")
        return True

    return False
