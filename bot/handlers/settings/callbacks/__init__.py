import logging
from telegram import Update
from telegram.ext import ContextTypes
import database
from bot.ui.keyboards import get_settings_ui, safe_edit_text

from .admin import handle_admin_callback
from .billing import handle_billing_callback
from .allocation import handle_allocation_callback
from .risk import handle_risk_callback
from .exchange import handle_exchange_callback
from .strategies import handle_strategies_callback
from .trades import handle_trades_callback
from .navigation import handle_navigation_callback

logger = logging.getLogger(__name__)

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main router for all settings-related callbacks.
    Delegates to modularized domain handlers.
    """
    query = update.callback_query
    chat_id = query.from_user.id
    user = database.get_user(chat_id)
    
    # Global Cleanup Handlers (from original monolithic callbacks)
    if query.data != "view_strategy_guide":
        photo_ids = context.user_data.pop('strategy_guide_photo_ids', [])
        for photo_id in photo_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=photo_id)
            except Exception:
                pass
                
    if query.data not in ["admin_view_free_trades", "free_active"]:
        sim_photo_ids = context.user_data.pop('admin_free_photo_ids', [])
        for photo_id in sim_photo_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=photo_id)
            except Exception:
                pass

    # Domain routing
    handlers = [
        handle_admin_callback,
        handle_billing_callback,
        handle_allocation_callback,
        handle_risk_callback,
        handle_exchange_callback,
        handle_strategies_callback,
        handle_trades_callback,
        handle_navigation_callback
    ]

    for handler in handlers:
        handled = await handler(query, update, context, user, chat_id)
        if handled:
            # If the handler returned True, we need to handle the UI refresh if back_to_settings was clicked or if it expects a UI refresh
            if query.data == "back_to_settings" or query.data == "apply_symbol_audit":
                try:
                    updated_user = database.get_user(chat_id)
                    msg, reply_markup = get_settings_ui(updated_user)
                    await safe_edit_text(update, context, msg, reply_markup=reply_markup)
                except Exception as e:
                    logger.error(f"Error rendering settings UI: {e}")
            return

    # Fallback rendering if no handler fully captured execution, or just render default settings menu
    try:
        updated_user = database.get_user(chat_id)
        msg, reply_markup = get_settings_ui(updated_user)
        await safe_edit_text(update, context, msg, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error rendering fallback settings UI: {e}")
        await query.answer("An error occurred.")
