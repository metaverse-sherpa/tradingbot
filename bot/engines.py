"""
Background Execution Engines

This module contains the asynchronous background loops that run concurrently with the 
Telegram bot polling process. These engines are responsible for non-blocking periodic 
tasks such as balance synchronization, crypto signal evaluation, and stock market scheduling.

Key Components:
1. sync_engine: A 60-second polling loop that fetches live account equity from connected exchanges.
2. signal_engine: A 15-minute scheduled loop that evaluates crypto OHLCV data, manages theoretical 
   (forward-testing) trades, and executes live positions for active users.
3. alpaca_equities_engine: A daily scheduler that wakes up at 9:31 AM EST to execute stock swing trades.
"""

import os
import sys
import time
import asyncio
import logging
from datetime import datetime, timedelta
import ccxt.async_support as ccxt
from telegram import InlineKeyboardMarkup

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Add scripts directory to path for imports
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.append(SCRIPTS_DIR)

import database
import charting
import live_bot_multi

from bot.config import (
    SUPER_ADMIN_ID,
    logger,
    is_stock,
    get_currency,
    format_price
)
from bot.ui.keyboards import get_nav_buttons, build_datetime_entity_message

async def sync_engine(application):
    """
    Sentinel Sync Task (60s loop)
    
    Responsibilities:
    - Iterates over all active users with connected API keys.
    - Asynchronously fetches their current futures/swap account balance via CCXT.
    - Updates the database with their current equity to ensure PnL stats in the UI are accurate.
    - Uses asyncio.gather for parallel network requests to prevent blocking.
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
                    
                    # 1. Sync Crypto
                    if user.get('api_key'):
                        ex_id = user.get('exchange_id', 'blofin')
                        if ex_id == 'alpaca': ex_id = 'blofin'
                        ex_class = getattr(ccxt, ex_id)
                        async with ex_class({
                            "apiKey": user['api_key'],
                            "secret": user['api_secret'],
                            "password": user['api_password'],
                            "options": {"defaultType": "swap"},
                        }) as user_ex:
                            acc_type = "swap" if ex_id in ['bitget', 'bingx'] else "futures"
                            balance = await user_ex.fetch_balance(params={"type": acc_type})
                            equity = float(balance.get("USDT", {}).get("total", 0))
                            await database.update_user_stats_from_engine(chat_id, equity, user_ex, application)
                            
                    # 2. Sync Stocks
                    if user.get('alpaca_api_key'):
                        # Stocks stats update logic can be minimal as Alpaca provides portfolio value directly
                        pass
                except Exception as e:
                    logger.error(f"Sync error for {user.get('telegram_chat_id')}: {e}")

            await asyncio.gather(*(sync_user(u) for u in active_users))
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Sentinel critical failure: {e}")
            await asyncio.sleep(60)

async def signal_engine(application):
    """
    Sherpa Signal Task (15m Precision Loop)
    
    This is the core engine for Crypto trading. It operates on a strict 15-minute schedule
    aligned with global candle closures (e.g., 00:00, 00:15, 00:30, 00:45).
    
    Execution Flow:
    1. Timer Math: Calculates the exact seconds remaining until the next 15m candle close + 30s buffer.
    2. Data Ingestion: Uses MarketDataManager to concurrently fetch the latest 100 15m OHLCV candles 
       for all tracked crypto symbols.
    3. Forward Testing (Simulation):
       a. Resolves open theoretical trades (checking if high/low hit TP/SL).
       b. Computes new signals and opens simulated trades for broadcast.
    4. Live Execution:
       a. Groups active users by their chosen strategy.
       b. Computes live signals.
       c. Places market limit orders with calculated risk constraints via CCXT.
       d. Broadcasts entry notifications with dynamically generated neon charts.
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
                    if is_stock(symbol):
                        continue
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
                            
                            display_pnl_pct = pnl_pct
                            from bot.config import CRYPTO_LEVERAGE
                            if not is_stock(symbol):
                                display_pnl_pct *= CRYPTO_LEVERAGE

                            strategy = t.get('strategy', 'Mean Reversion Scalper')
                            currency = get_currency(symbol)
                            if status == 'tp':
                                cheeky_note = (
                                    f"\n\n🏆 *Look what you missed out on!*\n"
                                    f"If you had been trading the *{strategy}* strategy, you would've earned *{display_pnl_pct:+.2f}%*!"
                                )
                            elif status == 'sl':
                                cheeky_note = (
                                    f"\n\n🛡️ *No strategy has a 100% win rate.*\n"
                                    f"Let's look for the next one!"
                                )
                            else:
                                cheeky_note = ""
                                
                            # Broadcast EXIT alert
                            all_targets = database.get_all_broadcast_targets()
                            now_ts = int(time.time())
                            exit_text, exit_entities = build_datetime_entity_message(
                                f"📊 *FREE TRADE CLOSED* (Forward Test)\n"
                                f"───────────────────────────────\n"
                                f"Symbol:        {symbol}\n"
                                f"Strategy:      {strategy}\n"
                                f"Direction:     {'LONG 📈' if side == 'buy' else 'SHORT 📉'}\n"
                                f"Exit Trigger:  {status.upper()}\n\n"
                                f"Entry Price:   {format_price(entry_price, symbol)}\n"
                                f"Exit Price:    {format_price(exit_price, symbol)}\n"
                                f"Trade PnL:     {display_pnl_pct:+.2f}%\n"
                                f"───────────────────────────────"
                                f"{cheeky_note}\n\n"
                                f"Closed at: ",
                                now_ts
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
                                        text=exit_text,
                                        entities=exit_entities,
                                        reply_markup=InlineKeyboardMarkup(kb),
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
                        
                        position_size_usd = 0.0
                        position_size_units = 0.0
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
                        currency = get_currency(symbol)
                        signal_ts = open_ts // 1000  # convert ms to seconds
                        entry_text, entry_entities = build_datetime_entity_message(
                            f"🏔️ *NEW FREE SIGNAL* (Forward Test)\n"
                            f"───────────────────────────────\n"
                            f"Symbol:        {symbol}\n"
                            f"Strategy:      {strategy_name}\n"
                            f"Direction:     {'LONG 📈' if side == 'buy' else 'SHORT 📉'}\n"
                            f"Risk Setting:  1.5%\n\n"
                            f"Free Entry: {format_price(entry, symbol)}\n"
                            f"Take Profit (TP): {format_price(tp, symbol)}\n"
                            f"Stop Loss (SL):   {format_price(sl, symbol)}\n\n"
                            f"Free Position Size: {position_size_units:.4f} units (~${position_size_usd:.2f} {currency})\n"
                            f"───────────────────────────────\n"
                            f"Current Free Balance: ${sim_balance:,.2f} {currency}\n\n"
                            f"Signal time: ",
                            signal_ts
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
                                            caption=entry_text,
                                            reply_markup=InlineKeyboardMarkup(kb),
                                            caption_entities=entry_entities,
                                        )
                                else:
                                    await application.bot.send_message(
                                        chat_id=target_id,
                                        text=entry_text,
                                        entities=entry_entities,
                                        reply_markup=InlineKeyboardMarkup(kb),
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
                                if ex_id == 'alpaca':
                                    ex_id = 'blofin'
                                ex_class = getattr(ccxt, ex_id)
                                async with ex_class({
                                    "apiKey": user['api_key'],
                                    "secret": user['api_secret'],
                                    "password": user['api_password'],
                                    "options": {"defaultType": "swap"},
                                }) as user_ex:
                                    
                                    acc_type = "swap" if ex_id in ['bitget', 'bingx'] else "futures"
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
                                        pos = await user_ex.fetch_positions()
                                        if not any(p.get('symbol') == norm_sym and float(p.get("contracts", 0) or 0) != 0 for p in pos):
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
    finally:
        logger.info("🏔️ Closing Sherpa Signal Task Market Data Manager...")
        await mdm.close()

async def alpaca_equities_engine(application):
    """
    Alpaca Stocks Daily Scheduler
    
    Unlike crypto which trades 24/7, this engine targets traditional market hours.
    It calculates the time until the next US market open (9:31 AM EST) and sleeps 
    asynchronously until that exact moment.
    
    Upon waking, it offloads the heavy lifting to `live_bot_multi_alpaca.main()`, 
    which handles the daily swing trading logic (selling previous positions and buying new ones).
    """
    import live_bot_multi_alpaca
    from zoneinfo import ZoneInfo

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

async def alpaca_fractional_monitor_engine(application):
    """
    Monitors active fractional stock trades via Alpaca Data API.
    Checks if the recent High or Low crossed TP/SL, and executes an exit.
    """
    import aiohttp
    logger.info("🦙 Starting Alpaca Fractional Shares Monitor Task (5m Loop)...")
    
    while True:
        try:
            # Sleep 5 minutes between checks
            await asyncio.sleep(300)
            
            open_trades = database.get_open_alpaca_trades()
            if not open_trades:
                continue
                
            # Group by user to use their respective API keys
            trades_by_user = {}
            for t in open_trades:
                cid = t['telegram_chat_id']
                if cid not in trades_by_user:
                    trades_by_user[cid] = []
                trades_by_user[cid].append(t)
                
            for chat_id, user_trades in trades_by_user.items():
                user = database.get_user(chat_id)
                if not user or not user.get('alpaca_api_key'):
                    continue
                    
                symbols = [t['symbol'] for t in user_trades]
                sym_str = ",".join(symbols)
                
                url = f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}"
                headers = {
                    "APCA-API-KEY-ID": user.get('alpaca_api_key'),
                    "APCA-API-SECRET-KEY": user.get('alpaca_api_secret')
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            logger.error(f"Alpaca data fetch failed for user {chat_id}: {resp.status}")
                            continue
                        data = await resp.json()
                        
                        for trade in user_trades:
                            sym = trade['symbol']
                            if sym not in data:
                                continue
                            
                            snapshot = data[sym]
                            daily_bar = snapshot.get("dailyBar", {})
                            if not daily_bar:
                                continue
                                
                            high_price = daily_bar.get('h', 0)
                            low_price = daily_bar.get('l', 0)
                            close_price = daily_bar.get('c', 0)
                            
                            tp = trade['tp_price']
                            sl = trade['sl_price']
                            qty = trade['qty']
                            
                            exit_reason = None
                            exit_price = None
                            
                            if high_price >= tp:
                                exit_reason = "TAKE PROFIT"
                                exit_price = tp
                            elif low_price <= sl:
                                exit_reason = "STOP LOSS"
                                exit_price = sl
                                
                            if exit_reason:
                                logger.info(f"Closing fractional {sym} for {chat_id}. Reason: {exit_reason} at {exit_price}")
                                order_payload = {
                                    "symbol": sym,
                                    "qty": str(qty),
                                    "side": "sell",
                                    "type": "market",
                                    "time_in_force": "day"
                                }
                                try:
                                    # Execute market sell
                                    await database.make_alpaca_request_async(user, "POST", "/v2/orders", json_data=order_payload)
                                    
                                    # Notify
                                    pnl_raw = (exit_price - trade['entry_price']) * qty
                                    pnl_pct = ((exit_price - trade['entry_price']) / trade['entry_price']) * 100
                                    
                                    import time
                                    database.close_alpaca_trade(trade['id'], int(time.time() * 1000), exit_price, pnl_raw, pnl_pct)

                                    
                                    msg = (
                                        f"🦙 *Alpaca Stock Strategy: Dynamic Exit Triggered* 🦙\n\n"
                                        f"Exited **{sym}** LONG position.\n"
                                        f"• Trigger: `{exit_reason}`\n"
                                        f"• Qty: `{qty}` shares\n"
                                        f"• Entry Price: `${trade['entry_price']:.2f}`\n"
                                        f"• Approximate Exit Price: `${close_price:.2f}`\n"
                                        f"• Estimated Trade PnL: *{pnl_pct:+.2f}%* (${pnl_raw:+.2f})\n"
                                    )
                                    # We need to import send_telegram_message or use application.bot.send_message
                                    await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                                except Exception as e:
                                    logger.error(f"Failed to close fractional trade {sym} for {chat_id}: {e}")
                                    
        except asyncio.CancelledError:
            logger.info("🦙 Alpaca Monitor task cancelled.")
            break
        except Exception as e:
            logger.error(f"Alpaca monitor error: {e}")
            await asyncio.sleep(60)

async def premium_expiration_engine(application):
    """
    Daily loop to check and alert users whose premium has expired.
    Checks once every 12 hours.
    """
    logger.info("⏳ Starting Premium Expiration Engine (12h Loop)...")
    
    while True:
        try:
            # Short initial delay to not block startup
            await asyncio.sleep(10)
            
            expired_users = database.get_expired_unnotified_users()
            if expired_users:
                logger.info(f"📬 Found {len(expired_users)} users whose premium expired. Sending alerts...")
                
                msg = (
                    "⚠️ *Your Premium Access Has Expired!*\n\n"
                    "Your Metaverse Sherpa autopilot has been paused, and live trade execution is no longer active for your account.\n\n"
                    "However, you will continue to receive free trading signals directly in Telegram!\n\n"
                    "To reactivate auto-trading across all your assets and return to autopilot mode, please renew your Premium Access by typing /settings or /premium."
                )
                
                for chat_id in expired_users:
                    try:
                        await application.bot.send_message(
                            chat_id=chat_id,
                            text=msg,
                            parse_mode="Markdown"
                        )
                        database.set_premium_expired_notified(chat_id, True)
                        logger.info(f"Notified {chat_id} of expiration.")
                    except Exception as e:
                        logger.error(f"Failed to send expiration notice to {chat_id}: {e}")
                        
            # Sleep 12 hours
            await asyncio.sleep(43200)
            
        except asyncio.CancelledError:
            logger.info("⏳ Premium Expiration Engine cancelled.")
            break
        except Exception as e:
            logger.error(f"⏳ Premium Expiration Engine error: {e}")
            await asyncio.sleep(3600)
