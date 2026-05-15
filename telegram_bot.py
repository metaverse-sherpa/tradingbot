import os
import logging
import asyncio
import ccxt
import pandas as pd
import live_bot_multi
import media_gen
import json
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest
import database
import charting
import time
import sys

# Add scripts directory to path for imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "scripts"))
from audit_3yr_portfolio import run_custom_audit
from sherpa_visual_audit import run_visual_audit

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = 1567788633  # Metaverse Sherpa Lead

def get_master_wallet():
    """Retrieves the master wallet from database config."""
    return database.get_config('master_usdt_wallet', "TUhiPWBbrJKV7cyrnSawZ7JUdLN8Qcg6u3")

# --- Institutional Revenue Constants ---
MASTER_USDT_WALLET = "TUhiPWBbrJKV7cyrnSawZ7JUdLN8Qcg6u3"

# Setup Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Silence chatty libraries to save disk space on VPS
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("ccxt.blofin").setLevel(logging.WARNING)

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
        # 🕵️ Attempt sleak inline update
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

async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggers the personalized visual 3-year audit for the user."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
    
    # Get current balance for projection
    balance = user.get('equity', 10000.0)
    if balance < 100: balance = 10000.0 # Default to 10k for new users
        
    await trigger_personalized_audit(update, context, user, start_balance=balance)

async def send_master_audit(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id):
    """Sends the institutional-grade 3-year master audit comparison instantly."""
    master_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "upsell_comparison.png")
    audit_msg = (
        "🏔️ *Metaverse Sherpa: Institutional Wealth Gap*\n"
        "Comparison: `Standard (1% Risk)` vs `Institutional (Premium)`\n\n"
        "📊 *Standard Tier (Always Free)*\n"
        "• PnL: *+64.5%* | Sharpe: *5.40*\n"
        "• Assets: 5 Core Institutional Tokens\n\n"
        "💎 *Institutional Tier (Premium Access)*\n"
        "• PnL: *+1,514.9%* | Sharpe: *4.83*\n"
        "• Assets: Full 20+ 'Sherpa Basket' Tokens\n\n"
        "📈 _Institutional access delivers a **23x profit multiplier** by unlocking the full 20-token basket and taking advantage of **Advanced Dynamic Compounding**._"
    )
    
    if os.path.exists(master_path):
        with open(master_path, 'rb') as photo:
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=photo, 
                caption=audit_msg, 
                parse_mode="Markdown",
                reply_markup=get_main_inline_menu(chat_id)
            )
    else:
        await context.bot.send_message(chat_id=chat_id, text=audit_msg, parse_mode="Markdown")

async def trigger_personalized_audit(update: Update, context: ContextTypes.DEFAULT_TYPE, user, start_balance=10000.0):
    """Runs a 3-year backtest for a specific user's risk and symbols with animation."""
    chat_id = user['telegram_chat_id']
    risk = user['risk_pct']
    syms = user['enabled_symbols']
    def_syms = ["BTC","ETH","SOL","DOGE","ADA","LINK","DOT","TON","ZEC","PEPE","BNB","NEAR","SUI","NOT","TAO","ONDO","ENA","FET","WIF"]
    # 🏔️ Master Cache Logic
    is_default = (risk == 1.5 and len(syms) >= 18 and start_balance == 10000.0)
    
    if not is_default:
        # 💎 Premium Gate with Killer Comparison Visual
        if not database.is_premium(user):
            upsell_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "upsell_comparison.png")
            premium_msg = (
                "🔒 *Premium Feature: Personal Projections*\n\n"
                "The chart above reveals the *Institutional Wealth Gap*.\n\n"
                "📊 *Free Tier (White)*: +64.5% PnL\n"
                "💎 *Premium Tier (Neon)*: +1,514.9% PnL\n\n"
                "Unlock **23x more profit potential** for just **$20/mo**.\n"
                "Institutional access unlocks full compounding power and the complete 'Sherpa Basket'.\n\n"
                "Refer 3 friends or subscribe to unlock!"
            )
            
            if os.path.exists(upsell_path):
                with open(upsell_path, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=chat_id, 
                        photo=photo, 
                        caption=premium_msg, 
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🤝 Refer 3 & Get 30 Days Free", callback_data="referral_menu")],
                            [InlineKeyboardButton("💎 Go Premium", callback_data="go_premium")]
                        ])
                    )
            else:
                await context.bot.send_message(chat_id=chat_id, text=premium_msg, parse_mode="Markdown")
            return
    master_path = os.path.join(BASE_DIR, "results", "master_audit.png")
    
    if is_default and os.path.exists(master_path):
        # Serve Master Audit Instantly
        audit_msg = (
            "🏔️ *Metaverse Sherpa: Institutional 3-Year Audit*\n"
            "Settings: `1.5% Risk` | `All Institutional Tokens`\n\n"
            "Final Equity: *$161,486.23*\n"
            "Total PnL: *+1,514.9%*\n"
            "Sharpe Ratio: *4.83*\n"
            "Win Rate: *61.2%*\n"
            "Max Drawdown: *18.8%*\n\n"
            "📈 _This simulation represents the core Sherpa algorithm's performance over the last 3 years._"
        )
        with open(master_path, 'rb') as photo:
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=photo, 
                caption=audit_msg, 
                parse_mode="Markdown",
                reply_markup=get_main_inline_menu(chat_id)
            )
        return

    # 🏔️ Custom Animation Frames
    frames = [
        "🥾 *Sherpa is packing the gear...*",
        "🧗‍♂️ *Climbing the 2024 candles...*",
        "🧗‍♂️ *Navigating the 2025 volatility...*",
        "🏔️ *Reaching the peak...*",
        "🛰️ *Syncing your private results...*"
    ]
    
    status_msg = await context.bot.send_message(
        chat_id=chat_id, 
        text=f"{frames[0]}\n\nProjecting your capital: `${start_balance:,.0f}`",
        parse_mode="Markdown"
    )
    
    # Start the visual audit
    # If it's a default run but we're missing the master chart, run it as 'admin' to save it
    sim_user_id = "admin" if is_default else chat_id
    audit_task = asyncio.create_task(asyncio.to_thread(run_visual_audit, risk, syms, user_id=sim_user_id, start_balance=start_balance))
    
    idx = 1
    while not audit_task.done():
        await asyncio.sleep(1.5)
        if idx < len(frames):
            try: await status_msg.edit_text(f"{frames[idx]}\n\nProjecting your capital: `${start_balance:,.0f}`", parse_mode="Markdown"); idx += 1
            except: pass
            
    try:
        stats, chart_path, df_eq = await audit_task
        if not stats or not chart_path:
            await status_msg.edit_text("❌ Personal audit failed. Check your settings."); return

        # 🏔️ Institutional Delta Engine: Compare with Last Audit
        last_stats = None
        if user.get('last_audit_stats'):
            try: last_stats = json.loads(user['last_audit_stats'])
            except: pass
            
        def get_delta(current, last, is_pct=True, is_dd=False, is_dollar=False):
            if not last: return ""
            diff = current - last
            if abs(diff) < 0.001: return " (—)"
            
            trend_icon = "⬆️" if diff > 0 else "⬇️"
            sign = "+" if diff > 0 else "-"
            val = abs(diff)
            
            if is_dollar:
                return f" ({trend_icon} {sign}${val:,.0f})"
            elif is_pct:
                return f" ({trend_icon} {sign}{val:.1f}%)"
            else:
                return f" ({trend_icon} {sign}{val:.2f})"

        pnl_delta = get_delta(stats['pnl_pct'], last_stats.get('pnl_pct')) if last_stats else ""
        win_delta = get_delta(stats['win_rate'], last_stats.get('win_rate')) if last_stats else ""
        dd_delta = get_delta(stats['max_dd'], last_stats.get('max_dd'), is_dd=True) if last_stats else ""
        equity_delta = get_delta(stats['final_equity'], last_stats.get('final_equity'), is_pct=False, is_dollar=True) if last_stats else ""
        sharpe_delta = get_delta(stats['sharpe'], last_stats.get('sharpe'), is_pct=False) if last_stats else ""

        audit_msg = (
            f"🏔️ *Your Personalized 3-Year Audit*\n"
            f"Start Balance: `${start_balance:,.0f}` | Risk: `{risk:.2f}%`\n\n"
            f"Final Equity: *${stats['final_equity']:,.2f}*{equity_delta}\n"
            f"Total PnL: *{stats['pnl_pct']:+.1f}%*{pnl_delta}\n"
            f"Sharpe Ratio: *{stats['sharpe']:.2f}*{sharpe_delta}\n"
            f"Win Rate: *{stats['win_rate']:.1f}%*{win_delta}\n"
            f"Max Drawdown: *{stats['max_dd']:.1f}%*{dd_delta}\n\n"
            "📈 _This simulation represents your settings applied over the last 3 years._"
        )
        
        # 💎 Institutional Memory: Update Last Audit Cache
        database.update_last_audit(chat_id, stats)
        
        await status_msg.delete()
        if os.path.exists(chart_path):
            with open(chart_path, 'rb') as photo:
                await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=audit_msg, parse_mode="Markdown", reply_markup=get_main_inline_menu(chat_id))
            if not is_default: os.remove(chart_path)
        else:
            await context.bot.send_message(chat_id=chat_id, text=audit_msg, parse_mode="Markdown", reply_markup=get_main_inline_menu(chat_id))
            
    except Exception as e:
        logger.error(f"Personal audit error: {e}")
        await status_msg.edit_text(f"❌ Error during simulation: {e}")
        
def get_nav_buttons(has_active_trades=False, is_admin=False):
    """Returns a standardized grid of inline navigation buttons, dynamically adding Panic Exit if trades are open."""
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
        kb.append([InlineKeyboardButton("🚨 PANIC EXIT (ALL)", callback_data="confirm_panic")])
    return kb

