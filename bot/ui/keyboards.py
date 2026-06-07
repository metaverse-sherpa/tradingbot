import os
import sys
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
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

def build_datetime_entity_message(text_before: str, unix_ts: int, text_after: str = "") -> tuple:
    """
    Builds a (text, entities) tuple for a message that embeds a date_time entity.
    Telegram clients will auto-format the placeholder timestamp text into the user's
    local timezone and locale (Bot API 9.5+). Falls back gracefully on older clients.

    Args:
        text_before: Plain text that appears before the timestamp.
        unix_ts: Unix timestamp in seconds (NOT milliseconds).
        text_after: Plain text that appears after the timestamp.

    Returns:
        A tuple (full_text, entities_list) ready to pass to send_message().
    """
    # Use a readable placeholder so older clients still show something sensible
    from datetime import datetime, timezone
    try:
        dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        placeholder = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        dt = None
        placeholder = str(unix_ts)

    offset = len(text_before)
    length = len(placeholder)
    full_text = f"{text_before}{placeholder}{text_after}"

    entity = MessageEntity(
        type=MessageEntity.DATE_TIME,
        offset=offset,
        length=length,
        unix_time=dt,
    )
    return full_text, [entity]

async def send_cached_photo(update, context, photo_path: str, caption: str = None, reply_markup = None, parse_mode = "Markdown"):
    """
    Sends a photo and caches the Telegram file_id in the database to dramatically speed up future sends.
    If the file has already been uploaded once, it uses the cached file_id.
    """
    chat_id = update.effective_chat.id
    if not os.path.exists(photo_path):
        logger.error(f"send_cached_photo: File not found at {photo_path}")
        if caption:
            await safe_edit_text(update, context, caption, reply_markup=reply_markup, parse_mode=parse_mode)
        return None

    # Use the filename as the cache key
    filename = os.path.basename(photo_path)
    cache_key = f"photo_cache_{filename}"
    cached_file_id = database.get_config(cache_key)

    try:
        if cached_file_id:
            # Delete old message if it was a callback
            if update.callback_query:
                try: await update.effective_message.delete()
                except: pass
                
            return await context.bot.send_photo(
                chat_id=chat_id,
                photo=cached_file_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except Exception as e:
        logger.warning(f"Failed to send cached photo {filename} (maybe invalid file_id). Re-uploading. Error: {e}")
        # Clear the invalid cache
        database.update_config(cache_key, "")
        cached_file_id = None

    # Upload from disk
    if update.callback_query:
        try: await update.effective_message.delete()
        except: pass

    with open(photo_path, 'rb') as photo:
        try:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            # Cache the largest photo's file_id
            if msg.photo:
                best_photo = msg.photo[-1]
                database.update_config(cache_key, best_photo.file_id)
            return msg
        except Exception as e:
            logger.error(f"Failed to upload photo {filename}: {e}")
            if caption:
                await safe_edit_text(update, context, caption, reply_markup=reply_markup, parse_mode=parse_mode)
            return None

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

def get_nav_buttons(has_active_trades=False, is_admin=False, has_exchange=True):
    """Returns a standardized grid of inline navigation buttons."""
    if has_exchange:
        kb = [
            [
                InlineKeyboardButton("🛰️ Live Trades", callback_data="opentrades_menu"),
                InlineKeyboardButton("📜 History", callback_data="history_menu")
            ],
            [
                InlineKeyboardButton("📊 Your Stats", callback_data="stats_menu")
            ],
            [
                InlineKeyboardButton("🤝 Refer & Earn", callback_data="refer_menu"),
                InlineKeyboardButton("💎 Get Premium", callback_data="premium_menu")
            ],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu"),
                InlineKeyboardButton("❓ Help", callback_data="help_menu")
            ],
            [
                InlineKeyboardButton("---- Free Signals ----", callback_data="dummy_spacer")
            ],
            [
                InlineKeyboardButton("🛰️ Active Signals", callback_data="free_active"),
                InlineKeyboardButton("📜 Closed Signals", callback_data="free_closed")
            ],
            [
                InlineKeyboardButton("📊 Free Signal Stats", callback_data="free_stats")
            ]
        ]
    else:
        kb = [
            [
                InlineKeyboardButton("---- Free Signals ----", callback_data="dummy_spacer")
            ],
            [
                InlineKeyboardButton("🛰️ Active Signals", callback_data="free_active"),
                InlineKeyboardButton("📜 Closed Signals", callback_data="free_closed")
            ],
            [
                InlineKeyboardButton("📊 Free Signal Stats", callback_data="free_stats")
            ],
            [
                InlineKeyboardButton("🤝 Refer & Earn", callback_data="refer_menu"),
                InlineKeyboardButton("💎 Get Premium", callback_data="premium_menu")
            ],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu"),
                InlineKeyboardButton("❓ Help", callback_data="help_menu")
            ]
        ]
        
    if is_admin:
        kb.append([InlineKeyboardButton("👑 Admin Console", callback_data="admin_command")])
    
    if has_active_trades and has_exchange:
        kb.append([InlineKeyboardButton("🚨 CLOSE ALL TRADES", callback_data="confirm_panic")])
    return kb

def get_main_inline_menu(chat_id=None):
    """Generates the main navigation menu markup."""
    has_active = False
    is_admin = False
    has_exchange = True
    if chat_id:
        user = database.get_user(chat_id)
        if user:
            has_active = user.get('has_open_positions', False)
            is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
            crypto_connected = bool(user.get('exchange_id') and user.get('api_key') and user.get('api_secret'))
            alpaca_connected = bool(user.get('alpaca_api_key') and user.get('alpaca_api_secret'))
            has_exchange = crypto_connected or alpaca_connected
            
    return InlineKeyboardMarkup(get_nav_buttons(has_active, is_admin, has_exchange))

