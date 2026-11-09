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
        
    active_stock = user.get('active_stock_strategy', 'Sherpa Velocity Pullback')
    stock_risk_val = user.get('stock_risk_pct', 2.0)
    
    keyboard = []
    stock_row = []
    stock_row.append(InlineKeyboardButton("🦙 Sherpa Velocity (Active)" if active_stock != "None" else "🦙 Sherpa Velocity", callback_data="set_strat_svp"))
    
    if active_stock == "None":
        stock_row.append(InlineKeyboardButton("▶️ Resume Strategy", callback_data="set_strat_stock_pause"))
    else:
        stock_row.append(InlineKeyboardButton("⏸️ Pause Strategy", callback_data="set_strat_stock_pause"))
        
    keyboard.append(stock_row)
    keyboard.append([InlineKeyboardButton("🔬 Backtest Strategy", callback_data="run_backtest")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    alpaca_connected = bool(user.get('alpaca_api_key') and user.get('alpaca_api_secret'))
    broker_mode = "Live" if "live" in (user.get('alpaca_endpoint') or "").lower() else "Paper"
    broker_status = f"Alpaca ({broker_mode})" if alpaca_connected else "Not Linked (Use /settings)"

    await update.effective_message.reply_text(
        "🎯 *Equities Strategy Manager*\n\n"
        "Our engine exclusively executes the proven **Sherpa Velocity Pullback** strategy on US equities!\n\n"
        "🦙 *Strategy Brain*: `Sherpa Velocity Pullback`\n"
        f"• Status: *{'🟢 Running' if active_stock != 'None' else '⏸️ Paused'}*\n"
        f"• Broker: *{broker_status}*\n"
        "• Universe: 37 Curated Megacap US Equities\n"
        "• Execution: Daily swing-trades evaluated at 9:31 AM EST\n"
        f"• Risk Per Trade: `{stock_risk_val:.2f}%`\n\n"
        "Use the controls below to pause/resume automated stock execution:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def strategy_guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a walkthrough of the active Sherpa Velocity Pullback equities strategy."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("Please run /setup first.")
        return
    
    guide_text = (
        "📖 *Sherpa Velocity Pullback Strategy Guide*\n\n"
        "🦙 *Strategy Overview*\n"
        "• **Asset Class**: US Equities (S&P 500 & NASDAQ 100 Megacaps)\n"
        "• **Broker**: Alpaca Markets (Paper & Live Fractional Shares)\n"
        "• **Philosophy**: Exploits oversold mean-reversion pullbacks during primary secular uptrends.\n"
        "• **Indicators**: Dynamic RSI, Bollinger Bands, and 200-day Trend Filter.\n"
        "• **Verified Metrics**: 68.4% Win Rate, 2.14 Sharpe Ratio, -22.7% Max Drawdown.\n"
        "• **Execution Frequency**: Evaluated at 9:31 AM EST market open.\n\n"
        "Use /settings to adjust your risk profile or link your Alpaca account."
    )
    
    kb = [[InlineKeyboardButton("🔙 Back to Strategy Menu", callback_data="strategy_menu")]]
    await update.effective_message.reply_text(guide_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def strategy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    chat_id = query.message.chat.id
    user = database.get_user(chat_id)
    if not user:
        await query.answer()
        return
        
    if query.data == "set_strat_svp":
        await query.answer("✅ Strategy set to Sherpa Velocity Pullback!")
        database.update_user_stock_strategy(chat_id, "Sherpa Velocity Pullback")
        class MockQuery:
            def __init__(self, q, d): self._q = q; self.data = d
            def __getattr__(self, name): return getattr(self._q, name)
        mock_query = MockQuery(query, "strategy_menu")
        from bot.handlers.settings.callbacks.strategies import handle_strategies_callback
        await handle_strategies_callback(mock_query, update, context, database.get_user(chat_id), chat_id)

    elif query.data == "set_strat_stock_pause":
        user_db = database.get_user(chat_id)
        current_strat = user_db.get('active_stock_strategy', 'Sherpa Velocity Pullback')
        if current_strat == "None":
            database.update_user_stock_strategy(chat_id, "Sherpa Velocity Pullback")
            await query.answer("▶️ Stock strategy Resumed!", show_alert=False)
        else:
            database.update_user_stock_strategy(chat_id, "None")
            await query.answer("⏸️ Stock strategy Paused!", show_alert=False)
            
        class MockQuery:
            def __init__(self, q, d): self._q = q; self.data = d
            def __getattr__(self, name): return getattr(self._q, name)
        mock_query = MockQuery(query, "strategy_menu")
        from bot.handlers.settings.callbacks.strategies import handle_strategies_callback
        await handle_strategies_callback(mock_query, update, context, database.get_user(chat_id), chat_id)
        
    elif query.data == "set_strat_stock_pause":
        user_db = database.get_user(chat_id)
        current_strat = user_db.get('active_stock_strategy', 'None')
        if current_strat == "None":
            if not user_db.get('alpaca_api_key') or not user_db.get('alpaca_api_secret') or not user_db.get('alpaca_endpoint'):
                context.user_data['exchange_id'] = 'alpaca'
                context.user_data['setup_step'] = 101
                guide = (
                    "🦙 *Alpaca API Setup Required*\n\n"
                    "To run the **Sherpa Velocity Pullback** stock strategy, you must first connect your Alpaca trading account.\n\n"
                    "Please paste your **Alpaca API Endpoint Base URL** below to begin setup:\n"
                    "• Paper Trading: `https://paper-api.alpaca.markets`\n"
                    "• Live Trading: `https://api.alpaca.markets`"
                )
                await query.answer()
                await safe_edit_text(update, context, guide)
                return
            else:
                database.update_user_stock_strategy(chat_id, "Sherpa Velocity Pullback")
                await query.answer("▶️ Stock strategy Resumed!", show_alert=False)
        else:
            database.update_user_stock_strategy(chat_id, "None")
            await query.answer("⏸️ Stock strategy Paused!", show_alert=False)
            
        class MockQuery:
            def __init__(self, q, d): self._q = q; self.data = d
            def __getattr__(self, name): return getattr(self._q, name)
        mock_query = MockQuery(query, "strategy_menu")
        from bot.handlers.settings.callbacks.strategies import handle_strategies_callback
        await handle_strategies_callback(mock_query, update, context, database.get_user(chat_id), chat_id)
        
    elif query.data == "set_strat_svp":
        if "Sherpa Velocity Pullback" in disabled:
            await query.answer("❌ This strategy is currently retired (disabled) by the administrator.", show_alert=True)
            return
            
        await query.answer()
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
            class MockQuery:
                def __init__(self, q, d): self._q = q; self.data = d
                def __getattr__(self, name): return getattr(self._q, name)
            mock_query = MockQuery(query, "strategy_menu")
            from bot.handlers.settings.callbacks.strategies import handle_strategies_callback
            await handle_strategies_callback(mock_query, update, context, database.get_user(chat_id), chat_id)
            
    elif query.data == "set_strat_soon":
        await query.answer("🚧 This strategy is coming soon!", show_alert=True)
