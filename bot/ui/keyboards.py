import os
import sys
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import database
from bot.config import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)

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
        ],
        [
            InlineKeyboardButton("---- Virtual Trades ----", callback_data="dummy_spacer")
        ],
        [
            InlineKeyboardButton("🛰️ Active Trades (Virtual)", callback_data="virtual_active"),
            InlineKeyboardButton("📜 Closed Trades (Virtual)", callback_data="virtual_closed")
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
        [InlineKeyboardButton("🔬 View Simulated Trades", callback_data="admin_view_simulated_trades")],
        [
            InlineKeyboardButton("📈 Share MR Stats", callback_data="shf_mr"),
            InlineKeyboardButton("🛡️ Share VK Stats", callback_data="shf_vk"),
            InlineKeyboardButton("🦙 Share SVP Stats", callback_data="shf_svp")
        ],
        [InlineKeyboardButton("🎁 Generate Gift Code", callback_data="admin_gift_prompt")],
        [InlineKeyboardButton("💰 Set Master Wallet", callback_data="prompt_admin_wallet")],
        [InlineKeyboardButton("🔗 Get Blofin Tutorial Link", callback_data="admin_get_link")],
        [InlineKeyboardButton("🕵️ Toggle Undercover", callback_data="toggle_undercover")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="close_admin")]
    ]

def get_backtest_inline_menu(chat_id=None, show_risk_button=False):
    """Generates the navigation menu markup with a 'Change Strategy' button above the nav buttons."""
    has_active = False
    is_admin = False
    is_premium = False
    if chat_id:
        user = database.get_user(chat_id)
        if user:
            has_active = user.get('has_open_positions', False)
            is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
            is_premium = database.is_premium(user)
    
    kb = []
    if show_risk_button:
        risk_label = f"⚖️ Set Risk % {'🔒' if not is_premium else ''}"
        kb.append([InlineKeyboardButton(risk_label, callback_data="set_risk")])
        
    kb.append([InlineKeyboardButton("⚖️ Change Strategy", callback_data="strategy_menu")])
    kb.extend(get_nav_buttons(has_active, is_admin))
    return InlineKeyboardMarkup(kb)

def get_settings_ui(user):
    privacy_status = "🔒 HIDDEN" if user['hide_dollars'] else "👁️ SHOWN"
    bot_status = "🟢 ACTIVE" if user['is_active'] else "🔴 PAUSED"
    risk_val = user.get('risk_pct', 1.5)
    syms = user.get('enabled_symbols', [])
    wallet_val = user.get('source_wallet')
    wallet_display = f"{wallet_val[:6]}...{wallet_val[-4:]}" if wallet_val else "(Not Set)"
    
    is_premium = database.is_premium(user)
    is_admin = (user.get('telegram_chat_id') == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
    
    tier_display = "👑 Sherpa Overlord (Permanent)" if is_admin else ("💎 Premium (Institutional)" if is_premium else "🥈 Standard")
    
    expiry_msg = ""
    if is_premium and not is_admin:
        days_left = database.get_premium_days_left(user)
        expiry_date = time.strftime('%Y-%m-%d', time.localtime(user['premium_expiry']))
        expiry_msg = f"Expires: *{expiry_date}* ({days_left} days left)\n"
    
    eq_type = user.get('custom_equity_type', 'all')
    eq_val = user.get('custom_equity_value')
    
    if eq_type == 'all' or eq_val is None:
        capital_display = "Full Account Balance (100%)"
    elif eq_type == 'pct':
        capital_display = f"{eq_val:.1f}% of Balance"
    elif eq_type == 'amount':
        capital_display = f"${eq_val:,.2f} USDT"
    else:
        capital_display = "Full Account Balance (100%)"

    msg = (
        f"⚙️ *Metaverse Sherpa Settings*\n\n"
        f"Status: *{bot_status}*\n"
        f"Tier: *{tier_display}*\n"
        f"{expiry_msg}"
        f"🪙 Crypto Strategy: *{user.get('active_crypto_strategy', 'Mean Reversion Scalper')}*\n"
        f"🦙 Stock Strategy: *{user.get('active_stock_strategy', 'None')}*\n"
        f"Risk Level: *{risk_val:.2f}%*\n"
        f"Active Symbols: *{len(syms)}/19*\n"
        f"Capital Allocation: *{capital_display}*\n"
        f"Dollar PnL: *{privacy_status}*\n"
        f"Source Wallet: `{wallet_display}`\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"⚖️ Set Risk % {'🔒' if not is_premium else ''}", callback_data="set_risk"),
         InlineKeyboardButton(f"🛰 Symbols {'🔒' if not is_premium else ''}", callback_data="manage_symbols")],
        [InlineKeyboardButton("💰 Capital Allocation", callback_data="capital_menu")],
        [InlineKeyboardButton(f"Toggle Privacy ({'Show $' if user['hide_dollars'] else 'Hide $'})", callback_data="toggle_privacy")],
        [InlineKeyboardButton("Change Strategy", callback_data="strategy_menu")],
        [InlineKeyboardButton("🔬 Backtest Your Strategy", callback_data="run_backtest")],
        [InlineKeyboardButton("🔌 Switch Exchange", callback_data="switch_exchange_prompt")],
    ]
    
    if is_admin:
        # Overlord has no need for renewal buttons
        pass
    elif is_premium:
        keyboard.append([InlineKeyboardButton("🔄 Renew Institutional Access", callback_data="premium_menu")])
    else:
        keyboard.append([InlineKeyboardButton("🤝 My Referral Link", callback_data="referral_menu")])
        keyboard.append([InlineKeyboardButton("💎 Go Premium ($20/mo)", callback_data="premium_menu")])
    
    keyboard.append([InlineKeyboardButton("👛 Set/Change Wallet", callback_data="prompt_set_wallet")])
    
    # 🏔️ Extend settings UI with main navigation footer menu
    has_active = user.get('has_open_positions', False)
    keyboard.extend(get_nav_buttons(has_active, is_admin))
    
    return msg, InlineKeyboardMarkup(keyboard)
