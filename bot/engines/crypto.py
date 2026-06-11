import os
import time
import asyncio
import ccxt.async_support as ccxt
from telegram import InlineKeyboardMarkup

import database
import charting
import live_bot_multi

from bot.config import (
    SUPER_ADMIN_ID,
    logger,
    is_stock,
    get_currency,
    format_price,
    get_symbol_link,
    CRYPTO_LEVERAGE
)
from bot.ui.keyboards import get_nav_buttons, build_datetime_entity_message
from bot.engines.base import SHARED_MARKETS, SHARED_MARKETS_TIME, SHARED_MARKETS_LOCK

async def theory_trades_resolution_engine(application):
    """
    Theoretical Trades Resolution Task (60s Precision Loop)
    
    Checks open theoretical (free) signals and resolves them if the current price (high/low of 1m candle)
    crosses TP/SL targets. Only queries market data for active symbols to prevent server strain.
    """
    logger.info("📡 Starting Theoretical Trades Resolution Task (60s loop)...")
    while True:
        try:
            await asyncio.sleep(60)
            
            open_theory_trades = database.get_open_theoretical_trades()
            if not open_theory_trades:
                continue
                
            crypto_trades = [t for t in open_theory_trades if not is_stock(t['symbol'])]
            if not crypto_trades:
                continue
                
            mdm = live_bot_multi.MarketDataManager()
            try:
                for t in crypto_trades:
                    symbol = t['symbol']
                    side = t['side']
                    entry_price = t['entry_price']
                    tp_price = t['tp_price']
                    sl_price = t['sl_price']
                    trade_id = t['id']
                    position_size = t['position_size']
                    
                    df = await mdm.fetch_ohlcv(symbol, "1m", limit=5)
                    if df is not None and len(df) > 0:
                        # Check last 2 candles of 1m timeframe
                        candles_to_check = df.iloc[-2:] if len(df) >= 2 else df.iloc[-1:]
                        
                        triggered = False
                        status = 'open'
                        exit_price = 0.0
                        
                        for idx, candle in candles_to_check.iterrows():
                            high = float(candle['high'])
                            low = float(candle['low'])
                            
                            if side == 'buy':  # Long
                                if low <= sl_price:
                                    triggered = True
                                    status = 'sl'
                                    exit_price = sl_price
                                    break
                                elif high >= tp_price:
                                    triggered = True
                                    status = 'tp'
                                    exit_price = tp_price
                                    break
                            else:  # Short
                                if high >= sl_price:
                                    triggered = True
                                    status = 'sl'
                                    exit_price = sl_price
                                    break
                                elif low <= tp_price:
                                    triggered = True
                                    status = 'tp'
                                    exit_price = tp_price
                                    break
                                    
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
                            if not is_stock(symbol):
                                display_pnl_pct *= CRYPTO_LEVERAGE
 
                            # Email alerts for exit
                            try:
                                from web_api.db_web import get_users_for_email_alerts
                                from web_api.email_service import send_alert_email, get_signal_alert_html
                                rt_users = get_users_for_email_alerts("realtime")
                                if rt_users:
                                    subject = f"🏆 Position Exited: {symbol}" if status == 'tp' else f"🛡️ Position Exited: {symbol}"
                                    side_str = "LONG" if side == 'buy' else "SHORT"
                                    html_content = get_signal_alert_html(
                                        symbol=symbol,
                                        side=side_str,
                                        strategy=t.get('strategy', 'Mean Reversion Scalper'),
                                        entry=entry_price,
                                        tp=tp_price,
                                        sl=sl_price,
                                        resolution=status,
                                        pnl_pct=display_pnl_pct
                                    )
                                    for ru in rt_users:
                                        if ru.get("email"):
                                            send_alert_email(ru["email"], subject, html_content)
                            except Exception as email_err:
                                logger.error(f"Failed to dispatch exit email alerts: {email_err}")
 
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
                                f"Symbol:        {get_symbol_link(symbol)}\n"
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
            finally:
                await mdm.close()
        except Exception as e:
            logger.error(f"Error in theory_trades_resolution_engine: {e}")

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
       a. (Theoretical trade resolution is handled separately by theory_trades_resolution_engine).
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

                # (Theoretical trade resolution is handled separately by theory_trades_resolution_engine every 60s)

                # 🧪 B. EVALUATE NEW THEORETICAL SIGNALS FOR ALL STRATEGIES
                disabled_strats = database.get_disabled_strategies()
                strategies_to_test = [s for s in ["Mean Reversion Scalper", "Valkyrie Elite Scalper"] if s not in disabled_strats]
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
                        
                        # Email alerts for entry
                        try:
                            from web_api.db_web import get_users_for_email_alerts
                            from web_api.email_service import send_alert_email, get_signal_alert_html
                            rt_users = get_users_for_email_alerts("realtime")
                            if rt_users:
                                subject = f"🛰️ New Alpha Signal: {symbol} ({'LONG' if side == 'buy' else 'SHORT'})"
                                side_str = "LONG" if side == 'buy' else "SHORT"
                                for ru in rt_users:
                                    if ru.get("email"):
                                        html_content = get_signal_alert_html(
                                            symbol=symbol,
                                            side=side_str,
                                            strategy=strategy_name,
                                            entry=entry,
                                            tp=tp,
                                            sl=sl,
                                            is_premium_user=ru.get("is_premium_user", False)
                                        )
                                        send_alert_email(ru["email"], subject, html_content)
                        except Exception as email_err:
                            logger.error(f"Failed to dispatch entry email alerts: {email_err}")
 
                        
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
                            f"Symbol:        {get_symbol_link(symbol)}\n"
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
                    disabled_strats = database.get_disabled_strategies()
                    strategy_groups = {}
                    for user in active_users:
                        strat = user.get('active_crypto_strategy', 'Valkyrie Elite Scalper')
                        if strat == 'None' or not strat:
                            continue  # Crypto strategy is paused for this user
                        if strat in disabled_strats:
                            continue  # Skip new signal entries for disabled strategy
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
                                chat_id = user.get('telegram_chat_id')
                                web_user_id = user.get('web_user_id')
                                if not user.get('api_key'): return
                                
                                ex_id = user.get('exchange_id', 'blofin')
                                if ex_id == 'alpaca':
                                    ex_id = 'blofin'
                                ex_class = getattr(ccxt, ex_id)
                                default_type = 'future' if ex_id == 'bingx' else 'swap'
                                async with ex_class({
                                    "apiKey": user['api_key'],
                                    "secret": user['api_secret'],
                                    "password": user['api_password'],
                                    "options": {"defaultType": default_type},
                                }) as user_ex:
                                    
                                    bal_params = database.get_exchange_balance_params(ex_id)
                                    balance = await user_ex.fetch_balance(params=bal_params)
                                    actual_equity = float(balance.get("USDT", {}).get("total", 0) or balance.get("USDT", {}).get("free", 0) or 0.0)
                                    
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
                                                if chat_id:
                                                    database.increment_opened(chat_id)
                                                    side_icon = "📈" if sig['side'] == 'buy' else "📉"
                                                    msg = (
                                                        f"{side_icon} *{strat_name}* SIGNAL!\n\n"
                                                        f"Symbol: {get_symbol_link(res['symbol'])}\n"
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
                                                else:
                                                    logger.info(f"Signal executed successfully for web-only user {web_user_id}. Symbol: {res['symbol']}")
                            except Exception as e:
                                logger.error(f"Signal execution error for {user.get('telegram_chat_id') or f'web_{user.get('web_user_id')}'}: {e}")
 
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
