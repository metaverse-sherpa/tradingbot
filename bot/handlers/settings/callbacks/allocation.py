import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database
from bot.ui.keyboards import safe_edit_text, get_settings_ui
from bot.handlers.settings.helpers import clear_input_states, show_symbol_menu

logger = logging.getLogger(__name__)

async def handle_allocation_callback(query, update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id: int) -> bool:
    """
    Handles callbacks related to capital allocation and symbol management.
    Returns True if the callback was handled, False otherwise.
    """
    
    if query.data == "capital_menu":
        await query.answer()
        clear_input_states(context)
        
        eq_type = user.get('custom_equity_type', 'all')
        eq_val = user.get('custom_equity_value')
        
        actual_balance = user.get('equity') or 0.0
        
        if eq_type == 'all' or eq_val is None:
            active_mode = "🏦 Use Full Balance (100%)"
            effective_cap = actual_balance
        elif eq_type == 'pct':
            active_mode = f"📊 Percentage Override ({eq_val:.1f}%)"
            effective_cap = actual_balance * (float(eq_val) / 100.0)
        elif eq_type == 'amount':
            active_mode = f"💵 Fixed Dollar Amount (${eq_val:,.2f} USDT)"
            effective_cap = min(float(eq_val), actual_balance)
            
        menu_text = (
            "💰 *Capital Allocation Settings*\n\n"
            "By default, the bot trades using your full exchange account balance. "
            "You can override this to isolate a specific dollar amount or percentage of your balance for trading.\n\n"
            f"• Current Balance: *${actual_balance:,.2f} USDT*\n"
            f"• Active Mode: *{active_mode}*\n"
            f"• Effective Trading Capital: *${effective_cap:,.2f} USDT*\n\n"
            "Select an option below to change your allocation:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏦 Use Full Balance (100%)", callback_data="set_cap_all")],
            [InlineKeyboardButton("💵 Set Fixed Dollar Amount ($)", callback_data="set_cap_amount_prompt")],
            [InlineKeyboardButton("📊 Set Percentage (%)", callback_data="set_cap_pct_prompt")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]
        ]
        
        await safe_edit_text(update, context, menu_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    if query.data == "set_cap_all":
        database.update_user_preference(chat_id, "custom_equity_type", "all")
        database.update_user_preference(chat_id, "custom_equity_value", None)
        await query.answer("✅ Reset to Full Balance!")
        
        updated_user = database.get_user(chat_id)
        msg, markup = get_settings_ui(updated_user)
        await safe_edit_text(update, context, msg, reply_markup=markup)
        return True

    if query.data == "set_cap_amount_prompt":
        await query.answer()
        clear_input_states(context)
        context.user_data['setting_cap_amount'] = True
        
        actual_balance = user.get('equity') or 0.0
        
        prompt_text = (
            "💵 *Set Fixed Dollar Amount (USDT)*\n\n"
            f"Your current exchange account balance is: *${actual_balance:,.2f} USDT*\n\n"
            "Please send the exact USDT amount you want the bot to trade with (e.g., `500` or `1250`):\n\n"
            "⚠️ _Note: This amount cannot exceed your current account balance._\n\n"
            "Tap /cancel to abort."
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Cancel", callback_data="capital_menu")]]
        await safe_edit_text(update, context, prompt_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    if query.data == "set_cap_pct_prompt":
        await query.answer()
        clear_input_states(context)
        context.user_data['setting_cap_pct'] = True
        
        prompt_text = (
            "📊 *Set Capital Percentage (%)*\n\n"
            "Please send the percentage of your balance you want the bot to trade with (a number between `1` and `100`, e.g. `50`):\n\n"
            "Tap /cancel to abort."
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Cancel", callback_data="capital_menu")]]
        await safe_edit_text(update, context, prompt_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    if query.data == "manage_symbols":
        await query.answer()
        await show_symbol_menu(update, context, user)
        return True

    if query.data.startswith("tsym_"):
        sym_to_toggle = query.data.split("_")[1]
        current_syms = user.get('enabled_symbols', [])
        if sym_to_toggle in current_syms:
            current_syms.remove(sym_to_toggle)
        else:
            current_syms.append(sym_to_toggle)
        database.update_user_preference(chat_id, "enabled_symbols", current_syms)
        await query.answer(f"✅ Updated {sym_to_toggle}")
        updated_user = database.get_user(chat_id)
        await show_symbol_menu(update, context, updated_user)
        return True

    if query.data == "apply_symbol_audit":
        await query.answer("🏔️ Settings Applied!")
        try:
            updated_user = database.get_user(chat_id)
            msg, reply_markup = get_settings_ui(updated_user)
            await safe_edit_text(update, context, msg, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to apply symbol settings for {chat_id}: {e}")
            from bot.ui.keyboards import get_main_inline_menu
            await safe_edit_text(update, context, f"❌ Error applying settings: {e}\n\nPlease try again or contact the Sherpa.", reply_markup=get_main_inline_menu(chat_id))
        return True

    return False