def get_main_inline_menu(chat_id=None):
    has_active = False
    is_admin = False
    if chat_id:
        user = database.get_user(chat_id)
        if user:
            has_active = user.get('has_open_positions', False)
            is_admin = (chat_id == ADMIN_CHAT_ID and not user.get('undercover_mode'))
    return InlineKeyboardMarkup(get_nav_buttons(has_active, is_admin))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bot_username = (await context.bot.get_me()).username
    
    # 🏔️ Sherpa Admin Alert: Notify on new member arrival
    is_new = database.get_user(chat_id) is None
    if is_new:
        try:
            full_name = update.effective_user.full_name
            username = f"@{update.effective_user.username}" if update.effective_user.username else "No Username"
            ref_info = f" (Referrer: `{context.args[0].split('_')[1]}`)" if context.args and context.args[0].startswith("ref_") else ""
            
            admin_msg = (
                "🏔️ *New Sherpa Scout Spotted!*\n\n"
                f"Name: `{full_name}`\n"
                f"User: {username}\n"
                f"ID: `{chat_id}`{ref_info}\n\n"
                "📈 _A new recruit has joined the trail. Awaiting setup..._"
            )
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown")
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
                    "💎 *Institutional Access Activated!*\n\nYour dashboard has been upgraded.",
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
                    
                    # Link and check for bonus
                    reward_granted = database.set_referrer(chat_id, referrer_id)
                    
                    # Notify Referrer
                    try:
                        if reward_granted:
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=(
                                    "🎉 *INSTITUTIONAL MILESTONE REACHED!*\n\n"
                                    "You've successfully recruited 3 new members to the trail. Your **Premium Institutional Access** has been activated for 30 days!\n\n"
                                    "🏔️ _The Sherpa honors your leadership._"
                                ),
                                parse_mode="Markdown"
                            )
                        else:
                            stats = database.get_referral_stats(referrer_id)
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=f"🤝 *New Institutional Recruit!*\nSomeone just joined via your link. Progress: *{stats % 3}/3* toward your next Premium month!",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        logger.error(f"Error sending referral notification: {e}")
            except Exception as e:
                logger.error(f"Error in deep-link processing: {e}")

    # --- 2. Deliver the Mission Briefing (PDF Guide) Instantly ---
    pdf_path = os.path.join(BASE_DIR, "tutorials", "MetaverseSherpa Blofin API Setup.pdf")
    if os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as doc:
            await context.bot.send_document(
                chat_id=chat_id,
                document=doc,
                caption="🏔️ *Welcome Scout!*\nAttached is your official **Blofin API Setup Guide**. Tap it to download and follow the instructions to link your account.",
                parse_mode="Markdown"
            )

    # --- 3. High-Authority Welcome Message ---
    welcome_msg = (
        "🏔️ *Metaverse Sherpa Trading Bot*\n\n"
        "The elite automated trading solution for institutional-grade professionals. We currently support **Blofin**, **Binance**, and **MEXC**.\n\n"
        "🛡️ *Security & Control*\n"
        "Your exchange API credentials are **fully encrypted** and isolated. Only the Sherpa engine can see them to execute trades. You maintain full control: trades include automatic Stop Loss and Take Profit.\n\n"
        "📊 *Access Tiers*\n"
        "• **Standard (Free)**: 5 core tokens | 1% risk.\n"
        "• **Institutional (Premium)**: 20+ tokens | Custom risk. **$20/mo**.\n\n"
        "🏆 Tap /setup to link your account and start your climb."
    )
    
    await update.effective_message.reply_text(welcome_msg, parse_mode="Markdown")

    # 4. Institutional Master Audit (Strictly Static Hook)
    await send_master_audit(update, context, chat_id)

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    keyboard = [
        [InlineKeyboardButton("🏔️ Blofin", callback_data="setex_blofin")],
        [InlineKeyboardButton("🔶 Binance", callback_data="setex_binance")],
        [InlineKeyboardButton("💠 MEXC", callback_data="setex_mexc")],
        [InlineKeyboardButton("📖 Download Blofin Guide (PDF)", callback_data="send_blofin_guide")]
    ]
    
    await update.effective_message.reply_text(
        "🌍 *Select Your Exchange*\n\n"
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
    
    if chat_id == ADMIN_CHAT_ID:
        footer = "\n\n───────────────────\n👑 *Sherpa Overlord Mission Control*"
        footer_kb = InlineKeyboardMarkup(get_admin_keyboard(get_master_wallet()))
        await update.effective_message.reply_text(f"🛑 *Action Cancelled.*{footer}", parse_mode="Markdown", reply_markup=footer_kb)
    else:
        await update.effective_message.reply_text("🛑 *Action Cancelled.*", parse_mode="Markdown")
        await update.effective_message.reply_text(
            "🛰️ *Main Menu Activated*",
            reply_markup=get_main_inline_menu(chat_id),
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.effective_message.text.strip()
    
    # --- 1. Handle Institutional Wallet Setup ---
    if context.user_data.get('setting_wallet'):
        # Basic TRON (TRC-20) Validation: Starts with T, length 34
        if text.startswith('T') and len(text) == 34:
            database.update_user_wallet(chat_id, text)
            context.user_data['setting_wallet'] = False
            
            # Descriptive Onboarding Step
            await update.effective_message.reply_text(
                "✅ *Institutional Wallet Linked & Verified!*\n\n"
                "Your identity is now synchronized with the institutional audit engine. You are now ready to cross the **23x Wealth Gap**.\n\n"
                "🏔️ *The Path to Institutional Access:*\n"
                "1️⃣ **Transfer $20 USDT** via the TRON (TRC-20) network to the Master Treasury.\n"
                "2️⃣ **Blockchain Audit**: The Sherpa's engine will automatically detect your transfer from your linked wallet.\n"
                "3️⃣ **Full Unlock**: Your account will instantly gain access to the complete 'Sherpa Basket' and professional risk controls.\n\n"
                "Tap below to view the Treasury Address and finalize your upgrade.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💎 Finalize Institutional Upgrade", callback_data="premium_menu")
                ]])
            )
            return
        else:
            await update.effective_message.reply_text(
                "❌ *Invalid TRC-20 Address*\n\n"
                "Institutional USDT (TRC-20) addresses must start with 'T' and be 34 characters long.\n"
                "Please check your address and try again.",
                parse_mode="Markdown"
            )
            return

    # --- 2. Handle Admin Master Wallet Setup ---
    if context.user_data.get('setting_admin_wallet') and chat_id == ADMIN_CHAT_ID:
        if text.startswith('T') and len(text) == 34:
            database.update_config('master_usdt_wallet', text)
            context.user_data['setting_admin_wallet'] = False
            await update.effective_message.reply_text(
                f"👑 *Overlord: Treasury Updated!*\n\n"
                f"New Master Wallet: `{text}`\n\n"
                "All institutional upgrades will now be directed to this address.",
                parse_mode="Markdown"
            )
            await show_admin_dashboard(update, context)
            return
        else:
            await update.effective_message.reply_text("❌ Invalid TRC-20 address for Treasury. Must start with 'T' and be 34 chars.")
            return

    step = context.user_data.get('setup_step', 0)
    
    if step == 1:
        context.user_data['api_key'] = text
        context.user_data['setup_step'] = 2
        # Delete user's message so their key isn't sitting in chat history
        try: await update.effective_message.delete()
        except: pass
        await update.effective_message.reply_text("✅ Key received and wiped from chat history.\n\nNow, please paste your **API Secret**:")
        
    elif step == 2:
        context.user_data['api_secret'] = text
        context.user_data['setup_step'] = 3
        try: await update.effective_message.delete()
        except: pass
        await update.effective_message.reply_text("✅ Secret received and wiped.\n\nFinally, please provide your **API Password / Passphrase**:")
        
    elif step == 3:
        context.user_data['api_pass'] = text
        context.user_data['api_password'] = text
        try: await update.effective_message.delete()
        except: pass
        
        # Save to DB and Activate
        database.upsert_user(
            chat_id, 
            context.user_data['api_key'],
            context.user_data['api_secret'],
            context.user_data['api_password'],
            exchange_id=context.user_data.get('exchange_id', 'blofin'),
            equity=0.0,
            is_active=True
        )
        
        # 💎 Stage 2 Admin Alert: Institutional Activation
        try:
            user_info = update.effective_user
            full_name = user_info.full_name
            username = f"@{user_info.username}" if user_info.username else "No Username"
            act_msg = (
                "💎 *Institutional Access Activated!*\n\n"
                f"User: `{full_name}` ({username})\n"
                f"ID: `{chat_id}`\n\n"
                "🚀 _Member has configured API and is now LIVE in the engine._"
            )
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=act_msg, parse_mode="Markdown")
        except: pass
        
        context.user_data.clear()
        keyboard = [[InlineKeyboardButton("💰 Check My Balance", callback_data="check_balance_setup")]]
        await update.effective_message.reply_text(
            "🎊 *Setup Complete!*\n\n"
            "The Sherpa is now tracking your account. Trading will begin on the next engine cycle.\n\n"
            "Tap the button below to verify your connection and check your trading funds.", 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        # Also send the persistent footer dashboard
        await update.effective_message.reply_text(
            "🛰️ *Main Menu Activated*",
            reply_markup=get_main_inline_menu(chat_id),
            parse_mode="Markdown"
        )
        return

    elif context.user_data.get('setting_risk'):
        try:
            val = float(text.replace("%", ""))
            if 0.01 <= val <= 100.0:
                database.update_user_preference(chat_id, "risk_pct", val)
                context.user_data.pop('setting_risk', None)
                await update.effective_message.reply_text(f"✅ Risk updated to *{val:.2f}%*", parse_mode="Markdown")
                # Trigger Audit
                user = database.get_user(chat_id)
                user_equity = user.get('equity', 10000.0)
                asyncio.create_task(trigger_personalized_audit(update, context, user, start_balance=user_equity))
                # Show settings again
                msg, reply_markup = get_settings_ui(user)
                await update.effective_message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await update.effective_message.reply_text("❌ Please enter a value between 0.01 and 100.")
        except:
            await update.effective_message.reply_text("❌ Invalid number. Please enter a value like `1.5`.")
    elif context.user_data.get('admin_gifting'):
        context.user_data.pop('admin_gifting', None)
        try:
            target_input = text
            target_id = None
            target_username = None
            is_universal = False
            
            # Resolve username if provided
            if target_input.startswith('@') or not target_input.isdigit():
                target_id = database.get_chat_id_by_username(target_input)
                if not target_id:
                    target_username = target_input.lstrip('@')
                    is_universal = False # It's NOT universal anymore, it's tied to a name!
            else:
                target_id = int(target_input)

            code = database.create_gift_code(target_id, target_username)
            bot_username = (await context.bot.get_me()).username
            
            # 🏔️ Sherpa Escaping: Definitive MarkdownV2 character handling
            from telegram.helpers import escape_markdown
            if target_id:
                display_target = str(target_id)
            elif target_username:
                display_target = f"@{target_username} (Reserved)"
            else:
                display_target = "ANY (Universal)"
                
            safe_id = escape_markdown(display_target, version=2)
            safe_code = escape_markdown(code, version=2)
            gift_url = f"https://t.me/{bot_username}?start=gift_{code}"
            
            # Escape EVERYTHING for the Admin message
            header_txt = "🎁 Reserved Gift Generated" if target_username else "🎁 Targeted Gift Generated"
            safe_header = escape_markdown(header_txt, version=2)
            desc_txt = f"Forward this link to @{target_username} (Identity locked):" if target_username else "Forward this link (or wait for auto-notify):"
            safe_desc = escape_markdown(desc_txt, version=2)
            safe_url = escape_markdown(gift_url, version=2)
            
            msg = (
                f"{safe_header}\n\n"
                f"Target: `{safe_id}`\n"
                f"Gift Code: `{safe_code}`\n\n"
                f"{safe_desc}\n"
                f"`{safe_url}`"
            )
            
            if target_username and not target_id:
                msg += escape_markdown("\n\n⚠️ Note: This user is not in the DB yet, but this link is LOCKED to their username. Only they can redeem it.", version=2)
            
            await update.message.reply_text(msg, parse_mode="MarkdownV2")

            # 🎁 Direct Notification (Only if already in DB)
            if target_id:
                try:
                    from telegram.helpers import escape_markdown
                    # Escape all text components for MarkdownV2
                    safe_gift_header = escape_markdown("🎁 Institutional Gift Received!", version=2)
                    safe_gift_desc1 = escape_markdown("The Sherpa Overlord has granted you 30 Days of Premium Institutional Access.", version=2)
                    safe_gift_desc2 = escape_markdown("Tap the link below to activate your account and unlock the full Sherpa Basket:", version=2)
                    safe_gift_url = escape_markdown(gift_url, version=2)

                    user_msg = (
                        f"*{safe_gift_header}*\n\n"
                        f"{safe_gift_desc1}\n\n"
                        f"{safe_gift_desc2}\n\n"
                        f"{safe_gift_url}"
                    )
                    await context.bot.send_message(chat_id=target_id, text=user_msg, parse_mode="MarkdownV2")
                    await update.message.reply_text(f"✅ User `{target_id}` has been notified directly.")
                except Exception as notify_err:
                    await update.message.reply_text(f"⚠️ Gift generated, but could not notify user directly: {notify_err}")

        except ValueError:
            await update.message.reply_text("❌ Invalid Input. Please enter a numerical ID or @username.")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to generate gift: {e}")
        
        await show_admin_dashboard(update, context)
        return

    elif context.user_data.get('admin_broadcasting'):
        context.user_data.pop('admin_broadcasting', None)
        text = update.message.text
        users = database.get_all_users()
        count = 0
        for u in users:
            target_id = u['telegram_chat_id']
            try:
                await context.bot.send_message(chat_id=target_id, text=text, parse_mode="Markdown")
                count += 1
            except Exception as e:
                logger.warning(f"Failed broadcast to {target_id}: {e}")
        footer = "\n\n───────────────────\n👑 *Sherpa Overlord Mission Control*"
        footer_kb = InlineKeyboardMarkup(get_admin_keyboard(get_master_wallet()))
        await update.message.reply_text(f"📢 Broadcast sent to {count} users.{footer}", parse_mode="Markdown", reply_markup=footer_kb)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
    
    await update.effective_message.reply_text("📊 Calculating your performance stats...")

    # Calculate Daily PnL from Exchange (Realized + Unrealized)
    realized_daily_pnl = 0.0
    total_unrealized_pnl = 0.0
    open_positions_count = 0
    import ccxt
    import time
    import live_bot_multi
    
    try:
        user_ex = ccxt.blofin({
            "apiKey": user['api_key'],
            "secret": user['api_secret'],
            "password": user['api_password'],
            "options": {"defaultType": "swap"},
        })
        
        now_ms = int(time.time() * 1000)
        twenty_four_hours_ago = now_ms - (24 * 60 * 60 * 1000)
        
        # 1. Get Realized PnL for last 24h
        for sym in live_bot_multi.SYMBOLS:
            try:
                trades = user_ex.fetch_my_trades(sym, since=twenty_four_hours_ago)
                for t in trades:
                    info = t.get("info", {})
                    gross_pnl = float(info.get("fillPnl") or 0)
                    if gross_pnl != 0:
                        fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                        net_pnl = gross_pnl - (fee * 2)
                        realized_daily_pnl += net_pnl
            except: pass
            
        # 2. Get Total Unrealized PnL from positions
        try:
            positions = user_ex.fetch_positions(live_bot_multi.SYMBOLS)
            for p in positions:
                contracts = float(p.get("contracts", 0) or 0)
                if contracts != 0:
                    open_positions_count += 1
                    total_unrealized_pnl += float(p.get("unrealizedPnl", 0) or 0)
        except: pass
            
    except Exception as e:
        logger.error(f"PnL calculation failed: {e}")

    wins = user['wins']
    losses = user['losses']
    cum_pnl_realized = user.get('cum_pnl', 0.0)
    equity = user.get('equity', 200.0)
    
    # Combined Totals
    overall_pnl_usdt = cum_pnl_realized + total_unrealized_pnl
    daily_pnl_usdt = realized_daily_pnl + total_unrealized_pnl
    
    total_closed = wins + losses
    wr = (wins / total_closed * 100) if total_closed > 0 else 0
    overall_pnl_pct = (overall_pnl_usdt / equity) * 100 if equity > 0 else 0
    daily_pnl_pct = (daily_pnl_usdt / equity) * 100 if equity > 0 else 0
    upnl_pct = (total_unrealized_pnl / equity) * 100 if equity > 0 else 0
    
    hide = user.get('hide_dollars', False)
    pnl_suffix = f" (${overall_pnl_usdt:+.2f})" if not hide else ""
    daily_suffix = f" (${daily_pnl_usdt:+.2f})" if not hide else ""
    
    msg = f"📊 *Your Trading Performance*\n"
    msg += "_(Includes Open Positions PnL)_\n\n"
    msg += f"Overall PnL: *{overall_pnl_pct:+.2f}%{pnl_suffix}*\n"
    msg += f"Daily PnL: *{daily_pnl_pct:+.2f}%{daily_suffix}*\n"
    flame = " 🔥" if wr > 50 else ""
    msg += f"Win Rate: *{wr:.1f}%{flame} ({wins} wins | {losses} losses)*\n\n"
    msg += f"Status: {'🟢 Active' if user['is_active'] else '🔴 Paused'}\n"
    msg += f"Open Positions: *{open_positions_count} ({upnl_pct:+.2f}%)*\n"
    msg += f"Closed Trades: *{total_closed}*\n"
    
    # Add Share Stats button
    is_admin = (chat_id == ADMIN_CHAT_ID and not user.get('undercover_mode'))
    cb_data = f"shs_{overall_pnl_pct:.2f}_{daily_pnl_pct:.2f}_{wr:.1f}_{total_closed}"
    keyboard = [
        [InlineKeyboardButton("📸 Share & Earn", callback_data=cb_data)],
        *get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin)
    ]
    
    await update.effective_message.reply_text(
        msg, 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode="Markdown"
    )

