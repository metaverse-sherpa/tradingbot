import os
import sys
import logging
import asyncio
import time
import json
from datetime import datetime
import ccxt.async_support as ccxt
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Add scripts directory to path for imports
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.append(SCRIPTS_DIR)

import database
import charting
import media_gen
import live_bot_multi
from bot.config import SUPER_ADMIN_ID, logger
from bot.ui.keyboards import (
    escape_md_v2,
    safe_edit_text,
    get_nav_buttons,
    get_main_inline_menu,
    get_backtest_inline_menu
)
from bot.ui.dashboards import render_history_dashboard

try:
    from sherpa_visual_audit import run_visual_audit
    from stock_backtester_daily import run_stock_visual_audit
except Exception as e:
    logger.error(f"Failed to import backtester functions: {e}")

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
    master_path = os.path.join(BASE_DIR, "results", "upsell_comparison.png")
    audit_msg = (
        "🏔️ *Metaverse Sherpa: Institutional Wealth Gap*\n"
        "Comparison: `Standard (Free Signals)` vs `Institutional (Exchange Autopilot)`\n"
        "_Both running at a conservative 1.0% Institutional Risk._\n\n"
        "📊 *Standard Tier (Always Free)*\n"
        "• Highly-accurate virtual trade signals delivered straight to your Telegram.\n"
        "• Core performance metrics dashboard & manual ledger access.\n\n"
        "💎 *Institutional Tier (Premium Access)*\n"
        "• Full autopilot: real-time execution directly on your connected exchange accounts (Blofin, Alpaca Stocks, Binance, MEXC).\n"
        "• Full 19+ symbol basket, custom sizing limits, and priority heartbeat processing.\n\n"
        "📈 _Institutional access delivers a **7.6x profit multiplier** by executing the full 20-token basket on autopilot without increasing your risk per trade._"
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
    crypto_risk = user.get('risk_pct', 1.5)
    stock_risk = user.get('stock_risk_pct', 1.0)
    syms = user.get('enabled_symbols', [])
    
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
            
    # 2. Check Premium gate and fetch correct balance based on target asset class
    if force_asset == 'stock':
        target_risk = stock_risk
        
        # Override start_balance with Alpaca equity if available and not overridden
        if user.get('alpaca_api_key'):
            try:
                acc = await database.make_alpaca_request_async(user, "GET", "/v2/account")
                alpaca_equity = float(acc.get("equity", 0) or acc.get("portfolio_value", 0))
                if alpaca_equity > 100.0:
                    start_balance = alpaca_equity
            except:
                pass
                
        is_default = (target_risk == 1.0 and start_balance == 10000.0)
    else:
        target_risk = crypto_risk
        is_default = (target_risk == 1.5 and len(syms) >= 18 and start_balance == 10000.0)
        
    if not is_default:
        # 💎 Premium Gate with Killer Comparison Visual
        if not database.is_premium(user):
            upsell_path = os.path.join(BASE_DIR, "results", "upsell_comparison.png")
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
            risk_val_pct=target_risk, 
            user_id=sim_user_id, 
            start_balance=start_balance
        ))
    else:
        strategy = user.get('active_crypto_strategy', 'Mean Reversion Scalper')
        if strategy == 'None':
            strategy = 'Mean Reversion Scalper'
        audit_task = asyncio.create_task(asyncio.to_thread(
            run_visual_audit, 
            target_risk, 
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
            rec_risk = 1.0 if target_risk >= 1.49 else max(0.5, round(target_risk * 0.67 * 2) / 2)
            advice_note = f"\n\n💡 *Risk Management Tip*:\nYour drawdown exceeds the **25.0% cap**. Consider lowering your risk allocation (e.g. **{rec_risk:.2f}%** instead of your current **{target_risk:.2f}%**) to keep capital drawdowns safely compressed."
        else:
            dd_line = f"Max Drawdown: *{stats['max_dd']:.1f}%*{dd_delta}"

        asset_title = "Stock" if force_asset == 'stock' else "Crypto"
        audit_msg = (
            f"🏔️ *Your Personalized 3-Year {asset_title} Audit*\n"
            f"Start Balance: `${start_balance:,.0f}` | Risk: `{target_risk:.2f}%`\n\n"
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
                    reply_markup=get_backtest_inline_menu(chat_id, show_risk_button=True, asset_type=force_asset)
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
                reply_markup=get_backtest_inline_menu(chat_id, show_risk_button=True, asset_type=force_asset)
            )
            
    except Exception as e:
        logger.error(f"Personal audit error: {e}")
        await status_msg.edit_text(f"❌ Error during simulation: {e}")

async def stats_simulated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explicitly shows simulated stats dashboard to any user."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    await show_forward_test_stats(update, context, chat_id, user)

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
            if ex_id == 'alpaca':
                ex_id = 'blofin'
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
                    positions = await user_ex.fetch_positions()
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
            
            equity_str_crypto = f"{equity:,.2f}" if not hide else "||HIDDEN||"
            crypto_msg = (
                f"🪙 *Crypto Wallet ({ex_id.upper()})*\n"
                f"• Portfolio Value: *${equity_str_crypto}* USD\n"
                f"• Overall PnL: *{overall_pnl_pct:+.2f}%{pnl_suffix}*\n"
                f"• Daily PnL: *{daily_pnl_pct:+.2f}%{daily_suffix}*\n"
                f"• Win Rate: *{wr:.1f}%{flame} ({wins} wins | {losses} losses)*\n"
                f"• Open Positions: *{open_positions_count} ({upnl_pct:+.2f}% unrealized)*\n"
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
            
            # Estimate overall growth based on starting stock equity
            start_equity = user.get('alpaca_start_equity')
            if not start_equity or start_equity == 0:
                start_equity = stock_equity if stock_equity > 0 else 10000.0
                if stock_equity > 0:
                    database.update_user_preference(chat_id, "alpaca_start_equity", start_equity)
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
                f"• Overall PnL: *{overall_pnl_str}* _(from ${start_equity:,.0f} base)_\n"
                f"• Daily PnL: *{daily_pnl_str}*\n"
                f"• Win Rate: *N/A (Broker Tracked)*\n"
                f"• Open Positions: *{stock_open_count} ({unrealized_str} unrealized)*\n"
                f"• Closed Trades: *{stock_closed_count}*\n"
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

    has_crypto = bool(user.get('api_key') and user.get('api_key') != "")
    has_stocks = bool(user.get('alpaca_api_key') and user.get('alpaca_api_key') != "")

    if not has_crypto and not has_stocks:
        await update.effective_message.reply_text("❌ No API credentials connected. Please set up Blofin/Bitget or Alpaca credentials in Settings first.")
        return

    active_exchange = user.get('exchange_id', 'blofin')

    # If they only have crypto, and have history cache, show cache immediately
    if active_exchange != 'alpaca' and user.get('history_cache'):
        try:
            import json
            last_10 = json.loads(user['history_cache'])
            await render_history_dashboard(update, context, last_10, chat_id, user)
            return
        except: pass

    if active_exchange == 'alpaca':
        if not has_stocks:
            await update.effective_message.reply_text("❌ No Alpaca credentials connected. Please set them up in Settings first.")
            return
        status_msg = await update.effective_message.reply_text("🔄 Fetching your recent trades directly from Alpaca...")
        try:
            orders = await database.make_alpaca_request_async(user, "GET", "/v2/orders", params={"status": "closed", "limit": 10})
            if orders:
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
            else:
                await status_msg.edit_text("No recently executed stock trades found in your Alpaca account.")
        except Exception as e:
            logger.error(f"Error fetching Alpaca history: {e}")
            await status_msg.edit_text(f"❌ Error fetching Alpaca history: {e}")
    else:
        if not has_crypto:
            await update.effective_message.reply_text("❌ No Blofin/Bitget credentials connected. Please set them up in Settings first.")
            return
        status_msg = await update.effective_message.reply_text("🔄 Fetching your recent trades directly from the exchange...")
        try:
            ex_id = active_exchange
            if ex_id == 'alpaca':
                ex_id = 'blofin'
            ex_class = getattr(ccxt, ex_id)
            async with ex_class({
                "apiKey": user['api_key'],
                "secret": user['api_secret'],
                "password": user['api_password'],
                "options": {"defaultType": "swap"},
            }) as user_ex:
                await user_ex.load_markets()
                
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
                    except Exception as sym_err:
                        logger.error(f"Error fetching history for {sym}: {sym_err}")

                await asyncio.gather(*(fetch_sym_history(sym) for sym in live_bot_multi.SYMBOLS))
                     
                all_closed.sort(key=lambda x: x['timestamp'], reverse=True)
                last_10 = all_closed[:10]
                
                if not last_10:
                    await status_msg.edit_text("No recently closed crypto trades found in your account.")
                    return
                    
                # Lock into Sherpa Cache
                database.set_history_cache(chat_id, last_10)
                
                await status_msg.delete()
                await render_history_dashboard(update, context, last_10, chat_id, user)
                
        except Exception as e:
            logger.error(f"Error fetching Crypto history: {e}")
            await status_msg.delete()
            await update.effective_message.reply_text(f"❌ Error fetching Crypto trade history: {e}")

async def fetch_alpaca_daily_bars_async(user, symbol, limit=60):
    from datetime import datetime, timedelta
    
    # We fetch up to 120 calendar days to guarantee limit (60) trading days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=120)
    
    start_str = start_date.strftime('%Y-%m-%dT00:00:00Z')
    end_str = end_date.strftime('%Y-%m-%dT23:59:59Z')
    
    url = "https://data.alpaca.markets/v2/stocks/bars"
    headers = {
        "APCA-API-KEY-ID": user.get("alpaca_api_key") or "",
        "APCA-API-SECRET-KEY": user.get("alpaca_api_secret") or "",
        "Content-Type": "application/json"
    }
    params = {
        "symbols": symbol,
        "timeframe": "1Day",
        "start": start_str,
        "end": end_str,
        "limit": 1000,
        "adjustment": "all"
    }
    
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                logger.error(f"Alpaca API error: {resp.text}")
                return None
            
            data = resp.json()
            bars = data.get("bars", {}).get(symbol, [])
            if not bars:
                return None
                
            records = []
            for b in bars:
                records.append({
                    "timestamp": pd.to_datetime(b["t"]),
                    "open": float(b["o"]),
                    "high": float(b["h"]),
                    "low": float(b["l"]),
                    "close": float(b["c"]),
                    "volume": float(b["v"])
                })
            df = pd.DataFrame(records)
            df.sort_values('timestamp', inplace=True)
            return df.tail(limit)
    except Exception as e:
        logger.error(f"Error fetching Alpaca daily bars for {symbol}: {e}")
        return None

async def open_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
        
    active_exchange = user.get('exchange_id', 'blofin')
    has_crypto = bool(user.get('api_key') and user.get('api_key') != "")
    has_stocks = bool(user.get('alpaca_api_key') and user.get('alpaca_api_key') != "")
    
    # 1. Fetch Alpaca Stock Trades
    if active_exchange == 'alpaca':
        if not has_stocks:
            await update.effective_message.reply_text("❌ No Alpaca credentials connected. Please set them up in Settings first.")
            return
        status_msg = await update.effective_message.reply_text("🔍 Checking your active stock trades...")
        try:
            positions = await database.make_alpaca_request_async(user, "GET", "/v2/positions")
            active_stocks = [p for p in positions if float(p.get("qty", 0)) != 0]
            
            if active_stocks:
                stock_trades_count = len(active_stocks)
                await update.effective_message.reply_text(
                    f"🦙 *Active Stock Trades Found: {stock_trades_count}*",
                    parse_mode="Markdown"
                )
                
                orders = []
                try:
                    orders = await database.make_alpaca_request_async(user, "GET", "/v2/orders", params={"status": "open"})
                except Exception as e:
                    logger.error(f"Failed to fetch Alpaca open orders: {e}")
                    
                for p in active_stocks:
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
                        
                        sl_str = escape_md_v2(f"{sl_price:.2f}") if sl_price > 0 else "None"
                        tp_str = escape_md_v2(f"{tp_price:.2f}") if tp_price > 0 else "None"
                        entry_str = escape_md_v2(f"{entry:.2f}")
                        caption = (
                            f"🟢 *{sym_v2} \\({side.upper()}\\)*\n"
                            f"PnL: ||{upnl_v2}|| USD \\({roe_v2}%\\) of ||{target_pnl_v2}|| \\({target_roe_v2}\\) Target\n"
                            f"• Entry: `{entry_str}` \\| SL: `{sl_str}` \\| TP: `{tp_str}`"
                        )
                        
                        chart_sent = False
                        try:
                            open_ts = 0
                            try:
                                closed_orders = await database.make_alpaca_request_async(user, "GET", "/v2/orders", params={"status": "closed", "limit": 50})
                                for o in closed_orders:
                                    if o.get("symbol") == sym and o.get("side") == ("buy" if side == "LONG" else "sell") and o.get("status") == "filled":
                                        filled_at = o.get("filled_at")
                                        if filled_at:
                                            import pandas as pd
                                            open_ts = int(pd.to_datetime(filled_at).timestamp() * 1000)
                                            break
                            except Exception as order_err:
                                logger.error(f"Failed to find entry filled time for stock {sym}: {order_err}")
                                
                            df_daily = await fetch_alpaca_daily_bars_async(user, sym, limit=60)
                            if df_daily is not None and not df_daily.empty:
                                chart_path = await asyncio.to_thread(
                                    charting.generate_trade_chart,
                                    sym,
                                    df_daily,
                                    entry,
                                    tp_price,
                                    sl_price,
                                    side,
                                    open_ts=open_ts,
                                    timeframe="1D",
                                    currency="USD"
                                )
                                
                                kb = [[InlineKeyboardButton(f"❌ Market Close {sym}", callback_data=f"confirm_close_{sym}")]]
                                with open(chart_path, 'rb') as photo:
                                    await context.bot.send_photo(
                                        chat_id=chat_id,
                                        photo=photo,
                                        caption=caption,
                                        parse_mode="MarkdownV2",
                                        reply_markup=InlineKeyboardMarkup(kb)
                                    )
                                try: os.remove(chart_path)
                                except: pass
                                chart_sent = True
                        except Exception as chart_err:
                            logger.error(f"Failed to generate Alpaca daily chart for {sym}: {chart_err}")
                            
                        if not chart_sent:
                            kb = [[InlineKeyboardButton(f"❌ Market Close {sym}", callback_data=f"confirm_close_{sym}")]]
                            await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
                    except Exception as e:
                        logger.error(f"Error processing Alpaca position: {e}")
                
                await update.effective_message.reply_text(
                    "🏔️ *Sherpa Navigation*",
                    reply_markup=get_main_inline_menu(chat_id)
                )
            else:
                await update.effective_message.reply_text("You have no active stock trades at the moment.", reply_markup=get_main_inline_menu(chat_id))
        except Exception as e:
            await update.effective_message.reply_text(f"❌ Error checking Alpaca positions: {e}")
        finally:
            await status_msg.delete()

    # 2. Fetch Crypto Trades
    else:
        if not has_crypto:
            await update.effective_message.reply_text("❌ No Blofin/Bitget credentials connected. Please set them up in Settings first.")
            return
        status_msg = await update.effective_message.reply_text("🔍 Checking your active crypto trades...")
        try:
            ex_id = active_exchange
            if ex_id == 'alpaca':
                ex_id = 'blofin'
            ex_class = getattr(ccxt, ex_id)
            async with ex_class({
                "apiKey": user['api_key'],
                "secret": user['api_secret'],
                "password": user['api_password'],
                "options": {"defaultType": "swap"},
            }) as user_ex:
                await user_ex.load_markets()
                
                positions = await user_ex.fetch_positions()
                active_crypto = [p for p in positions if float(p.get("contracts", 0) or 0) != 0]
                
                if active_crypto:
                    crypto_trades_count = len(active_crypto)
                    await update.effective_message.reply_text(
                        f"🪙 *Active Crypto Trades Found: {crypto_trades_count}*\nGenerating charts...",
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
                            
                            t_trade = database.get_active_theoretical_trade_by_symbol(sym)
                            sl_price = t_trade['sl_price'] if (t_trade and t_trade.get('sl_price') is not None) else 0.0
                            tp_price = t_trade['tp_price'] if (t_trade and t_trade.get('tp_price') is not None) else 0.0
                            
                            upnl_v2 = escape_md_v2(f"{upnl:+.2f}")
                            roe_v2 = escape_md_v2(f"{roe:+.2f}")
                            sym_v2 = escape_md_v2(sym.split(":")[0])
                            
                            sl_val = escape_md_v2(f"{sl_price:.4f}")
                            tp_val = escape_md_v2(f"{tp_price:.4f}")
                            
                            target_roe_str = "N/A"
                            target_pnl_usdt = 0.0
                            if tp_price > 0:
                                contracts = float(p.get("contracts", 0) or 0)
                                target_pnl_usdt = (tp_price - entry) * contracts * contract_size if side == "LONG" else (entry - tp_price) * contracts * contract_size
                                target_roe = (target_pnl_usdt / initial_margin * 100) if initial_margin > 0 else 0.0
                                target_roe_str = f"{target_roe:+.1f}%"
                            
                            target_pnl_v2 = escape_md_v2(f"{target_pnl_usdt:+.2f}")
                            target_roe_v2 = escape_md_v2(target_roe_str)
                            
                            caption = (
                                f"{'🟢' if side == 'LONG' else '🔴'} *{sym_v2} \\({side}\\)*\n"
                                f"PnL: ||{upnl_v2}|| USDT \\({roe_v2}%\\) of ||{target_pnl_v2}|| \\({target_roe_v2}\\) Target\n"
                                f"SL: `{sl_val}` \\| TP: `{tp_val}`"
                            )
                            
                            try:
                                ohlcv = await user_ex.fetch_ohlcv(sym, "15m", limit=60)
                                import pandas as pd
                                df_chart = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                                
                                chart_path = await asyncio.to_thread(
                                    charting.generate_trade_chart,
                                    sym,
                                    df_chart,
                                    entry,
                                    tp_price,
                                    sl_price,
                                    side,
                                    open_ts=0,
                                    timeframe="15M",
                                    currency="USDT"
                                )
                                
                                kb = [[InlineKeyboardButton(f"❌ Market Close {sym}", callback_data=f"confirm_close_{sym}")]]
                                with open(chart_path, 'rb') as photo:
                                    await context.bot.send_photo(
                                        chat_id=chat_id,
                                        photo=photo,
                                        caption=caption,
                                        parse_mode="MarkdownV2",
                                        reply_markup=InlineKeyboardMarkup(kb)
                                    )
                                try: os.remove(chart_path)
                                except: pass
                            except Exception as ce:
                                logger.error(f"Failed to generate position chart for {sym}: {ce}")
                                kb = [[InlineKeyboardButton(f"❌ Market Close {sym}", callback_data=f"confirm_close_{sym}")]]
                                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
                        except Exception as e:
                            logger.error(f"Error processing position: {e}")

                    await asyncio.gather(*(process_active_position(p) for p in active_crypto))
                    
                    await update.effective_message.reply_text(
                        "🏔️ *Sherpa Navigation*",
                        reply_markup=get_main_inline_menu(chat_id)
                    )
                else:
                    await update.effective_message.reply_text(
                        "🏔️ *Sherpa is scanning the mountains and valleys for the next high-probability trade.*\n\nYou have no active trades at the moment.", 
                        parse_mode="Markdown", 
                        reply_markup=get_main_inline_menu(chat_id)
                    )
        except Exception as e:
            await update.effective_message.reply_text(f"❌ Error checking Crypto positions: {e}")
        finally:
            await status_msg.delete()

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    new_val = not user['hide_dollars']
    database.update_user_preference(chat_id, "hide_dollars", 1 if new_val else 0)
    status = "HIDDEN 🔒" if new_val else "SHOWN 👁️"
    await update.effective_message.reply_text(f"✅ Privacy Mode: Dollar amounts are now *{status}*.", parse_mode="Markdown")

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
            if ex_id == 'alpaca':
                ex_id = 'blofin'
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
            f"🪙 *Crypto Account \\({crypto_details['exchange']}\\)*\n"
            f"• Available Cash: ||*${free_str}*|| USDT\n"
            f"• Total Value: ||*${total_str}*|| USDT\n"
        )
        
    if stock_details:
        free_str = escape_md_v2(f"{stock_details['free']:,.2f}")
        total_str = escape_md_v2(f"{stock_details['total']:,.2f}")
        msg_parts.append(
            f"🦙 *Stock Account \\(Alpaca\\)*\n"
            f"• Buying Power: ||*${free_str}*|| USD\n"
            f"• Portfolio Value: ||*${total_str}*|| USD\n"
        )

    if errors:
        msg_parts.append("\n⚠️ *Some queries failed*:")
        for err in errors:
            msg_parts.append(f"_• {escape_md_v2(str(err))}_")

    msg = "\n".join(msg_parts)
    await target.reply_text(msg, parse_mode="MarkdownV2", reply_markup=get_main_inline_menu(chat_id))

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
        
    elif data.startswith("shf_"): # SHARE FORWARD TESTING STATS
        parts = data.split("_")
        strat_key = parts[1]
        strat_mapping = {
            "mr": "Mean Reversion Scalper",
            "vk": "Valkyrie Elite Scalper",
            "svp": "Sherpa Velocity Pullback"
        }
        strat_name = strat_mapping.get(strat_key, "Mean Reversion Scalper")
        stats = database.get_theoretical_stats_by_strategy(strat_name)
        pnl = stats['cumulative_pnl']
        win_rate = stats['win_rate']
        total = stats['total_trades']
        wins = stats['wins']
        losses = stats['losses']
        
        bot_username = (await context.bot.get_me()).username
        card_path = media_gen.generate_forward_test_card(
            strat_name, pnl, win_rate, total, wins, losses,
            user_id=chat_id,
            bot_username=bot_username
        )
        share_label = f"forward testing stats for {strat_name}"
        
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
        elif data.startswith("shf_"):
            # Forward testing stats
            parts = data.split("_")
            strat_key = parts[1]
            strat_mapping = {
                "mr": "Mean Reversion Scalper",
                "vk": "Valkyrie Elite Scalper",
                "svp": "Sherpa Velocity Pullback"
            }
            strat_name = strat_mapping.get(strat_key, "Mean Reversion Scalper")
            stats = database.get_theoretical_stats_by_strategy(strat_name)
            is_profit = stats['cumulative_pnl'] >= 0
            
            emoji_map = {
                "mr": "📈",
                "vk": "🛡️",
                "svp": "🦙"
            }
            strat_emoji = emoji_map.get(strat_key, "🏔️")
            if is_profit:
                headline = f"{strat_emoji} *Crushing forward testing with the {strat_name} strategy on the Metaverse Sherpa Bot!* 🏔️"
            else:
                headline = f"{strat_emoji} *Forward testing in progress with the {strat_name} strategy on the Metaverse Sherpa Bot!* 🏔️"
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
        
        # Cleanup
        os.remove(card_path)
    else:
        await query.answer("❌ Error generating card.", show_alert=True)

async def close_single_position(chat_id, sym):
    """Tactically closes a single position for a user."""
    user = database.get_user(chat_id)
    if not user: return False, "User not found."
    
    is_stock = "/" not in sym and ":" not in sym
    
    if is_stock:
        try:
            await database.make_alpaca_request_async(user, "DELETE", f"/v2/positions/{sym}")
            return True, f"Market Closed {sym} stock position."
        except Exception as e:
            return False, f"Failed to close {sym} stock position on Alpaca: {e}"

    try:
        ex_id = user.get('exchange_id', 'blofin')
        if ex_id == 'alpaca':
            ex_id = 'blofin'
        ex_class = getattr(ccxt, ex_id)
        async with ex_class({
            "apiKey": user['api_key'],
            "secret": user['api_secret'],
            "password": user['api_password'],
            "options": {"defaultType": "swap"},
        }) as user_ex:
            # Fetch the specific position
            positions = await user_ex.fetch_positions()
            pos = next((p for p in positions if p.get('symbol') == sym and float(p.get("contracts", 0) or 0) != 0), None)
            
            if not pos:
                return False, f"No active position found for {sym}."
                
            side = str(pos.get('side') or '').upper()
            contracts = float(pos.get('contracts') or 0)
            
            # Market close order
            is_long = side in ["LONG", "BUY", "LONG_POSITION"]
            order_side = "sell" if is_long else "buy"
            
            # Determine position parameters dynamically for the order
            params = {"reduceOnly": True}
            
            # Extract marginMode
            margin_mode = pos.get('marginMode')
            if not margin_mode and 'info' in pos:
                margin_mode = pos['info'].get('marginMode')
            if margin_mode:
                params["marginMode"] = margin_mode.lower()
            else:
                params["marginMode"] = "isolated"
                
            # Extract positionSide
            raw_pos_side = None
            if 'info' in pos:
                raw_pos_side = pos['info'].get('positionSide') or pos['info'].get('posSide')
            if raw_pos_side:
                params["positionSide"] = raw_pos_side.lower()
            else:
                params["positionSide"] = "long" if is_long else "short"
                
            await user_ex.create_market_order(sym, order_side, contracts, params=params)
            
            return True, f"Market Closed {sym} position."
    except Exception as e:
        return False, f"Failed to close {sym}: {e}"

async def panic_close_all(chat_id):
    """Closes all active positions for a user across all symbols."""
    user = database.get_user(chat_id)
    if not user: return False, "User not found."
    
    has_crypto = bool(user.get('api_key') and user.get('api_key') != "")
    has_stocks = bool(user.get('alpaca_api_key') and user.get('alpaca_api_key') != "")
    
    if not has_crypto and not has_stocks:
        return False, "❌ No exchange API credentials connected."
        
    results = []
    
    # 1. Close stocks if configured
    if has_stocks:
        try:
            await database.make_alpaca_request_async(user, "DELETE", "/v2/positions", params={"cancel_orders": "true"})
            results.append("✅ Closed all active stock positions on Alpaca.")
        except Exception as e:
            results.append(f"❌ Failed to close stock positions on Alpaca: {e}")
            
    # 2. Close crypto if configured
    if has_crypto:
        try:
            async with database.get_exchange_client(user) as user_ex:
                positions = await user_ex.fetch_positions()
                active = [p for p in positions if float(p.get("contracts", 0) or 0) != 0]
                
                if not active:
                    if not has_stocks:
                        return True, "No active trades to close."
                else:
                    for p in active:
                        try:
                            sym = p['symbol']
                            side = str(p.get('side') or '').upper()
                            contracts = float(p.get('contracts') or 0)
                            
                            is_long = side in ["LONG", "BUY", "LONG_POSITION"]
                            order_side = "sell" if is_long else "buy"
                            
                            # Determine position parameters dynamically for the order
                            params = {"reduceOnly": True}
                            
                            # Extract marginMode
                            margin_mode = p.get('marginMode')
                            if not margin_mode and 'info' in p:
                                margin_mode = p['info'].get('marginMode')
                            if margin_mode:
                                params["marginMode"] = margin_mode.lower()
                            else:
                                params["marginMode"] = "isolated"
                                
                            # Extract positionSide
                            raw_pos_side = None
                            if 'info' in p:
                                raw_pos_side = p['info'].get('positionSide') or p['info'].get('posSide')
                            if raw_pos_side:
                                params["positionSide"] = raw_pos_side.lower()
                            else:
                                params["positionSide"] = "long" if is_long else "short"
                                
                            await user_ex.create_market_order(sym, order_side, contracts, params=params)
                            results.append(f"✅ Closed crypto {sym}")
                        except Exception as e:
                            results.append(f"❌ Failed crypto {p['symbol']}: {e}")
        except Exception as e:
            results.append(f"❌ Failed to close crypto positions: {e}")
            
    if not results:
        return True, "No active trades found to close."
        
    return True, "\n".join(results)
