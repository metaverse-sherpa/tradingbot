import os
import logging
import asyncio
import ccxt.async_support as ccxt
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
import bot_ui
from bot_ui import escape_md_v2, safe_edit_text, get_nav_buttons, get_main_inline_menu, get_admin_keyboard, get_backtest_inline_menu
import time
import sys
from datetime import datetime

# Add scripts directory to path for imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "scripts"))
from audit_3yr_portfolio import run_custom_audit
from sherpa_visual_audit import run_visual_audit
from stock_backtester_daily import run_stock_visual_audit

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", 1567788633))

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

# Removed UI helpers (Moved to bot_ui.py)

async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggers the personalized visual 3-year audit for the user."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
    
    # Calculate starting balance using Capital Allocation Override
    actual_equity = user.get('equity') or 0.0
    if actual_equity <= 100.0:
        actual_equity = 10000.0
        
    eq_type = user.get('custom_equity_type', 'all')
    eq_val = user.get('custom_equity_value')
    
    balance = actual_equity
    if eq_type == 'amount' and eq_val is not None:
        balance = min(float(eq_val), actual_equity)
    elif eq_type == 'pct' and eq_val is not None:
        balance = actual_equity * (float(eq_val) / 100.0)
        
    await trigger_personalized_audit(update, context, user, start_balance=balance)

async def send_master_audit(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id):
    """Sends the institutional-grade 3-year master audit comparison instantly."""
    master_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "upsell_comparison.png")
    audit_msg = (
        "🏔️ *Metaverse Sherpa: Institutional Wealth Gap*\n"
        "Comparison: `Standard (5 Tokens)` vs `Institutional (Full 20-Token Basket)`\n"
        "_Both running at a conservative 1.0% Institutional Risk._\n\n"
        "📊 *Standard Tier (Always Free)*\n"
        "• PnL: *+27.5%* | Sharpe: *3.90*\n"
        "• Assets: 5 Core Institutional Tokens\n\n"
        "💎 *Institutional Tier (Premium Access)*\n"
        "• PnL: *+208.7%* | Sharpe: *1.56*\n"
        "• Assets: Full 20+ 'Sherpa Basket' Tokens\n\n"
        "📈 _Institutional access delivers a **7.6x profit multiplier** by unlocking the full 20-token basket without increasing your risk per trade._"
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

async def trigger_personalized_audit(update: Update, context: ContextTypes.DEFAULT_TYPE, user, start_balance=10000.0, force_asset=None):
    """Runs a 3-year backtest for a specific user's risk and symbols with animation, supporting stock daily backtests."""
    chat_id = user['telegram_chat_id']
    risk = user['risk_pct']
    syms = user['enabled_symbols']
    
    active_crypto = user.get('active_crypto_strategy', 'Mean Reversion Scalper')
    active_stock = user.get('active_stock_strategy', 'None')
    
    # 1. Determine target asset class if force_asset is None
    if force_asset is None:
        if active_crypto != 'None' and active_stock != 'None':
            # Both are active, let user choose!
            context.user_data['backtest_balance'] = start_balance
            kb = [
                [
                    InlineKeyboardButton("🪙 Crypto Backtest", callback_data="run_backtest_crypto"),
                    InlineKeyboardButton("🦙 Stock Backtest", callback_data="run_backtest_stock")
                ],
                [InlineKeyboardButton("⚙️ Back to Settings", callback_data="back_to_settings")]
            ]
            msg = (
                "🔬 *Choose Strategy to Backtest*\n\n"
                "You currently have both **Crypto** and **Stock** strategies active.\n"
                "Please select which 3-year performance audit you would like to run:"
            )
            if update.callback_query:
                await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(kb))
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return
        elif active_stock != 'None':
            force_asset = 'stock'
        else:
            force_asset = 'crypto'
            
    # 2. Check Premium gate based on target asset class
    if force_asset == 'stock':
        is_default = (risk == 1.0 and start_balance == 10000.0)
    else:
        is_default = (risk == 1.5 and len(syms) >= 18 and start_balance == 10000.0)
        
    if not is_default:
        # 💎 Premium Gate with Killer Comparison Visual
        if not database.is_premium(user):
            upsell_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "upsell_comparison.png")
            premium_msg = (
                "🔒 *Premium Feature: Personal Projections*\n\n"
                "The chart above reveals the *Institutional Wealth Gap*.\n\n"
                "📊 *Free Tier (White)*: +27.5% PnL\n"
                "💎 *Premium Tier (Neon)*: +208.7% PnL\n\n"
                "Unlock **7.6x more profit potential** for just **$20/mo**.\n"
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
                            [InlineKeyboardButton("💎 Go Premium", callback_data="premium_menu")]
                        ])
                    )
            else:
                await context.bot.send_message(chat_id=chat_id, text=premium_msg, parse_mode="Markdown")
            return
            
    # 3. Check for Master Audit instantly
    if force_asset == 'stock':
        master_path = os.path.join(BASE_DIR, "results", "stock_master_audit.png")
        # Check root directory too in case it was created there
        if not os.path.exists(master_path):
            master_path = os.path.join(BASE_DIR, "stock_master_audit.png")
            
        if is_default and os.path.exists(master_path):
            audit_msg = (
                "🦙 *Metaverse Sherpa: Stock Institutional 3-Year Audit*\n"
                "Strategy: `Sherpa Velocity Pullback` | Settings: `1.0% Risk`\n\n"
                "Final Equity: *$21,348.60*\n"
                "Total PnL: *+113.5%*\n"
                "Sharpe Ratio: *1.87*\n"
                "Win Rate: *62.4%*\n"
                "Max Drawdown: *14.2%*\n\n"
                "📈 _This simulation represents the core Sherpa Stock algorithm's performance over the last 3 years._"
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
    else:
        master_path = os.path.join(BASE_DIR, "results", "master_audit.png")
        if is_default and os.path.exists(master_path):
            audit_msg = (
                "🏔️ *Metaverse Sherpa: Crypto Institutional 3-Year Audit*\n"
                "Settings: `1.5% Risk` | `All 20 Institutional Tokens`\n\n"
                "Final Equity: *$30,869.74*\n"
                "Total PnL: *+208.7%*\n"
                "Sharpe Ratio: *1.56*\n"
                "Win Rate: *54.9%*\n"
                "Max Drawdown: *23.9%*\n\n"
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

    # 4. Set Animation Frames
    if force_asset == 'stock':
        frames = [
            "🦙 *Sherpa is packing the stock daily swing indicators...*",
            "📊 *Connecting to the historical daily database cache...*",
            "📈 *Running Velocity Pullback scanners on megacaps...*",
            "📉 *Simulating the 2023 pullback opportunities...*",
            "🏛️ *Surviving the 2024 tech volatility and rate spikes...*",
            "🌊 *Calculating dynamic SMA(5) and RSI exits...*",
            "🛡️ *Applying 1.0% institutional risk-sizing rules...*",
            "⚖️ *Measuring Sharpe ratio and maximum drawdown bounds...*",
            "📊 *Plotting your daily stock equity curves...*",
            "🏔️ *Stock strategy projection successfully mapped!*"
        ]
    else:
        frames = [
            "🥾 *Sherpa is packing the quantitative gear...*",
            "🧗‍♂️ *Securing the ropes on the Bollinger bands...*",
            "🏔️ *Climbing the 2023 peaks and valleys...*",
            "📉 *Surviving the 2024 bear traps and liquidation zones...*",
            "📈 *Riding the 2025 parabolic momentum curves...*",
            "🛰️ *Calibrating the Blofin high-frequency antennas...*",
            "💎 *Polishing the institutional risk multipliers...*",
            "📊 *Plotting your private equity curves...*",
            "🗺️ *Mapping out the final risk audits...*",
            "🏔️ *Planting the Sherpa flag at the peak...*"
        ]
        
    status_msg = await context.bot.send_message(
        chat_id=chat_id, 
        text=f"{frames[0]}\n\nProjecting your capital: `${start_balance:,.0f}`",
        parse_mode="Markdown"
    )
    
    # 5. Run the visual audit in background thread
    sim_user_id = "admin" if is_default else chat_id
    if force_asset == 'stock':
        audit_task = asyncio.create_task(asyncio.to_thread(
            run_stock_visual_audit, 
            risk_val_pct=risk, 
            user_id=sim_user_id, 
            start_balance=start_balance
        ))
    else:
        strategy = user.get('active_crypto_strategy', 'Mean Reversion Scalper')
        if strategy == 'None':
            strategy = 'Mean Reversion Scalper'
        audit_task = asyncio.create_task(asyncio.to_thread(
            run_visual_audit, 
            risk, 
            syms, 
            user_id=sim_user_id, 
            start_balance=start_balance, 
            strategy_name=strategy
        ))
        
    idx = 1
    while not audit_task.done():
        await asyncio.sleep(1.5)
        if idx < len(frames):
            try:
                await status_msg.edit_text(f"{frames[idx]}\n\nProjecting your capital: `${start_balance:,.0f}`", parse_mode="Markdown")
                idx += 1
            except:
                pass
                
    try:
        stats, chart_path, df_eq = await audit_task
        if not stats or not chart_path:
            await status_msg.edit_text("❌ Personal audit failed. Check your settings.")
            return

        # 🏔️ Institutional Delta Engine: Compare with Last Audit
        last_stats = None
        if user.get('last_audit_stats'):
            try:
                last_stats = json.loads(user['last_audit_stats'])
            except:
                pass
            
        def get_delta(current, last, is_pct=True, is_dd=False, is_dollar=False):
            if not last: return ""
            diff = current - last
            if abs(diff) < 0.001: return ""
            
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

        advice_note = ""
        if stats['max_dd'] > 25.0:
            dd_line = f"⚠️ *Max Drawdown: {stats['max_dd']:.1f}%{dd_delta}*"
            rec_risk = 1.0 if risk >= 1.49 else max(0.5, round(risk * 0.67 * 2) / 2)
            advice_note = f"\n\n💡 *Risk Management Tip*:\nYour drawdown exceeds the **25.0% cap**. Consider lowering your risk allocation (e.g. **{rec_risk:.2f}%** instead of your current **{risk:.2f}%**) to keep capital drawdowns safely compressed."
        else:
            dd_line = f"Max Drawdown: *{stats['max_dd']:.1f}%*{dd_delta}"

        asset_title = "Stock" if force_asset == 'stock' else "Crypto"
        audit_msg = (
            f"🏔️ *Your Personalized 3-Year {asset_title} Audit*\n"
            f"Start Balance: `${start_balance:,.0f}` | Risk: `{risk:.2f}%`\n\n"
            f"Final Equity: *${stats['final_equity']:,.2f}* ({stats['pnl_pct']:+.1f}%)\n"
            f"Sharpe Ratio: *{stats['sharpe']:.2f}*{sharpe_delta}\n"
            f"Win Rate: *{stats['win_rate']:.1f}%*{win_delta}\n"
            f"{dd_line}"
            f"{advice_note}\n\n"
            f"📈 _This simulation represents your settings applied over the last 3 years of {asset_title.lower()} trading._"
        )
        
        # 💎 Institutional Memory: Update Last Audit Cache
        database.update_last_audit(chat_id, stats)
        
        await status_msg.delete()
        show_risk = stats['max_dd'] > 25.0
        if os.path.exists(chart_path):
            with open(chart_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=chat_id, 
                    photo=photo, 
                    caption=audit_msg, 
                    parse_mode="Markdown", 
                    reply_markup=get_backtest_inline_menu(chat_id, show_risk_button=show_risk)
                )
            if not is_default:
                try:
                    os.remove(chart_path)
                except:
                    pass
        else:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=audit_msg, 
                parse_mode="Markdown", 
                reply_markup=get_backtest_inline_menu(chat_id, show_risk_button=show_risk)
            )
            
    except Exception as e:
        logger.error(f"Personal audit error: {e}")
        await status_msg.edit_text(f"❌ Error during simulation: {e}")
        
# Removed Navigation helpers (Moved to bot_ui.py)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bot_username = (await context.bot.get_me()).username
    
    # 🏔️ Sherpa Admin Alert: Notify on new member arrival
    is_new = database.get_user(chat_id) is None
    if is_new:
        try:
            full_name = update.effective_user.full_name
            username = f"@{update.effective_user.username}" if update.effective_user.username else "No Username"
            
            # Auto-initialize user in DB immediately
            database.upsert_user(chat_id, "", "", "", "blofin", is_active=False, full_name=full_name, username=username)
            
            ref_info = f" (Referrer: `{context.args[0].split('_')[1]}`)" if context.args and context.args[0].startswith("ref_") else ""
            
            admin_msg = (
                "🏔️ *New Sherpa Scout Spotted!*\n\n"
                f"Name: `{full_name}`\n"
                f"User: {username}\n"
                f"ID: `{chat_id}`{ref_info}\n\n"
                "📈 _A new recruit has joined the trail. Awaiting setup..._"
            )
            await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=admin_msg, parse_mode="Markdown")
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
        [InlineKeyboardButton("🔷 Bitget", callback_data="setex_bitget")],
        [InlineKeyboardButton("🦙 Alpaca Stocks", callback_data="setex_alpaca")],
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
    
    if chat_id == SUPER_ADMIN_ID:
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

