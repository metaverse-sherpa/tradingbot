import os
import sys
import time
import logging
import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import database
from bot.config import SUPER_ADMIN_ID, logger, get_master_wallet, format_price, get_currency, is_stock
from bot.ui.keyboards import (
    escape_md_v2,
    safe_edit_text,
    get_nav_buttons,
    get_main_inline_menu,
    get_admin_keyboard,
    get_settings_ui
)
from bot.ui.dashboards import build_forward_test_stats_block

# Optional dependencies in root (safe dynamically imported/resolved via sys.path)
import charting
import live_bot_multi
import media_gen

def clear_input_states(context):
    """Clears all mutually exclusive interactive input states from user_data."""
    for key in ['setting_wallet', 'setting_admin_wallet', 'admin_broadcasting', 'admin_gifting', 'setting_crypto_risk', 'setting_stock_risk', 'setup_step', 'setting_cap_amount', 'setting_cap_pct']:
        context.user_data.pop(key, None)

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
        
    msg, reply_markup = get_settings_ui(user)
    await update.effective_message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

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

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Dynamic imports to prevent circular dependencies
    from bot.handlers.trading import (
        balance_command, open_trades, list_trades, stats,
        close_single_position, panic_close_all, trigger_personalized_audit, send_master_audit
    )
    from bot.handlers.system import docs, contact_command
    from bot.handlers.admin import admin_command, show_admin_dashboard, show_premium_menu
    
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
                
    # Clean up admin/user simulated trade photos when leaving either of those views
    if query.data not in ["admin_view_free_trades", "free_active"]:
        sim_photo_ids = context.user_data.pop('admin_free_photo_ids', [])
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
        from bot.handlers.admin import show_refer_dashboard
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

    if query.data == "admin_view_free_trades":
        if chat_id != SUPER_ADMIN_ID and not (user and user.get('is_admin')):
            logger.warning(f"UNAUTHORIZED FREE TRADES ACCESS ATTEMPT: {chat_id}")
            return
        
        await query.answer("Fetching free trades...")
        open_sim_trades = database.get_open_theoretical_trades()
        trades = database.get_recent_theoretical_trades(10)
        
        photo_ids = []
        
        if open_sim_trades:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🛰️ *Live Free Trades Found: {len(open_sim_trades)}*\nGenerating progress charts...",
                parse_mode="Markdown"
            )
            
            mdm = live_bot_multi.MarketDataManager()
            try:
                for t in open_sim_trades:
                    sym = t['symbol']
                    side = t['side']
                    entry = t['entry_price']
                    tp = t['tp_price']
                    sl = t['sl_price']
                    open_ts = t['open_time']
                    pos_size = t['position_size']
                    strat = t['strategy']
                    
                    if is_stock(sym):
                        try:
                            import pandas as pd
                            conn = sqlite3.connect("data/stock_daily_cache.db")
                            df_chart = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", conn, params=(sym,))
                            conn.close()
                            if not df_chart.empty:
                                df_chart['timestamp'] = pd.to_datetime(df_chart['date']).astype(int) // 10**6
                                df_chart = df_chart.tail(60).copy()
                            else:
                                df_chart = None
                        except Exception as stock_db_err:
                            logger.error(f"Failed to fetch stock daily cache for {sym}: {stock_db_err}")
                            df_chart = None
                    else:
                        df_chart = await mdm.fetch_ohlcv(sym, "15m")
                        
                    if df_chart is None or (hasattr(df_chart, 'empty') and df_chart.empty):
                        continue
                        
                    current = float(df_chart['close'].iloc[-1])
                    side_lower = str(side).lower()
                    pnl_raw = current - entry if side_lower in ['buy', 'long'] else entry - current
                    pnl_pct = (pnl_raw / entry) * 100
                    
                    currency = get_currency(sym)
                    if is_stock(sym):
                        pnl_val = pos_size * (pnl_pct / 100)
                    else:
                        pnl_val = pos_size * pnl_raw
                    
                    side_str = "LONG" if side_lower in ['buy', 'long'] else "SHORT"
                    
                    chart_file = None
                    try:
                        tf = "1D" if is_stock(sym) else "15M"
                        curr = "USD" if is_stock(sym) else "USDT"
                        chart_file = await asyncio.to_thread(
                            charting.generate_trade_chart,
                            sym,
                            df_chart,
                            entry,
                            tp,
                            sl,
                            side_str,
                            open_ts=open_ts,
                            timeframe=tf,
                            currency=curr
                        )
                    except Exception as chart_err:
                        logger.error(f"Free chart generation failed for {sym}: {chart_err}")
                    
                    caption = (
                        f"🧪 *ACTIVE FREE POSITION* (Forward Test)\n"
                        f"🤖 Strategy: *{strat}*\n\n"
                        f"{'🟢' if side_str == 'LONG' else '🔴'} *{sym} ({side_str})*\n"
                        f"PnL: ||{pnl_pct:+.2f}% ({pnl_val:+.2f} {currency})|| of target\n"
                        f"• Entry: `{format_price(entry, sym)}` | SL: `{format_price(sl, sym)}` | TP: `{format_price(tp, sym)}`"
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
                context.user_data['admin_free_photo_ids'] = photo_ids
                
        # Send historical/summary message
        if not trades:
            msg = (
                "🔬 *Recent Free Forward Trades*\n\n"
                "No free trades have been opened or resolved yet on this platform! ⏳\n\n"
                "Once the 15-minute engine completes signal passes and places free trades, they will be logged here."
            )
        else:
            msg_parts = ["🔬 *Recent Free Forward Trades Summary*\n_Showing last 10 activities_\n"]
            for t in trades:
                open_time_str = "???"
                if t.get('open_time'):
                    open_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t['open_time'] / 1000))
                
                direction = "LONG 📈" if t['side'] in ['buy', 'long', 'LONG'] else "SHORT 📉"
                strat_name = t['strategy']
                if "Mean Reversion" in strat_name:
                    strat_icon = "📈"
                    strat_short = "Mean Rev"
                elif "Valkyrie" in strat_name:
                    strat_icon = "🛡️"
                    strat_short = "Valkyrie"
                else:
                    strat_icon = "🏔️"
                    strat_short = "Pullback"
                
                curr = get_currency(t['symbol'])
                if t['status'] == 'open':
                    status_line = "⏳ *OPEN POSITION*"
                    pnl_line = ""
                    price_line = f"• Entry: `{format_price(t['entry_price'], t['symbol'])}` | SL: `{format_price(t['sl_price'], t['symbol'])}` | TP: `{format_price(t['tp_price'], t['symbol'])}`"
                else:
                    status_icon = "✅ Take Profit" if t['status'] == 'tp' else ("❌ Stop Loss" if t['status'] == 'sl' else f"⚠️ {t['status'].upper()}")
                    status_line = f"Resolved: *{status_icon}*"
                    pnl_line = f"\n  PnL: *{t['pnl_pct']:+.2f}% ({t['pnl_usdt']:+.2f} {curr})*"
                    exit_price = t['tp_price'] if t['status'] == 'tp' else t['sl_price']
                    price_line = f"• Entry: `{format_price(t['entry_price'], t['symbol'])}` | Exit: `{format_price(exit_price, t['symbol'])}`"
                
                msg_parts.append(
                    f"• *{t['symbol']}* ({direction}) | {strat_icon} _{strat_short}_\n"
                    f"  {status_line}{pnl_line}\n"
                    f"  {price_line}\n"
                    f"  Opened: _{open_time_str}_\n"
                )
            msg = "\n".join(msg_parts)
            
        kb = [[InlineKeyboardButton("🔙 Back to Admin Control", callback_data="admin_command")]]
        
        if open_sim_trades:
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
                    import html
                    if update.effective_user.username:
                        username_clean = update.effective_user.username
                        safe_username = html.escape(f"@{username_clean}")
                        user_display = f"<a href=\"https://t.me/{username_clean}\">{safe_username}</a>"
                    else:
                        user_display = f"ID: <code>{chat_id}</code>"
                    
                    await context.bot.send_message(
                        chat_id=SUPER_ADMIN_ID,
                        text=(
                            "💰 <b>INSTITUTIONAL REVENUE CONFIRMED!</b>\n\n"
                            f"User: {user_display}\n"
                            f"Required: <b>${required_price:.2f} USDT</b>\n\n"
                            "📈 <i>The treasury is growing.</i>"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error sending institutional revenue admin alert: {e}")

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
        elif exchange_id == 'bingx':
            guide = (
                "🟦 *BingX API Setup*\n\n"
                "1️⃣ Go to **API Management** on BingX.\n"
                "2️⃣ Create Key -> Enable **'Perpetual Futures Trading'**.\n"
                "3️⃣ (Optional) Whitelist the VPS IP for security.\n\n"
                "Please paste your **BingX API Key** below:"
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
    elif query.data == "dummy_spacer":
        await query.answer()
        return
    elif query.data == "free_active":
        await query.answer()
        await open_free_trades(update, context)
        return
    elif query.data == "free_closed":
        await query.answer()
        await list_free_trades(update, context)
        return
    elif query.data == "free_stats":
        await query.answer()
        await show_free_trade_stats(update, context)
        return
    elif query.data.startswith("manual_exec_"):
        await query.answer("Initiating live execution...")
        trade_id = query.data.split("_")[-1]
        from bot.handlers.trading import execute_manual_trade_callback
        await execute_manual_trade_callback(update, context, trade_id)
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
        
        # Escape markdown characters to prevent parsing errors from API exception messages
        safe_report = str(report).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
        
        icon = "✅" if success else "❌"
        await query.message.reply_text(
            f"{icon} *Trade Close Report*\n\n{safe_report}",
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
        stock_risk_val = user.get('stock_risk_pct', 1.0)
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
            f"⚖️ *Current Crypto Risk*: `{risk_val:.2f}% per trade`\n"
            f"⚖️ *Current Stock Risk*: `{stock_risk_val:.2f}% per trade`\n\n"
            "Use the controls below to independently activate or pause each engine:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏔️ Preview My Performance", callback_data="run_backtest")],
            [InlineKeyboardButton("🪙 Set Crypto Risk %", callback_data="set_crypto_risk"),
             InlineKeyboardButton("🦙 Set Stock Risk %", callback_data="set_stock_risk")],
            
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

    elif query.data == "set_crypto_risk":
        await query.answer()
        clear_input_states(context)
        context.user_data['setting_crypto_risk'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False), is_admin=(chat_id == SUPER_ADMIN_ID and not user.get('undercover_mode')))
        ]
        await safe_edit_text(
            update, context,
            "🪙 *Set Crypto Risk Percentage*\n\n"
            "Please type your preferred risk-per-trade for crypto as a number (e.g., `1.5` or `2.0`).\n\n"
            "_Current: " + f"{user['risk_pct']:.2f}%_",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif query.data == "set_stock_risk":
        await query.answer()
        clear_input_states(context)
        context.user_data['setting_stock_risk'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Cancel", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False), is_admin=(chat_id == SUPER_ADMIN_ID and not user.get('undercover_mode')))
        ]
        await safe_edit_text(
            update, context,
            "🦙 *Set Stock Risk Percentage*\n\n"
            "Please type your preferred risk-per-trade for stocks as a number (e.g., `1.0` or `1.5`).\n\n"
            "_Current: " + f"{user.get('stock_risk_pct', 1.0):.2f}%_",
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

    elif query.data == "switch_exchange_prompt":
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("🏔️ Blofin", callback_data="setex_blofin")],
            [InlineKeyboardButton("🔶 Binance", callback_data="setex_binance")],
            [InlineKeyboardButton("💠 MEXC", callback_data="setex_mexc")],
            [InlineKeyboardButton("🔷 Bitget", callback_data="setex_bitget")],
            [InlineKeyboardButton("🟦 BingX", callback_data="setex_bingx")],
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
        context.user_data.pop('setting_crypto_risk', None)
        context.user_data.pop('setting_stock_risk', None)
        await query.answer()

    # Refresh and show settings UI
    user = database.get_user(chat_id)
    msg, reply_markup = get_settings_ui(user)
    await safe_edit_text(update, context, msg, reply_markup=reply_markup)


async def open_free_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return

    open_sim_trades = database.get_open_theoretical_trades()
    
    if not open_sim_trades:
        msg = (
            "🛰️ *Live Free Positions*\n\n"
            "No active free trades are open at this time. "
            "The Sherpa is constantly scanning the markets for new free trade setups! ⏳"
        )
        await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id), parse_mode="Markdown")
        return

    # Delete previous messages/photos if any
    query = update.callback_query
    if query:
        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Failed to delete original message in open_free_trades: {e}")

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🛰️ *Live Free Trades Found: {len(open_sim_trades)}*\nGenerating progress charts...",
        parse_mode="Markdown"
    )

    photo_ids = []
    
    active_live_symbols = set()
    # Fetch active Alpaca stock symbols
    if user.get("alpaca_api_key"):
        try:
            positions = await database.make_alpaca_request_async(user, "GET", "/v2/positions")
            for p in positions:
                if float(p.get("qty", 0)) != 0:
                    active_live_symbols.add(p['symbol'])
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca positions for free stats check: {e}")
            
    # Fetch active Crypto symbols
    has_crypto = bool(user.get('api_key') and user.get('api_key') != "")
    if has_crypto:
        ex_id = user.get('exchange_id', 'blofin')
        if ex_id != 'alpaca':
            try:
                import ccxt.async_support as ccxt
                ex_class = getattr(ccxt, ex_id)
                exchange = ex_class({
                    "apiKey": user['api_key'],
                    "secret": user['api_secret'],
                    "password": user['api_password'],
                    "options": {"defaultType": "swap"},
                    "enableRateLimit": True,
                })
                await exchange.load_markets()
                pos = await exchange.fetch_positions()
                for p in pos:
                    if float(p.get('contracts', 0) or 0) != 0:
                        raw_sym = p.get('symbol', '')
                        clean_sym = raw_sym.split(':')[0].replace('/', '')
                        active_live_symbols.add(clean_sym)
                await exchange.close()
            except Exception as e:
                logger.error(f"Failed to fetch Crypto positions for free stats check: {e}")

    mdm = live_bot_multi.MarketDataManager()
    try:
        for t in open_sim_trades:
            sym = t['symbol']
            side = t['side']
            entry = t['entry_price']
            tp = t['tp_price']
            sl = t['sl_price']
            open_ts = t['open_time']
            pos_size = t['position_size']
            strat = t['strategy']
            
            if is_stock(sym):
                df_chart = None
                if user.get("alpaca_api_key"):
                    try:
                        from bot.handlers.trading import fetch_alpaca_daily_bars_async
                        df_chart = await fetch_alpaca_daily_bars_async(user, sym, limit=60)
                        if df_chart is not None and not df_chart.empty:
                            if hasattr(df_chart['timestamp'].dt, 'tz') and df_chart['timestamp'].dt.tz is not None:
                                df_chart['timestamp'] = df_chart['timestamp'].dt.tz_localize(None)
                    except Exception as live_err:
                        logger.error(f"Failed to fetch live free trade data for {sym}: {live_err}")
                
                if df_chart is None or (hasattr(df_chart, 'empty') and df_chart.empty):
                    try:
                        import pandas as pd
                        conn = sqlite3.connect("data/stock_daily_cache.db")
                        df_chart = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", conn, params=(sym,))
                        conn.close()
                        if not df_chart.empty:
                            df_chart['timestamp'] = pd.to_datetime(df_chart['date']).astype(int) // 10**6
                            df_chart = df_chart.tail(60).copy()
                        else:
                            df_chart = None
                    except Exception as stock_db_err:
                        logger.error(f"Failed to fetch stock daily cache for {sym}: {stock_db_err}")
                        df_chart = None
            else:
                df_chart = await mdm.fetch_ohlcv(sym, "15m")
                
            if df_chart is None or (hasattr(df_chart, 'empty') and df_chart.empty):
                continue
                
            current = float(df_chart['close'].iloc[-1])
            side_lower = str(side).lower()
            is_long = side_lower in ['buy', 'long', 'l']
            pnl_raw = current - entry if is_long else entry - current
            pnl_pct = (pnl_raw / entry) * 100
            
            target_pnl_raw = tp - entry if is_long else entry - tp
            target_pnl_pct = (target_pnl_raw / entry) * 100
            
            currency = get_currency(sym)
            if is_stock(sym):
                pnl_val = pos_size * (pnl_pct / 100)
                target_pnl_val = pos_size * (target_pnl_pct / 100)
            else:
                pnl_val = pos_size * pnl_raw
                target_pnl_val = pos_size * target_pnl_raw
            
            side_str = "LONG" if is_long else "SHORT"
            
            chart_file = None
            try:
                tf = "1D" if is_stock(sym) else "15M"
                curr = "USD" if is_stock(sym) else "USDT"
                chart_file = await asyncio.to_thread(
                    charting.generate_trade_chart,
                    sym,
                    df_chart,
                    entry,
                    tp,
                    sl,
                    side_str,
                    open_ts=open_ts,
                    timeframe=tf,
                    currency=curr
                )
            except Exception as chart_err:
                logger.error(f"Free chart generation failed for {sym}: {chart_err}")
            
            # Calculate percentages
            sl_pct_val = (((sl - entry) / entry) * 100 if side_str == 'LONG' else ((entry - sl) / entry) * 100) if sl > 0 else 0
            tp_pct_val = (((tp - entry) / entry) * 100 if side_str == 'LONG' else ((entry - tp) / entry) * 100) if tp > 0 else 0
            
            upnl_str = f"{'+' if pnl_val >= 0 else '-'}${abs(pnl_val):.2f}"
            target_pnl_str = f"{'+' if target_pnl_val >= 0 else '-'}${abs(target_pnl_val):.2f}"
            
            sl_str = f"${sl:.2f} ({sl_pct_val:+.0f}%)" if sl > 0 else "None"
            tp_str = f"${tp:.2f} ({tp_pct_val:+.0f}%)" if tp > 0 else "None"
            entry_str = f"${entry:.2f}"
            
            caption = (
                f"🛰️ *ACTIVE FREE POSITION* (Forward Test)\n"
                f"🤖 Strategy: *{strat}*\n\n"
                f"{'🟢' if side_str == 'LONG' else '🔴'} *{sym} ({side_str})*\n"
                f"Current PnL: {pnl_pct:+.2f}% ({upnl_str}) of {target_pnl_pct:+.2f}% ({target_pnl_str})\n"
                f"• Entry: `{entry_str}` | SL: `{sl_str}` | TP: `{tp_str}`"
            )
            
            # Conditionally generate the 'Open Live Trade' button
            reply_markup = None
            clean_t_sym = sym.replace('/', '')
            if clean_t_sym not in active_live_symbols:
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"▶️ Open Live Trade", callback_data=f"manual_exec_{t['id']}")]])
            
            if chart_file and os.path.exists(chart_file):
                with open(chart_file, 'rb') as photo:
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    photo_ids.append(msg.message_id)
                try: os.remove(chart_file)
                except: pass
            else:
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=btn,
                    parse_mode="Markdown"
                )
                photo_ids.append(msg.message_id)
    except Exception as e:
        logger.error(f"Error in open_free_trades: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error displaying free trades: {e}")
    finally:
        await mdm.close()
        try:
            await status_msg.delete()
        except:
            pass

    if photo_ids:
        context.user_data['admin_free_photo_ids'] = photo_ids

    # Send navigation footer at the very end
    await context.bot.send_message(
        chat_id=chat_id,
        text="🏔️ *Sherpa Navigation*",
        reply_markup=get_main_inline_menu(chat_id),
        parse_mode="Markdown"
    )