async def list_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
        
    # 🏔️ Sherpa Cache: Check for instant local results first
    if user.get('history_cache'):
        try:
            import json
            last_10 = json.loads(user['history_cache'])
            await render_history_dashboard(update, context, last_10, chat_id, user)
            return
        except: pass

    status_msg = await update.effective_message.reply_text("🔄 Fetching your recent trades directly from the exchange...")
    
    try:
        user_ex = database.get_exchange_client(user)
        user_ex.load_markets()
        
        import live_bot_multi
        all_closed = []
        # We check the last 100 trades to ensure we find enough realized PnL events
        for sym in live_bot_multi.SYMBOLS:
            try:
                norm_sym = database.normalize_symbol(sym, user_ex.id)
                trades = user_ex.fetch_my_trades(norm_sym, limit=50)
                for t in trades:
                    info = t.get("info", {})
                    gross_pnl = 0
                    if user_ex.id == 'blofin':
                        gross_pnl = float(info.get("fillPnl") or 0)
                    else:
                        gross_pnl = float(info.get("realizedPnl") or 0)
                        
                    if gross_pnl != 0:
                        fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                        net_pnl = gross_pnl - (fee * 2)
                        
                        side_raw = t.get('side', 'buy').lower()
                        is_long = (side_raw == 'sell')
                        
                        # Calculate ROE
                        try:
                            market = user_ex.market(sym)
                            contract_size = float(market.get('contractSize', 1))
                            initial_margin = (t['price'] * t['amount'] * contract_size) / 20
                            roe_val = (net_pnl / initial_margin) * 100 if initial_margin > 0 else 0
                        except: roe_val = 0

                        all_closed.append({
                            "symbol": sym,
                            "timestamp": t['timestamp'],
                            "net_pnl": net_pnl,
                            "price": t['price'],
                            "amount": t['amount'],
                            "side": "l" if is_long else "s",
                            "roe_val": roe_val
                        })
            except: pass
                 
        all_closed.sort(key=lambda x: x['timestamp'], reverse=True)
        last_10 = all_closed[:10]
        
        if not last_10:
            await status_msg.edit_text("No recently closed trades found in your account.")
            return
            
        # Lock into Sherpa Cache
        database.set_history_cache(chat_id, last_10)
        
        await status_msg.delete()
        await render_history_dashboard(update, context, last_10, chat_id, user)
            
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        await update.effective_message.reply_text(f"❌ Error fetching trade history: {e}")

async def render_history_dashboard(update, context, last_10, chat_id, user):
    """Renders the final sexy history message from trade data."""
    history_text = "📜 *Metaverse Sherpa History*\n\n"
    buttons = []
    
    for i, t in enumerate(last_10):
        import datetime
        dt_raw = datetime.datetime.fromtimestamp(t['timestamp']/1000).strftime('%m-%d %H:%M')
        dt = escape_md_v2(dt_raw)
        
        sym_v2 = escape_md_v2(t['symbol'].split("/")[0])
        dir_icon = "📈" if t['side'] == "l" else "📉"
        roe_v2 = escape_md_v2(f"{t['roe_val']:+.1f}%")
        pnl_val_v2 = escape_md_v2(f"${t['net_pnl']:+.2f}")
        status_icon = "🏆" if t['net_pnl'] > 0 else "❌"
        
        history_text += (
            f"{i+1}\. *{sym_v2}* {dir_icon} \| _{dt}_\n"
            f"{status_icon} PnL: ||{pnl_val_v2}|| \(*{roe_v2}*\)\n"
            f"\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\n"
        )
        
        win_icon = " 🏆" if t['net_pnl'] > 0 else ""
        cb_data = f"shc_{t['symbol']}_{t['side']}_{t['roe_val']:.2f}_{t['price']:.4f}_{t['price']:.4f}_{t['net_pnl']:.2f}"
        buttons.append(InlineKeyboardButton(f"{i+1}-{sym_v2}{win_icon}", callback_data=cb_data))
        
    history_text += "\n*Tap a button below to Share & Earn 📸*"
    
    is_admin = (chat_id == ADMIN_CHAT_ID and not user.get('undercover_mode'))
    grid = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    grid.append([InlineKeyboardButton(" ", callback_data="none")])
    grid.extend(get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin))
    
    await update.effective_message.reply_text(
        history_text, 
        reply_markup=InlineKeyboardMarkup(grid),
        parse_mode="MarkdownV2"
    )