def clear_input_states(context):
    """Clears all mutually exclusive interactive input states from user_data."""
    for key in ['setting_wallet', 'setting_admin_wallet', 'admin_broadcasting', 'admin_gifting', 'setting_risk', 'setup_step', 'setting_cap_amount', 'setting_cap_pct']:
        context.user_data.pop(key, None)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.effective_message.text.strip()
    
    # --- Capital Fixed Amount Input Validation ---
    if context.user_data.get('setting_cap_amount'):
        try:
            val = float(text)
            if val <= 0:
                raise ValueError()
        except ValueError:
            await update.effective_message.reply_text("❌ *Invalid Amount*: Please enter a valid positive number (e.g. `500`):", parse_mode="Markdown")
            return
            
        # Get actual balance
        user = database.get_user(chat_id)
        actual_balance = user.get('equity') or 0.0
        if val > actual_balance:
            await update.effective_message.reply_text(
                f"❌ *Value Exceeds Balance*\n\n"
                f"You specified **${val:,.2f} USDT**, which exceeds your current exchange account balance of **${actual_balance:,.2f} USDT**.\n\n"
                "Please specify a lower amount (or tap /cancel to abort):",
                parse_mode="Markdown"
            )
            return
            
        database.update_user_preference(chat_id, "custom_equity_type", "amount")
        database.update_user_preference(chat_id, "custom_equity_value", val)
        context.user_data['setting_cap_amount'] = False
        
        await update.effective_message.reply_text(
            f"✅ *Capital Allocation Updated!*\n\n"
            f"The bot will now trade with a fixed capital limit of **${val:,.2f} USDT**.",
            parse_mode="Markdown"
        )
        # Display settings menu
        user = database.get_user(chat_id)
        msg, markup = get_settings_ui(user)
        await update.effective_message.reply_text(msg, reply_markup=markup, parse_mode="Markdown")
        return

    # --- Capital Percentage Input Validation ---
    if context.user_data.get('setting_cap_pct'):
        try:
            val = float(text)
            if val <= 0 or val > 100:
                raise ValueError()
        except ValueError:
            await update.effective_message.reply_text("❌ *Invalid Percentage*: Please enter a valid number between `1` and `100` (e.g. `50`):", parse_mode="Markdown")
            return
            
        database.update_user_preference(chat_id, "custom_equity_type", "pct")
        database.update_user_preference(chat_id, "custom_equity_value", val)
        context.user_data['setting_cap_pct'] = False
        
        await update.effective_message.reply_text(
            f"✅ *Capital Allocation Updated!*\n\n"
            f"The bot will now trade with **{val:.1f}%** of your account balance.",
            parse_mode="Markdown"
        )
        # Display settings menu
        user = database.get_user(chat_id)
        msg, markup = get_settings_ui(user)
        await update.effective_message.reply_text(msg, reply_markup=markup, parse_mode="Markdown")
        return

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
    if context.user_data.get('setting_admin_wallet') and chat_id == SUPER_ADMIN_ID:
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
    
    if step == 101:
        context.user_data['alpaca_endpoint'] = text.strip()
        context.user_data['setup_step'] = 102
        try: await update.effective_message.delete()
        except: pass
        await update.effective_message.reply_text("✅ Endpoint Base URL received.\n\nNow, please paste your **Alpaca API Key ID**:")
        return
        
    elif step == 102:
        context.user_data['alpaca_api_key'] = text.strip()
        context.user_data['setup_step'] = 103
        try: await update.effective_message.delete()
        except: pass
        await update.effective_message.reply_text("✅ Key ID received and wiped from chat history.\n\nFinally, please paste your **Alpaca API Secret Key**:")
        return
        
    elif step == 103:
        alpaca_secret = text.strip()
        try: await update.effective_message.delete()
        except: pass
        
        # Save to DB and Activate
        database.update_user_preference(chat_id, "alpaca_endpoint", context.user_data['alpaca_endpoint'])
        database.update_user_preference(chat_id, "alpaca_api_key", context.user_data['alpaca_api_key'])
        database.update_user_preference(chat_id, "alpaca_api_secret", alpaca_secret)
        database.update_user_preference(chat_id, "exchange_id", "alpaca")
        database.update_user_preference(chat_id, "strategy", "Sherpa Velocity Pullback")
        database.set_active(chat_id, True)
        
        # Admin Alert
        try:
            user_info = update.effective_user
            full_name = user_info.full_name
            username = f"@{user_info.username}" if user_info.username else "No Username"
            act_msg = (
                "🦙 *Alpaca Stocks Activated!*\n\n"
                f"User: `{full_name}` ({username})\n"
                f"ID: `{chat_id}`\n\n"
                "🚀 _Member has configured Alpaca and is now LIVE in the SVP Stock strategy._"
            )
            await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=act_msg, parse_mode="Markdown")
        except: pass
        
        context.user_data.clear()
        
        await update.effective_message.reply_text(
            "🎊 *Setup Complete!*\n\n"
            "The Sherpa is now tracking your Alpaca Stock account. Trades will execute daily at **9:31 AM EST**.\n\n"
            "Your bot is now active and the *Sherpa Velocity Pullback* strategy has been automatically enabled! 🦙📈",
            parse_mode="Markdown"
        )
        
        # Send persistent footer dashboard
        await update.effective_message.reply_text(
            "🛰️ *Main Menu Activated*",
            reply_markup=get_main_inline_menu(chat_id),
            parse_mode="Markdown"
        )
        return

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
            await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=act_msg, parse_mode="Markdown")
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
                # Show settings again
                user = database.get_user(chat_id)
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

