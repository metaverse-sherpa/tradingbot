import os
import sys
import logging
import ccxt.async_support as ccxt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import database
from bot.config import SUPER_ADMIN_ID, logger
from bot.ui.keyboards import (
    get_nav_buttons,
    get_main_inline_menu,
    get_admin_keyboard
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # 🏔️ Sherpa Admin Alert: Notify on new member arrival
    is_new = database.get_user(chat_id) is None
    if is_new:
        try:
            full_name = update.effective_user.full_name
            username = f"@{update.effective_user.username}" if update.effective_user.username else "No Username"
            
            # Auto-initialize user in DB immediately
            database.upsert_user(chat_id, "", "", "", "blofin", is_active=False, full_name=full_name, username=username)
            
            import html
            safe_name = html.escape(str(full_name))
            
            if update.effective_user.username:
                username_clean = update.effective_user.username
                safe_username = html.escape(f"@{username_clean}")
                user_display = f"<a href=\"https://t.me/{username_clean}\">{safe_username}</a>"
            else:
                user_display = "No Username"
            
            ref_info = ""
            if context.args and context.args[0].startswith("ref_"):
                raw_ref = context.args[0].split('_')[1]
                ref_info = f" (Referrer: <code>{html.escape(raw_ref)}</code>)"
                
            admin_msg = (
                "🏔️ <b>New Sherpa Scout Spotted!</b>\n\n"
                f"Name: {safe_name}\n"
                f"User: {user_display}\n"
                f"ID: <code>{chat_id}</code>{ref_info}\n\n"
                "📈 <i>A new recruit has joined the trail. Awaiting setup...</i>"
            )
            try:
                await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=admin_msg, parse_mode="HTML")
            except Exception as html_err:
                logger.warning(f"HTML new user notification failed: {html_err}. Falling back to plain text.")
                plain_msg = (
                    "🏔️ New Sherpa Scout Spotted!\n\n"
                    f"Name: {full_name}\n"
                    f"User: {username}\n"
                    f"ID: {chat_id}\n\n"
                    "📈 A new recruit has joined the trail. Awaiting setup..."
                )
                await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=plain_msg)
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
    
    # --- 1. Handle Deep Linking ---
    if context.args:
        arg = context.args[0]
        if arg.startswith("gift_"):
            code = arg.split("_")[1]
            current_uname = update.effective_user.username
            success, msg = database.redeem_gift_code(chat_id, code, current_username=current_uname)
            await update.effective_message.reply_text(msg, parse_mode="Markdown")
            if success:
                # Refresh view
                await update.effective_message.reply_text(
                    "💎 *Premium access Activated!*\n\nYour dashboard has been upgraded.",
                    reply_markup=get_main_inline_menu(chat_id),
                    parse_mode="Markdown"
                )
                return
        elif arg.startswith("ref_"):
            try:
                referrer_id = int(arg.split("_")[1])
                if referrer_id != chat_id:
                    # Always ensure the recruit is initialized in DB first
                    full_name = update.effective_user.full_name
                    username = f"@{update.effective_user.username}" if update.effective_user.username else None
                    database.upsert_user(chat_id, "", "", "", "blofin", is_active=False, full_name=full_name, username=username)
                    
                    # Link
                    linked = database.set_referrer(chat_id, referrer_id)
                    
                    # Notify Referrer
                    try:
                        if linked:
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=f"🤝 *New Recruit!*\nSomeone just joined via your link. They must upgrade to Premium access to count towards your 3-referral bonus.",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        logger.error(f"Error sending referral notification: {e}")
            except Exception as e:
                logger.error(f"Error in deep-link processing: {e}")
        elif arg == "guide_blofin":
            pdf_path = os.path.join(BASE_DIR, "tutorials", "MetaverseSherpa Blofin API Setup.pdf")
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as doc:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=doc,
                        caption="🏔️ *Blofin API Setup Guide*\nRequested via deep-link. Follow these steps to link your account securely.",
                        parse_mode="Markdown"
                    )

    # --- 2. High-Authority Welcome Message ---
    # Check if they have an expired premium
    user = database.get_user(chat_id)
    expired_alert = ""
    if user and user.get('had_premium_before') and not database.is_premium(user):
        expired_alert = "⚠️ *Your Premium Access Has Expired*\nYour autopilot is currently paused. Please renew to resume live trading.\n\n"

    welcome_msg = (
        f"{expired_alert}"
        "🏔️ *Metaverse Sherpa Trading Bot*\n\n"
        "The elite automated trading solution for institutional-grade professionals. We now support automated trading of both **Crypto** (via **Blofin**, **Binance**, and **MEXC**) and **Stocks** (via **Alpaca**).\n\n"
        "🛡️ *Security & Control*\n"
        "Your exchange API credentials are **fully encrypted** and isolated. Only the Sherpa engine can see them to execute trades. You maintain full control: trades include automatic Stop Loss and Take Profit.\n\n"
        "📊 *Access Tiers*\n"
        "• **Standard (Always Free)**: Receive real-time free signal signals directly in your Telegram chat as the Sherpa scans the markets.\n"
        "• **Premium**: Full autopilot mode. The Sherpa connects directly to your exchange accounts to automatically execute and manage actual trades in real-time. **$20/mo**.\n\n"
        "📖 Tap /strategyguide to view different trading strategies.\n\n"
        "🏆 Tap /setup to link your account and start your climb."
    )
    
    await update.effective_message.reply_text(
        welcome_msg, 
        parse_mode="Markdown",
        reply_markup=get_main_inline_menu(chat_id)
    )

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    
    warning_text = ""
    if not user or not database.is_premium(user):
        warning_text = "⚠️ *Note:* You can configure your exchange settings now, but live auto-trading will only activate once you sign up for /premium.\n\n"

    keyboard = [
        [InlineKeyboardButton("🏔️ Blofin", callback_data="setex_blofin")],
        [InlineKeyboardButton("🔶 Binance", callback_data="setex_binance")],
        [InlineKeyboardButton("💠 MEXC", callback_data="setex_mexc")],
        [InlineKeyboardButton("🔷 Bitget", callback_data="setex_bitget")],
        [InlineKeyboardButton("🟦 BingX", callback_data="setex_bingx")],
        [InlineKeyboardButton("🦙 Alpaca Stocks", callback_data="setex_alpaca")],
        [InlineKeyboardButton("📖 Download Blofin Guide (PDF)", callback_data="send_blofin_guide")]
    ]
    
    await update.effective_message.reply_text(
        f"{warning_text}🌍 *Select Your Exchange*\n\n"
        "Which exchange would you like to link to the Metaverse Sherpa?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears all states and returns to the appropriate menu."""
    chat_id = update.effective_chat.id
    context.user_data.pop('setting_wallet', None)
    context.user_data.pop('setting_admin_wallet', None)
    context.user_data.pop('admin_broadcasting', None)
    context.user_data.pop('setting_risk', None)
    context.user_data.pop('setup_step', None)
    
    if chat_id == SUPER_ADMIN_ID:
        from bot.config import MASTER_USDT_WALLET
        master_wallet = database.get_config('master_usdt_wallet', MASTER_USDT_WALLET)
        footer = "\n\n───────────────────\n👑 *Sherpa Overlord Mission Control*"
        footer_kb = InlineKeyboardMarkup(get_admin_keyboard(master_wallet))
        await update.effective_message.reply_text(f"🛑 *Action Cancelled.*{footer}", parse_mode="Markdown", reply_markup=footer_kb)
    else:
        await update.effective_message.reply_text("🛑 *Action Cancelled.*", parse_mode="Markdown")

async def docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a brief tutorial of all bot commands and multi-exchange setup."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    is_admin = False
    if user:
        is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin', False))

    help_text = (
        "📖 *Metaverse Sherpa Bot - User Manual*\n\n"
        "Welcome! The Metaverse Sherpa is an institutional-grade, multi-exchange futures trading bot built for high-precision trade execution.\n\n"
        "📊 *Trading & Performance*\n"
        "• /stats - Your personal performance dashboard. Shows Win Rate, Profit Factor, Cumulative PnL, and Daily PnL.\n"
        "• /opentrades - Visual engine audit. Fetches live active positions with customized target/stop charts.\n"
        "• /list - Historical ledger. Lists your 10 most recent closed trades sync'd directly from the exchange.\n\n"
        "💰 *Account & Sizing Controls*\n"
        "• /balance - Live wallet audit. Checks available USDT margin, margin utilized, and total equity value.\n"
        "• /settings - Sizing controls. Customize **Capital Allocation** (trade using full balance, fixed $X amount, or X% balance isolation) and adjust risk tolerance tiers.\n"
        "• /setup - API Engine Room. Step-by-step wizard to connect/update exchange API keys.\n\n"
        "🎯 *Control & Strategy*\n"
        "• /strategy - Swapping brains. Instantly select your preferred active algorithmic model.\n"
        "• /strategyguide - Deep-dive. Displays sequential visual guides and comparison matrix with detailed neon infographics.\n"
        "• /stop - Emergency brake. Pauses the automated execution cycle for your account.\n"
        "• /resume - Re-enable. Resumes the high-speed trade heartbeat loop.\n\n"
        "🔌 *Multi-Exchange Setup Guides*\n"
        "🏔️ *Blofin*: Create API Key with **'Read'** & **'Trade'** permissions. Set a passphrase and keep it handy.\n"
        "🔶 *Binance*: Create API Key under API Management -> Enable Futures permissions -> Whitelist VPS IP for safety.\n"
        "💠 *MEXC*: Complete Primary KYC -> Create Key with Futures permissions -> Whitelist VPS IP to avoid 90-day expiry.\n"
        "🔷 *Bitget*: Create API Key -> Enable Futures Trading -> Set Passphrase -> Whitelist VPS IP.\n\n"
        "🤝 *Institutional Support*\n"
        "• /contact - Connect directly with @metaverse\\_sherpa or join our official community channel.\n\n"
        "⚠️ *Risk Disclaimer:* _Automated trading carries substantial risk of capital loss. The Metaverse Sherpa executes with professional-grade sizing (defaulting to 1.5% institutional risk per trade), but is **not financial advice**. Past backtest audits do not guarantee live market profits. Trade responsibly._"
    )
    keyboard = [
        [InlineKeyboardButton("📖 Strategy Guide & Differences", callback_data="view_strategy_guide")],
        [InlineKeyboardButton("📖 Download Blofin Setup Guide (PDF)", callback_data="send_blofin_guide")]
    ]
    keyboard.extend(get_nav_buttons(is_admin=is_admin))
    
    await update.effective_message.reply_text(
        help_text, 
        parse_mode="Markdown", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides contact info for the Sherpa."""
    chat_id = update.effective_chat.id
    msg = (
        "🏔️ *Contact the Sherpa*\n\n"
        "Have questions, feedback, or a new strategy idea? Reach out directly to the project lead:\n\n"
        "👤 *Lead:* @metaverse\\_sherpa\n"
        "📢 *Community:* [Join Here](https://t.me/+2pYhCm5BOoI0Mjkx)\n\n"
        "We are constantly refining the Metaverse Sherpa engine and value your input!"
    )
    await update.effective_message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_inline_menu(chat_id))

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    database.set_active(chat_id, False)
    await update.effective_message.reply_text("🔴 Trading is now paused for your account. The engine will skip you.", reply_markup=get_main_inline_menu(chat_id))

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    database.set_active(chat_id, True)
    await update.effective_message.reply_text("🟢 Trading is resumed! The engine will pick you up on the next cycle.", reply_markup=get_main_inline_menu(chat_id))

async def diagnose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    target = update.effective_message
        
    user_data = database.get_user(chat_id)
    if not user_data:
        await target.reply_text("❌ No user profile found. Please run /setup first.")
        return
        
    status_msg = await target.reply_text(
        "🔍 *Sherpa Live Diagnostic Engine Initiated...*\n"
        "Testing database status, strategy configs, and live exchange endpoints...",
        parse_mode="Markdown"
    )
    
    report_lines = [
        "📋 *Sherpa Live Diagnostics Report*",
        f"• Telegram ID: `{chat_id}`",
        f"• Bot Engine Status: `{'🟢 ACTIVE' if user_data.get('is_active') else '🔴 PAUSED'}`",
        f"• Undercover Mode: `{'🔒 ON' if user_data.get('undercover_mode') else '👁️ OFF'}`",
        ""
    ]
    
    # 1. Crypto Strategy Audit
    crypto_strat = user_data.get('active_crypto_strategy', 'Mean Reversion Scalper')
    has_crypto_creds = bool(user_data.get('api_key') and user_data.get('api_key') != "")
    report_lines.append("🪙 *Crypto Strategy Engine*")
    report_lines.append(f"• Strategy: `{crypto_strat}`")
    
    if has_crypto_creds:
        ex_id = user_data.get('exchange_id', 'blofin')
        report_lines.append(f"• Exchange: `{ex_id.upper()}`")
        report_lines.append("• Credentials: `✅ Configured`")
        report_lines.append("• Live Connection Check: _Testing..._")
        await status_msg.edit_text("\n".join(report_lines), parse_mode="Markdown")
        
        try:
            ex_class = getattr(ccxt, ex_id)
            async with ex_class({
                "apiKey": user_data['api_key'],
                "secret": user_data['api_secret'],
                "password": user_data['api_password'] or "",
                "options": {"defaultType": "swap"},
                "timeout": 8000
            }) as user_ex:
                acc_type = "swap" if ex_id in ['bitget', 'bingx'] else "futures"
                await user_ex.fetch_balance(params={"type": acc_type})
                report_lines[-1] = "• Live Connection Check: `✅ Connected Successfully`"
        except Exception as e:
            err_msg = str(e)
            if "152406" in err_msg or "whitelist" in err_msg.lower():
                report_lines[-1] = (
                    "• Live Connection Check: `❌ BLOCKED BY EXCHANGE`\n"
                    "  ⚠️ *Error*: IP Whitelist Mismatch!\n"
                    "  _Your API key has a whitelist enabled, and our server IP is not in it._"
                )
            else:
                clean_err = err_msg.replace("`", "").replace("*", "").replace("_", "")
                report_lines[-1] = f"• Live Connection Check: `❌ Failed`\n  ⚠️ *Error*: `{clean_err}`"
    else:
        report_lines.append("• Credentials: `❌ Not Connected` (Crypto trading disabled)")
        
    await status_msg.edit_text("\n".join(report_lines), parse_mode="Markdown")
        
    # 2. Stock Strategy Audit
    stock_strat = user_data.get('active_stock_strategy', 'None')
    has_stock_creds = bool(user_data.get('alpaca_api_key') and user_data.get('alpaca_api_key') != "")
    
    report_lines.append("")
    report_lines.append("🦙 *Stock Strategy Engine*")
    report_lines.append(f"• Strategy: `{stock_strat}`")
    
    if has_stock_creds:
        report_lines.append("• Exchange: `ALPACA`")
        report_lines.append("• Credentials: `✅ Configured`")
        report_lines.append("• Live Connection Check: _Testing..._")
        await status_msg.edit_text("\n".join(report_lines), parse_mode="Markdown")
        
        try:
            account = await database.make_alpaca_request_async(user_data, "GET", "/v2/account")
            report_lines[-1] = "• Live Connection Check: `✅ Connected Successfully`"
        except Exception as e:
            clean_err = str(e).replace("`", "").replace("*", "").replace("_", "")
            report_lines[-1] = f"• Live Connection Check: `❌ Failed`\n  ⚠️ *Error*: `{clean_err}`"
    else:
        report_lines.append("• Credentials: `❌ Not Connected` (Stock trading disabled)")
        
    await status_msg.edit_text("\n".join(report_lines), parse_mode="Markdown")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a Telegram message to the Super Admin."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Send trace to Super Admin
    import traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    
    err_msg = (
        f"🚨 *HANDLER CRASH*\n\n"
        f"Update: `{update}`\n\n"
        f"*Error:* `{context.error}`\n\n"
        f"*Traceback:*\n```\n{tb_string[:3500]}\n```"
    )
    try:
        await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=err_msg, parse_mode="Markdown")
    except Exception as markdown_err:
        try:
            plain_err_msg = (
                f"🚨 HANDLER CRASH (Plain Text Fallback)\n\n"
                f"Update: {update}\n\n"
                f"Error: {context.error}\n\n"
                f"Traceback:\n{tb_string[:3500]}"
            )
            await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=plain_err_msg)
        except Exception as fallback_err:
            logger.error(f"Failed to send plain crash report to super admin: {fallback_err}")
