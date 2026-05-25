import os
import sys
import logging
import asyncio
import time
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
    safe_edit_text,
    get_settings_ui
)

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
        # Resolve sherpa_visual_audit path dynamically
        sys.path.append(os.path.join(BASE_DIR, "scripts"))
        if not os.path.exists(chart_path):
            from sherpa_visual_audit import generate_strategy_comparison_chart
            await asyncio.to_thread(generate_strategy_comparison_chart)
            
        photo_ids = []
        
        from bot.ui.keyboards import send_cached_photo
        
        # 1. Send the comparison visual chart first
        msg = await send_cached_photo(update, context, chart_path, caption="📊 *Metaverse Sherpa: 3-Year Strategy Comparison Visual*")
        if msg: photo_ids.append(msg.message_id)
        
        # 2. Send Intro & Mean Reversion text description
        await context.bot.send_message(
            chat_id=chat_id,
            text=intro_text,
            parse_mode="Markdown"
        )
        
        # 3. Send Mean Reversion Infographic
        msg = await send_cached_photo(update, context, mr_path)
        if msg: photo_ids.append(msg.message_id)
        
        # 4. Send Valkyrie Elite text description
        await context.bot.send_message(
            chat_id=chat_id,
            text=valk_text,
            parse_mode="Markdown"
        )
        
        # 5. Send Valkyrie Elite Infographic
        msg = await send_cached_photo(update, context, valk_path)
        if msg: photo_ids.append(msg.message_id)
            
        # 6. Send Sherpa Velocity Pullback text description
        await context.bot.send_message(
            chat_id=chat_id,
            text=stock_text,
            parse_mode="Markdown"
        )
        
        # 7. Send Sherpa Velocity Pullback Infographic
        msg = await send_cached_photo(update, context, stock_path)
        if msg: photo_ids.append(msg.message_id)
        
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
