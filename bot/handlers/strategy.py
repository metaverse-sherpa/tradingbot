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
        
    active_crypto = user.get('active_crypto_strategy', 'Valkyrie Elite Scalper')
    active_stock = user.get('active_stock_strategy', 'None')
    risk_val = user.get('risk_pct', 1.5)
    
    disabled = database.get_disabled_strategies()
    mr_active = "Mean Reversion Scalper" not in disabled
    vk_active = "Valkyrie Elite Scalper" not in disabled
    svp_active = "Sherpa Velocity Pullback" not in disabled
    
    # Dynamically build strategy buttons row
    crypto_row = []
    if mr_active:
        crypto_row.append(InlineKeyboardButton("🪙 Mean Rev" + (" (Active)" if active_crypto == "Mean Reversion Scalper" else ""), callback_data="set_strat_mean"))
    if vk_active:
        crypto_row.append(InlineKeyboardButton("🪙 Valkyrie" + (" (Active)" if active_crypto == "Valkyrie Elite Scalper" else ""), callback_data="set_strat_valk"))
        
    keyboard = []
    if crypto_row:
        keyboard.append(crypto_row)
        
    if active_crypto == "None":
        keyboard.append([InlineKeyboardButton("▶️ Resume Crypto Strategy", callback_data="set_strat_crypto_pause")])
    else:
        keyboard.append([InlineKeyboardButton("⏸️ Pause Crypto Strategy", callback_data="set_strat_crypto_pause")])
    
    stock_row = []
    if svp_active:
        stock_row.append(InlineKeyboardButton("🦙 Alpaca Stock" + (" (Active)" if active_stock == "Sherpa Velocity Pullback" else ""), callback_data="set_strat_svp"))
    
    if active_stock == "None":
        stock_row.append(InlineKeyboardButton("▶️ Resume Stock Strategy", callback_data="set_strat_stock_pause"))
    else:
        stock_row.append(InlineKeyboardButton("⏸️ Pause Stock Strategy", callback_data="set_strat_stock_pause"))
        
    keyboard.append(stock_row)
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")])
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
    # We will trigger the same dynamic view_strategy_guide callback to prevent code duplication!
    query = update.callback_query
    if query:
        query.data = "view_strategy_guide"
        from bot.handlers.settings import settings_callback
        await settings_callback(update, context)
    else:
        # Send strategy manual text
        chat_id = update.effective_chat.id
        user = database.get_user(chat_id)
        if not user:
            await update.effective_message.reply_text("Please run /setup first.")
            return
        
        disabled = database.get_disabled_strategies()
        mr_active = "Mean Reversion Scalper" not in disabled
        vk_active = "Valkyrie Elite Scalper" not in disabled
        svp_active = "Sherpa Velocity Pullback" not in disabled
        
        guide_text = "📖 *Sherpa Strategy Guide & Comparison*\n\n"
        if mr_active:
            guide_text += "📈 *Mean Reversion Scalper*\n• Philosophy: Revert to 200 EMA from overextended Bollinger Bands.\n\n"
        if vk_active:
            guide_text += "🛡️ *Valkyrie Elite Scalper*\n• Philosophy: Wick rejection pullbacks during squeezes.\n\n"
        if svp_active:
            guide_text += "🦙 *Sherpa Velocity Pullback*\n• Philosophy: Momentum pullbacks on megacap US equities.\n\n"
        guide_text += "Please tap /strategy to swap strategy brains or configure settings."
        
        kb = [[InlineKeyboardButton("🔙 Back to Strategy Menu", callback_data="strategy_menu")]]
        await update.effective_message.reply_text(guide_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def strategy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    chat_id = query.message.chat.id
    user = database.get_user(chat_id)
    if not user:
        await query.answer()
        return
        
    current_risk = user.get('risk_pct', 1.5)
    disabled = database.get_disabled_strategies()
    
    if query.data == "set_strat_mean":
        if "Mean Reversion Scalper" in disabled:
            await query.answer("❌ This strategy is currently retired (disabled) by the administrator.", show_alert=True)
            return
            
        await query.answer()
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
            class MockQuery:
                def __init__(self, q, d): self._q = q; self.data = d
                def __getattr__(self, name): return getattr(self._q, name)
            mock_query = MockQuery(query, "strategy_menu")
            from bot.handlers.settings.callbacks.strategies import handle_strategies_callback
            await handle_strategies_callback(mock_query, update, context, database.get_user(chat_id), chat_id)
            
    elif query.data == "set_strat_valk":
        if "Valkyrie Elite Scalper" in disabled:
            await query.answer("❌ This strategy is currently retired (disabled) by the administrator.", show_alert=True)
            return
            
        await query.answer()
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
            class MockQuery:
                def __init__(self, q, d): self._q = q; self.data = d
                def __getattr__(self, name): return getattr(self._q, name)
            mock_query = MockQuery(query, "strategy_menu")
            from bot.handlers.settings.callbacks.strategies import handle_strategies_callback
            await handle_strategies_callback(mock_query, update, context, database.get_user(chat_id), chat_id)
            
    elif query.data == "set_strat_crypto_pause":
        user_db = database.get_user(chat_id)
        current_strat = user_db.get('active_crypto_strategy', 'Valkyrie Elite Scalper')
        if current_strat == "None":
            database.update_user_crypto_strategy(chat_id, "Valkyrie Elite Scalper")
            await query.answer("▶️ Crypto strategy Resumed!", show_alert=False)
        else:
            database.update_user_crypto_strategy(chat_id, "None")
            await query.answer("⏸️ Crypto strategy Paused!", show_alert=False)
            
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