async def show_forward_test_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: dict):
    """Displays the bot's global theoretical forward testing performance dashboard."""
    stats_data = database.get_theoretical_stats()
    
    current_balance = stats_data['current_balance']
    wins = stats_data['wins']
    losses = stats_data['losses']
    win_rate = stats_data['win_rate']
    cumulative_pnl = stats_data['cumulative_pnl']
    
    # Calculate % growth since $1k
    growth_pct = ((current_balance - 1000.0) / 1000.0) * 100
    
    msg = (
        "📊 *Bot Forward Test Performance* (Simulated)\n"
        "🏔️ _Simulated paper trading starting from a $1,000 balance_\n\n"
        f"Simulated Balance: *${current_balance:,.2f} USDT*\n"
        f"Simulated Growth: *{growth_pct:+.2f}%*\n"
        f"Win Rate: *{win_rate:.1f}% ({wins} wins | {losses} losses)*\n"
        f"Total Completed: *{wins + losses} trades*\n"
        f"Cumulative PnL: *{cumulative_pnl:+,.2f} USDT*\n\n"
        "💡 *How this works:*\n"
        "The bot automatically forward-tests every 15-minute signal at **1.5% institutional risk**. "
        "Trades open and close purely based on Take Profit and Stop Loss levels.\n\n"
        "🏆 *Link your exchange API keys via /setup to start executing these signals automatically!*"
    )
    
    is_admin = (chat_id == SUPER_ADMIN_ID or (user and user.get('is_admin'))) and not (user and user.get('undercover_mode'))
    keyboard = get_nav_buttons(is_admin=is_admin)
    
    await update.effective_message.reply_text(
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def stats_simulated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explicitly shows simulated stats dashboard to any user."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    await show_forward_test_stats(update, context, chat_id, user)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user or (not user.get('api_key') and not user.get('alpaca_api_key')):
        await show_forward_test_stats(update, context, chat_id, user)
        return
    
    status_msg = await update.effective_message.reply_text("📊 Calculating your performance stats...")

    crypto_msg = ""
    stock_msg = ""
    errors = []
    has_crypto = False

    # 1. Fetch Crypto Stats if API Key exists
    if user.get('api_key') and user.get('api_key') != "":
        has_crypto = True
        realized_daily_pnl = 0.0
        total_unrealized_pnl = 0.0
        open_positions_count = 0
        try:
            ex_id = user.get('exchange_id', 'blofin')
            ex_class = getattr(ccxt, ex_id)
            async with ex_class({
                "apiKey": user['api_key'],
                "secret": user['api_secret'],
                "password": user['api_password'],
                "options": {"defaultType": "swap"},
            }) as user_ex:
                
                now_ms = int(time.time() * 1000)
                twenty_four_hours_ago = now_ms - (24 * 60 * 60 * 1000)
                
                # Fetch Realized PnL fetching for last 24h
                async def fetch_sym_pnl(sym):
                    nonlocal realized_daily_pnl
                    try:
                        params = {'instType': 'SWAP'} if user_ex.id == 'blofin' else {}
                        trades = await user_ex.fetch_my_trades(sym, since=twenty_four_hours_ago, params=params)
                        for t in trades:
                            info = t.get("info", {})
                            gross_pnl = float(info.get("fillPnl") or 0)
                            if gross_pnl != 0:
                                fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                                net_pnl = gross_pnl - (fee * 2)
                                realized_daily_pnl += net_pnl
                    except: pass

                await asyncio.gather(*(fetch_sym_pnl(sym) for sym in live_bot_multi.SYMBOLS))
                
                # Get Total Unrealized PnL from positions
                try:
                    norm_syms = [database.normalize_symbol(sym, user_ex.id) for sym in live_bot_multi.SYMBOLS]
                    positions = await user_ex.fetch_positions(norm_syms)
                    for p in positions:
                        contracts = float(p.get("contracts", 0) or 0)
                        if contracts != 0:
                            open_positions_count += 1
                            total_unrealized_pnl += float(p.get("unrealizedPnl", 0) or 0)
                except: pass
                
            wins = user['wins']
            losses = user['losses']
            cum_pnl_realized = user.get('cum_pnl', 0.0)
            equity = user.get('equity', 200.0)
            
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
            
            flame = " 🔥" if wr > 50 else ""
            
            crypto_msg = (
                f"🪙 *Crypto Wallet ({ex_id.upper()})*\n"
                f"• Overall PnL: *{overall_pnl_pct:+.2f}%{pnl_suffix}*\n"
                f"• Daily PnL: *{daily_pnl_pct:+.2f}%{daily_suffix}*\n"
                f"• Win Rate: *{wr:.1f}%{flame} ({wins} wins | {losses} losses)*\n"
                f"• Open Positions: *{open_positions_count} ({upnl_pct:+.2f}%)*\n"
                f"• Closed Trades: *{total_closed}*\n"
            )
        except Exception as ce:
            errors.append(f"Crypto: {ce}")

    # 2. Fetch Stock Stats if Alpaca API Key exists
    if user.get('alpaca_api_key') and user.get('alpaca_api_key') != "":
        try:
            account = await database.make_alpaca_request_async(user, "GET", "/v2/account")
            positions = await database.make_alpaca_request_async(user, "GET", "/v2/positions")
            orders = await database.make_alpaca_request_async(user, "GET", "/v2/orders", params={"status": "closed", "limit": 100})
            
            stock_equity = float(account.get("equity", 0) or account.get("portfolio_value", 0))
            last_equity = float(account.get("last_equity", 0) or stock_equity)
            
            stock_daily_pnl = stock_equity - last_equity
            stock_daily_pnl_pct = (stock_daily_pnl / last_equity * 100) if last_equity > 0 else 0.0
            
            stock_unrealized = sum(float(p.get("unrealized_pl", 0) or p.get("unrealized_intraday_pl", 0) or 0) for p in positions)
            stock_open_count = len(positions)
            stock_closed_count = len(orders)
            
            # Estimate overall growth based on starting stock equity (default $10k if not specified)
            start_equity = 10000.0
            overall_stock_pnl = stock_equity - start_equity
            overall_stock_pnl_pct = (overall_stock_pnl / start_equity * 100)
            
            hide = user.get('hide_dollars', False)
            equity_str = f"{stock_equity:,.2f}" if not hide else "||HIDDEN||"
            daily_pnl_str = f"{stock_daily_pnl_pct:+.2f}%" + (f" (${stock_daily_pnl:+.2f})" if not hide else "")
            overall_pnl_str = f"{overall_stock_pnl_pct:+.2f}%" + (f" (${overall_stock_pnl:+.2f})" if not hide else "")
            unrealized_str = f"{stock_unrealized:+.2f}" if not hide else "||HIDDEN||"
            
            stock_msg = (
                f"🦙 *Stock Account (Alpaca)*\n"
                f"• Portfolio Value: *${equity_str}* USD\n"
                f"• Overall PnL: *{overall_pnl_str}* _(from $10k base)_\n"
                f"• Daily PnL: *{daily_pnl_str}*\n"
                f"• Open Positions: *{stock_open_count}* (_${unrealized_str}_ unrealized)\n"
                f"• Closed Orders: *{stock_closed_count}* recent\n"
            )
        except Exception as se:
            errors.append(f"Stocks: {se}")

    # Build final message
    msg_parts = ["📊 *Your Live Portfolio Performance* 📊\n"]
    if crypto_msg:
        msg_parts.append(crypto_msg)
    if stock_msg:
        msg_parts.append(stock_msg)
        
    if errors:
        msg_parts.append("\n⚠️ *Some queries failed*:")
        for err in errors:
            msg_parts.append(f"_• {str(err)}_")

    msg = "\n".join(msg_parts)
    
    # Configure navigation buttons
    is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
    
    if has_crypto and 'overall_pnl_pct' in locals():
        cb_data = f"shs_{overall_pnl_pct:.2f}_{daily_pnl_pct:.2f}_{wr:.1f}_{total_closed}"
        keyboard = [
            [InlineKeyboardButton("📸 Share & Earn", callback_data=cb_data)],
            *get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin)
        ]
    else:
        keyboard = get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin)

    await status_msg.delete()
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
    
    if user.get('exchange_id') == 'alpaca':
        try:
            orders = await database.make_alpaca_request_async(user, "GET", "/v2/orders", params={"status": "closed", "limit": 20})
            if not orders:
                await status_msg.edit_text("No recently executed stock trades found in your Alpaca account.")
                return
            
            lines = ["🦙 *Recent Alpaca Stock Orders:*"]
            for o in orders:
                sym = o.get("symbol")
                side = o.get("side", "").upper()
                qty = o.get("filled_qty") or o.get("qty")
                price = o.get("filled_avg_price") or o.get("limit_price") or "0"
                t_str = o.get("filled_at") or o.get("updated_at") or ""
                date_part = t_str.split("T")[0] if "T" in t_str else t_str
                
                emoji = "🟢" if side == "BUY" else "🔴"
                try:
                    price_val = float(price)
                except:
                    price_val = 0.0
                lines.append(f"{emoji} *{side}* {sym} | Qty: `{qty}` | Price: `${price_val:.2f}` | Date: `{date_part}`")
                
            await status_msg.delete()
            await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=get_main_inline_menu(chat_id))
            return
        except Exception as e:
            await status_msg.edit_text(f"❌ Error fetching Alpaca history: {e}")
            return

    try:
        async with database.get_exchange_client(user) as user_ex:
            await user_ex.load_markets()
            
            import live_bot_multi
            all_closed = []
            
            async def fetch_sym_history(sym):
                try:
                    norm_sym = database.normalize_symbol(sym, user_ex.id)
                    trades = await user_ex.fetch_my_trades(norm_sym, limit=50)
                    
                    order_groups = {}
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
                            
                            order_id = t.get('order') or t.get('id') or f"{t['timestamp']}_{sym}"
                            if order_id not in order_groups:
                                order_groups[order_id] = []
                                
                            order_groups[order_id].append({
                                "net_pnl": net_pnl,
                                "price": t['price'],
                                "amount": t['amount'],
                                "timestamp": t['timestamp'],
                                "is_long": is_long
                            })
                            
                    for order_id, fills in order_groups.items():
                        total_net_pnl = sum(f['net_pnl'] for f in fills)
                        total_amount = sum(f['amount'] for f in fills)
                        total_cost = sum(f['price'] * f['amount'] for f in fills)
                        avg_price = total_cost / total_amount if total_amount > 0 else fills[0]['price']
                        
                        max_timestamp = max(f['timestamp'] for f in fills)
                        is_long = fills[0]['is_long']
                        
                        try:
                            market = user_ex.market(sym)
                            contract_size = float(market.get('contractSize', 1))
                            initial_margin = (avg_price * total_amount * contract_size) / 20
                            roe_val = (total_net_pnl / initial_margin) * 100 if initial_margin > 0 else 0
                        except:
                            roe_val = 0
                            
                        all_closed.append({
                            "symbol": sym,
                            "timestamp": max_timestamp,
                            "net_pnl": total_net_pnl,
                            "price": avg_price,
                            "amount": total_amount,
                            "side": "l" if is_long else "s",
                            "roe_val": roe_val
                        })
                except: pass

            await asyncio.gather(*(fetch_sym_history(sym) for sym in live_bot_multi.SYMBOLS))
                 
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
            f"{i+1}\\. *{sym_v2}* {dir_icon} \\| _{dt}_\n"
            f"{status_icon} PnL: ||{pnl_val_v2}|| \\(*{roe_v2}*\\)\n"
            f"\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n"
        )
        
        win_icon = " 🏆" if t['net_pnl'] > 0 else ""
        cb_data = f"shc_{t['symbol']}_{t['side']}_{t['roe_val']:.2f}_{t['price']:.4f}_{t['price']:.4f}_{t['net_pnl']:.2f}"
        buttons.append(InlineKeyboardButton(f"{i+1}-{sym_v2}{win_icon}", callback_data=cb_data))
        
    history_text += "\n*Tap a button below to Share & Earn 📸*"
    
    is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
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
    
    if user.get('exchange_id') == 'alpaca':
        try:
            positions = await database.make_alpaca_request_async(user, "GET", "/v2/positions")
            active = [p for p in positions if float(p.get("qty", 0)) != 0]
            
            if not active:
                await update.effective_message.reply_text("🏔️ *Sherpa is scanning the mountains and valleys for the next high-probability stock trade.*\n\nYou have no active stock trades at the moment.", parse_mode="Markdown", reply_markup=get_main_inline_menu(chat_id))
                return
                
            await update.effective_message.reply_text(
                f"🛰 *Active Stock Trades Found: {len(active)}*",
                parse_mode="Markdown"
            )
            
            orders = []
            try:
                orders = await database.make_alpaca_request_async(user, "GET", "/v2/orders", params={"status": "open"})
            except Exception as e:
                logger.error(f"Failed to fetch Alpaca open orders: {e}")
                
            for p in active:
                try:
                    sym = p['symbol']
                    qty = float(p['qty'])
                    entry = float(p['avg_entry_price'])
                    upnl = float(p['unrealized_pl'])
                    side = p['side'].upper()
                    
                    tp_price = 0
                    sl_price = 0
                    for o in orders:
                        if o.get("symbol") == sym:
                            if o.get("type") == "stop" and o.get("side") == "sell":
                                sl_price = float(o.get("stop_price") or 0)
                            elif o.get("type") == "limit" and o.get("side") == "sell":
                                tp_price = float(o.get("limit_price") or 0)
                                
                    target_roe_str = "N/A"
                    target_pnl_dollars = 0.0
                    if tp_price > 0:
                        target_roe = ((tp_price - entry) / entry) * 100 if side == "LONG" else ((entry - tp_price) / entry) * 100
                        target_roe_str = f"{target_roe:+.1f}%"
                        target_pnl_dollars = (entry * qty) * (target_roe / 100)
                        
                    initial_margin = entry * qty
                    roe = (upnl / initial_margin * 100) if initial_margin > 0 else 0
                    
                    upnl_v2 = escape_md_v2(f"{upnl:+.2f}")
                    roe_v2 = escape_md_v2(f"{roe:+.2f}")
                    target_pnl_v2 = escape_md_v2(f"{target_pnl_dollars:+.2f}")
                    target_roe_v2 = escape_md_v2(target_roe_str)
                    sym_v2 = escape_md_v2(sym)
                    
                    caption = (
                        f"{'🟢' if side.lower() == 'long' else '🔴'} *{sym_v2} \\({side.upper()}\\)*\n"
                        f"PnL: ||{upnl_v2}|| USD \\({roe_v2}%\\) of ||{target_pnl_v2}|| \\({target_roe_v2}\\) Target"
                    )
                    
                    kb = [[InlineKeyboardButton(f"❌ Market Close {sym}", callback_data=f"confirm_close_{sym}")]]
                    await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
                except Exception as e:
                    logger.error(f"Error processing Alpaca position: {e}")
            return
        except Exception as e:
            await update.effective_message.reply_text(f"❌ Error checking Alpaca positions: {e}")
            return

    try:
        async with database.get_exchange_client(user) as user_ex:
            await user_ex.load_markets()
            
            import live_bot_multi
            import charting
            import os
            
            # Normalize all symbols for this exchange
            norm_syms = [database.normalize_symbol(s, user_ex.id) for s in live_bot_multi.SYMBOLS]
            positions = await user_ex.fetch_positions(norm_syms)
            active = [p for p in positions if float(p.get("contracts", 0) or 0) != 0]
            
            if not active:
                await update.effective_message.reply_text("🏔️ *Sherpa is scanning the mountains and valleys for the next high-probability trade.*\n\nYou have no active trades at the moment.", parse_mode="Markdown", reply_markup=get_main_inline_menu(chat_id))
                return
                
            await update.effective_message.reply_text(
                f"🛰 *Active Trades Found: {len(active)}*\nGenerating charts...",
                parse_mode="Markdown"
            )

            async def process_active_position(p):
                try:
                    sym = p['symbol']
                    side = p['side'].upper()
                    entry = float(p['entryPrice'] or 0)
                    upnl = float(p['unrealizedPnl'] or 0)
                    
                    market = user_ex.market(sym)
                    contract_size = float(market.get('contractSize', 1))
                    initial_margin = (entry * float(p['contracts']) * contract_size) / live_bot_multi.LEVERAGE
                    roe = (upnl / initial_margin * 100) if initial_margin > 0 else 0
                    
                    # 2. Fetch TP/SL Prices
                    tp_price = 0
                    sl_price = 0
                    target_roe_str = "N/A"
                    
                    try:
                        all_tpsl = await user_ex.private_get_trade_orders_tpsl_pending({"instType": "SWAP"})
                        if all_tpsl and "data" in all_tpsl:
                            for o in all_tpsl["data"]:
                                if o.get('instId') == market['id']:
                                    tp = float(o.get('tpTriggerPrice') or 0)
                                    sl = float(o.get('slTriggerPrice') or 0)
                                    if tp > 0: tp_price = tp
                                    if sl > 0: sl_price = sl
                        
                        if tp_price > 0:
                            target_roe = ((tp_price - entry) / entry) * live_bot_multi.LEVERAGE * 100 if side == "LONG" else ((entry - tp_price) / entry) * live_bot_multi.LEVERAGE * 100
                            target_roe_str = f"{target_roe:+.1f}%"
                    except: pass

                    # 3. Generate the Chart (Async)
                    try:
                        open_ts = int(p.get('info', {}).get('createTime') or 0)
                        ohlcv = await user_ex.fetch_ohlcv(sym, timeframe='15m', limit=100)
                        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        chart_path = await asyncio.to_thread(charting.generate_trade_chart, sym, df, entry, tp_price, sl_price, side, open_ts)
                    except Exception as e:
                        logger.error(f"Chart generation failed for {sym}: {e}")
                        chart_path = None

                    # 4. Final Output
                    target_pnl_dollars = initial_margin * (float(target_roe_str.strip("%")) / 100) if target_roe_str != "N/A" else 0
                    upnl_v2 = escape_md_v2(f"{upnl:+.2f}")
                    roe_v2 = escape_md_v2(f"{roe:+.2f}")
                    target_pnl_v2 = escape_md_v2(f"{target_pnl_dollars:+.2f}")
                    target_roe_v2 = escape_md_v2(target_roe_str)
                    sym_v2 = escape_md_v2(sym)
                    
                    caption = (
                        f"{'🟢' if side.lower() == 'long' else '🔴'} *{sym_v2} \\({side.upper()}\\)*\n"
                        f"PnL: ||{upnl_v2}|| USDT \\({roe_v2}%\\) of ||{target_pnl_v2}|| \\({target_roe_v2}\\) Target"
                    )
                    
                    # Keyboard for tactical management
                    kb = [[InlineKeyboardButton(f"❌ Market Close {sym}", callback_data=f"confirm_close_{sym}")]]
                    
                    if chart_path and os.path.exists(chart_path):
                        with open(chart_path, 'rb') as photo:
                            await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
                    else:
                        await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
                except Exception as e:
                    logger.error(f"Position processing error for {p.get('symbol')}: {e}")

            await asyncio.gather(*(process_active_position(p) for p in active))
            
    except Exception as e:
        logger.error(f"Error checking open trades: {e}")
        await update.effective_message.reply_text(f"❌ Error fetching positions: {e}")
        # 4. Finally send the footer once
        await update.effective_message.reply_text("🛰️ *Sherpa Command Center*", reply_markup=get_main_inline_menu(chat_id), parse_mode="Markdown")