def get_admin_keyboard(master_wallet):
    """Generates the specialized keyboard for the Sherpa Overlord."""
    disabled = database.get_disabled_strategies()
    
    share_row = []
    if "Mean Reversion Scalper" not in disabled:
        share_row.append(InlineKeyboardButton("📈 Share MR Stats", callback_data="shf_mr"))
    if "Valkyrie Elite Scalper" not in disabled:
        share_row.append(InlineKeyboardButton("🛡️ Share VK Stats", callback_data="shf_vk"))
    if "Sherpa Velocity Pullback" not in disabled:
        share_row.append(InlineKeyboardButton("🦙 Share SVP Stats", callback_data="shf_svp"))
        
    return [
        [InlineKeyboardButton("🌍 Global Broadcast", callback_data="admin_broadcast_prompt")],
        [InlineKeyboardButton("📊 Detailed User Report", callback_data="admin_user_audit")],
        [InlineKeyboardButton("🔬 View Free Signals", callback_data="admin_view_free_trades")],
        share_row if share_row else [],
        [InlineKeyboardButton("🚫 Manage Strategies", callback_data="admin_manage_strategies")],
        [InlineKeyboardButton("🎁 Generate Gift Code", callback_data="admin_gift_prompt")],
        [InlineKeyboardButton("🚫 Revoke Premium Access", callback_data="admin_revoke_prompt")],
        [InlineKeyboardButton("💰 Set Master Wallet", callback_data="prompt_admin_wallet")],
        [InlineKeyboardButton("🔗 Get Blofin Tutorial Link", callback_data="admin_get_link")],
        [InlineKeyboardButton("📧 Toggle Email Premium-Only", callback_data="toggle_emails_premium")],
        [InlineKeyboardButton("🕵️ Toggle Undercover", callback_data="toggle_undercover")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="close_admin")]
    ]

def get_backtest_inline_menu(chat_id=None, show_risk_button=True, asset_type='crypto'):
    """Generates the navigation menu markup with a 'Change Strategy' button above the nav buttons."""
    has_active = False
    is_admin = False
    is_premium = False
    has_exchange = True
    if chat_id:
        user = database.get_user(chat_id)
        if user:
            has_active = user.get('has_open_positions', False)
            is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
            is_premium = database.is_premium(user)
            crypto_connected = bool(user.get('exchange_id') and user.get('api_key') and user.get('api_secret'))
            alpaca_connected = bool(user.get('alpaca_api_key') and user.get('alpaca_api_secret'))
            has_exchange = crypto_connected or alpaca_connected
    
    kb = []
    if show_risk_button:
        if asset_type == 'stock':
            risk_label = f"⚖️ Set Stock Risk % {'🔒' if not is_premium else ''}"
            callback = "set_stock_risk"
        else:
            risk_label = f"⚖️ Set Crypto Risk % {'🔒' if not is_premium else ''}"
            callback = "set_crypto_risk"
        kb.append([InlineKeyboardButton(risk_label, callback_data=callback)])
        
    kb.append([InlineKeyboardButton("⚖️ Change Strategy", callback_data="strategy_menu")])
    kb.extend(get_nav_buttons(has_active, is_admin, has_exchange))
    return InlineKeyboardMarkup(kb)

def get_settings_ui(user):
    privacy_status = "🔒 HIDDEN" if user['hide_dollars'] else "👁️ SHOWN"
    bot_status = "🟢 ACTIVE" if user['is_active'] else "🔴 PAUSED"
    risk_val = user.get('risk_pct', 1.5)
    stock_risk_val = user.get('stock_risk_pct', 2.0)
    syms = user.get('enabled_symbols', [])
    wallet_val = user.get('source_wallet')
    wallet_line = f"Source Wallet: `{wallet_val[:6]}...{wallet_val[-4:]}`\n" if wallet_val else "Source Wallet: Not Set (Use button below)\n"
    
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
        f"🪙 Crypto Risk: *{risk_val:.2f}%*\n"
        f"🦙 Stock Risk: *{stock_risk_val:.2f}%*\n"
        f"Capital Allocation: *{capital_display}*\n"
        f"Dollar PnL: *{privacy_status}*\n"
        f"{wallet_line}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(f"🪙 Crypto Risk % {'⚙️' if not is_premium else ''}", callback_data="set_crypto_risk"),
            InlineKeyboardButton(f"🦙 Stock Risk % {'⚙️' if not is_premium else ''}", callback_data="set_stock_risk")
        ],
        [InlineKeyboardButton(f"🛰 Symbols {'⚙️' if not is_premium else ''}", callback_data="manage_symbols")],
        [InlineKeyboardButton("💰 Capital Allocation", callback_data="capital_menu")],
        [InlineKeyboardButton("Privacy On 🔒" if user['hide_dollars'] else "Privacy Off 👁️", callback_data="toggle_privacy")],
        [
            InlineKeyboardButton("Change Strategy", callback_data="strategy_menu"),
            InlineKeyboardButton("🔬 Backtest", callback_data="run_backtest")
        ],
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
    crypto_connected = bool(user.get('exchange_id') and user.get('api_key') and user.get('api_secret'))
    alpaca_connected = bool(user.get('alpaca_api_key') and user.get('alpaca_api_secret'))
    has_exchange = crypto_connected or alpaca_connected
    
    has_active = user.get('has_open_positions', False)
    keyboard.extend(get_nav_buttons(has_active, is_admin, has_exchange))
    
    return msg, InlineKeyboardMarkup(keyboard)

async def safe_query_answer(query, *args, **kwargs):
    """Answers a callback query safely, swallowing timeout and invalid query errors."""
    try:
        await query.answer(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Swallowed callback query answer exception: {e}")