async def list_free_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return

    # Fetch last 20 theoretical trades to ensure we can get 10 closed ones
    trades = database.get_recent_theoretical_trades(20)
    closed_trades = [t for t in trades if t.get('status') != 'open'][:10]

    if not closed_trades:
        msg = (
            "📜 *Closed Free Trades History*\n\n"
            "No resolved free trades found on this platform yet! ⏳\n\n"
            "Once free trades are resolved via Take Profit or Stop Loss, they will appear here."
        )
        await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id), parse_mode="Markdown")
        return

    msg_parts = ["📜 *Closed Free Trades History*\n_Showing last 10 activities_\n"]
    for t in closed_trades:
        open_time_str = "???"
        if t.get('open_time'):
            open_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t['open_time'] / 1000))
        
        direction = "LONG 📈" if t['side'] in ['buy', 'long', 'LONG'] else "SHORT 📉"
        strat_name = t['strategy']
        if "Mean Reversion" in strat_name:
            strat_icon = "📈"
            strat_short = "Mean Rev"
        elif "Valkyrie" in strat_name:
            strat_icon = "🛡️"
            strat_short = "Valkyrie"
        else:
            strat_icon = "🏔️"
            strat_short = "Pullback"
        
        curr = get_currency(t['symbol'])
        status_icon = "🟢 Take Profit" if t['status'] == 'tp' else ("🔴 Stop Loss" if t['status'] == 'sl' else f"⚠️ {t['status'].upper()}")
        status_line = f"Resolved: *{status_icon}*"
        pnl_line = f"\n  PnL: *{t['pnl_pct']:+.2f}% ({t['pnl_usdt']:+.2f} {curr})*"
        exit_price = t['tp_price'] if t['status'] == 'tp' else t['sl_price']
        price_line = f"• Entry: `{format_price(t['entry_price'], t['symbol'])}` | Exit: `{format_price(exit_price, t['symbol'])}`"
        
        msg_parts.append(
            f"• *{t['symbol']}* ({direction}) | {strat_icon} _{strat_short}_\n"
            f"  {status_line}{pnl_line}\n"
            f"  {price_line}\n"
            f"  Opened: _{open_time_str}_\n"
        )
    msg = "\n".join(msg_parts)

    await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id), parse_mode="Markdown")


async def show_free_trade_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return

    msg = await build_forward_test_stats_block()
    await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id), parse_mode="Markdown")