async def strategy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("Please run /setup first.")
        return
        
    active_crypto = user.get('active_crypto_strategy', 'Mean Reversion Scalper')
    active_stock = user.get('active_stock_strategy', 'None')
    risk_val = user.get('risk_pct', 1.5)
    
    keyboard = [
        [
            InlineKeyboardButton("🪙 Mean Rev" + (" (Active)" if active_crypto == "Mean Reversion Scalper" else ""), callback_data="set_strat_mean"),
            InlineKeyboardButton("🪙 Valkyrie" + (" (Active)" if active_crypto == "Valkyrie Elite Scalper" else ""), callback_data="set_strat_valk"),
        ],
        [InlineKeyboardButton("⏸️ Pause Crypto Strategy" + (" (Paused)" if active_crypto == "None" else ""), callback_data="set_strat_crypto_pause")],
        [
            InlineKeyboardButton("🦙 Alpaca Stock" + (" (Active)" if active_stock == "Sherpa Velocity Pullback" else ""), callback_data="set_strat_svp"),
            InlineKeyboardButton("⏸️ Pause Stock Strategy" + (" (Paused)" if active_stock == "None" else ""), callback_data="set_strat_stock_pause")
        ],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.effective_message.reply_text(
        "🎯 *Simultaneous Strategy Manager*\n\n"
        "Our engine supports running **one active crypto strategy** and **one active stock strategy** concurrently!\n\n"
        "🪙 *Crypto Strategy Engine* (Blofin/Bitget)\n"
        f"• Current: *{active_crypto}*\n"
        "• Execution: 24/7 background scalper.\n\n"
        "🦙 *Stock Strategy Engine* (Alpaca)\n"
        f"• Current: *{active_stock}*\n"
        "• Execution: Daily swing-trades at 9:31 AM EST.\n\n"
        f"⚖️ *Current Risk*: `{risk_val:.2f}% per trade`\n\n"
        "Use the controls below to independently activate or pause each engine:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def strategy_guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a sequential visual walkthrough of both active strategies with pre-rendered infographics."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("Please run /setup first.")
        return
        
    intro_text = (
        "📖 *Sherpa Strategy Guide & Comparison*\n\n"
        "Choose the algorithm that best aligns with your risk tolerance and market outlook:\n\n"
        "📈 *Mean Reversion Scalper*\n"
        "• *Philosophy*: Mean Reversion. Assumes that prices that deviate excessively from the 20-period Bollinger Bands will snap back (revert) to the 200 EMA trend-line.\n"
        "• *Indicators*: Bollinger Bands + EMA 200 + ADX trend strength + Wilder RSI.\n"
        "• *Pace*: Highly active. Averages ~0.84 trades/day.\n"
        "• *Drawdown Profile*: Optimized for recommended **1.0% risk**, maintaining a safe drawdown of **~21.9%** (well below the 25% safety ceiling) while delivering **+384.1%** PnL."
    )
    valk_text = (
        "🛡️ *Valkyrie Elite Scalper*\n"
        "• *Philosophy*: Wick Rejection. Targets high-integrity trend continuation pullbacks on high-volume assets. It waits for price spikes to pierce the bands and quickly close back inside.\n"
        "• *Indicators*: Bollinger Bands + Volatility Squeeze + Wick piercing verification + ADX + standard RSI.\n"
        "• *Pace*: Patient and calculated. Averages ~0.68 trades/day.\n"
        "• *Drawdown Profile*: Highly protected; ultra-low peak drawdown ceiling (~16.2% to 19.5% on expanded basket)."
    )
    stock_text = (
        "🦙 *Sherpa Velocity Pullback (SVP)*\n"
        "• *Philosophy*: Momentum Pullback. Targets short-term, institutional-grade oversold pullback cycles on megacap US equities (NASDAQ/NYSE top 40) during robust, verified long-term uptrends.\n"
        "• *Indicators*: Daily Close > EMA(50) AND EMA(50) > EMA(200), 3-period Wilder RSI (< 10).\n"
        "• *Pace*: Daily swing. Executes scans daily at market open (9:31 AM EST).\n"
        "• *Drawdown Profile*: Ultra-safe equity curve, maintaining a tight **14.2%** maximum drawdown with a verified **+113.5%** return and high **66.9%** win rate over a 3-year period."
    )
    matrix_text = (
        "📊 *Comparative Matrix:*\n"
        "• *Focus*: Volatility Extremes vs Wick Rejection vs Equities Pullbacks\n"
        "• *Active Basket*: 29-Token Basket vs 7-Token Premium vs NASDAQ/NYSE Top 40\n"
        "• *Trigger Logic*: Close outside bands vs Wick pierce & close inside vs 3-Period RSI < 10\n"
        "• *Risk Profile*: Crypto Scalper (21.9% DD) vs Safe Crypto Scalper (19.5% DD) vs Stock Daily Swing (14.2% DD)\n\n"
        "💡 _Recommendation_: Use *Mean Reversion* if you prefer maximum trade frequency and compounding potential. Use *Valkyrie Elite* if you prioritize capital safety and smooth growth curves in crypto. Activate *Sherpa Velocity Pullback (SVP)* to diversify into high-liquidity megacap US equities with low drawdown."
    )
    
    kb = [
        [InlineKeyboardButton("🔙 Back to Strategy Menu", callback_data="strategy_menu")],
        *get_nav_buttons(user.get('has_open_positions', False))
    ]
    
    chart_path = os.path.join(BASE_DIR, "results", "strategy_comparison.png")
    mr_path = os.path.join(BASE_DIR, "results", "mean_reversion_infographic.png")
    valk_path = os.path.join(BASE_DIR, "results", "valkyrie_elite_infographic.png")
    stock_path = os.path.join(BASE_DIR, "results", "stock_strategy_infographic.png")
    
    try:
        if not os.path.exists(chart_path):
            from sherpa_visual_audit import generate_strategy_comparison_chart
            await asyncio.to_thread(generate_strategy_comparison_chart)
            
        photo_ids = []
        
        # 1. Send the comparison visual chart first
        with open(chart_path, 'rb') as photo:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption="📊 *Metaverse Sherpa: 3-Year Strategy Comparison Visual*",
                parse_mode="Markdown"
            )
            photo_ids.append(msg.message_id)
        
        # 2. Send Intro & Mean Reversion text description
        await context.bot.send_message(
            chat_id=chat_id,
            text=intro_text,
            parse_mode="Markdown"
        )
        
        # 3. Send Mean Reversion Infographic
        with open(mr_path, 'rb') as photo:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo
            )
            photo_ids.append(msg.message_id)
        
        # 4. Send Valkyrie Elite text description
        await context.bot.send_message(
            chat_id=chat_id,
            text=valk_text,
            parse_mode="Markdown"
        )
        
        # 5. Send Valkyrie Elite Infographic
        with open(valk_path, 'rb') as photo:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo
            )
            photo_ids.append(msg.message_id)
            
        # 6. Send Sherpa Velocity Pullback text description
        await context.bot.send_message(
            chat_id=chat_id,
            text=stock_text,
            parse_mode="Markdown"
        )
        
        # 7. Send Sherpa Velocity Pullback Infographic
        with open(stock_path, 'rb') as photo:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo
            )
            photo_ids.append(msg.message_id)
        
        # 8. Send Comparative Matrix & final keyboard menu
        await context.bot.send_message(
            chat_id=chat_id,
            text=matrix_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        
        context.user_data['strategy_guide_photo_ids'] = photo_ids
    except Exception as e:
        logger.error(f"❌ Error in /strategyguide command: {e}")
        # Fallback
        guide_text = (
            "📖 *Sherpa Strategy Guide & Comparison*\n\n"
            "📈 *Mean Reversion Scalper*\n"
            "• Philosophy: Revert to 200 EMA from overextended Bollinger Bands.\n\n"
            "🛡️ *Valkyrie Elite Scalper*\n"
            "• Philosophy: Wick rejection pullbacks during squeezes.\n\n"
            "🦙 *Sherpa Velocity Pullback*\n"
            "• Philosophy: Momentum pullbacks on megacap US equities.\n\n"
            "Full visual and interactive infographics are displayed in the sequential guide above."
        )
        await update.effective_message.reply_text(
            guide_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )

async def strategy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat.id
    user = database.get_user(chat_id)
    if not user:
        return
        
    current_risk = user.get('risk_pct', 1.5)
    
    if query.data == "set_strat_mean":
        database.update_user_crypto_strategy(chat_id, "Mean Reversion Scalper")
        msg = "✅ Crypto strategy set to: *Mean Reversion Scalper*"
        
        # Proactive Risk Mismatch Warning for Mean Reversion (Recommends 1.0%)
        if abs(current_risk - 1.0) > 0.01:
            msg += (
                "\n\n⚠️ *Risk Mismatch Detected!*\n"
                f"Your current risk-per-trade is set to **{current_risk:.2f}%**, but the Mean Reversion Scalper recommends a **1.00%** risk allocation to prevent excessive drawdowns.\n\n"
                "Would you like to instantly align your risk settings?"
            )
            keyboard = [
                [InlineKeyboardButton("⚖️ Update Risk to 1.00%", callback_data="set_risk_to_1.0")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]
            ]
            await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id))
            
    elif query.data == "set_strat_valk":
        database.update_user_crypto_strategy(chat_id, "Valkyrie Elite Scalper")
        msg = "✅ Crypto strategy set to: *Valkyrie Elite Scalper*"
        
        # Proactive Risk Mismatch Warning for Valkyrie (Recommends 1.5%)
        if abs(current_risk - 1.5) > 0.01:
            msg += (
                "\n\n⚠️ *Risk Mismatch Detected!*\n"
                f"Your current risk-per-trade is set to **{current_risk:.2f}%**, but the Valkyrie Elite Scalper recommends a **1.50%** risk allocation to maximize compounding efficiency safely.\n\n"
                "Would you like to instantly align your risk settings?"
            )
            keyboard = [
                [InlineKeyboardButton("⚖️ Update Risk to 1.50%", callback_data="set_risk_to_1.5")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]
            ]
            await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id))
            
    elif query.data == "set_strat_crypto_pause":
        database.update_user_crypto_strategy(chat_id, "None")
        msg = "⏸️ Crypto strategy has been *Paused*!"
        await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id))
        
    elif query.data == "set_strat_stock_pause":
        database.update_user_stock_strategy(chat_id, "None")
        msg = "⏸️ Stock strategy has been *Paused*!"
        await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id))
        
    elif query.data == "set_strat_svp":
        # Check if the user has Alpaca credentials set
        if not user.get('alpaca_api_key') or not user.get('alpaca_api_secret') or not user.get('alpaca_endpoint'):
            # Start Alpaca onboarding flow!
            context.user_data['exchange_id'] = 'alpaca'
            context.user_data['setup_step'] = 101
            guide = (
                "🦙 *Alpaca API Setup Required*\n\n"
                "To run the **Sherpa Velocity Pullback** stock strategy, you must first connect your Alpaca trading account.\n\n"
                "Please paste your **Alpaca API Endpoint Base URL** below to begin setup:\n"
                "• Paper Trading: `https://paper-api.alpaca.markets`\n"
                "• Live Trading: `https://api.alpaca.markets`"
            )
            await safe_edit_text(update, context, guide)
            return
        else:
            database.update_user_stock_strategy(chat_id, "Sherpa Velocity Pullback")
            msg = "✅ Stock strategy set to: *Sherpa Velocity Pullback* (Alpaca Stocks) 🦙📈"
            await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id))
            
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

