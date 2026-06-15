import os
import time
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database
from bot.config import (
    SUPER_ADMIN_ID,
    logger,
    is_stock,
    CRYPTO_LEVERAGE,
    get_symbol_link,
    get_currency,
    format_price
)
from bot.ui.keyboards import (
    get_settings_ui,
    safe_edit_text,
    get_main_inline_menu
)
from bot.ui.dashboards import build_forward_test_stats_block
import charting
import live_bot_multi

async def open_free_trades(update: Update, context: ContextTypes.DEFAULT_TYPE, sort_mode='date'):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return

    disabled = database.get_disabled_strategies()
    open_sim_trades = [t for t in database.get_open_theoretical_trades() if t.get('strategy') not in disabled]
    
    if not open_sim_trades:
        msg = (
            "🛰️ *Live Free Signals*\n\n"
            "No active free signals are open at this time. "
            "The Sherpa is constantly scanning the markets for new free signal setups! ⏳"
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
        text=f"🛰️ *Live Free Signals Found: {len(open_sim_trades)}*\nGenerating progress charts...",
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
    has_crypto = bool(user.get('api_key'))
    if has_crypto:
        ex_id = user.get('exchange_id', 'blofin')
        if ex_id != 'alpaca':
            futures_type = user.get('bingx_futures_type', 'standard') or 'standard'
            try:
                import ccxt.async_support as ccxt
                ex_class = getattr(ccxt, ex_id)
                default_type = 'swap'
                exchange = ex_class({
                    "apiKey": user['api_key'],
                    "secret": user['api_secret'],
                    "password": user['api_password'],
                    "options": {"defaultType": default_type},
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
                logger.error(f"Failed to fetch Crypto positions for free stats check on exchange {ex_id} ({futures_type} futures) for user {chat_id}: {e}")

    from live_bot_multi_alpaca import check_is_market_open
    is_mkt_open = check_is_market_open()

    mdm = live_bot_multi.MarketDataManager()
    trade_data_list = []
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
                try:
                    from bot.handlers.trading import fetch_alpaca_daily_bars_async
                    df_chart = await fetch_alpaca_daily_bars_async(user, sym, limit=120)
                    if df_chart is not None and not df_chart.empty:
                        if hasattr(df_chart['timestamp'].dt, 'tz') and df_chart['timestamp'].dt.tz is not None:
                            df_chart['timestamp'] = df_chart['timestamp'].dt.tz_localize(None)
                except Exception as live_err:
                    logger.error(f"Failed to fetch live free signal data for {sym}: {live_err}")
                
                if df_chart is None or (hasattr(df_chart, 'empty') and df_chart.empty):
                    try:
                        import pandas as pd
                        conn = sqlite3.connect("data/stock_daily_cache.db")
                        df_chart = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", conn, params=(sym,))
                        conn.close()
                        if not df_chart.empty:
                            df_chart['timestamp'] = pd.to_datetime(df_chart['date']).astype('datetime64[ms]').astype('int64')
                            df_chart = df_chart.copy()
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
            
            if not is_stock(sym):
                pnl_pct *= CRYPTO_LEVERAGE
                target_pnl_pct *= CRYPTO_LEVERAGE
                pnl_val = pos_size * pnl_raw
                target_pnl_val = pos_size * target_pnl_raw
            else:
                pnl_val = pos_size * (pnl_pct / 100)
                target_pnl_val = pos_size * (target_pnl_pct / 100)
            
            side_str = "LONG" if is_long else "SHORT"
            
            trade_data_list.append({
                't': t,
                'df_chart': df_chart,
                'sym': sym,
                'side_str': side_str,
                'entry': entry,
                'tp': tp,
                'sl': sl,
                'open_ts': open_ts,
                'pos_size': pos_size,
                'strat': strat,
                'pnl_pct': pnl_pct,
                'pnl_val': pnl_val,
                'target_pnl_pct': target_pnl_pct,
                'target_pnl_val': target_pnl_val
            })
            
        if sort_mode == 'progress':
            trade_data_list.sort(key=lambda x: x['pnl_pct'])
            
        for td in trade_data_list:
            t = td['t']
            df_chart = td['df_chart']
            sym = td['sym']
            side_str = td['side_str']
            entry = td['entry']
            tp = td['tp']
            sl = td['sl']
            open_ts = td['open_ts']
            strat = td['strat']
            pnl_pct = td['pnl_pct']
            pnl_val = td['pnl_val']
            target_pnl_pct = td['target_pnl_pct']
            target_pnl_val = td['target_pnl_val']
            
            chart_file = None
            cached_chart_path = f"data/cached_charts/trade_{t['id']}.jpg"
            use_cache = False
            
            if is_stock(sym) and not is_mkt_open:
                if os.path.exists(cached_chart_path):
                    chart_file = cached_chart_path
                    use_cache = True
            
            if not use_cache:
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
                    
                    if is_stock(sym) and not is_mkt_open and chart_file and os.path.exists(chart_file):
                        os.makedirs("data/cached_charts", exist_ok=True)
                        import shutil
                        shutil.copy(chart_file, cached_chart_path)
                except Exception as chart_err:
                    logger.error(f"Free chart generation failed for {sym}: {chart_err}")
            
            # Calculate percentages
            lev = 1.0 if is_stock(sym) else CRYPTO_LEVERAGE
            sl_pct_val = (((sl - entry) / entry) * 100 if side_str == 'LONG' else ((entry - sl) / entry) * 100) * lev if sl > 0 else 0
            tp_pct_val = (((tp - entry) / entry) * 100 if side_str == 'LONG' else ((entry - tp) / entry) * 100) * lev if tp > 0 else 0
            
            upnl_str = f"{'+' if pnl_val >= 0 else '-'}${abs(pnl_val):.2f}"
            target_pnl_str = f"{'+' if target_pnl_val >= 0 else '-'}${abs(target_pnl_val):.2f}"
            
            is_premium = database.is_premium(user)
            sym_link = get_symbol_link(sym, text=f"*{sym}*")
            caption = (
                f"🛰️ *ACTIVE FREE SIGNAL* \n"
                f"🤖 Strategy: *{strat}*\n\n"
                f"{'🟢' if side_str == 'LONG' else '🔴'} {sym_link} ({side_str})\n"
                f"Current PnL: {pnl_pct:+.2f}% ({upnl_str}) of {target_pnl_pct:+.2f}% ({target_pnl_str})"
            )
            
            if is_premium:
                sl_str = f"${sl:.2f} ({sl_pct_val:+.0f}%)" if sl > 0 else "None"
                tp_str = f"${tp:.2f} ({tp_pct_val:+.0f}%)" if tp > 0 else "None"
                entry_str = f"${entry:.2f}"
                caption += f"\n• Entry: `{entry_str}` | SL: `{sl_str}` | TP: `{tp_str}`"
            else:
                caption += "\n\n_🔒 Upgrade to /Premium to unlock signal details (e.g. Entry, TP, SL, chart) and to automate the trades on your favorite exchange!_"
            
            # Conditionally generate the 'Open Live Trade' button
            reply_markup = None
            if is_premium:
                clean_t_sym = sym.replace('/', '')
                if clean_t_sym not in active_live_symbols:
                    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"▶️ Open Live Trade", callback_data=f"manual_exec_{t['id']}")]])
            
            if is_premium and chart_file and os.path.exists(chart_file):
                with open(chart_file, 'rb') as photo:
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    photo_ids.append(msg.message_id)
                if chart_file != cached_chart_path:
                    try: os.remove(chart_file)
                    except: pass
            else:
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                photo_ids.append(msg.message_id)
    except Exception as e:
        logger.error(f"Error in open_free_trades: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error displaying free signals: {e}")
    finally:
        await mdm.close()
        try:
            await status_msg.delete()
        except:
            pass

    if photo_ids:
        context.user_data['admin_free_photo_ids'] = photo_ids

    # Send navigation footer at the very end
    sort_btn = InlineKeyboardButton("↕️ Sort By Progress %", callback_data="free_active_progress") if sort_mode == 'date' else InlineKeyboardButton("↕️ Sort By Date Time", callback_data="free_active_date")
    
    keyboard = [
        [sort_btn],
        *get_main_inline_menu(chat_id).inline_keyboard
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🏔️ *Sherpa Navigation*\n_Currently sorted by: {'Progress %' if sort_mode == 'progress' else 'Date Time'}_",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def list_free_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return

    # Fetch last 50 theoretical trades to ensure we can get 10 closed ones
    disabled = database.get_disabled_strategies()
    trades = [t for t in database.get_recent_theoretical_trades(50) if t.get('strategy') not in disabled]
    closed_trades = [t for t in trades if t.get('status') != 'open'][:10]

    if not closed_trades:
        msg = (
            "📜 *Closed Free Signals History*\n\n"
            "No resolved free signals found on this platform yet! ⏳\n\n"
            "Once free signals are resolved via Take Profit or Stop Loss, they will appear here."
        )
        await safe_edit_text(update, context, msg, reply_markup=get_main_inline_menu(chat_id), parse_mode="Markdown")
        return

    msg_parts = ["📜 *Closed Free Signals History*\n_Showing last 10 activities_\n"]
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
        
        display_pnl_pct = t['pnl_pct']
        if not is_stock(t['symbol']):
            display_pnl_pct *= CRYPTO_LEVERAGE
            
        status_icon = "✅ Take Profit" if t['status'] == 'tp' else ("❌ Stop Loss" if t['status'] == 'sl' else f"⚠️ {t['status'].upper()}")
        status_line = f"Resolved: *{status_icon}*"
        pnl_line = f"\n  PnL: *{display_pnl_pct:+.2f}% ({t['pnl_usdt']:+.2f} {curr})*"
        exit_price = t['tp_price'] if t['status'] == 'tp' else t['sl_price']
        price_line = f"• Entry: `{format_price(t['entry_price'], t['symbol'])}` | Exit: `{format_price(exit_price, t['symbol'])}`"
        
        msg_parts.append(
            f"• {get_symbol_link(t['symbol'])} ({direction}) | {strat_icon} _{strat_short}_\n"
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
