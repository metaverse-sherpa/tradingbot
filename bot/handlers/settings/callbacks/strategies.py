import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database
from bot.ui.keyboards import safe_edit_text, get_nav_buttons

logger = logging.getLogger(__name__)

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

async def handle_strategies_callback(query, update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id: int) -> bool:
    """
    Handles callbacks related to strategies, strategy guides, and backtests.
    Returns True if the callback was handled, False otherwise.
    """

    if query.data == "strategy_menu":
        await query.answer()
        risk_val = user.get('risk_pct', 1.5)
        stock_risk_val = user.get('stock_risk_pct', 2.0)
        active_crypto = user.get('active_crypto_strategy', 'Valkyrie Elite Scalper')
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
            f"⚖️ *Current Crypto Risk*: `{risk_val:.2f}% per trade`\n"
            f"⚖️ *Current Stock Risk*: `{stock_risk_val:.2f}% per trade`\n\n"
            "Use the controls below to independently activate or pause each engine:"
        )
        
        disabled = database.get_disabled_strategies()
        
        crypto_row = []
        if "Mean Reversion Scalper" not in disabled:
            crypto_row.append(InlineKeyboardButton("🪙 Mean Rev" + (" (Active)" if active_crypto == "Mean Reversion Scalper" else ""), callback_data="set_strat_mean"))
        if "Valkyrie Elite Scalper" not in disabled:
            crypto_row.append(InlineKeyboardButton("🪙 Valkyrie" + (" (Active)" if active_crypto == "Valkyrie Elite Scalper" else ""), callback_data="set_strat_valk"))

        stock_row = []
        if "Sherpa Velocity Pullback" not in disabled:
            stock_row.append(InlineKeyboardButton("🦙 Alpaca Stock" + (" (Active)" if active_stock == "Sherpa Velocity Pullback" else ""), callback_data="set_strat_svp"))
        
        if active_stock == "None":
            stock_row.append(InlineKeyboardButton("▶️ Resume Stock Strategy", callback_data="set_strat_stock_pause"))
        else:
            stock_row.append(InlineKeyboardButton("⏸️ Pause Stock Strategy", callback_data="set_strat_stock_pause"))

        keyboard = [
            [InlineKeyboardButton("🏔️ Preview My Performance", callback_data="run_backtest")],
            [InlineKeyboardButton("🪙 Set Crypto Risk %", callback_data="set_crypto_risk"),
             InlineKeyboardButton("🦙 Set Stock Risk %", callback_data="set_stock_risk")],
        ]
        if crypto_row:
            keyboard.append(crypto_row)
            
        if active_crypto == "None":
            keyboard.append([InlineKeyboardButton("▶️ Resume Crypto Strategy", callback_data="set_strat_crypto_pause")])
        else:
            keyboard.append([InlineKeyboardButton("⏸️ Pause Crypto Strategy", callback_data="set_strat_crypto_pause")])
        keyboard.append(stock_row)
        keyboard.append([InlineKeyboardButton("📖 Strategy Guide & Differences", callback_data="view_strategy_guide")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")])
        keyboard.extend(get_nav_buttons(user.get('has_open_positions', False)))
        
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
        return True

    if query.data == "view_strategy_guide":
        await query.answer()
        disabled = database.get_disabled_strategies()
        mr_active = "Mean Reversion Scalper" not in disabled
        vk_active = "Valkyrie Elite Scalper" not in disabled
        svp_active = "Sherpa Velocity Pullback" not in disabled

        intro_text = (
            "📖 *Sherpa Strategy Guide & Comparison*\n\n"
            "Choose the algorithm that best aligns with your risk tolerance and market outlook:\n\n"
        )
        if mr_active:
            intro_text += (
                "📈 *Mean Reversion Scalper*\n"
                "• *Philosophy*: Mean Reversion. Assumes that prices that deviate excessively from the 20-period Bollinger Bands will snap back (revert) to the 200 EMA trend-line.\n"
                "• *Indicators*: Bollinger Bands + EMA 200 + ADX trend strength + Wilder RSI.\n"
                "• *Pace*: Highly active. Averages ~0.84 trades/day.\n"
                "• *Drawdown Profile*: Optimized for recommended **1.0% risk**, maintaining a safe drawdown of **~21.9%** (well below the 25% safety ceiling) while delivering **+384.1%** PnL.\n\n"
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

        matrix_parts = ["📊 *Comparative Matrix:*\n"]
        rec_parts = []
        if mr_active:
            matrix_parts.append("• *Mean Reversion*: Focus on Volatility Extremes | 29-Token Basket | Trigger: Close outside bands | 21.9% DD")
            rec_parts.append("Use *Mean Reversion* if you prefer maximum trade frequency and compounding potential.")
        if vk_active:
            matrix_parts.append("• *Valkyrie Elite*: Focus on Wick Rejection | 7-Token Premium | Trigger: Wick pierce & close inside | 19.5% DD")
            rec_parts.append("Use *Valkyrie Elite* if you prioritize capital safety and smooth growth curves in crypto.")
        if svp_active:
            matrix_parts.append("• *Stock Daily Swing*: Focus on Equities Pullbacks | NASDAQ/NYSE Top 40 | Trigger: 3-Period RSI < 10 | 14.2% DD")
            rec_parts.append("Activate *Sherpa Velocity Pullback (SVP)* to diversify into high-liquidity megacap US equities with low drawdown.")

        matrix_text = "\n".join(matrix_parts) + "\n\n💡 _Recommendation_: " + " ".join(rec_parts)
        
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
            try:
                await query.message.delete()
            except:
                pass
            
            photo_ids = []
            from bot.ui.keyboards import send_cached_photo
            
            # 1. Send the comparison visual chart first (if at least two strategies are active)
            if (int(mr_active) + int(vk_active) + int(svp_active)) >= 2:
                if not os.path.exists(chart_path):
                    from bot.handlers.trading import sherpa_visual_audit
                    # Fallback to local import if needed
                    try:
                        from sherpa_visual_audit import generate_strategy_comparison_chart
                        await asyncio.to_thread(generate_strategy_comparison_chart)
                    except:
                        pass
                if os.path.exists(chart_path):
                    msg = await send_cached_photo(update, context, chart_path, caption="📊 *Metaverse Sherpa: Strategy Comparison Visual*")
                    if msg: photo_ids.append(msg.message_id)
            
            # 2. Send Intro & Mean Reversion text description
            if mr_active:
                await context.bot.send_message(chat_id=chat_id, text=intro_text, parse_mode="Markdown")
                if os.path.exists(mr_path):
                    msg = await send_cached_photo(update, context, mr_path)
                    if msg: photo_ids.append(msg.message_id)
            else:
                await context.bot.send_message(chat_id=chat_id, text="📖 *Sherpa Strategy Guide & Comparison*\n\nChoose the active algorithm that best aligns with your risk tolerance:", parse_mode="Markdown")
            
            # 3. Send Valkyrie Elite
            if vk_active:
                await context.bot.send_message(chat_id=chat_id, text=valk_text, parse_mode="Markdown")
                if os.path.exists(valk_path):
                    msg = await send_cached_photo(update, context, valk_path)
                    if msg: photo_ids.append(msg.message_id)
                
            # 4. Send Sherpa Velocity Pullback
            if svp_active:
                await context.bot.send_message(chat_id=chat_id, text=stock_text, parse_mode="Markdown")
                if os.path.exists(stock_path):
                    msg = await send_cached_photo(update, context, stock_path)
                    if msg: photo_ids.append(msg.message_id)
            
            # 5. Send Comparative Matrix & final keyboard menu
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
            guide_text = "📖 *Sherpa Strategy Guide & Comparison*\n\n"
            if mr_active:
                guide_text += "📈 *Mean Reversion Scalper*\n• Philosophy: Revert to 200 EMA from overextended Bollinger Bands.\n\n"
            if vk_active:
                guide_text += "🛡️ *Valkyrie Elite Scalper*\n• Philosophy: Wick rejection pullbacks during squeezes.\n\n"
            if svp_active:
                guide_text += "🦙 *Sherpa Velocity Pullback*\n• Philosophy: Momentum pullbacks on megacap US equities.\n\n"
            guide_text += "Full visual and interactive infographics are displayed in the sequential guide above."
            await safe_edit_text(update, context, guide_text, reply_markup=InlineKeyboardMarkup(kb))
        return True

    if query.data.startswith("run_backtest"):
        from bot.handlers.trading import trigger_personalized_audit
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
        return True

    return False
