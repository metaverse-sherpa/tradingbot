import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database

logger = logging.getLogger(__name__)

# Constants (Mirroring telegram_bot.py for now)
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", 1567788633))

def escape_md_v2(text):
    """Escapes all reserved characters for Telegram MarkdownV2."""
    if not text: return ""
    # Characters that must be escaped in MarkdownV2
    reserved = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in reserved:
        text = str(text).replace(char, f"\\{char}")
    return text

async def safe_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = "Markdown"):
    """Surgically edits a message or sends a fresh one if media conflict exists."""
    query = update.callback_query
    if not query:
        return await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    
    try:
        # 🕵️ Attempt sleek inline update
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        error_str = str(e)
        if "Message is not modified" in error_str:
            return
        
        # 🏔️ Fallback: If it's a photo message or other edit conflict, send fresh
        try:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            # Try to clean up the orphaned photo menu
            try: await query.message.delete()
            except: pass
        except Exception as e2:
            logger.error(f"SafeEdit Fatal Error: {e2}")

def get_nav_buttons(has_active_trades=False, is_admin=False):
    """Returns a standardized grid of inline navigation buttons."""
    kb = [
        [
            InlineKeyboardButton("🛰️ Active Trades", callback_data="opentrades_menu"),
            InlineKeyboardButton("📜 History", callback_data="history_menu")
        ],
        [
            InlineKeyboardButton("📊 Your Stats", callback_data="stats_menu"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu")
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="help_menu"),
            InlineKeyboardButton("🤝 Refer & Earn", callback_data="refer_menu")
        ]
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("👑 Admin Console", callback_data="admin_command")])
    
    if has_active_trades:
        kb.append([InlineKeyboardButton("🚨 CLOSE ALL TRADES", callback_data="confirm_panic")])
    return kb

def get_main_inline_menu(chat_id=None):
    """Generates the main navigation menu markup."""
    has_active = False
    is_admin = False
    if chat_id:
        user = database.get_user(chat_id)
        if user:
            has_active = user.get('has_open_positions', False)
            is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
    return InlineKeyboardMarkup(get_nav_buttons(has_active, is_admin))

def get_admin_keyboard(master_wallet):
    """Generates the specialized keyboard for the Sherpa Overlord."""
    return [
        [InlineKeyboardButton("🌍 Global Broadcast", callback_data="admin_broadcast_prompt")],
        [InlineKeyboardButton("📊 Detailed User Report", callback_data="admin_user_audit")],
        [InlineKeyboardButton("🎁 Generate Gift Code", callback_data="admin_gift_prompt")],
        [InlineKeyboardButton("💰 Set Master Wallet", callback_data="prompt_admin_wallet")],
        [InlineKeyboardButton("🔗 Get Blofin Tutorial Link", callback_data="admin_get_link")],
        [InlineKeyboardButton("🕵️ Toggle Undercover", callback_data="toggle_undercover")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="close_admin")]
    ]

def get_backtest_inline_menu(chat_id=None):
    """Generates the navigation menu markup with a 'Change Strategy' button above the nav buttons."""
    has_active = False
    is_admin = False
    if chat_id:
        user = database.get_user(chat_id)
        if user:
            has_active = user.get('has_open_positions', False)
            is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
    kb = [
        [InlineKeyboardButton("⚖️ Change Strategy", callback_data="strategy_menu")]
    ]
    kb.extend(get_nav_buttons(has_active, is_admin))
    return InlineKeyboardMarkup(kb)
