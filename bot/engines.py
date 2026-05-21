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
from bot.ui.keyboards import get_nav_buttons

async def sync_engine(application):
    """
    High-speed task (60s) for trade notifications and PnL syncing.
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
                            acc_type = "swap" if ex_id == 'bitget' else "futures"
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
    Institutional task (15m) for Signal Generation and Trade Execution.
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
                            
                            strategy = t.get('strategy', 'Mean Reversion Scalper')
                            currency = get_currency(symbol)
                            if status == 'tp':
                                cheeky_note = (
                                    f"\n\n🏆 *Look what you missed out on!*\n"
                                    f"If you had been trading the *{strategy}* strategy, you would've earned *{pnl_pct:+.2f}%*!"
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
                            exit_msg = (
                                f"📊 *SIMULATED TRADE CLOSED* (Forward Test)\n"
                                f"───────────────────────────────\n"
                                f"Symbol:        *{symbol}*\n"
                                f"Strategy:      *{strategy}*\n"
                                f"Direction:     *{'LONG 📈' if side == 'buy' else 'SHORT 📉'}*\n"
                                f"Exit Trigger:  *{status.upper()}*\n\n"
                                f"Entry Price:   `{format_price(entry_price, symbol)}`\n"
                                f"Exit Price:    `{format_price(exit_price, symbol)}`\n"
                                f"Trade PnL:     *{pnl_pct:+.2f}%* ({pnl_usdt:+.2f} {currency})\n"
                                f"───────────────────────────────\n"
                                f"Simulated Balance:  *${new_bal:,.2f} {currency}*"
                                f"{cheeky_note}"
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
                                        text=exit_msg,
                                        reply_markup=InlineKeyboardMarkup(kb),
                                        parse_mode="Markdown"
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
                        entry_msg = (
                            f"🏔️ *NEW SIMULATED SIGNAL* (Forward Test)\n"
                            f"───────────────────────────────\n"
                            f"Symbol:        *{symbol}*\n"
                            f"Strategy:      *{strategy_name}*\n"
                            f"Direction:     *{'LONG 📈' if side == 'buy' else 'SHORT 📉'}*\n"
                            f"Risk Setting:  `1.5%`\n\n"
                            f"Simulated Entry: `{format_price(entry, symbol)}`\n"
                            f"Take Profit (TP): `{format_price(tp, symbol)}`\n"
                            f"Stop Loss (SL):   `{format_price(sl, symbol)}`\n\n"
                            f"Simulated Position Size: `{position_size_units:.4f}` units (~${position_size_usd:.2f} {currency})\n"
                            f"───────────────────────────────\n"
                            f"Current Simulated Balance: *${sim_balance:,.2f} {currency}*"
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
                                            caption=entry_msg,
                                            reply_markup=InlineKeyboardMarkup(kb),
                                            parse_mode="Markdown"
                                        )
                                else:
                                    await application.bot.send_message(
                                        chat_id=target_id,
                                        text=entry_msg,
                                        reply_markup=InlineKeyboardMarkup(kb),
                                        parse_mode="Markdown"
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
                                    
                                    acc_type = "swap" if ex_id == 'bitget' else "futures"
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
    Daily background scheduler for Alpaca Stocks Sherpa Velocity Pullback strategy.
    Runs daily at 9:31 AM EST.
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
