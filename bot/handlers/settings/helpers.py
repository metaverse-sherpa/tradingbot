from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.config import SUPER_ADMIN_ID, get_symbol_link
from bot.ui.keyboards import get_nav_buttons, safe_edit_text

def clear_input_states(context):
    """Clears all mutually exclusive interactive input states from user_data."""
    for key in ['setting_wallet', 'setting_admin_wallet', 'admin_broadcasting', 'admin_gifting', 'admin_direct_gifting', 'admin_direct_gifting_custom', 'direct_gift_target_id', 'admin_revoking', 'setting_crypto_risk', 'setting_stock_risk', 'setup_step', 'setting_cap_amount', 'setting_cap_pct']:
        context.user_data.pop(key, None)

async def show_symbol_menu(update, context, user):
    query = update.callback_query
    chat_id = user['telegram_chat_id']
    
    strategy = user.get('active_crypto_strategy', 'Valkyrie Elite Scalper')
    if strategy == "Valkyrie Elite Scalper":
        all_syms = ["SOL", "LINK", "BTC", "ADA", "DOT", "ETH", "SUI"]
        title_text = "🛰 *Manage Valkyrie Symbols*\n\nTap a symbol to toggle it ON or OFF. Valkyrie operates on these Top 7 institutional volume assets."
    else:
        all_syms = ["BTC","ETH","SOL","DOGE","ADA","LINK","DOT","TON","ZEC","PEPE","BNB","NEAR","SUI","NOT","TAO","ONDO","ENA","FET","WIF"]
        title_text = "🛰 *Manage Symbols*\n\nTap a symbol to toggle it ON or OFF for your account."
        
    enabled = user['enabled_symbols']
    
    keyboard = []
    row = []
    for s in all_syms:
        label = f"✅ {s}" if s in enabled else f"❌ {s}"
        row.append(InlineKeyboardButton(label, callback_data=f"tsym_{s}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🚀 Apply Settings", callback_data="apply_symbol_audit")])
    keyboard.append([InlineKeyboardButton("───────────────", callback_data="none")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")])
    is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
    keyboard.extend(get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin))
    
    await safe_edit_text(
        update, context,
        title_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