async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Super Admin only: Promotes a user to Admin."""
    chat_id = update.effective_chat.id
    if chat_id != SUPER_ADMIN_ID: return
    
    if not context.args:
        await update.message.reply_text("Usage: `/promote <chat_id>`", parse_mode="Markdown")
        return
        
    try:
        target_id = int(context.args[0])
        database.set_admin_status(target_id, True)
        await update.message.reply_text(f"✅ User `{target_id}` promoted to Admin.", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_id, text="💎 *Promotion Success*\nYou have been granted Admin privileges by the Super Admin.", parse_mode="Markdown")
        except: pass
    except:
        await update.message.reply_text("❌ Invalid Chat ID.")

async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Super Admin only: Demotes a user from Admin status."""
    chat_id = update.effective_chat.id
    if chat_id != SUPER_ADMIN_ID: return
    
    if not context.args:
        await update.message.reply_text("Usage: `/demote <chat_id>`", parse_mode="Markdown")
        return
        
    try:
        target_id = int(context.args[0])
        database.set_admin_status(target_id, False)
        await update.message.reply_text(f"✅ User `{target_id}` demoted from Admin.", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Invalid Chat ID.")

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
    except: pass

async def show_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gated dashboard for the Sherpa Overlord."""
    chat_id = update.effective_chat.id
    if chat_id != SUPER_ADMIN_ID: return
    
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
                        # Official USDT TRC-20 Contract
                        if contract == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t":
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
    
    # 🧪 Simulated Forward Testing Analytics
    theory_stats = database.get_theoretical_stats()
    open_theory_count = len(database.get_open_theoretical_trades())
    growth_pct = ((theory_stats['current_balance'] - 1000.0) / 1000.0) * 100
    
    mr_stats = database.get_theoretical_stats_by_strategy("Mean Reversion Scalper")
    vk_stats = database.get_theoretical_stats_by_strategy("Valkyrie Elite Scalper")
    svp_stats = database.get_theoretical_stats_by_strategy("Sherpa Velocity Pullback")
    
    last_sync = time.strftime('%H:%M:%S')
    admin_msg = (
        "👑 *Sherpa Overlord Mission Control*\n\n"
        f"Identity Status: *{admin_status}*\n\n"
        "📊 *Platform Analytics*\n"
        f"• Total Users: `{stats['total_users']}`\n"
        f"• Total Referrals: `{stats['total_referrals']}`\n"
        f"• Active Premium: `{stats['premium_users']}`\n"
        f"• Last Deploy: *2026-05-14 10:08*\n\n"
        "🧪 *Simulated Forward Testing*\n"
        f"• Compounding Balance: *${theory_stats['current_balance']:,.2f} USDT* ({growth_pct:+.2f}%)\n"
        f"• Open Simulated Trades: `{open_theory_count} open`\n\n"
        "📈 *Mean Reversion Scalper*\n"
        f"• Win Rate: `{mr_stats['win_rate']:.1f}%` ({mr_stats['wins']} W | {mr_stats['losses']} L)\n"
        f"• Cumulative PnL: `+{mr_stats['cumulative_pnl']:+.2f} USDT`\n\n"
        "🛡️ *Valkyrie Elite Scalper*\n"
        f"• Win Rate: `{vk_stats['win_rate']:.1f}%` ({vk_stats['wins']} W | {vk_stats['losses']} L)\n"
        f"• Cumulative PnL: `+{vk_stats['cumulative_pnl']:+.2f} USDT`\n\n"
        "🦙 *Sherpa Velocity Pullback*\n"
        f"• Win Rate: `{svp_stats['win_rate']:.1f}%` ({svp_stats['wins']} W | {svp_stats['losses']} L)\n"
        f"• Cumulative PnL: `+{svp_stats['cumulative_pnl']:+.2f} USDT`\n\n"
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
    
    # Clean up strategy guide photos if the user clicks any action other than view_strategy_guide
    if query.data != "view_strategy_guide":
        photo_ids = context.user_data.pop('strategy_guide_photo_ids', [])
        for photo_id in photo_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=photo_id)
            except:
                pass
                
    # Clean up admin simulated trade photos when leaving
    if query.data != "admin_view_simulated_trades":
        sim_photo_ids = context.user_data.pop('admin_simulated_photo_ids', [])
        for photo_id in sim_photo_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=photo_id)
            except:
                pass
                
    if query.data.startswith("set_risk_to_"):
        try:
            val = float(query.data.split("_")[-1])
            database.update_user_preference(chat_id, "risk_pct", val)
            await query.answer(f"✅ Risk aligned to {val:.2f}%!")
            user = database.get_user(chat_id)
            
            # Setup dynamic confirmation message with inline keyboard
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
            return
        except Exception as e:
            logger.error(f"Error handling set_risk_to_ callback: {e}")
            await query.answer("❌ Error updating risk settings.", show_alert=True)
            return

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

    if query.data == "admin_get_link":
        if chat_id != SUPER_ADMIN_ID: return
        await query.answer()
        bot_username = (await context.bot.get_me()).username
        deep_link = f"https://t.me/{bot_username}?start=guide_blofin"
        msg = (
            "🔗 *Marketing Deep-Link*\n\n"
            "This link will instantly deliver the Blofin Guide to prospective users.\n\n"
            "Tap to Copy:\n"
            f"`{deep_link}`"
        )
        await query.message.reply_text(msg, parse_mode="Markdown")
        return

    if query.data == "admin_command":
        if chat_id != SUPER_ADMIN_ID: return
        await admin_command(update, context)
        return

    if query.data == "admin_user_audit":
        if chat_id != SUPER_ADMIN_ID: return
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
            msg += f"• `{u['telegram_chat_id']}` \\| *{name}*{uname}\n  Status: {status} \\| Tier: {tier}\n"
            
            # 🤝 Display Referral Tree
            if u.get('recruit_list'):
                msg += "  *Recruits:* \n"
                for rec in u['recruit_list']:
                    r_name = escape_md_v2(rec.get('full_name') or "Unknown")
                    r_uname = escape_md_v2(f" (@{rec['username']})") if rec.get('username') else ""
                    msg += f"  └\\─ {r_name}{r_uname} \\(`{rec['telegram_chat_id']}`\\)\n"
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
        if chat_id != SUPER_ADMIN_ID: return
        clear_input_states(context)
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
        clear_input_states(context)
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
        if chat_id != SUPER_ADMIN_ID: return
        await query.answer("🔍 Fetching Mission Logs...")
        try:
            import subprocess
            from telegram.helpers import escape_markdown
            # Get last 50 lines of journalctl for better visibility
            logs = subprocess.check_output(["journalctl", "-u", "tradingbot", "-n", "50", "--no-pager"], text=True)
            safe_logs = escape_markdown(logs, version=2)
            
            kb = [[InlineKeyboardButton("🔄 Refresh Logs", callback_data="view_logs")],
                  [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_command")]]
            
            msg = f"📋 *Sherpa Operational Logs* \\(Last 50 Lines\\)\n\n```\n{safe_logs}\n```"
            
            if query.message.text and "Operational Logs" in query.message.text:
                await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="MarkdownV2")
            else:
                await query.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to fetch logs: {e}")
        return

    if query.data == "apply_symbol_audit":
        await query.answer("🏔️ Settings Applied!")
        try:
            user = database.get_user(chat_id)
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
        clear_input_states(context)
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
        if chat_id != SUPER_ADMIN_ID: return
        clear_input_states(context)
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
        if chat_id != SUPER_ADMIN_ID: 
            logger.warning(f"UNAUTHORIZED TOGGLE ATTEMPT: {chat_id}")
            return
        database.toggle_undercover(chat_id)
        await query.answer("🔄 Identity Toggled!")
        await show_admin_dashboard(update, context)
        return

    if query.data == "admin_view_simulated_trades":
        if chat_id != SUPER_ADMIN_ID and not (user and user.get('is_admin')):
            logger.warning(f"UNAUTHORIZED SIMULATED TRADES ACCESS ATTEMPT: {chat_id}")
            return
        
        await query.answer("Fetching simulated trades...")
        open_trades = database.get_open_theoretical_trades()
        trades = database.get_recent_theoretical_trades(10)
        
        photo_ids = []
        
        if open_trades:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🛰️ *Active Simulated Trades Found: {len(open_trades)}*\nGenerating progress charts...",
                parse_mode="Markdown"
            )
            
            import live_bot_multi
            import charting
            import os
            
            mdm = live_bot_multi.MarketDataManager()
            try:
                for t in open_trades:
                    sym = t['symbol']
                    side = t['side']
                    entry = t['entry_price']
                    tp = t['tp_price']
                    sl = t['sl_price']
                    open_ts = t['open_time']
                    pos_size = t['position_size']
                    strat = t['strategy']
                    
                    df_chart = await mdm.fetch_ohlcv(sym, "15m")
                    if df_chart is None:
                        continue
                        
                    current = df_chart['close'].iloc[-1]
                    pnl_raw = current - entry if side == 'buy' or side == 'long' else entry - current
                    pnl_pct = (pnl_raw / entry) * 100
                    pnl_usdt = pos_size * pnl_raw
                    
                    side_str = "LONG" if side == 'buy' or side == 'long' else "SHORT"
                    
                    chart_file = None
                    try:
                        chart_file = await asyncio.to_thread(
                            charting.generate_trade_chart,
                            sym,
                            df_chart,
                            entry,
                            tp,
                            sl,
                            side_str,
                            open_ts=open_ts
                        )
                    except Exception as chart_err:
                        logger.error(f"Simulated chart generation failed for {sym}: {chart_err}")
                    
                    caption = (
                        f"🧪 *ACTIVE SIMULATED POSITION* (Forward Test)\n"
                        f"🤖 Strategy: *{strat}*\n\n"
                        f"{'🟢' if side_str == 'LONG' else '🔴'} *{sym} ({side_str})*\n"
                        f"PnL: ||{pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)|| of target\n"
                        f"• Entry: `{entry:.8f}` | SL: `{sl:.8f}` | TP: `{tp:.8f}`"
                    )
                    
                    kb = [[InlineKeyboardButton("🔙 Back to Admin Control", callback_data="admin_command")]]
                    
                    if chart_file and os.path.exists(chart_file):
                        with open(chart_file, 'rb') as photo:
                            msg = await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=photo,
                                caption=caption,
                                parse_mode="Markdown",
                                reply_markup=InlineKeyboardMarkup(kb)
                            )
                            photo_ids.append(msg.message_id)
                    else:
                        msg = await context.bot.send_message(
                            chat_id=chat_id,
                            text=caption,
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
            finally:
                await mdm.close()
                
            if photo_ids:
                context.user_data['admin_simulated_photo_ids'] = photo_ids
                
        # Send historical/summary message
        if not trades:
            msg = (
                "🔬 *Recent Simulated Forward Trades*\n\n"
                "No simulated trades have been opened or resolved yet on this platform! ⏳\n\n"
                "Once the 15-minute engine completes signal passes and places simulated trades, they will be logged here."
            )
        else:
            msg_parts = ["🔬 *Recent Simulated Forward Trades Summary*\n_Showing last 10 activities_\n"]
            for t in trades:
                open_time_str = "???"
                if t.get('open_time'):
                    open_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t['open_time'] / 1000))
                
                direction = "LONG 📈" if t['side'] == 'buy' or t['side'] == 'long' else "SHORT 📉"
                strat_icon = "📈" if "Mean Reversion" in t['strategy'] else "🛡️"
                strat_short = "Mean Rev" if "Mean Reversion" in t['strategy'] else "Valkyrie"
                
                if t['status'] == 'open':
                    status_line = "⏳ *OPEN POSITION*"
                    pnl_line = ""
                    price_line = f"• Entry: `{t['entry_price']:.8f}` | SL: `{t['sl_price']:.8f}` | TP: `{t['tp_price']:.8f}`"
                else:
                    status_icon = "✅ Take Profit" if t['status'] == 'tp' else "❌ Stop Loss"
                    status_line = f"Resolved: *{status_icon}*"
                    pnl_line = f"\n  PnL: *{t['pnl_pct']:+.2f}% ({t['pnl_usdt']:+.2f} USDT)*"
                    exit_price = t['tp_price'] if t['status'] == 'tp' else t['sl_price']
                    price_line = f"• Entry: `{t['entry_price']:.8f}` | Exit: `{exit_price:.8f}`"
                
                msg_parts.append(
                    f"• *{t['symbol']}* ({direction}) | {strat_icon} _{strat_short}_\n"
                    f"  {status_line}{pnl_line}\n"
                    f"  {price_line}\n"
                    f"  Opened: _{open_time_str}_\n"
                )
            msg = "\n".join(msg_parts)
            
        kb = [[InlineKeyboardButton("🔙 Back to Admin Control", callback_data="admin_command")]]
        
        if open_trades:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(kb))
        return

    if query.data == "view_strategy_guide":
        await query.answer()
        intro_text = (
            "📖 *Sherpa Strategy Guide & Comparison*\n\n"
            "Choose the algorithm that best aligns with your risk tolerance and market outlook:\n\n"
            "📈 *Mean Reversion Scalper*\n"
            "• *Philosophy*: Mean Reversion. Assumes that prices that deviate excessively from the 20-period Bollinger Bands will snap back (revert) to the 200 EMA trend-line.\n"
            "• *Indicators*: Bollinger Bands + EMA 200 + ADX trend strength + Wilder RSI.\n"
            "• *Pace*: Highly active. Averages ~0.84 trades/day.\n"
            "• *Drawdown Profile*: Optimized for recommended **1.0% risk**, maintaining a safe drawdown of **~21.9%** (well below the 25% safety ceiling) while delivering **+384.1%** PnL."
        )
        valk_text = (
            "🛡️ *Valkyrie Elite Scalper*\n"
            "• *Philosophy*: Wick Rejection. Targets high-integrity trend continuation pullbacks on high-volume assets. It waits for price spikes to pierce the bands and quickly close back inside.\n"
            "• *Indicators*: Bollinger Bands + Volatility Squeeze + Wick piercing verification + ADX + standard RSI.\n"
            "• *Pace*: Patient and calculated. Averages ~0.68 trades/day.\n"
            "• *Drawdown Profile*: Highly protected; ultra-low peak drawdown ceiling (~16.2% to 19.5% on expanded basket)."
        )
        stock_text = (
            "🦙 *Sherpa Velocity Pullback (SVP)*\n"
            "• *Philosophy*: Momentum Pullback. Targets short-term, institutional-grade oversold pullback cycles on megacap US equities (NASDAQ/NYSE top 40) during robust, verified long-term uptrends.\n"
            "• *Indicators*: Daily Close > EMA(50) AND EMA(50) > EMA(200), 3-period Wilder RSI (< 10).\n"
            "• *Pace*: Daily swing. Executes scans daily at market open (9:31 AM EST).\n"
            "• *Drawdown Profile*: Ultra-safe equity curve, maintaining a tight **14.2%** maximum drawdown with a verified **+113.5%** return and high **66.9%** win rate over a 3-year period."
        )
        matrix_text = (
            "📊 *Comparative Matrix:*\n"
            "• *Focus*: Volatility Extremes vs Wick Rejection vs Equities Pullbacks\n"
            "• *Active Basket*: 29-Token Basket vs 7-Token Premium vs NASDAQ/NYSE Top 40\n"
            "• *Trigger Logic*: Close outside bands vs Wick pierce & close inside vs 3-Period RSI < 10\n"
            "• *Risk Profile*: Crypto Scalper (21.9% DD) vs Safe Crypto Scalper (19.5% DD) vs Stock Daily Swing (14.2% DD)\n\n"
            "💡 _Recommendation_: Use *Mean Reversion* if you prefer maximum trade frequency and compounding potential. Use *Valkyrie Elite* if you prioritize capital safety and smooth growth curves in crypto. Activate *Sherpa Velocity Pullback (SVP)* to diversify into high-liquidity megacap US equities with low drawdown."
        )
        guide_text = (
            "📖 *Sherpa Strategy Guide & Comparison*\n\n"
            "📈 *Mean Reversion Scalper*\n"
            "• Philosophy: Revert to 200 EMA from overextended Bollinger Bands.\n\n"
            "🛡️ *Valkyrie Elite Scalper*\n"
            "• Philosophy: Wick rejection pullbacks during squeezes.\n\n"
            "🦙 *Sherpa Velocity Pullback*\n"
            "• Philosophy: Momentum pullbacks on megacap US equities.\n\n"
            "Full visual and interactive infographics are displayed in the sequential guide above."
        )
        kb = [
            [InlineKeyboardButton("🔙 Back to Strategy Menu", callback_data="strategy_menu")],
            *get_nav_buttons(user.get('has_open_positions', False))
        ]
        
        chart_path = os.path.join(BASE_DIR, "results", "strategy_comparison.png")
        mr_path = os.path.join(BASE_DIR, "results", "mean_reversion_infographic.png")
        valk_path = os.path.join(BASE_DIR, "results", "valkyrie_elite_infographic.png")
        stock_path = os.path.join(BASE_DIR, "results", "stock_strategy_infographic.png")
        
        chart_sent = False
        
        try:
            if not os.path.exists(chart_path):
                from sherpa_visual_audit import generate_strategy_comparison_chart
                await asyncio.to_thread(generate_strategy_comparison_chart)
                
            if os.path.exists(chart_path) and os.path.exists(mr_path) and os.path.exists(valk_path) and os.path.exists(stock_path):
                try:
                    await query.message.delete()
                except:
                    pass
                
                photo_ids = []
                
                # 1. Send the comparison visual chart first
                with open(chart_path, 'rb') as photo:
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption="📊 *Metaverse Sherpa: 3-Year Strategy Comparison Visual*",
                        parse_mode="Markdown"
                    )
                    photo_ids.append(msg.message_id)
                
                # 2. Send Intro & Mean Reversion text description
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=intro_text,
                    parse_mode="Markdown"
                )
                
                # 3. Send Mean Reversion Infographic
                with open(mr_path, 'rb') as photo:
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo
                    )
                    photo_ids.append(msg.message_id)
                
                # 4. Send Valkyrie Elite text description
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=valk_text,
                    parse_mode="Markdown"
                )
                
                # 5. Send Valkyrie Elite Infographic
                with open(valk_path, 'rb') as photo:
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo
                    )
                    photo_ids.append(msg.message_id)
                    
                # 6. Send Sherpa Velocity Pullback text description
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=stock_text,
                    parse_mode="Markdown"
                )
                
                # 7. Send Sherpa Velocity Pullback Infographic
                with open(stock_path, 'rb') as photo:
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo
                    )
                    photo_ids.append(msg.message_id)
                
                # 8. Send Comparative Matrix & final keyboard menu
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=matrix_text,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                
                context.user_data['strategy_guide_photo_ids'] = photo_ids
                chart_sent = True
        except Exception as e:
            logger.error(f"❌ Error generating/sending strategy guide chart: {e}")
            
        if not chart_sent:
            await safe_edit_text(update, context, guide_text, reply_markup=InlineKeyboardMarkup(kb))
        return

    if query.data.startswith("run_backtest"):
        force_asset = None
        if query.data == "run_backtest_crypto":
            force_asset = 'crypto'
        elif query.data == "run_backtest_stock":
            force_asset = 'stock'
            
        await query.answer("🔬 Generating Backtest Projection...")
        # Recover or calculate starting balance
        balance = context.user_data.get('backtest_balance')
        if balance is None:
            actual_equity = user.get('equity') or 0.0
            if actual_equity <= 100.0:
                actual_equity = 10000.0
                
            eq_type = user.get('custom_equity_type', 'all')
            eq_val = user.get('custom_equity_value')
            
            balance = actual_equity
            if eq_type == 'amount' and eq_val is not None:
                balance = min(float(eq_val), actual_equity)
            elif eq_type == 'pct' and eq_val is not None:
                balance = actual_equity * (float(eq_val) / 100.0)
            
        # Store requested balance for callback continuity
        context.user_data['backtest_balance'] = balance
        await trigger_personalized_audit(update, context, user, start_balance=balance, force_asset=force_asset)
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
        if source_wallet == get_master_wallet() and chat_id != SUPER_ADMIN_ID:
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
                        chat_id=SUPER_ADMIN_ID,
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
        
    elif query.data.startswith("setex_"):
        exchange_id = query.data.split("_")[1]
        context.user_data['exchange_id'] = exchange_id
        await query.answer()
        
        if exchange_id == 'alpaca':
            context.user_data['setup_step'] = 101
            guide = (
                "🦙 *Alpaca API Setup*\n\n"
                "To connect your Alpaca Stock account, we will prompt you for your Endpoint Base URL, Key ID, and Secret Key sequentially.\n\n"
                "1️⃣ Please paste your **Alpaca API Endpoint Base URL** below:\n"
                "• Paper Trading: `https://paper-api.alpaca.markets`\n"
                "• Live Trading: `https://api.alpaca.markets`"
            )
            await safe_edit_text(update, context, guide)
            return

        context.user_data['setup_step'] = 1
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
        elif exchange_id == 'bitget':
            guide = (
                "🔷 *Bitget API Setup*\n\n"
                "1️⃣ Go to **API Management** on Bitget.\n"
                "2️⃣ Create Key -> Enable **'Futures Trading'**.\n"
                "3️⃣ Note your passphrase for the final step.\n"
                "4️⃣ (Optional) Whitelist the VPS IP for security.\n\n"
                "Please paste your **Bitget API Key** below:"
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
            "⚠️ *CONFIRM CLOSE ALL TRADES*\n\n"
            "You are about to close **ALL OPEN TRADES** at current market prices.\n\n"
            "❗ *Strategic Warning:*\n"
            "By closing early, you may miss out on significant profit potential. Your performance statistics will also deviate from the Sherpa algorithm's official results.\n\n"
            "Are you absolutely sure you want to exit the market now?",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    elif query.data.startswith("confirm_close_"):
        sym = query.data.replace("confirm_close_", "")
        await query.answer()
        kb = [
            [InlineKeyboardButton("✅ YES, CLOSE NOW", callback_data=f"execute_close_{sym}")],
            [InlineKeyboardButton("❌ NO, KEEP OPEN", callback_data="opentrades_menu")]
        ]
        warn_msg = (
            f"⚠️ *CLOSE {sym} CONFIRMATION*\n\n"
            f"You are about to close your **{sym}** position manually at market price.\n\n"
            "❗ *Strategic Warning:*\n"
            "By closing early, you may miss out on significant profit potential. Your performance statistics will also deviate from the Sherpa algorithm's official results.\n\n"
            "Are you absolutely sure?"
        )
        # Send as a fresh message below the chart instead of deleting the chart
        await query.message.reply_text(warn_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return

    elif query.data.startswith("execute_close_"):
        sym = query.data.replace("execute_close_", "")
        await query.answer(f"🚨 Closing {sym}...")
        success, report = await close_single_position(chat_id, sym)
        
        icon = "✅" if success else "❌"
        await query.message.reply_text(
            f"{icon} *Trade Close Report*\n\n{report}",
            parse_mode="Markdown",
            reply_markup=get_main_inline_menu(chat_id)
        )
        return

    elif query.data == "panic_execute":
        await query.answer("🚨 Executing Market Exit...")
        success, report = await panic_close_all(chat_id)
        
        icon = "✅" if success else "❌"
        msg = (
            f"{icon} *Market Exit Report*\n\n"
            f"{report}\n\n"
            "The engine has been paused for your account to prevent new entries. Tap /resume when you are ready to restart."
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
        active_crypto = user.get('active_crypto_strategy', 'Mean Reversion Scalper')
        active_stock = user.get('active_stock_strategy', 'None')
        
        strategy_overview = (
            "🎯 *Simultaneous Strategy Manager*\n\n"
            "Our engine supports running **one active crypto strategy** and **one active stock strategy** concurrently!\n\n"
            "🪙 *Crypto Strategy Engine* (Blofin/Bitget)\n"
            f"• Current: *{active_crypto}*\n"
            "• Execution: 24/7 background scalper.\n\n"
            "🦙 *Stock Strategy Engine* (Alpaca)\n"
            f"• Current: *{active_stock}*\n"
            "• Execution: Daily swing-trades at 9:31 AM EST.\n\n"
            f"⚖️ *Current Risk*: `{risk_val:.2f}% per trade`\n\n"
            "Use the controls below to independently activate or pause each engine:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏔️ Preview My Performance", callback_data="run_backtest")],
            [InlineKeyboardButton("⚖️ Set Risk %", callback_data="set_risk")],
            
            # Crypto Toggles Row
            [
                InlineKeyboardButton("🪙 Mean Rev" + (" (Active)" if active_crypto == "Mean Reversion Scalper" else ""), callback_data="set_strat_mean"),
                InlineKeyboardButton("🪙 Valkyrie" + (" (Active)" if active_crypto == "Valkyrie Elite Scalper" else ""), callback_data="set_strat_valk"),
            ],
            [InlineKeyboardButton("⏸️ Pause Crypto Strategy" + (" (Paused)" if active_crypto == "None" else ""), callback_data="set_strat_crypto_pause")],
            
            # Stock Toggles Row
            [
                InlineKeyboardButton("🦙 Alpaca Stock" + (" (Active)" if active_stock == "Sherpa Velocity Pullback" else ""), callback_data="set_strat_svp"),
                InlineKeyboardButton("⏸️ Pause Stock Strategy" + (" (Paused)" if active_stock == "None" else ""), callback_data="set_strat_stock_pause")
            ],
            
            [InlineKeyboardButton("📖 Strategy Guide & Differences", callback_data="view_strategy_guide")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False))
        ]
        
        if query.message.photo:
            try:
                await query.message.delete()
            except:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=strategy_overview,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await safe_edit_text(update, context, strategy_overview, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif query.data == "set_risk":
        await query.answer()
        clear_input_states(context)
        context.user_data['setting_risk'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False), is_admin=(chat_id == SUPER_ADMIN_ID and not user.get('undercover_mode')))
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

    elif query.data == "capital_menu":
        await query.answer()
        clear_input_states(context)
        
        # Display Capital Allocation Sub-dashboard
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
        return

    elif query.data == "set_cap_all":
        database.update_user_preference(chat_id, "custom_equity_type", "all")
        database.update_user_preference(chat_id, "custom_equity_value", None)
        await query.answer("✅ Reset to Full Balance!")
        
        # Reload Settings
        user = database.get_user(chat_id)
        msg, markup = get_settings_ui(user)
        await safe_edit_text(update, context, msg, reply_markup=markup)
        return

    elif query.data == "set_cap_amount_prompt":
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
        return

    elif query.data == "set_cap_pct_prompt":
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

    elif query.data == "switch_exchange_prompt":
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("🏔️ Blofin", callback_data="setex_blofin")],
            [InlineKeyboardButton("🔶 Binance", callback_data="setex_binance")],
            [InlineKeyboardButton("💠 MEXC", callback_data="setex_mexc")],
            [InlineKeyboardButton("🔷 Bitget", callback_data="setex_bitget")],
            [InlineKeyboardButton("🦙 Alpaca Stocks", callback_data="setex_alpaca")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]
        ]
        await safe_edit_text(
            update, context,
            "🌍 *Select Your Exchange*\n\n"
            "Which exchange would you like to link to the Metaverse Sherpa?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
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
    
    strategy = user.get('active_crypto_strategy', 'Mean Reversion Scalper')
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
            is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
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

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    target = update.effective_message
        
    user_data = database.get_user(chat_id)
    if not user_data:
        await target.reply_text("❌ No user profile found. Please run /setup first.")
        return

    crypto_details = None
    stock_details = None
    errors = []

    # 1. Fetch Crypto Balance (Blofin/Bitget) if configured
    if user_data.get('api_key') and user_data.get('api_key') != "":
        try:
            ex_id = user_data.get('exchange_id', 'blofin')
            ex_class = getattr(ccxt, ex_id)
            async with ex_class({
                "apiKey": user_data['api_key'],
                "secret": user_data['api_secret'],
                "password": user_data['api_password'],
                "options": {"defaultType": "swap"},
            }) as user_ex:
                acc_type = "swap" if ex_id == 'bitget' else "futures"
                balance = await user_ex.fetch_balance(params={"type": acc_type})
                free = float(balance.get("USDT", {}).get("free", 0))
                
                # True Equity Calculation
                total_value = free
                try:
                    positions = await user_ex.fetch_positions()
                    for p in positions:
                        margin = float(p.get('initialMargin') or p.get('margin') or p.get('info', {}).get('margin') or 0)
                        upnl = float(p.get('unrealizedPnl') or p.get('info', {}).get('unrealizedPnl') or 0)
                        total_value += (margin + upnl)
                except:
                    pass
                
                crypto_details = {
                    "exchange": ex_id.upper(),
                    "free": free,
                    "total": total_value
                }
        except Exception as e:
            errors.append(f"Crypto ({user_data.get('exchange_id', 'blofin').upper()}): {e}")

    # 2. Fetch Alpaca/Stock Balance if configured
    if user_data.get('alpaca_api_key') and user_data.get('alpaca_api_key') != "":
        try:
            account = await database.make_alpaca_request_async(user_data, "GET", "/v2/account")
            free = float(account.get("cash", 0))
            total_value = float(account.get("equity", 0) or account.get("portfolio_value", 0))
            stock_details = {
                "free": free,
                "total": total_value
            }
        except Exception as e:
            errors.append(f"Stocks (Alpaca): {e}")

    # 3. Handle cases where no keys are set
    if crypto_details is None and stock_details is None:
        if errors:
            await target.reply_text("❌ Error fetching balances:\n" + "\n".join(errors))
        else:
            await target.reply_text("❌ No API credentials connected. Please set up Blofin/Bitget or Alpaca credentials in Settings first.")
        return

    # 4. Format a gorgeous unified markdown message
    msg_parts = ["💰 *Your Unified Portfolio Balance* 💰\n"]
    
    if crypto_details:
        free_str = escape_md_v2(f"{crypto_details['free']:,.2f}")
        total_str = escape_md_v2(f"{crypto_details['total']:,.2f}")
        msg_parts.append(
            f"🪙 *Crypto Account ({crypto_details['exchange']})*\n"
            f"• Available Cash: ||*${free_str}*|| USDT\n"
            f"• Total Value: ||*${total_str}*|| USDT\n"
        )
        
    if stock_details:
        free_str = escape_md_v2(f"{stock_details['free']:,.2f}")
        total_str = escape_md_v2(f"{stock_details['total']:,.2f}")
        msg_parts.append(
            f"🦙 *Stock Account (Alpaca)*\n"
            f"• Buying Power: ||*${free_str}*|| USD\n"
            f"• Portfolio Value: ||*${total_str}*|| USD\n"
        )

    if errors:
        msg_parts.append("\n⚠️ *Some queries failed*:")
        for err in errors:
            msg_parts.append(f"_• {escape_md_v2(str(err))}_")

    msg = "\n".join(msg_parts)
    await target.reply_text(msg, parse_mode="MarkdownV2", reply_markup=get_main_inline_menu(chat_id))

async def sync_engine(application):
    """
    High-speed task (60s) for trade notifications and PnL syncing.
    """
    logger.info("📡 Starting Sentinel Sync Task (60s Notifications)...")
    while True:
        try:
            active_users = database.get_all_active_users()
            if not active_users:
                await asyncio.sleep(60)
                continue
            
            async def sync_user(user):
                try:
                    chat_id = user['telegram_chat_id']
                    if not user.get('api_key'): return

                    ex_id = user.get('exchange_id', 'blofin')
                    ex_class = getattr(ccxt, ex_id)
                    async with ex_class({
                        "apiKey": user['api_key'],
                        "secret": user['api_secret'],
                        "password": user['api_password'],
                        "options": {"defaultType": "swap"},
                    }) as user_ex:
                        # Fetch balance and sync closed trades
                        acc_type = "swap" if ex_id == 'bitget' else "futures"
                        balance = await user_ex.fetch_balance(params={"type": acc_type})
                        equity = float(balance.get("USDT", {}).get("total", 0))
                        await database.update_user_stats_from_engine(chat_id, equity, user_ex, application)
                except Exception as e:
                    logger.error(f"Sync error for {user.get('telegram_chat_id')}: {e}")

            await asyncio.gather(*(sync_user(u) for u in active_users))
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Sentinel critical failure: {e}")
            await asyncio.sleep(60)

async def signal_engine(application):
    """
    Institutional task (15m) for Signal Generation and Trade Execution.
    """
    logger.info("🏔️ Starting Sherpa Signal Task (15m Precision)...")
    mdm = live_bot_multi.MarketDataManager()
    try:
        while True:
            try:
                # 1. Wait until next 15-minute mark + buffer
                now = time.time()
                seconds_past_mark = now % 900
                wait_time = 900 - seconds_past_mark + 30
                logger.info(f"Sherpa Sleeping {wait_time:.1f}s until next candle close...")
                await asyncio.sleep(wait_time)

                # Reset MDM cache for the new cycle
                mdm.ohlcv_cache = {}
                
                # Fetch all OHLCV in parallel using public API
                await asyncio.gather(*(mdm.fetch_ohlcv(sym, "15m", limit=100) for sym in live_bot_multi.SYMBOLS))

                # 🧪 A. RESOLVE OPEN THEORETICAL TRADES
                open_theory_trades = database.get_open_theoretical_trades()
                for t in open_theory_trades:
                    symbol = t['symbol']
                    side = t['side']
                    entry_price = t['entry_price']
                    tp_price = t['tp_price']
                    sl_price = t['sl_price']
                    trade_id = t['id']
                    position_size = t['position_size']
                    
                    df = await mdm.fetch_ohlcv(symbol, "15m")
                    if df is not None and len(df) > 0:
                        last_candle = df.iloc[-1]
                        high = float(last_candle['high'])
                        low = float(last_candle['low'])
                        
                        triggered = False
                        status = 'open'
                        exit_price = 0.0
                        
                        if side == 'buy':  # Long
                            if low <= sl_price:
                                triggered = True
                                status = 'sl'
                                exit_price = sl_price
                            elif high >= tp_price:
                                triggered = True
                                status = 'tp'
                                exit_price = tp_price
                        else:  # Short
                            if high >= sl_price:
                                triggered = True
                                status = 'sl'
                                exit_price = sl_price
                            elif low <= tp_price:
                                triggered = True
                                status = 'tp'
                                exit_price = tp_price
                        
                        if triggered:
                            close_time = int(time.time() * 1000)
                            pnl_raw = exit_price - entry_price if side == 'buy' else entry_price - exit_price
                            pnl_pct = (pnl_raw / entry_price) * 100
                            pnl_usdt = position_size * pnl_raw
                            
                            current_bal = database.get_theoretical_balance()
                            new_bal = current_bal + pnl_usdt
                            database.update_theoretical_balance(new_bal)
                            
                            database.close_theoretical_trade(trade_id, exit_price, close_time, status, pnl_raw, pnl_pct, pnl_usdt)
                            
                            # Broadcast EXIT alert
                            all_targets = database.get_all_broadcast_targets()
                            exit_msg = (
                                f"🔔 *SIMULATED TRADE CLOSED!* (Forward Test)\n"
                                f"🏔️ _Global strategy tracker resolution_\n\n"
                                f"Symbol: *{symbol}*\n"
                                f"Direction: *{'LONG 📈' if side == 'buy' else 'SHORT 📉'}*\n"
                                f"Exit Trigger: *{status.upper()}*\n\n"
                                f"Entry Price: `{entry_price:.8f}`\n"
                                f"Exit Price: `{exit_price:.8f}`\n"
                                f"Trade PnL: *{pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)*\n\n"
                                f"Simulated Balance: *${new_bal:,.2f} USDT*"
                            )
                            for target_id in all_targets:
                                try:
                                    is_adm = (target_id == SUPER_ADMIN_ID)
                                    u = database.get_user(target_id)
                                    if u:
                                        is_adm = (target_id == SUPER_ADMIN_ID or u.get('is_admin')) and not u.get('undercover_mode')
                                    kb = get_nav_buttons(is_admin=is_adm)
                                    await application.bot.send_message(
                                        chat_id=target_id,
                                        text=exit_msg,
                                        reply_markup=InlineKeyboardMarkup(kb),
                                        parse_mode="Markdown"
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed forward test exit broadcast to {target_id}: {e}")

                # 🧪 B. EVALUATE NEW THEORETICAL SIGNALS FOR ALL STRATEGIES
                strategies_to_test = ["Mean Reversion Scalper", "Valkyrie Elite Scalper"]
                open_theory_trades = database.get_open_theoretical_trades()
                open_theory_keys = {(t['symbol'], t['strategy']) for t in open_theory_trades}
                
                for strategy_name in strategies_to_test:
                    signals = {}
                    for symbol in live_bot_multi.SYMBOLS:
                        # Avoid duplicate positions for this symbol/strategy pair
                        if (symbol, strategy_name) in open_theory_keys:
                            continue
                            
                        df = await mdm.fetch_ohlcv(symbol, "15m")
                        if df is not None:
                            sig = live_bot_multi.compute_signal(df, symbol.split("/")[0], strategy_name=strategy_name)
                            if sig:
                                signals[symbol] = sig
                                
                    for symbol, sig in signals.items():
                        entry = sig['entry']
                        side = sig['side']
                        sl_dist = sig['sl_dist']
                        rr = sig['rr']
                        
                        if side == 'buy': # Long
                            sl = entry - sl_dist
                            tp = entry + (sl_dist * rr)
                        else: # Short
                            sl = entry + sl_dist
                            tp = entry - (sl_dist * rr)
                            
                        open_ts = int(time.time() * 1000)
                        
                        sim_balance = database.get_theoretical_balance()
                        risk_val = 0.015  # 1.5% default institutional risk setting
                        
                        if sl_dist > 0:
                            position_size_usd = (sim_balance * risk_val) / (sl_dist / entry)
                            position_size_units = position_size_usd / entry
                        
                        database.add_theoretical_trade(
                            symbol=symbol,
                            strategy=strategy_name,
                            side=side,
                            entry_price=entry,
                            tp_price=tp,
                            sl_price=sl,
                            open_time=open_ts,
                            position_size=position_size_units
                        )
                        
                        chart_file = None
                        try:
                            df_chart = await mdm.fetch_ohlcv(symbol, timeframe='15m')
                            side_str = "LONG" if side == 'buy' else "SHORT"
                            chart_file = await asyncio.to_thread(
                                charting.generate_trade_chart,
                                symbol,
                                df_chart,
                                entry,
                                tp,
                                sl,
                                side_str,
                                open_ts=open_ts
                            )
                        except Exception as chart_err:
                            logger.error(f"Forward test chart generation failed: {chart_err}")
                        
                        all_targets = database.get_all_broadcast_targets()
                        entry_msg = (
                            f"🏔️ *NEW SIMULATED SIGNAL!* (Forward Test)\n"
                            f"🤖 *Strategy:* `{strategy_name}`\n\n"
                            f"Symbol: *{symbol}*\n"
                            f"Direction: *{'LONG 📈' if side == 'buy' else 'SHORT 📉'}*\n"
                            f"Risk Setting: `1.5%`\n"
                            f"Simulated Entry: `{entry:.8f}`\n"
                            f"Take Profit (TP): `{tp:.8f}`\n"
                            f"Stop Loss (SL): `{sl:.8f}`\n\n"
                            f"Simulated Position Size: `{position_size_units:.4f}` units (~${position_size_usd:.2f} USD)\n"
                            f"Current Simulated Balance: *${sim_balance:,.2f} USDT*"
                        )
                        
                        for target_id in all_targets:
                            try:
                                is_adm = (target_id == SUPER_ADMIN_ID)
                                u = database.get_user(target_id)
                                if u:
                                    is_adm = (target_id == SUPER_ADMIN_ID or u.get('is_admin')) and not u.get('undercover_mode')
                                kb = get_nav_buttons(is_admin=is_adm)
                                
                                if chart_file and os.path.exists(chart_file):
                                    with open(chart_file, 'rb') as photo:
                                        await application.bot.send_photo(
                                            chat_id=target_id,
                                            photo=photo,
                                            caption=entry_msg,
                                            reply_markup=InlineKeyboardMarkup(kb),
                                            parse_mode="Markdown"
                                        )
                                else:
                                    await application.bot.send_message(
                                        chat_id=target_id,
                                        text=entry_msg,
                                        reply_markup=InlineKeyboardMarkup(kb),
                                        parse_mode="Markdown"
                                    )
                            except Exception as e:
                                logger.warning(f"Failed forward test entry broadcast to {target_id}: {e}")

                # 2. Process Signals (Active Users)
                active_users = database.get_all_active_users()
                if active_users:
                    strategy_groups = {}
                    for user in active_users:
                        strat = user.get('active_crypto_strategy', 'Mean Reversion Scalper')
                        if strat == 'None' or not strat:
                            continue  # Crypto strategy is paused for this user
                        if strat not in strategy_groups: strategy_groups[strat] = []
                        strategy_groups[strat].append(user)
                    
                    for strat_name, users in strategy_groups.items():
                        user_signals = {}
                        for symbol in live_bot_multi.SYMBOLS:
                            df = await mdm.fetch_ohlcv(symbol, "15m")
                            if df is not None:
                                sig = live_bot_multi.compute_signal(df, symbol.split("/")[0], strategy_name=strat_name)
                                if sig: user_signals[symbol] = sig
                        
                        async def execute_user_signals(user):
                            try:
                                chat_id = user['telegram_chat_id']
                                if not user.get('api_key'): return
                                
                                ex_id = user.get('exchange_id', 'blofin')
                                ex_class = getattr(ccxt, ex_id)
                                async with ex_class({
                                    "apiKey": user['api_key'],
                                    "secret": user['api_secret'],
                                    "password": user['api_password'],
                                    "options": {"defaultType": "swap"},
                                }) as user_ex:
                                    
                                    acc_type = "swap" if ex_id == 'bitget' else "futures"
                                    balance = await user_ex.fetch_balance(params={"type": acc_type})
                                    actual_equity = float(balance.get("USDT", {}).get("total", 0))
                                    
                                    # Custom Capital Allocation Override
                                    eq_type = user.get('custom_equity_type', 'all')
                                    eq_val = user.get('custom_equity_value')
                                    
                                    equity = actual_equity
                                    if eq_type == 'amount' and eq_val is not None:
                                        equity = min(float(eq_val), actual_equity)
                                    elif eq_type == 'pct' and eq_val is not None:
                                        equity = actual_equity * (float(eq_val) / 100.0)
                                    
                                    user_enabled = user.get('enabled_symbols', [])
                                    user_risk = user.get('risk_pct', 1.5)
                                    
                                    for symbol, sig in user_signals.items():
                                        if symbol.split("/")[0] not in user_enabled: continue
                                        
                                        norm_sym = database.normalize_symbol(symbol, user_ex.id)
                                        pos = await user_ex.fetch_positions([norm_sym])
                                        if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                                            if live_bot_multi.DRY_RUN: continue
                                                
                                            res = await live_bot_multi.place_order(user_ex, norm_sym, sig, equity, risk_pct=user_risk)
                                            if res:
                                                database.increment_opened(chat_id)
                                                side_icon = "📈" if sig['side'] == 'buy' else "📉"
                                                msg = (
                                                    f"{side_icon} *{strat_name}* SIGNAL!\n\n"
                                                    f"Symbol: *{res['symbol']}*\n"
                                                    f"Risk: `{user_risk:.2f}%`\n"
                                                    f"Entry: `{res['entry']:.8f}`\n"
                                                    f"TP: `{res['tp']:.8f}`\n"
                                                    f"SL: `{res['sl']:.8f}`"
                                                )
                                                try:
                                                    df = await mdm.fetch_ohlcv(symbol, timeframe='15m')
                                                    side_str = "LONG" if sig['side'] == 'buy' else "SHORT"
                                                    open_ts = int(time.time() * 1000)
                                                    chart_file = await asyncio.to_thread(charting.generate_trade_chart, res['symbol'], df, res['entry'], res['tp'], res['sl'], side_str, open_ts=open_ts)
                                                    is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
                                                    keyboard = get_nav_buttons(True, is_admin=is_admin)
                                                    with open(chart_file, 'rb') as photo:
                                                        await application.bot.send_photo(chat_id=chat_id, photo=photo, caption=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                                                except Exception as chart_err:
                                                    logger.error(f"Chart generation failed: {chart_err}")
                                                    await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                            except Exception as e:
                                logger.error(f"Signal execution error for {user.get('telegram_chat_id')}: {e}")

                        await asyncio.gather(*(execute_user_signals(u) for u in users))
                
                logger.info(f"Engine pass complete.")
            except Exception as e:
                logger.error(f"Engine pass critical failure: {e}")
                
                # Notify admins of the critical error
                admins_to_notify = set(database.get_all_admins() + [SUPER_ADMIN_ID])
                err_msg = f"🚨 *ENGINE PASS CRITICAL FAILURE*\n\nError: `{e}`\n\nThe engine loop has caught an exception and will pause for 60 seconds before retrying."
                for admin_id in admins_to_notify:
                    try:
                        await application.bot.send_message(chat_id=admin_id, text=err_msg, parse_mode="Markdown")
                    except Exception as notify_err:
                        logger.error(f"Failed to send error notification to admin {admin_id}: {notify_err}")
                
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Engine pass critical failure: {e}")
                
                # Notify admins of the critical error
                admins_to_notify = set(database.get_all_admins() + [SUPER_ADMIN_ID])
                err_msg = f"🚨 *ENGINE PASS CRITICAL FAILURE*\n\nError: `{e}`\n\nThe engine loop has caught an exception and will pause for 60 seconds before retrying."
                for admin_id in admins_to_notify:
                    try:
                        await application.bot.send_message(chat_id=admin_id, text=err_msg, parse_mode="Markdown")
                    except Exception as notify_err:
                        logger.error(f"Failed to send error notification to admin {admin_id}: {notify_err}")
                
                await asyncio.sleep(60)
    finally:
        logger.info("🏔️ Closing Sherpa Signal Task Market Data Manager...")
        await mdm.close()

async def alpaca_equities_engine(application):
    """
    Daily background scheduler for Alpaca Stocks Sherpa Velocity Pullback strategy.
    Runs daily at 9:31 AM EST.
    """
    import live_bot_multi_alpaca
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta

    logger.info("🦙 Starting Alpaca Stocks Daily Scheduler (9:31 AM EST)...")
    while True:
        try:
            tz = ZoneInfo('US/Eastern')
            now = datetime.now(tz)
            
            # Target is 9:31:00 AM EST today
            target = now.replace(hour=9, minute=31, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
                
            wait_time = (target - now).total_seconds()
            logger.info(f"Alpaca Stocks Scheduler sleeping for {wait_time:.1f}s until next run at {target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            await asyncio.sleep(wait_time)
            
            logger.info("🦙 Waking up! Running daily stock swing execution...")
            await live_bot_multi_alpaca.main()
            
            # Prevent double-fire by sleeping 60 seconds
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("🦙 Alpaca Stocks Daily Scheduler task cancelled.")
            break
        except Exception as e:
            logger.error(f"🦙 Alpaca Stocks Daily Scheduler error: {e}")
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

    # 🚀 Notify Overlord of Deployment Success
    try:
        import subprocess
        # Fetch the latest 3 commit messages for the changelog
        try:
            changelog = subprocess.check_output(['git', 'log', '-n', '3', '--pretty=format:• %s (%ar)']).decode('utf-8')
        except:
            changelog = "• New deployment (Audit Trail Unavailable)"
            
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now_v2 = escape_md_v2(now)
        changelog_v2 = escape_md_v2(changelog)
        msg = (
            "🚀 *Deployment Success*\n\n"
            "The MetaverseSherpa Trading Bot has been upgraded and is now online\\.\n\n"
            f"🕒 *Timestamp:* `{now_v2}`\n\n"
            "📜 *Recent Fixes:* \n" + changelog_v2 + "\n\n"
            "🔬 *What to Test Next:*\n"
            "• Verify 'Close Trade' tactical confirmation on /opentrades\n"
            "• Audit the new 'Glass Progress Bar' for layout overlap\n"
            "• Confirm Blofin Tutorial deep\\_link delivers PDF correctly"
        )
        await application.bot.send_message(
            chat_id=SUPER_ADMIN_ID,
            text=msg,
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")

    # 🚀 Start Triple-Heartbeat Engine (including Stocks Daily Scheduler)
    task1 = asyncio.create_task(sync_engine(application))
    task2 = asyncio.create_task(signal_engine(application))
    task3 = asyncio.create_task(alpaca_equities_engine(application))
    application.bot_data['bg_tasks'] = [task1, task2, task3]

async def post_stop(application: ApplicationBuilder):
    """Gracefully cancel background engines to release TCP sockets safely."""
    logger.info("Gracefully shutting down background engines...")
    bg_tasks = application.bot_data.get('bg_tasks', [])
    for task in bg_tasks:
        task.cancel()
        
    if bg_tasks:
        # Wait for them to cancel, triggering CCXT finally/__aexit__ blocks
        await asyncio.gather(*bg_tasks, return_exceptions=True)
    
    # Give aiohttp a small buffer to sweep the unclosed connectors
    await asyncio.sleep(0.5)
    logger.info("Background engines shut down.")

def main():
    try:
        # Ensure database table exists
        database.init_db()

        # Initialize Bot Application with the post_init and post_stop hooks
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).post_stop(post_stop).build()
        app.add_error_handler(error_handler)
        
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
        app.add_handler(CommandHandler("forwardtest", stats_simulated))
        app.add_handler(CommandHandler("fstats", stats_simulated))
        app.add_handler(CommandHandler("opentrades", open_trades))
        app.add_handler(CommandHandler("list", list_trades))
        app.add_handler(CommandHandler("backtest", backtest))
        app.add_handler(CommandHandler("balance", balance_command))
        app.add_handler(CommandHandler("strategy", strategy_command))
        app.add_handler(CommandHandler("strategyguide", strategy_guide_command))
        app.add_handler(CommandHandler("promote", promote_command))
        app.add_handler(CommandHandler("demote", demote_command))
        app.add_handler(CommandHandler("cancel", cancel_command))
        app.add_handler(CallbackQueryHandler(strategy_callback, pattern="^set_strat_"))
        app.add_handler(CallbackQueryHandler(settings_callback, pattern="^capital_menu|^set_cap_all|^set_cap_amount_prompt|^set_cap_pct_prompt|^run_backtest|^admin_get_link|^send_blofin_guide|^apply_symbol_audit|^toggle_privacy|^strategy_menu|^toggle_active|^set_risk|^set_risk_to_|^manage_symbols|^tsym_|^back_to_settings|^setex_|^check_balance_setup|^opentrades_menu|^history_menu|^stats_menu|^help_menu|^settings_menu|^contact_menu|^refer_menu|^referral_menu|^confirm_panic|^panic_execute|^confirm_close_|^execute_close_|^admin_user_audit|^admin_broadcast_prompt|^admin_command|^admin_gift_prompt|^view_logs|^prompt_admin_wallet|^toggle_undercover|^close_admin|^premium_menu|^check_payment|^prompt_set_wallet|^activate_with_credits|^admin_view_simulated_trades|^view_strategy_guide|^switch_exchange_prompt"))
        app.add_handler(CallbackQueryHandler(share_callback, pattern="^sh"))
        app.add_handler(CommandHandler("stop", stop_bot))
        app.add_handler(CommandHandler("resume", resume_bot))
        
        # Catch all non-command messages (used for the setup step flow)
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        logger.info("Starting Telegram Bot Polling...")
        app.run_polling()
    except Exception as e:
        import traceback
        import requests
        err_msg = f"🚨 *FATAL BOT CRASH*\n\nThe Cyber-Sherpa has fallen! 🏔️\n\n*Error:* `{str(e)}`"
        try:
            tb = traceback.format_exc()
            # Send to Super Admin via simple HTTP request to bypass complex bot setup
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": SUPER_ADMIN_ID,
                "text": f"{err_msg}\n\n*Traceback:*\n```\n{tb[:3500]}\n```",
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=10)
        except: pass
        logger.critical(f"FATAL ERROR: {e}\n{traceback.format_exc()}")
        raise e

if __name__ == "__main__":
    main()

async def close_single_position(chat_id, sym):
    """Tactically closes a single position for a user."""
    user = database.get_user(chat_id)
    if not user: return False, "User not found."
    
    if user.get('exchange_id') == 'alpaca':
        try:
            await database.make_alpaca_request_async(user, "DELETE", f"/v2/positions/{sym}")
            return True, f"Market Closed {sym} stock position."
        except Exception as e:
            return False, f"Failed to close {sym} stock position on Alpaca: {e}"

    try:
        async with database.get_exchange_client(user) as user_ex:
            # Fetch the specific position
            positions = await user_ex.fetch_positions([sym])
            pos = next((p for p in positions if float(p.get("contracts", 0) or 0) != 0), None)
            
            if not pos:
                return False, f"No active position found for {sym}."
                
            side = pos['side'].upper()
            contracts = float(pos['contracts'])
            
            # Market close order
            order_side = "sell" if side == "LONG" else "buy"
            await user_ex.create_market_order(sym, order_side, contracts, params={"reduceOnly": True})
            
            return True, f"Market Closed {sym} position."
    except Exception as e:
        return False, f"Failed to close {sym}: {e}"

async def panic_close_all(chat_id):
    """Closes all active positions for a user across all symbols."""
    user = database.get_user(chat_id)
    if not user: return False, "User not found."
    
    if user.get('exchange_id') == 'alpaca':
        try:
            await database.make_alpaca_request_async(user, "DELETE", "/v2/positions", params={"cancel_orders": "true"})
            return True, "✅ Closed all active stock positions and cancelled all open stock orders on Alpaca."
        except Exception as e:
            return False, f"Failed to close Alpaca positions: {e}"

    try:
        async with database.get_exchange_client(user) as user_ex:
            import live_bot_multi
            
            # Normalize all symbols for this exchange
            norm_syms = [database.normalize_symbol(s, user_ex.id) for s in live_bot_multi.SYMBOLS]
            positions = await user_ex.fetch_positions(norm_syms)
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
                    await user_ex.create_market_order(sym, order_side, contracts, params={"reduceOnly": True})
                    results.append(f"✅ Closed {sym}")
                except Exception as e:
                    results.append(f"❌ Failed {p['symbol']}: {e}")
                    
            return True, "\n".join(results)
    except Exception as e:
        return False, f"Critical failure: {e}"
