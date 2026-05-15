import os
import logging
import asyncio
import time
import json
import requests
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database
import charting
import live_bot_multi
import bot_ui
from bot_ui import escape_md_v2, safe_edit_text, get_nav_buttons, get_main_inline_menu, get_admin_keyboard

logger = logging.getLogger(__name__)

# Constants (Mirroring telegram_bot.py)
ADMIN_CHAT_ID = 1567788633
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
    
async def send_master_audit(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id):
    """Sends the institutional-grade 3-year master audit comparison instantly."""
    master_path = os.path.join(BASE_DIR, "results", "upsell_comparison.png")
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

async def trigger_personalized_audit(update: Update, context: ContextTypes.DEFAULT_TYPE, user, start_balance=10000.0):
    """Runs a 3-year backtest for a specific user's risk and symbols with animation."""
    chat_id = user['telegram_chat_id']
    risk = user['risk_pct']
    syms = user['enabled_symbols']
    
    # 🏔️ Master Cache Logic
    is_default = (risk == 1.5 and len(syms) >= 18 and start_balance == 10000.0)
    
    if not is_default:
        if not database.is_premium(user):
            upsell_path = os.path.join(BASE_DIR, "results", "upsell_comparison.png")
            premium_msg = (
                "🔒 *Premium Feature: Personal Projections*\n\n"
                "Unlock **7.6x more profit potential** for just **$20/mo**.\n"
                "Refer 3 friends or subscribe to unlock!"
            )
            if os.path.exists(upsell_path):
                with open(upsell_path, 'rb') as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=premium_msg, parse_mode="Markdown")
            return

    frames = ["🥾 *Sherpa is packing the gear...*", "🧗‍♂️ *Climbing the 2024 candles...*", "🏔️ *Reaching the peak...*"]
    status_msg = await context.bot.send_message(chat_id=chat_id, text=frames[0], parse_mode="Markdown")
    
    # Mocking audit task for now to keep it clean, but in reality it calls run_visual_audit
    from sherpa_visual_audit import run_visual_audit
    stats, chart_path, df_eq = await asyncio.to_thread(run_visual_audit, risk, syms, user_id=chat_id, start_balance=start_balance)
    
    audit_msg = f"🏔️ *Audit Complete*\nFinal Equity: *${stats['final_equity']:,.2f}*"
    await status_msg.delete()
    with open(chart_path, 'rb') as photo:
        await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=audit_msg, parse_mode="Markdown")

async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user: return
    await trigger_personalized_audit(update, context, user)

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
        # get_master_wallet and show_admin_dashboard would need to be accessible
        # For now, just basic text
        await update.effective_message.reply_text(f"🛑 *Action Cancelled.*{footer}", parse_mode="Markdown")
    else:
        await update.effective_message.reply_text("🛑 *Action Cancelled.*", parse_mode="Markdown")
        await update.effective_message.reply_text(
            "🛰️ *Main Menu Activated*",
            reply_markup=get_main_inline_menu(chat_id),
            parse_mode="Markdown"
        )
