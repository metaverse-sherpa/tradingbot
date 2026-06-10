import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database
from bot.ui.keyboards import safe_edit_text, get_main_inline_menu, safe_query_answer
from bot.handlers.settings.free_trades import open_free_trades, list_free_trades, show_free_trade_stats

logger = logging.getLogger(__name__)

async def handle_trades_callback(query, update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id: int) -> bool:
    """
    Handles callbacks related to trades: open trades, history, stats, free trades, panic close.
    Returns True if the callback was handled, False otherwise.
    """
    
    from bot.handlers.trading import (
        open_trades, list_trades, stats, close_single_position, panic_close_all, execute_manual_trade_callback
    )

    if query.data == "opentrades_menu":
        await query.answer()
        await open_trades(update, context)
        return True

    if query.data == "history_menu":
        await query.answer()
        await list_trades(update, context)
        return True

    if query.data == "stats_menu":
        await query.answer()
        await stats(update, context)
        return True

    if query.data.startswith("free_active"):
        if "_" in query.data and query.data != "free_active":
            parts = query.data.split("_")
            if len(parts) > 2:
                context.user_data['active_signals_sort'] = parts[-1]
                
        sort_mode = context.user_data.get('active_signals_sort', 'date')
        await safe_query_answer(query)
        await open_free_trades(update, context, sort_mode=sort_mode)
        return True

    if query.data == "free_closed":
        await safe_query_answer(query)
        await list_free_trades(update, context)
        return True

    if query.data == "free_stats":
        await safe_query_answer(query)
        await show_free_trade_stats(update, context)
        return True

    if query.data.startswith("manual_exec_"):
        await query.answer("Initiating live execution...")
        trade_id = query.data.split("_")[-1]
        await execute_manual_trade_callback(update, context, trade_id)
        return True

    if query.data == "confirm_panic":
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
        return True

    if query.data.startswith("confirm_close_"):
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
        await query.message.reply_text(warn_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return True

    if query.data.startswith("execute_close_"):
        sym = query.data.replace("execute_close_", "")
        await query.answer(f"🚨 Closing {sym}...")
        success, report = await close_single_position(chat_id, sym)
        
        safe_report = str(report).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
        
        icon = "✅" if success else "❌"
        await query.message.reply_text(
            f"{icon} *Trade Close Report*\n\n{safe_report}",
            parse_mode="Markdown",
            reply_markup=get_main_inline_menu(chat_id)
        )
        return True

    if query.data == "panic_execute":
        await query.answer("🚨 Executing Market Exit...")
        success, report = await panic_close_all(chat_id)
        
        icon = "✅" if success else "❌"
        msg = (
            f"{icon} *Market Exit Report*\n\n"
            f"{report}\n\n"
            "The engine has been paused for your account to prevent new entries. Tap /resume when you are ready to restart."
        )
        database.set_active(chat_id, False)
        
        await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id))
        return True

    return False
