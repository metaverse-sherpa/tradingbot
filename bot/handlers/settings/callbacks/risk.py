import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database
from bot.config import SUPER_ADMIN_ID
from bot.ui.keyboards import safe_edit_text, get_nav_buttons
from bot.handlers.settings.helpers import clear_input_states

logger = logging.getLogger(__name__)

async def handle_risk_callback(query, update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id: int) -> bool:
    """
    Handles callbacks related to risk management settings.
    Returns True if the callback was handled, False otherwise.
    """
    if query.data.startswith("set_risk_to_"):
        try:
            val = float(query.data.split("_")[-1])
            database.update_user_preference(chat_id, "risk_pct", val)
            await query.answer(f"✅ Risk aligned to {val:.2f}%!")
            
            kb = [
                [InlineKeyboardButton("🔬 Backtest Your Strategy", callback_data="run_backtest")],
                [InlineKeyboardButton("⚙️ Back to Settings", callback_data="back_to_settings")]
            ]
            await safe_edit_text(
                update, context,
                f"⚖️ *Institutional Risk Aligned!*\n\n"
                f"Successfully updated your risk-per-trade to **{val:.2f}%** to match the strategy's recommended allocation profile.",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logger.error(f"Error handling set_risk_to_ callback: {e}")
            await query.answer("❌ Error updating risk settings.", show_alert=True)
        return True

    if query.data == "set_crypto_risk":
        await query.answer()
        clear_input_states(context)
        context.user_data['setting_crypto_risk'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False), is_admin=(chat_id == SUPER_ADMIN_ID and not user.get('undercover_mode')))
        ]
        await safe_edit_text(
            update, context,
            "🪙 *Set Crypto Risk Percentage*\n\n"
            "Please type your preferred risk-per-trade for crypto as a number (e.g., `1.5` or `2.0`).\n\n"
            "_Current: " + f"{user.get('risk_pct', 1.5):.2f}%_",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    if query.data == "set_stock_risk":
        await query.answer()
        clear_input_states(context)
        context.user_data['setting_stock_risk'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False), is_admin=(chat_id == SUPER_ADMIN_ID and not user.get('undercover_mode')))
        ]
        await safe_edit_text(
            update, context,
            "🦙 *Set Stock Risk Percentage*\n\n"
            "Please type your preferred risk-per-trade for stocks as a number (e.g., `2.0` or `1.5`).\n\n"
            "_Current: " + f"{user.get('stock_risk_pct', 2.0):.2f}%_",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    return False