async def open_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
        
    await update.effective_message.reply_text("🔍 Checking your active trades on the exchange...")
    
    try:
        user_ex = database.get_exchange_client(user)
        user_ex.load_markets()
        
        import live_bot_multi
        import charting
        import os
        
        # Normalize all symbols for this exchange
        norm_syms = [database.normalize_symbol(s, user_ex.id) for s in live_bot_multi.SYMBOLS]
        positions = user_ex.fetch_positions(norm_syms)
        active = [p for p in positions if float(p.get("contracts", 0) or 0) != 0]
        
        if not active:
            await update.effective_message.reply_text("You have no active trades at the moment.", reply_markup=get_main_inline_menu(chat_id))
            return
            
        await update.effective_message.reply_text(
            f"🛰 *Active Trades Found: {len(active)}*\nGenerating charts...",
            reply_markup=get_main_inline_menu(chat_id),
            parse_mode="Markdown"
        )

        for p in active:
            sym = p['symbol']
            side = p['side'].upper()
            entry = float(p['entryPrice'] or 0)
            mark_price = float(p.get('markPrice') or 0)
            upnl = float(p['unrealizedPnl'] or 0)
            
            # 1. Calculate Current ROE
            try:
                market = user_ex.market(sym)
                contract_size = float(market.get('contractSize', 1))
                initial_margin = (entry * float(p['contracts']) * contract_size) / live_bot_multi.LEVERAGE
                roe = (upnl / initial_margin * 100) if initial_margin > 0 else 0
            except:
                roe = 0
                initial_margin = 0
            
            # 2. Fetch TP/SL Prices and Calculate Target ROE
            tp_price = 0
            sl_price = 0
            target_roe_str = "N/A"
            
            try:
                # 🛡️ Verified Blofin TPSL system
                try:
                    all_tpsl = user_ex.private_get_trade_orders_tpsl_pending({"instType": "SWAP"})
                    if all_tpsl and "data" in all_tpsl:
                        for o in all_tpsl["data"]:
                            if o.get('instId') == market['id']:
                                tp = float(o.get('tpTriggerPrice') or 0)
                                sl = float(o.get('slTriggerPrice') or 0)
                                if tp > 0: tp_price = tp
                                if sl > 0: sl_price = sl
                except: pass
                    
                if tp_price > 0:
                    if side == "LONG":
                        target_roe = ((tp_price - entry) / entry) * live_bot_multi.LEVERAGE * 100
                    else: # SHORT
                        target_roe = ((entry - tp_price) / entry) * live_bot_multi.LEVERAGE * 100
                    target_roe_str = f"{target_roe:+.1f}%"
            except: pass

            # 3. Generate the Chart
            chart_path = None
            try:
                open_ts = int(p.get('info', {}).get('createTime') or 0)
                ohlcv = user_ex.fetch_ohlcv(sym, timeframe='15m', limit=100)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                chart_path = charting.generate_trade_chart(sym, df, entry, tp_price, sl_price, side, open_ts)
            except Exception as e:
                logger.error(f"Chart generation failed for {sym}: {e}")

            # 4. Calculate Dollar Targets for Summary
            target_pnl_dollars = 0
            if tp_price > 0:
                target_pnl_dollars = initial_margin * (target_roe / 100)
            
            # Format for MarkdownV2 using helper
            upnl_v2 = escape_md_v2(f"{upnl:+.2f}")
            roe_v2 = escape_md_v2(f"{roe:+.2f}")
            sym_v2 = escape_md_v2(sym)
            
            caption = (
                f"{'🟢' if side.lower() == 'long' else '🔴'} *{sym_v2} \\({side.upper()}\\)*\n"
                f"PnL: ||{upnl_v2}|| USDT \\({roe_v2}%\\)"
            )

            if chart_path and os.path.exists(chart_path):
                # Prepare Share Button
                s_side = "l" if side.lower() == "long" else "s"
                callback_data = f"sha_{sym}_{s_side}_{roe:.1f}_{entry:.6g}_{mark_price:.6g}_{upnl:.1f}"
                keyboard = [[InlineKeyboardButton("Share & Earn 📸", callback_data=callback_data)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                with open(chart_path, 'rb') as photo:
                    await update.effective_message.reply_photo(photo, caption=caption, parse_mode="MarkdownV2", reply_markup=reply_markup)
                os.remove(chart_path) # Cleanup
            else:
                # Fallback for no chart
                await update.effective_message.reply_text(caption, parse_mode="MarkdownV2")
        
        # 4. Finally send the footer once
        await update.effective_message.reply_text("🛰️ *Sherpa Command Center*", reply_markup=get_main_inline_menu(chat_id), parse_mode="Markdown")
        
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Error fetching positions: {e}")

async def strategy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("Please run /setup first.")
        return
        
    keyboard = [
        [InlineKeyboardButton("Mean Reversion Scalper (Active)", callback_data="set_strat_mean")],
        [InlineKeyboardButton("Crypto Chart Patterns (Coming Soon)", callback_data="set_strat_soon")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current = user.get('strategy', 'Mean Reversion Scalper')
    await update.effective_message.reply_text(
        f"🎯 *Strategy Selection*\n\n"
        f"Your current strategy: *{current}*\n\n"
        f"Choose a strategy for your account:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def strategy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "set_strat_mean":
        database.update_user_strategy(query.message.chat.id, "Mean Reversion Scalper")
        await safe_edit_text(update, context, "✅ Strategy set to: *Mean Reversion Scalper*", reply_markup=get_main_inline_menu(query.message.chat.id))
    elif query.data == "set_strat_soon":
        await query.answer("🚧 This strategy is coming soon!", show_alert=True)

def get_settings_ui(user):
    privacy_status = "🔒 HIDDEN" if user['hide_dollars'] else "👁️ SHOWN"
    bot_status = "🟢 ACTIVE" if user['is_active'] else "🔴 PAUSED"
    risk_val = user.get('risk_pct', 1.5)
    syms = user.get('enabled_symbols', [])
    wallet_val = user.get('source_wallet')
    wallet_display = f"{wallet_val[:6]}...{wallet_val[-4:]}" if wallet_val else "(Not Set)"
    
    is_premium = database.is_premium(user)
    is_admin = (user.get('telegram_chat_id') == ADMIN_CHAT_ID and not user.get('undercover_mode'))
    
    tier_display = "👑 Sherpa Overlord (Permanent)" if is_admin else ("💎 Premium (Institutional)" if is_premium else "🥈 Standard")
    
    expiry_msg = ""
    if is_premium and not is_admin:
        days_left = database.get_premium_days_left(user)
        expiry_date = time.strftime('%Y-%m-%d', time.localtime(user['premium_expiry']))
        expiry_msg = f"Expires: *{expiry_date}* ({days_left} days left)\n"
    
    msg = (
        f"⚙️ *Metaverse Sherpa Settings*\n\n"
        f"Status: *{bot_status}*\n"
        f"Tier: *{tier_display}*\n"
        f"{expiry_msg}"
        f"Strategy: *{user['strategy']}*\n"
        f"Risk Level: *{risk_val:.2f}%*\n"
        f"Active Symbols: *{len(syms)}/19*\n"
        f"Dollar PnL: *{privacy_status}*\n"
        f"Source Wallet: `{wallet_display}`\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"⚖️ Set Risk % {'🔒' if not is_premium else ''}", callback_data="set_risk"),
         InlineKeyboardButton(f"🛰 Symbols {'🔒' if not is_premium else ''}", callback_data="manage_symbols")],
        [InlineKeyboardButton(f"Toggle Privacy ({'Show $' if user['hide_dollars'] else 'Hide $'})", callback_data="toggle_privacy")],
        [InlineKeyboardButton("Change Strategy", callback_data="strategy_menu")],
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
    
    if user['is_active']:
        keyboard.append([InlineKeyboardButton("🔴 Stop Trading", callback_data="toggle_active")])
    else:
        keyboard.append([InlineKeyboardButton("🟢 Resume Trading", callback_data="toggle_active")])
        
    # Append the universal navigation footer
    keyboard.extend(get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin))
    
    return msg, InlineKeyboardMarkup(keyboard)

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
        
    msg, reply_markup = get_settings_ui(user)
    await update.effective_message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def show_refer_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified helper to show the Institutional Recruitment Dashboard."""
    chat_id = update.effective_chat.id
    bot_username = (await context.bot.get_me()).username
    stats = database.get_referral_stats(chat_id)
    
    invite_link = f"https://t.me/{bot_username}?start=ref_{chat_id}"
    
    refer_msg = (
        "🏔️ *Institutional Recruitment Dashboard*\n\n"
        "Expand the trail and unlock the **23x Wealth Gap** for free!\n\n"
        f"📊 *Your Status:* `{stats}` Recruits\n"
        f"📈 *Next Reward:* `{3 - (stats % 3)}` more for **30 Days Premium**\n\n"
        "🔗 *Your Institutional Invite Link:*\n"
        f"`{invite_link}`\n\n"
        "💡 _Every 3 recruits who join the trail instantly unlocks 30 days of full 'Sherpa Basket' access._"
    )
    
    kb = [[InlineKeyboardButton("📱 Share Invite Link", url=f"https://t.me/share/url?url={invite_link}&text=Unlock%20the%20Institutional%20Wealth%20Gap%20with%20the%20Metaverse%20Sherpa%20Trading%20Bot!%20🏔️")]]
    await safe_edit_text(update, context, refer_msg, reply_markup=InlineKeyboardMarkup(kb))

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_refer_dashboard(update, context)

async def show_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the Institutional Premium Upgrade dashboard."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user: return
    
    wallet_val = user.get('source_wallet')
    is_premium = database.is_premium(user)
    
    if not wallet_val:
        await update.effective_message.reply_text(
            "⚠️ *Source Wallet Required*\n\n"
            "To unlock Institutional access, you must first set your **Source Wallet Address** so the Sherpa can verify your payment.\n\n"
            "Tap the button below to link your wallet first.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👛 Set Wallet", callback_data="prompt_set_wallet")]])
        )
        return

    credits = user.get('referral_credits', 0.0)
    final_price = max(0.0, 20.0 - credits)
    
    credit_msg = f"💰 *Available Credit:* `${credits:.2f}`\n" if credits > 0 else ""
    price_msg = f"💳 *Institutional Access Fee:* ~~[ $20 ]~~ **${final_price:.2f} USDT** / 30 Days\n" if credits > 0 else f"💳 *Institutional Access Fee:* **$20 USDT / 30 Days**\n"

    premium_msg = (
        "💎 *Go Institutional: Unlock the 23x Wealth Gap*\n\n"
        "Unlock the full power of the Metaverse Sherpa engine. Moving from Standard to Institutional tier grants you access to professional-grade tools used by elite traders:\n\n"
        "🏔️ *Institutional Tier Benefits:*\n"
        "• **The Full Sherpa Basket**: Trade all 19+ premium symbols (Standard is limited to top 5).\n"
        "• **Advanced Risk Control**: Set custom risk-per-trade percentages.\n"
        "• **Priority Execution**: Your trades are prioritized in the engine's background loop.\n"
        "• **Zero Friction**: Automated on-chain audits keep your access active.\n\n"
        f"{credit_msg}"
        f"{price_msg}\n"
        "📥 *The Step-by-Step Upgrade Path:*\n"
        "1. **Copy the Treasury Address** below (Tap to copy).\n"
        f"2. **Send exactly ${final_price:.2f} USDT** via the **TRON (TRC-20)** network.\n"
        "3. **Tap 'Audit My Payment'** below once sent.\n\n"
        "🏛️ *Master Treasury Address (TRC-20):*\n"
        f"`{get_master_wallet()}`\n\n"
        f"🕵️‍♂️ *Verifying Transfer From:* `{wallet_val}`\n\n"
        "⚠️ _Note: Activation is fully automated. The Sherpa's audit engine will scan the blockchain for your transaction and unlock your access within 1-3 minutes of on-chain confirmation._"
    )
    
    kb = []
    if final_price == 0:
        kb.append([InlineKeyboardButton("🚀 Activate with Credits", callback_data="activate_with_credits")])
    else:
        kb.append([InlineKeyboardButton("🔎 Audit My Payment & Unlock", callback_data="check_payment")])
    
    kb.append([InlineKeyboardButton("👛 Change My Linked Wallet", callback_data="prompt_set_wallet")])
    kb.append([InlineKeyboardButton("🔙 Return to Settings", callback_data="settings_menu")])
    await safe_edit_text(update, context, premium_msg, reply_markup=InlineKeyboardMarkup(kb))

def get_admin_keyboard(master_wallet):
    """Definitive High-Authority Command Buttons."""
    return [
        [InlineKeyboardButton("📊 User & Referral Audit", callback_data="admin_user_audit")],
        [InlineKeyboardButton("🎁 Gift Premium Access", callback_data="admin_gift_prompt")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast_prompt")],
        [InlineKeyboardButton("🔍 View Live VPS Logs", callback_data="view_logs")],
        [InlineKeyboardButton("🕶️ Toggle Undercover Mode", callback_data="toggle_undercover")],
        [InlineKeyboardButton("👛 Update Master Wallet", callback_data="prompt_admin_wallet")],
        [InlineKeyboardButton("📜 View Audit Trail (TronScan)", url=f"https://tronscan.org/#/address/{master_wallet}")],
        [InlineKeyboardButton("🔙 Close Console", callback_data="close_admin")]
    ]

async def show_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gated dashboard for the Sherpa Overlord."""
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_CHAT_ID: return
    
    user = database.get_user(chat_id)
    if not user: return

    stats = database.get_platform_stats()
    master_wallet = get_master_wallet()
    
    # Query Wallet Balances via TronGrid and Price via CCXT
    total_val = 0.0
    trx_bal = 0.0
    usdt_bal = 0.0
    try:
        import requests
        url = f"https://api.trongrid.io/v1/accounts/{master_wallet}"
        resp = requests.get(url, timeout=7)
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            if data:
                acc = data[0]
                # TRX Balance (6 decimals)
                trx_bal = float(acc.get('balance', 0)) / 10**6
                
                # USDT Balance (TRC-20)
                trc20_tokens = acc.get('trc20', [])
                for token_map in trc20_tokens:
                    for contract, raw_bal in token_map.items():
                        if contract == "TR7NHqjehp3u3M11K2xv39zSQqyvssF6t":
                            usdt_bal = float(raw_bal) / 10**6
                            break
        
        # Fetch Real-Time TRX Price via TronScan (matches your dashboard)
        try:
            price_url = "https://apilist.tronscan.org/api/token/price?token=trx"
            price_resp = requests.get(price_url, timeout=5)
            trx_price = float(price_resp.json().get('price', 0.35))
        except:
            trx_price = 0.35 # Future-proof fallback based on your reality
            
        total_val = (trx_bal * trx_price) + usdt_bal
        balance_display = f"${total_val:,.2f}"
    except Exception as e:
        logger.error(f"Treasury Sync Error: {e}")
        balance_display = "??? (Offline)"

    admin_status = "🕵️‍♂️ Undercover" if user.get('undercover_mode') else "👑 Overlord"
    
    last_sync = time.strftime('%H:%M:%S')
    admin_msg = (
        "👑 *Sherpa Overlord Mission Control*\n\n"
        f"Identity Status: *{admin_status}*\n\n"
        "📊 *Platform Analytics*\n"
        f"• Total Users: `{stats['total_users']}`\n"
        f"• Total Referrals: `{stats['total_referrals']}`\n"
        f"• Active Premium: `{stats['premium_users']}`\n"
        f"• Last Deploy: *2026-05-14 10:08*\n\n"
        "💰 *Total Treasury Value*\n"
        f"• Master Wallet: `{master_wallet}`\n"
        f"• TRX: `{trx_bal:,.1f}` | USDT: `${usdt_bal:,.2f}`\n"
        f"• **Live Balance: {balance_display}**\n\n"
        f"🕒 _Last Sync: {last_sync}_"
    )
    
    kb = get_admin_keyboard(master_wallet)
    await safe_edit_text(update, context, admin_msg, reply_markup=InlineKeyboardMarkup(kb))

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_admin_dashboard(update, context)

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.from_user.id
    user = database.get_user(chat_id)
    
    if query.data == "activate_with_credits":
        user = database.get_user(chat_id)
        credits = user.get('referral_credits', 0.0)
        if credits < 20.0:
            await query.answer("❌ Insufficient credits.", show_alert=True)
            return
            
        await query.answer("🚀 Activating with Credits...")
        database.consume_referral_credits(chat_id, 20.0)
        database.add_premium_days(chat_id, 30)
        database.set_active(chat_id, True)
        
        # 🤝 Referral Reward: Grant $5 to the person who referred THIS user
        referrer_id = user.get('referred_by')
        if referrer_id:
            database.add_referral_credit(referrer_id, 5.0)
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text="💰 *Institutional Referral Reward!*\nOne of your recruits just activated Premium Access. You've earned a **$5.00 Credit** on your next month!",
                    parse_mode="Markdown"
                )
            except: pass

        await query.message.reply_text("💎 *INSTITUTIONAL ACCESS ACTIVATED!*\nSuccessfully used $20.00 in referral credits.", parse_mode="Markdown")
        msg, rm = get_settings_ui(user)
        await safe_edit_text(update, context, msg, reply_markup=rm)
        return

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
        return

    if query.data == "admin_command":
        if chat_id != ADMIN_CHAT_ID: return
        await admin_command(update, context)
        return

    if query.data == "admin_user_audit":
        if chat_id != ADMIN_CHAT_ID: return
        await query.answer("📊 Generating Audit...")
        report = database.get_detailed_user_report()
        
        msg = "🏔️ *Sherpa Institutional User Audit*\n\n"
        for u in report:
            tier = "💎 Paid" if u['is_premium'] else "🥈 Free"
            name = escape_md_v2(u.get('full_name') or "Unknown")
            uname = escape_md_v2(f" (@{u['username']})") if u.get('username') else ""
            
            # 🕵️‍♂️ Last-Mile Identity Fetch (if Unknown)
            if name == "Unknown":
                try:
                    member = await context.bot.get_chat_member(chat_id=u['telegram_chat_id'], user_id=u['telegram_chat_id'])
                    name = escape_md_v2(member.user.full_name)
                    uname = escape_md_v2(f" (@{member.user.username})") if member.user.username else ""
                except: pass

            status = "🟢 Active" if u['is_active'] else "⚪️ Setup"
            msg += f"• `{u['telegram_chat_id']}` \| *{name}*{uname}\n  Status: {status} \| Tier: {tier}\n"
            
            # 🤝 Display Referral Tree
            if u.get('recruit_list'):
                msg += "  *Recruits:* \n"
                for rec in u['recruit_list']:
                    r_name = escape_md_v2(rec.get('full_name') or "Unknown")
                    r_uname = escape_md_v2(f" (@{rec['username']})") if rec.get('username') else ""
                    msg += f"  └\─ {r_name}{r_uname} \(`{rec['telegram_chat_id']}`\)\n"
            else:
                msg += "  *Recruits:* None\n"
            msg += "\n"
        
        # Split message if too long
        # 👑 UX Persistence: Append Divider and Command Center to the LAST part
        footer = "\n\n───────────────────\n👑 *Sherpa Overlord Mission Control*"
        footer_kb = InlineKeyboardMarkup(get_admin_keyboard(get_master_wallet()))
        
        if len(msg) > 4000:
            parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            for i, p in enumerate(parts):
                if i == len(parts) - 1:
                    await context.bot.send_message(chat_id=chat_id, text=p + footer, parse_mode="MarkdownV2", reply_markup=footer_kb)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=p, parse_mode="MarkdownV2")
        else:
            await query.message.reply_text(msg + footer, parse_mode="MarkdownV2", reply_markup=footer_kb)
        
        return

    if query.data == "admin_broadcast_prompt":
        if chat_id != ADMIN_CHAT_ID: return
        context.user_data['admin_broadcasting'] = True
        await query.message.reply_text(
            "📢 *Institutional Broadcast Mode*\n\n"
            "Please type the message you would like to send to **ALL** users. "
            "You can use Markdown for formatting.\n\n"
            "Tap /cancel to abort.",
            parse_mode="Markdown"
        )
        return

    if query.data == "admin_gift_prompt":
        context.user_data['admin_gifting'] = True
        await query.message.reply_text(
            "🎁 *Institutional Gifting Center*\n\n"
            "Please enter the **Telegram Chat ID** of the user you wish to gift a free month of Premium access to.\n\n"
            "You can find this ID in the 'User & Referral Audit' report.\n\n"
            "Tap /cancel to abort.",
            parse_mode="Markdown"
        )
        return

    if query.data == "view_logs":
        if chat_id != ADMIN_CHAT_ID: return
        await query.answer("🔍 Fetching Mission Logs...")
        try:
            import subprocess
            from telegram.helpers import escape_markdown
            # Get last 50 lines of journalctl for better visibility
            logs = subprocess.check_output(["journalctl", "-u", "tradingbot", "-n", "50", "--no-pager"], text=True)
            safe_logs = escape_markdown(logs, version=2)
            
            kb = [[InlineKeyboardButton("🔄 Refresh Logs", callback_data="view_logs")],
                  [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_command")]]
            
            msg = f"📋 *Sherpa Operational Logs* \(Last 50 Lines\)\n\n```\n{safe_logs}\n```"
            
            if query.message.text and "Operational Logs" in query.message.text:
                await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="MarkdownV2")
            else:
                await query.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to fetch logs: {e}")
        return

    if query.data == "apply_symbol_audit":
        await query.answer("🏔️ Applying Institutional Settings...")
        try:
            # Trigger single definitive audit
            user = database.get_user(chat_id)
            user_equity = user.get('equity', 10000.0)
            logger.info(f"Triggering personalized audit for user {chat_id} with equity {user_equity}")
            
            # Fire and forget the audit task
            asyncio.create_task(trigger_personalized_audit(update, context, user, start_balance=user_equity))
            
            # IMMEDIATELY return to main settings so UI doesn't hang
            msg, reply_markup = get_settings_ui(user)
            await safe_edit_text(update, context, msg, reply_markup=reply_markup)
            return
        except Exception as e:
            logger.error(f"Failed to apply symbol settings for {chat_id}: {e}")
            await safe_edit_text(update, context, f"❌ Error applying settings: {e}\n\nPlease try again or contact the Sherpa.", reply_markup=get_main_inline_menu(chat_id))
            return

    if query.data == "refer_menu":
        await show_refer_dashboard(update, context)
        await query.answer()
        return
    
    if query.data == "prompt_set_wallet":
        context.user_data['setting_wallet'] = True
        await query.message.reply_text(
            "👛 *Institutional Wallet Setup*\n\n"
            "Please send your **USDT (TRC-20) Address** below.\n\n"
            "This address will be used to automatically verify your subscription payments and enable frictionless future renewals.",
            parse_mode="Markdown"
        )
        await query.answer()
        return

    if query.data == "prompt_admin_wallet":
        if chat_id != ADMIN_CHAT_ID: return
        context.user_data['setting_admin_wallet'] = True
        await query.message.reply_text(
            "👑 *Overlord: Update Treasury Address*\n\n"
            "Please send the new **Master USDT (TRC-20) Address** below.\n\n"
            "⚠️ _This will instantly update the destination for all new institutional upgrades._",
            parse_mode="Markdown"
        )
        await query.answer()
        return

    if query.data == "close_admin":
        await query.answer("Returning to Main Menu...")
        await query.message.delete()
        # Call the actual command to send a fresh message with footer
        await settings_command(update, context)
        return

    if query.data == "toggle_undercover":
        if chat_id != ADMIN_CHAT_ID: 
            logger.warning(f"UNAUTHORIZED TOGGLE ATTEMPT: {chat_id}")
            return
        database.toggle_undercover(chat_id)
        await query.answer("🔄 Identity Toggled!")
        await show_admin_dashboard(update, context)
        return

    if query.data == "premium_menu":
        await show_premium_menu(update, context)
        await query.answer()
        return

    if query.data == "check_payment":
        await query.answer("🔎 Auditing Blockchain...")
        # 1. Get user and their source wallet
        user = database.get_user(chat_id)
        source_wallet = user.get('source_wallet')
        
        if not source_wallet:
            await query.message.reply_text("❌ No source wallet linked. Please set your wallet first.")
            return

        # 👑 Admin-Only Self-Audit Security
        if source_wallet == get_master_wallet() and chat_id != ADMIN_CHAT_ID:
            await query.message.reply_text(
                "❌ *Invalid Source Wallet*\n\n"
                "You cannot use the Master Treasury address as your source wallet. Please link your personal USDT (TRC-20) address in Settings.",
                parse_mode="Markdown"
            )
            return
            
        await query.message.reply_text("🔎 *Auditing Blockchain for your transfer...*\n\nThis usually takes 1-3 minutes. Please wait and click again if activation is not instant.", parse_mode="Markdown")
        
        # 2. Query TronScan API
        import requests
        url = "https://apilist.tronscan.org/api/token_trc20/transfers"
        params = {
            "limit": 20,
            "start": 0,
            "direction": 1, # Incoming to MASTER
            "address": get_master_wallet(),
            "relatedAddress": source_wallet
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            transfers = data.get('token_transfers', [])
            
            # Calculate required amount based on credits
            credits = user.get('referral_credits', 0.0)
            required_price = max(0.1, 20.0 - credits) # Min $0.1 for blockchain audit
            
            found = False
            for tx in transfers:
                # TRC-20 USDT contract: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
                if tx.get('contract_address') == 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':
                    amount = float(tx.get('quant')) / 10**6
                    # Check for required price (allow a small range just in case of fees)
                    if (required_price - 0.5) <= amount <= (required_price + 0.5):
                        found = True
                        break
            
            if found:
                # Activate!
                database.add_premium_days(chat_id, 30)
                database.set_active(chat_id, True)
                
                # Consume Credits used
                if credits > 0:
                    database.consume_referral_credits(chat_id, 20.0)
                
                # 🤝 Referral Reward: Grant $5 to the person who referred THIS user
                referrer_id = user.get('referred_by')
                if referrer_id:
                    database.add_referral_credit(referrer_id, 5.0)
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text="💰 *Institutional Referral Reward!*\nOne of your recruits just activated Premium Access. You've earned a **$5.00 Credit** on your next month!",
                            parse_mode="Markdown"
                        )
                    except: pass
                
                # 👑 Notify Overlord of Revenue
                try:
                    user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID: `{chat_id}`"
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"💰 *INSTITUTIONAL REVENUE CONFIRMED!*\n\nUser: {user_info}\nRequired: *${required_price:.2f} USDT*\n\n📈 _The treasury is growing._",
                        parse_mode="Markdown"
                    )
                except: pass

                await query.message.reply_text(
                    "💎 *INSTITUTIONAL ACCESS ACTIVATED!*\n\n"
                    "Congratulations. Your account has been upgraded to the Institutional Tier for **30 days**.\n\n"
                    "🏔️ *Power Unlocked:*\n"
                    "• Full 19+ Symbol Basket enabled.\n"
                    "• Custom Risk Management enabled.\n"
                    "• Priority Background Processing enabled.\n\n"
                    "The Sherpa engine is now live on your account. Happy climbing!",
                    parse_mode="Markdown"
                )
                # Show settings again to confirm
                msg, markup = get_settings_ui(database.get_user(chat_id))
                await query.message.reply_text(msg, reply_markup=markup, parse_mode="Markdown")
            else:
                await query.message.reply_text(
                    "❌ *No matching transfer found yet.*\n\n"
                    "On-chain confirmation can take a few minutes. Please wait and try again shortly.\n\n"
                    f"ℹ️ _Looking for $20 USDT from_ `{source_wallet}` _to_ `{get_master_wallet()}`",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            logger.error(f"Error checking payment: {e}")
            await query.message.reply_text("⚠️ _Blockchain audit engine is busy. Please try again in 60 seconds._")
        
        return
        exchange_id = query.data.split("_")[1]
        context.user_data['exchange_id'] = exchange_id
        context.user_data['setup_step'] = 1
        await query.answer()
        
        # Customize instructions based on exchange
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
        else:
            guide = (
                "🏔️ *Blofin API Setup*\n\n"
                "1️⃣ Go to **API Management** on Blofin.\n"
                "2️⃣ Create Key with **'Read'** & **'Trade'** permissions.\n"
                "3️⃣ Note your passphrase for the final step.\n\n"
                "Please paste your **Blofin API Key** below:"
            )
            
        await safe_edit_text(update, context, guide)
        return

    if not user:
        if not query.data.startswith("setex_"):
            await query.answer("User record not found. Please run /setup.")
            return

    if query.data == "check_balance_setup":
        await query.answer()
        await balance_command(update, context)
        return
    elif query.data == "opentrades_menu":
        await query.answer()
        await open_trades(update, context)
        return
    elif query.data == "history_menu":
        await query.answer()
        await list_trades(update, context)
        return
    elif query.data == "stats_menu":
        await query.answer()
        await stats(update, context)
        return
    elif query.data == "help_menu":
        await query.answer()
        await docs(update, context)
        return
    elif query.data == "settings_menu":
        await query.answer()
        await settings_command(update, context)
        return
    elif query.data == "contact_menu":
        await query.answer()
        await contact_command(update, context)
        return
    elif query.data == "referral_menu":
        await query.answer()
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}"
        count = database.get_referral_stats(chat_id)
        
        msg = (
            "🤝 *Sherpa Referral Program*\n\n"
            "Grow the community and earn **Free Premium Days**!\n\n"
            "Your Link (Tap to Copy):\n"
            f"`{ref_link}`\n\n"
            f"Total Referrals: *{count}*\n\n"
            "Share this link with your friends. For every friend who sets up their API keys, you both get **5 bonus days** of unlimited usage!"
        )
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False))
        ]
        await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif query.data == "confirm_panic":
        await query.answer()
        kb = [
            [InlineKeyboardButton("✅ YES, CLOSE ALL TRADES NOW!", callback_data="panic_execute")],
            [InlineKeyboardButton("❌ NO, ABORT", callback_data="back_to_settings")]
        ]
        await safe_edit_text(
            update, context,
            "⚠️ *EMERGENCY CONFIRMATION*\n\n"
            "You are about to close **ALL OPEN TRADES** at current market prices.\n\n"
            "This action is immediate and cannot be undone. Are you absolutely sure you want to exit the market now?",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    elif query.data == "panic_execute":
        await query.answer("🚨 Executing Panic Exit...")
        success, report = await panic_close_all(chat_id)
        
        icon = "🏆" if success else "❌"
        msg = (
            f"{icon} *Panic Exit Report*\n\n"
            f"{report}\n\n"
            "The engine has been paused for your account to prevent new entries."
        )
        # Force stop the bot for this user after panic exit
        database.set_active(chat_id, False)
        
        await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id))
        return



    elif query.data == "toggle_privacy":
        new_val = not user['hide_dollars']
        database.update_user_preference(chat_id, "hide_dollars", 1 if new_val else 0)
        await query.answer("✅ Privacy Mode updated!")
        
    elif query.data == "toggle_active":
        new_val = not user['is_active']
        database.set_active(chat_id, new_val)
        status_txt = "Bot Resumed! 🟢" if new_val else "Bot Stopped! 🔴"
        await query.answer(status_txt)

    elif query.data == "strategy_menu":
        await query.answer()
        risk_val = user.get('risk_pct', 1.5)
        
        strategy_overview = (
            "🎯 *Strategy Selection & Overview*\n\n"
            "🛡️ *Engine: Mean Reversion Scalper*\n"
            "This strategy uses Bollinger Band volatility expansion/contraction to identify overextended price moves. It enters 'reversion' trades to capture the snap-back to the mean.\n\n"
            "📊 *Core Parameters:*\n"
            "• *Target R:R*: 1:1.5 or better\n"
            "• *Risk Per Trade*: User-defined (% of equity)\n"
            "• *Logic*: Auto-calculates position size based on SL distance.\n\n"
            "📈 *3-Year Performance Proof:*\n"
            "• Total PnL: *+576.2%*\n"
            "• Win Rate: *60.0%*\n"
            "• Max Drawdown: *18.8%*\n\n"
            f"⚖️ *Current Risk*: `{risk_val:.2f}% per trade`\n\n"
            "Select a strategy or adjust your risk below:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏔️ Preview My Performance", callback_data="backtest_menu")],
            [InlineKeyboardButton("⚖️ Set Risk %", callback_data="set_risk")],
            [InlineKeyboardButton("Mean Reversion Scalper (Active)", callback_data="set_strat_mean")],
            [InlineKeyboardButton("🚧 Crypto Chart Patterns (Soon)", callback_data="set_strat_soon")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False))
        ]
        await safe_edit_text(update, context, strategy_overview, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif query.data == "set_risk":
        await query.answer()
        context.user_data['setting_risk'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False), is_admin=(chat_id == ADMIN_CHAT_ID and not user.get('undercover_mode')))
        ]
        await safe_edit_text(
            update, context,
            "⚖️ *Set Risk Percentage*\n\n"
            "Please type your preferred risk-per-trade as a number (e.g., `1.5` or `2.0`).\n\n"
            "This percentage of your equity will be risked on every trade based on the SL distance.\n\n"
            "_Current: " + f"{user['risk_pct']:.2f}%_",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif query.data == "compare_institutional":
        await query.answer("🏔️ Loading Institutional Power baseline...")
        await send_master_audit(update, context, chat_id)
        return

    elif query.data == "manage_symbols":
        await query.answer()
        await show_symbol_menu(update, context, user)
        return

    elif query.data.startswith("tsym_"): # TOGGLE SYMBOL
        sym_to_toggle = query.data.split("_")[1]
        current_syms = user['enabled_symbols']
        if sym_to_toggle in current_syms:
            current_syms.remove(sym_to_toggle)
        else:
            current_syms.append(sym_to_toggle)
        database.update_user_preference(chat_id, "enabled_symbols", current_syms)
        await query.answer(f"✅ Updated {sym_to_toggle}")
        # Re-show menu (Silent, no audit)
        user = database.get_user(chat_id)
        await show_symbol_menu(update, context, user)
        return



    elif query.data.startswith("confirm_close_"):
        sym = query.data.replace("confirm_close_", "")
        await query.answer()
        kb = [
            [InlineKeyboardButton(f"✅ YES, CLOSE {sym} NOW!", callback_data=f"execute_close_{sym}")],
            [InlineKeyboardButton("❌ NO, ABORT", callback_data="opentrades_menu")]
        ]
        await safe_edit_text(
            update, context,
            f"⚠️ *INSTITUTIONAL CONFIRMATION REQUIRED*\n\n"
            f"Are you sure you want to Market Close your *{sym}* position?\n\n"
            "This will instantly exit the trade at current market price.",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    elif query.data.startswith("execute_close_"):
        sym = query.data.replace("execute_close_", "")
        await query.answer(f"🛑 Closing {sym}...")
        
        success, result = await close_single_position(chat_id, sym)
        icon = "✅" if success else "❌"
        await query.message.reply_text(f"{icon} *Tactical Close:* {result}", parse_mode="Markdown")
        
        # Refresh open trades
        await open_trades(update, context)
        return

    elif query.data == "back_to_settings":
        context.user_data.pop('setting_risk', None)
        await query.answer()

    # Refresh and show settings UI
    user = database.get_user(chat_id)
    msg, reply_markup = get_settings_ui(user)
    await safe_edit_text(update, context, msg, reply_markup=reply_markup)

async def show_symbol_menu(update, context, user):
    query = update.callback_query
    chat_id = user['telegram_chat_id']
    all_syms = ["BTC","ETH","SOL","DOGE","ADA","LINK","DOT","TON","ZEC","PEPE","BNB","NEAR","SUI","NOT","TAO","ONDO","ENA","FET","WIF"]
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
    keyboard.append([InlineKeyboardButton("🚀 Apply & Run Audit", callback_data="apply_symbol_audit")])
    keyboard.append([InlineKeyboardButton("───────────────", callback_data="none")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")])
    is_admin = (chat_id == ADMIN_CHAT_ID and not user.get('undercover_mode'))
    keyboard.extend(get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin))
    
    await safe_edit_text(
        update, context,
        "🛰 *Manage Symbols*\n\nTap a symbol to toggle it ON or OFF for your account.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    new_val = not user['hide_dollars']
    database.update_user_preference(chat_id, "hide_dollars", 1 if new_val else 0)
    status = "HIDDEN 🔒" if new_val else "SHOWN 👁️"
    await update.effective_message.reply_text(f"✅ Privacy Mode: Dollar amounts are now *{status}*.", parse_mode="Markdown")

async def share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = query.from_user.id
    user = database.get_user(chat_id)
    
    # Notify user we're working on it
    await query.answer("📸 Generating your Sherpa Share Card...")
    
    card_path = None
    share_label = ""
    
    if data.startswith("shs_"): # SHARE STATS
        # Format: shs_{overall}_{daily}_{wr}_{total}
        parts = data.split("_")
        overall, daily, wr, total = float(parts[1]), float(parts[2]), float(parts[3]), int(parts[4])
        bot_username = (await context.bot.get_me()).username
        card_path = media_gen.generate_stats_card(overall, daily, wr, total, user_id=chat_id, bot_username=bot_username)
        share_label = "performance summary"
        
    elif data.startswith("sh_") or data.startswith("sha_") or data.startswith("shc_"): # SHARE TRADE
        # Format: sh_{sym}_{side}_{roe}_{entry}_{mark}_{pnl}
        parts = data.split("_")
        is_active = data.startswith("sha_")
        is_closed = data.startswith("shc_")
        
        sym = parts[1]
        side = "long" if parts[2] == "l" else "short"
        roe, entry, mark, pnl = float(parts[3]), float(parts[4]), float(parts[5]), float(parts[6])
        bot_username = (await context.bot.get_me()).username
        card_path = media_gen.generate_pnl_card(
            sym, side, roe, entry, mark, 
            hide_dollars=user['hide_dollars'] if user else True, 
            pnl_usdt=pnl,
            user_id=chat_id,
            bot_username=bot_username
        )
        share_label = f"trade results for {sym}"
    
    if card_path and os.path.exists(card_path):
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}"
        
        # Context-Aware Viral Message
        is_trade_card = data.startswith("sh_") or data.startswith("sha_") or data.startswith("shc_")
        if is_trade_card:
            parts = data.split("_")
            is_active = data.startswith("sha_")
            roe = float(parts[3])
            is_profit = roe >= 0
            
            if not is_active:
                # Closed trades or generic legacy
                if is_profit:
                    headline = "🏆 *Just crushed another trade with the Metaverse Sherpa Bot!* 🏔️"
                else:
                    headline = "🌧️ *Sometimes a trail gets rained out, but there's always another trail to hike. On to the next one!* 🏔️"
            else:
                # ACTIVE trades - High Integrity messaging
                if is_profit:
                    headline = "🛰️ *Another promising looking trade with the Metaverse Sherpa Bot!* 🏔️"
                else:
                    headline = "📈 *Currently in drawdown, but looking promising because we buy the dip with the Metaverse Sherpa Bot!* 🏔️"
        else:
            # Overall Stats
            overall = float(data.split("_")[1])
            is_profit = overall >= 0
            headline = "🏔️ *Climbing to new heights with the Metaverse Sherpa Bot!*" if is_profit else "🧗‍♂️ *Navigating the market peaks. The Sherpa never misses a trail!*"

        # Conditional Viral Payload (Only show referral links/buttons for profit)
        if is_profit:
            viral_caption = (
                f"{headline}\n\n"
                "Join the elite circle of automated traders. Tap below to copy my invite link and start your 5-day trial:\n\n"
                f"`{ref_link}`"
            )
            
            # Create a pre-filled Telegram share URL
            share_text = f"{headline.replace('*', '')}\n\nJoin the elite circle of automated traders. Start your 5-day trial here:\n{ref_link}"
            import urllib.parse
            encoded_text = urllib.parse.quote(share_text)
            share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={encoded_text}"
            
            keyboard = [
                [InlineKeyboardButton("🏆 Forward to Friend", url=share_url)],
                *get_nav_buttons(user.get('has_open_positions', False))
            ]
        else:
            # For losses, keep it humble and private (No referral link or share button)
            viral_caption = headline
            is_admin = (chat_id == ADMIN_CHAT_ID and not user.get('undercover_mode'))
            keyboard = get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin)
        with open(card_path, 'rb') as photo:
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=photo, 
                caption=viral_caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        # No need to edit the original message - keep the history dashboard intact
        
        # Cleanup
        os.remove(card_path)
    else:
        await query.answer("❌ Error generating card.", show_alert=True)

async def docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a brief tutorial of all bot commands."""
    help_text = (
        "📖 *Metaverse Sherpa Bot - User Manual*\n\n"
        "Welcome! Here is a guide to everything your bot can do:\n\n"
        
        "📊 *Trading & Performance*\n"
        "• /stats - Your dashboard. Shows Overall PnL, Daily PnL (last 24h), and Win Rate.\n"
        "• /opentrades - Visual check. Fetches all live positions and generates charts.\n"
        "• /list - History. Shows your last 10 closed trades directly from the exchange.\n\n"
        
        "💰 *Account Management*\n"
        "• /balance - Check your wallet. Shows available USDT and Total Value.\n"
        "• /setup - The engine room. Connect or update your Blofin API keys securely.\n\n"
        
        "🎯 *Control & Strategy*\n"
        "• /strategy - Swap brains. Switch between different trading algorithms.\n"
        "• /stop - Emergency brake. Pauses the trading engine for your account.\n"
        "• /resume - Green light. Restarts the automated engine.\n\n"
        
        "🔑 *Blofin API Setup Guide*\n"
        "1. Go to **API Management** on Blofin.\n"
        "2. Create Key with **'Read'** & **'Trade'** permissions.\n"
        "3. Use the passphrase you set during creation.\n\n"
        
        "🤝 *Support*\n"
        "• /contact - Reach out to @metaverse\\_sherpa for questions or ideas.\n\n"
        
        "_Need more help? Just tap any command to try it out!_\n\n"
        "⚠️ *Disclaimer:* _Automated trading carries significant risk. The Metaverse Sherpa is a tool for professional-grade execution and is **not financial advice**. Past performance does not guarantee future results. Trade at your own risk._"
    )
    chat_id = update.effective_chat.id
    await update.effective_message.reply_text(help_text, parse_mode="Markdown")
    
    # Send PDF Documentation
    pdf_path = os.path.join(BASE_DIR, "tutorials", "MetaverseSherpa Blofin API Setup.pdf")
    if os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as doc:
            await context.bot.send_document(
                chat_id=chat_id,
                document=doc,
                caption="📖 *Official Blofin Setup Guide (PDF)*",
                parse_mode="Markdown",
                reply_markup=get_main_inline_menu(chat_id)
            )
    else:
        await update.effective_message.reply_text("🛰️ *Main Menu Activated*", reply_markup=get_main_inline_menu(chat_id), parse_mode="Markdown")

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

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    target = update.effective_message
        
    user_data = database.get_user(chat_id)
    
    if not user_data:
        await target.reply_text("❌ No API keys found. Please run /setup first.")
        return
        
    await target.reply_text("💰 Fetching your live balance...")
    
    try:
        # Note: database.get_user already returns decrypted keys
        user_ex = database.get_exchange_client(user_data)
        
        balance = user_ex.fetch_balance(params={"type": "futures"})
        free = float(balance.get("USDT", {}).get("free", 0))
        
        # True Equity Calculation: Available + Margin + Unrealized PnL
        total_value = free
        try:
            positions = user_ex.fetch_positions()
            for p in positions:
                margin = float(p.get('info', {}).get('margin', 0))
                upnl = float(p.get('info', {}).get('unrealizedPnl', 0))
                total_value += (margin + upnl)
        except: pass
        
        # Format numbers with commas and escape for MarkdownV2 using helper
        free_str = escape_md_v2(f"{free:,.2f}")
        total_str = escape_md_v2(f"{total_value:,.2f}")
        
        msg = (
            "💰 *Your Account Balance*\n\n"
            f"Available Cash: ||*${free_str}*|| USDT\n"
            f"Total Account Value: ||*${total_str}*|| USDT\n\n"
            "_Total Value \\= Available \\+ Margin \\+ PnL_"
        )
        await target.reply_text(msg, parse_mode="MarkdownV2", reply_markup=get_main_inline_menu(chat_id))
        
    except Exception as e:
        await target.reply_text(f"❌ Error fetching balance: {e}")

async def trading_engine(application):
    logger.info("Starting Multi-Tenant Engine Task...")
    while True:
        try:
            # 1. Get all active users
            active_users = database.get_all_active_users()
            if not active_users:
                await asyncio.sleep(60)
                continue
            
            # 2. Group users by strategy to optimize API calls
            strategy_groups = {}
            for user in active_users:
                strat = user.get('strategy', 'Mean Reversion Scalper')
                if strat not in strategy_groups:
                    strategy_groups[strat] = []
                strategy_groups[strat].append(user)
            
            logger.info(f"Engine Pass: Processing {len(active_users)} users across {len(strategy_groups)} strategies...")
            
            # 3. Process each strategy group
            public_ex = ccxt.blofin({"options": {"defaultType": "swap"}})
            public_ex.load_markets()
            
            for strat_name, users in strategy_groups.items():
                signals = {}
                # Calculate signals once for this strategy
                for symbol in live_bot_multi.SYMBOLS:
                    try:
                        ohlcv = public_ex.fetch_ohlcv(symbol, "15m", limit=100)
                        df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                        sig = live_bot_multi.compute_signal(df, symbol.split("/")[0], strategy_name=strat_name)
                        if sig:
                            signals[symbol] = sig
                    except: pass
                
                # Execute for all users in this group
                for user in users:
                    try:
                        chat_id = user['telegram_chat_id']
                        # Last-mile credential check
                        if not user.get('api_key'):
                            # Silence noise for users without API keys
                            pass
                            continue

                        user_ex = ccxt.blofin({
                            "apiKey": user['api_key'],
                            "secret": user['api_secret'],
                            "password": user['api_password'],
                            "options": {"defaultType": "swap"},
                        })
                        
                        balance = user_ex.fetch_balance(params={"type": "futures"})
                        equity = float(balance.get("USDT", {}).get("total", 0))
                        
                        # Sync stats and history
                        database.update_user_stats_from_engine(chat_id, equity, user_ex, application)
                        
                        # Execute signals
                        user_enabled = user.get('enabled_symbols', [])
                        user_risk = user.get('risk_pct', 1.5)
                        
                        for symbol, sig in signals.items():
                            clean_sym = symbol.split("/")[0]
                            if clean_sym not in user_enabled:
                                continue
                                
                            pos = user_ex.fetch_positions([symbol])
                            if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                                if live_bot_multi.DRY_RUN:
                                    logger.info(f"DRY RUN: skipping order for {chat_id}")
                                    continue
                                    
                                res = live_bot_multi.place_order(user_ex, symbol, sig, equity, risk_pct=user_risk)
                                if res:
                                    database.increment_opened(chat_id)
                                    msg = (
                                        f"🏆 *{strat_name}* SIGNAL!\n\n"
                                        f"Symbol: *{res['symbol']}*\n"
                                        f"Risk: `{user_risk:.2f}%`\n"
                                        f"Entry: `{res['entry']:.8f}`\n"
                                        f"TP: `{res['tp']:.8f}`\n"
                                        f"SL: `{res['sl']:.8f}`"
                                    )
                                    # Generate and send chart
                                    try:
                                        ohlcv = user_ex.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                                        df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                                        side_str = "LONG" if sig['side'] == 'buy' else "SHORT"
                                        open_ts = int(time.time() * 1000)
                                        chart_file = charting.generate_trade_chart(res['symbol'], df, res['entry'], res['tp'], res['sl'], side_str, open_ts=open_ts)
                                        
                                        # Add Nav Buttons to the Signal
                                        keyboard = get_nav_buttons(True, is_admin=(target_id == ADMIN_CHAT_ID)) # System notifications, usually no undercover needed for bot itself
                                        
                                        await application.bot.send_photo(
                                            chat_id=chat_id, 
                                            photo=open(chart_file, 'rb'),
                                            caption=msg,
                                            reply_markup=InlineKeyboardMarkup(keyboard),
                                            parse_mode="Markdown"
                                        )
                                    except Exception as chart_err:
                                        logger.error(f"Chart generation failed: {chart_err}")
                                        await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Error for user {user.get('telegram_chat_id')}: {e}")
            
            # Wait 5 minutes before next pass
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Engine pass critical failure: {e}")
            await asyncio.sleep(60)

async def post_init(application: ApplicationBuilder):
    # Set the bot's command menu (the button in the bottom left of Telegram)
    await application.bot.set_my_commands([
        ("opentrades", "🛰 View live active positions"),
        ("list", "📜 List last 10 closed trades"),
        ("stats", "📊 View account performance"),
        ("balance", "💰 Check available USDT balance"),
        ("help", "❓ Get help & command guide"),
        ("settings", "⚙️ Bot settings & privacy"),
        ("docs", "📖 View user manual & tutorials"),
        ("contact", "🤝 Contact @metaverse_sherpa"),
        ("reset", "🔄 Reconfigure API keys"),
    ])
    # This automatically starts the background engine when the Telegram bot boots up
    asyncio.create_task(trading_engine(application))

def main():
    # Ensure database table exists
    database.init_db()

    # Initialize Bot Application with the post_init hook
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Register Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("refer", refer_command))
    app.add_handler(CommandHandler("premium", show_premium_menu))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("docs", docs))
    app.add_handler(CommandHandler("help", docs))
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("reset", setup))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("opentrades", open_trades))
    app.add_handler(CommandHandler("list", list_trades))
    app.add_handler(CommandHandler("backtest", backtest))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("strategy", strategy_command))
    app.add_handler(CommandHandler("contact", contact_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(strategy_callback, pattern="^set_strat_"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^send_blofin_guide|^apply_symbol_audit|^toggle_privacy|^strategy_menu|^toggle_active|^set_risk|^manage_symbols|^tsym_|^back_to_settings|^setex_|^check_balance_setup|^opentrades_menu|^history_menu|^stats_menu|^help_menu|^settings_menu|^contact_menu|^referral_menu|^confirm_panic|^panic_execute|^confirm_close_|^execute_close_|^admin_user_audit|^admin_broadcast_prompt|^admin_command|^admin_gift_prompt|^view_logs|^prompt_admin_wallet|^toggle_undercover|^close_admin|^premium_menu|^check_payment|^prompt_set_wallet"))
    app.add_handler(CallbackQueryHandler(share_callback, pattern="^sh"))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("resume", resume_bot))
    
    # Catch all non-command messages (used for the setup step flow)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    logger.info("Starting Telegram Bot Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

async def close_single_position(chat_id, sym):
    """Tactically closes a single position for a user."""
    user = database.get_user(chat_id)
    if not user: return False, "User not found."
    
    try:
        user_ex = database.get_exchange_client(user)
        # Fetch the specific position
        positions = user_ex.fetch_positions([sym])
        pos = next((p for p in positions if float(p.get("contracts", 0) or 0) != 0), None)
        
        if not pos:
            return False, f"No active position found for {sym}."
            
        side = pos['side'].upper()
        contracts = float(pos['contracts'])
        
        # Market close order
        order_side = "sell" if side == "LONG" else "buy"
        user_ex.create_market_order(sym, order_side, contracts, params={"reduceOnly": True})
        
        return True, f"Market Closed {sym} position."
    except Exception as e:
        return False, f"Failed to close {sym}: {e}"

async def panic_close_all(chat_id):
    """Closes all active positions for a user across all symbols."""
    user = database.get_user(chat_id)
    if not user: return False, "User not found."
    
    try:
        user_ex = database.get_exchange_client(user)
        import live_bot_multi
        
        # Normalize all symbols for this exchange
        norm_syms = [database.normalize_symbol(s, user_ex.id) for s in live_bot_multi.SYMBOLS]
        positions = user_ex.fetch_positions(norm_syms)
        active = [p for p in positions if float(p.get("contracts", 0) or 0) != 0]
        
        if not active:
            return True, "No active trades to close."
            
        results = []
        for p in active:
            try:
                sym = p['symbol']
                side = p['side'].upper()
                contracts = float(p['contracts'])
                
                # Market close order
                order_side = "sell" if side == "LONG" else "buy"
                user_ex.create_market_order(sym, order_side, contracts, params={"reduceOnly": True})
                results.append(f"✅ Closed {sym}")
            except Exception as e:
                results.append(f"❌ Failed {p['symbol']}: {e}")
                
        return True, "\n".join(results)
    except Exception as e:
        return False, f"Critical failure: {e}"
