import logging
from telegram import Update
from telegram.ext import ContextTypes
import database
from bot.ui.keyboards import safe_query_answer
from bot.handlers.settings.commands import settings_command

logger = logging.getLogger(__name__)

async def handle_navigation_callback(query, update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id: int) -> bool:
    """
    Handles callbacks related to general navigation, help, contact, and simple toggles.
    Returns True if the callback was handled, False otherwise.
    """
    
    from bot.handlers.system import docs, contact_command
    from bot.handlers.trading import balance_command

    if query.data == "check_balance_setup":
        await query.answer()
        await balance_command(update, context)
        return True

    if query.data == "dummy_spacer":
        await safe_query_answer(query)
        return True

    if query.data == "help_menu":
        await query.answer()
        await docs(update, context)
        return True

    if query.data == "settings_menu":
        await query.answer()
        await settings_command(update, context)
        return True

    if query.data == "contact_menu":
        await query.answer()
        await contact_command(update, context)
        return True

    if query.data == "close_admin":
        await query.answer("Returning to Main Menu...")
        try:
            await query.message.delete()
        except Exception:
            pass
        await settings_command(update, context)
        return True

    if query.data == "toggle_privacy":
        if user:
            new_val = not user.get('hide_dollars', False)
            database.update_user_preference(chat_id, "hide_dollars", 1 if new_val else 0)
            await query.answer("✅ Privacy Mode updated!")
        else:
            await query.answer("User not found.")
        return True

    if query.data == "toggle_active":
        if user:
            new_val = not user.get('is_active', False)
            database.set_active(chat_id, new_val)
            status_txt = "Bot Resumed! 🟢" if new_val else "Bot Stopped! 🔴"
            await query.answer(status_txt)
        else:
            await query.answer("User not found.")
        return True

    if query.data == "back_to_settings":
        context.user_data.pop('setting_crypto_risk', None)
        context.user_data.pop('setting_stock_risk', None)
        await query.answer()
        # It's expected to fall through to the settings UI rendering in the main callback router.
        # But we return True, so the main router should handle the UI refresh.
        return True

    return False
