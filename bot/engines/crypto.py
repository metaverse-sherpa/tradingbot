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
    logger.debug("📡 Starting Theoretical Trades Resolution Task (60s loop)...")
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
                    position_size = float(t.get('position_size') or 1.0)
                    
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
                            gross_usdt = position_size * pnl_raw
                            fee_usdt = (position_size * entry_price + position_size * exit_price) * 0.0005
                            pnl_usdt = gross_usdt - fee_usdt
                            
                            current_bal = database.get_theoretical_balance()
                            new_bal = current_bal + pnl_usdt
                            database.update_theoretical_balance(new_bal)
                            
                            database.close_theoretical_trade(trade_id, exit_price, close_time, status, pnl_raw, pnl_pct, pnl_usdt)
                            
                            display_pnl_pct = pnl_pct
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
                                f"📊 *FREE SIGNAL CLOSED* \n"
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
            try:
                from utils_error import send_telegram_alert
                send_telegram_alert("Engine Error (Crypto Theory Trades Loop)", e)
            except: pass

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
    logger.debug("🏔️ Starting Sherpa Signal Task (15m Precision)...")
    mdm = live_bot_multi.MarketDataManager()
    try:
        while True:
            try:
                # 1. Wait until next 15-minute mark + buffer
                now = time.time()
                seconds_past_mark = now % 900
                wait_time = 900 - seconds_past_mark + 30
                logger.debug(f"Sherpa Sleeping {wait_time:.1f}s until next candle close...")
                await asyncio.sleep(wait_time)

                # Reset MDM cache for the new cycle
                mdm.ohlcv_cache = {}
                
                # Fetch all OHLCV in parallel using public API
                await asyncio.gather(*(mdm.fetch_ohlcv(sym, "15m", limit=1000) for sym in live_bot_multi.SYMBOLS))

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
                                 open_ts=open_ts,
                                 strategy=strategy_name
                            )
                        except Exception as chart_err:
                            logger.error(f"Forward test chart generation failed: {chart_err}")
                        
                        all_targets = database.get_all_broadcast_targets()
                        currency = get_currency(symbol)
                        signal_ts = open_ts // 1000  # convert ms to seconds
                        entry_text, entry_entities = build_datetime_entity_message(
                            f"🏔️ *NEW FREE SIGNAL* \n"
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
                    
                    sem = asyncio.Semaphore(3)
                    for strat_name, users in strategy_groups.items():
                        user_signals = {}
                        for symbol in live_bot_multi.SYMBOLS:
                            df = await mdm.fetch_ohlcv(symbol, "15m")
                            if df is not None:
                                sig = live_bot_multi.compute_signal(df, symbol.split("/")[0], strategy_name=strat_name)
                                if sig: user_signals[symbol] = sig
                        
                        if not user_signals:
                            logger.debug(f"No signals generated for strategy '{strat_name}'. Skipping user trade check.")
                            continue
                            
                        async def execute_user_signals(user):
                            async with sem:
                                try:
                                    chat_id = user.get('telegram_chat_id')
                                    web_user_id = user.get('web_user_id')
                                    if not user.get('api_key'): return
                                    
                                    ex_id = user.get('exchange_id', 'blofin')
                                    if ex_id == 'alpaca':
                                        ex_id = 'blofin'
                                    futures_type = user.get('bingx_futures_type', 'standard') or 'standard'
                                    
                                    try:
                                        async with database.get_exchange_client(user) as user_ex:
                                            # Share loaded markets across identical exchanges to save API overhead
                                            async with SHARED_MARKETS_LOCK:
                                                cache_time = SHARED_MARKETS_TIME.get(user_ex.id, 0)
                                                if user_ex.id in SHARED_MARKETS and (time.time() - cache_time) < 900:
                                                    user_ex.markets = SHARED_MARKETS[user_ex.id]
                                                else:
                                                    await user_ex.load_markets()
                                                    SHARED_MARKETS[user_ex.id] = user_ex.markets
                                                    SHARED_MARKETS_TIME[user_ex.id] = time.time()
                                            
                                            bal_params = database.get_exchange_balance_params(ex_id, futures_type=futures_type)
                                            balance = await user_ex.fetch_balance(params=bal_params)
                                            if ex_id == 'coinbase':
                                                usd_bal = balance.get('USD', {})
                                                usdc_bal = balance.get('USDC', {})
                                                if not isinstance(usd_bal, dict): usd_bal = {}
                                                if not isinstance(usdc_bal, dict): usdc_bal = {}
                                                actual_equity = float(usd_bal.get("total") or usd_bal.get("free") or balance.get("free", {}).get("USD") or balance.get("total", {}).get("USD") or 0.0) + float(usdc_bal.get("total") or usdc_bal.get("free") or balance.get("free", {}).get("USDC") or balance.get("total", {}).get("USDC") or 0.0)
                                            else:
                                                asset = 'USDT'
                                                actual_equity = float(balance.get(asset, {}).get("total", 0) or balance.get(asset, {}).get("free", 0) or 0.0)
                                            
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
                                                side_str = "LONG" if sig['side'] == 'buy' else "SHORT"
                                                try:
                                                    try:
                                                        pos = await user_ex.fetch_positions()
                                                    except Exception as pos_err:
                                                        if ex_id != 'coinbase':
                                                            logger.error(f"Error fetching positions for {ex_id}: {pos_err}")
                                                        pos = []
                                                        
                                                    if not any(p.get('symbol') == norm_sym and float(p.get("contracts", 0) or 0) != 0 for p in pos):
                                                        if live_bot_multi.DRY_RUN: continue
                                                            
                                                        res = await live_bot_multi.place_order(user_ex, norm_sym, sig, equity, risk_pct=user_risk)
                                                        if res:
                                                            if chat_id:
                                                                database.increment_opened(chat_id)
                                                                side_icon = "📈" if sig['side'] == 'buy' else "📉"
                                                                from web_api.disclaimer import NFA_SHORT_MARKDOWN
                                                                msg = (
                                                                    f"{side_icon} *{strat_name}* SIGNAL!\n\n"
                                                                    f"Symbol: {get_symbol_link(res['symbol'])}\n"
                                                                    f"Risk: `{user_risk:.2f}%`\n"
                                                                    f"Entry: `{res['entry']:.8f}`\n"
                                                                    f"TP: `{res['tp']:.8f}`\n"
                                                                    f"SL: `{res['sl']:.8f}`"
                                                                    f"{NFA_SHORT_MARKDOWN}"
                                                                )
                                                                try:
                                                                    df = await mdm.fetch_ohlcv(symbol, timeframe='15m')
                                                                    chart_file = await asyncio.to_thread(charting.generate_trade_chart, res['symbol'], df, res['entry'], res['tp'], res['sl'], side_str, open_ts=int(time.time() * 1000), strategy=strategy_name)
                                                                    is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
                                                                    keyboard = get_nav_buttons(True, is_admin=is_admin)
                                                                    with open(chart_file, 'rb') as photo:
                                                                        await application.bot.send_photo(chat_id=chat_id, photo=photo, caption=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                                                                except Exception as chart_err:
                                                                    logger.error(f"Chart generation failed: {chart_err}")
                                                                    await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                                                            else:
                                                                logger.info(f"Signal executed successfully for web-only user {web_user_id}. Symbol: {res['symbol']}")
                                                except Exception as sym_err:
                                                    logger.error(f"Signal execution failed for user {chat_id or f'web_{web_user_id}'} on {ex_id} executing {side_str} trade on {symbol}: {sym_err}")
                                                    err_str = str(sym_err).lower()
                                                    if "insufficient" not in err_str and "balance" not in err_str:
                                                        from utils_error import send_telegram_alert
                                                        user_info = f"User: {chat_id or f'web_{web_user_id}'}, Symbol: {symbol}, Side: {side_str}"
                                                        send_telegram_alert(f"Engine Error (Crypto Signal) [{user_info}]", sym_err)
                                    except Exception as client_err:
                                        logger.error(f"Exchange client setup or balance sync failed for user {chat_id or f'web_{web_user_id}'} on {ex_id}: {client_err}")
                                        err_str = str(client_err).lower()
                                        if "insufficient" not in err_str and "balance" not in err_str:
                                            from utils_error import send_telegram_alert
                                            user_info = f"User: {chat_id or f'web_{web_user_id}'}, Exchange: {ex_id}"
                                            send_telegram_alert(f"Engine Error (Exchange Client) [{user_info}]", client_err)
                                except Exception as outer_err:
                                    logger.error(f"Signal execution outer error for user {user.get('telegram_chat_id') or 'web_' + str(user.get('web_user_id', '?'))}: {outer_err}")
                                    err_str = str(outer_err).lower()
                                    if "insufficient" not in err_str and "balance" not in err_str:
                                        from utils_error import send_telegram_alert
                                        user_info = f"User: {user.get('telegram_chat_id') or 'web_' + str(user.get('web_user_id', '?'))}"
                                        send_telegram_alert(f"Engine Error (Signal Outer) [{user_info}]", outer_err)
                        
                        await asyncio.gather(*(execute_user_signals(u) for u in users))
                
                logger.debug(f"Engine pass complete.")
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
        logger.debug("🏔️ Closing Sherpa Signal Task Market Data Manager...")
        await mdm.close()


async def execute_ai_recommendations_autopilot(application=None):
    """
    Auto-Execution Engine for AI Crypto Recommendations.
    Triggered daily at 01:00 AM EST after new Conservative & Income recommendations are generated.
    
    Rules enforced:
    1. Premium-only users with active exchange credentials and active_crypto_strategy == 'AI Recommendations Autopilot'.
    2. Enforces max 5 concurrent open positions.
    3. Caps total capital at risk to <= 25% of balance.
    4. Conservative leverage (capped at 2x - 3x max) with SL strictly above liquidation.
    5. Immediate market execution at current price.
    """
    logger.info("🤖 Starting AI Recommendations Autopilot execution pass...")
    try:
        now_ts = int(time.time())
        # Fetch active Conservative & Income crypto recommendations
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM AIRecommendations 
                WHERE status = 'active' 
                  AND category = 'crypto' 
                  AND LOWER(risk_profile) = 'conservative' 
                  AND LOWER(investment_goal) = 'income'
                ORDER BY created_at DESC LIMIT 5
            """)
            active_recs = [dict(r) for r in c.fetchall()]

        if not active_recs:
            logger.info("No active Conservative/Income crypto recommendations found to auto-execute.")
            return

        # Fetch active users
        active_users = database.get_all_active_users()
        if not active_users:
            return

        # Filter users configured for AI Recommendations Autopilot and with Premium access
        autopilot_users = []
        for u in active_users:
            strat = u.get('active_crypto_strategy', 'AI Recommendations Autopilot')
            if strat != 'AI Recommendations Autopilot':
                continue
            
            # Premium verification
            web_exp = u.get("premium_expiry") or 0
            is_adm = u.get("is_admin", False)
            if not is_adm and web_exp <= now_ts:
                continue

            if not u.get('api_key') or not u.get('api_secret'):
                continue
                
            autopilot_users.append(u)

        if not autopilot_users:
            logger.info("No active premium autopilot users found.")
            return

        logger.info(f"Executing AI Recommendations Autopilot for {len(autopilot_users)} users across {len(active_recs)} recommendations...")

        for user in autopilot_users:
            chat_id = user.get('telegram_chat_id')
            web_user_id = user.get('web_user_id') or user.get('id')
            ex_id = user.get('exchange_id', 'blofin')
            if ex_id == 'alpaca':
                ex_id = 'blofin'

            try:
                async with database.get_exchange_client(user) as user_ex:
                    # 1. Fetch current open positions to check count limit (< 5) and existing symbols
                    try:
                        open_positions = await user_ex.fetch_positions()
                    except Exception as pe:
                        if ex_id != 'coinbase':
                            logger.error(f"Autopilot: error fetching positions for {ex_id}: {pe}")
                        open_positions = []

                    active_open = [p for p in open_positions if float(p.get("contracts", 0.0) or 0.0) != 0]
                    if len(active_open) >= 5:
                        logger.debug(f"User {chat_id or web_user_id} already has {len(active_open)} active positions (max 5). Skipping new entries.")
                        continue

                    open_symbols_normalized = {database.normalize_symbol(p.get('symbol', ''), user_ex.id) for p in active_open}

                    # 2. Fetch balance & calculate capital caps (max 25% total capital risk)
                    futures_type = user.get('bingx_futures_type', 'standard') or 'standard'
                    bal_params = database.get_exchange_balance_params(ex_id, futures_type=futures_type)
                    balance = await user_ex.fetch_balance(params=bal_params)

                    if ex_id == 'coinbase':
                        usd_bal = balance.get('USD', {})
                        usdc_bal = balance.get('USDC', {})
                        if not isinstance(usd_bal, dict): usd_bal = {}
                        if not isinstance(usdc_bal, dict): usdc_bal = {}
                        actual_equity = float(usd_bal.get("total") or usd_bal.get("free") or 0.0) + float(usdc_bal.get("total") or usdc_bal.get("free") or 0.0)
                    else:
                        actual_equity = float(balance.get('USDT', {}).get("total", 0) or balance.get('USDT', {}).get("free", 0) or 0.0)

                    if actual_equity <= 10.0:
                        logger.warning(f"User {chat_id or web_user_id} equity too low (${actual_equity:.2f}) for autopilot.")
                        continue

                    # Custom Capital Allocation Override
                    eq_type = user.get('custom_equity_type', 'all')
                    eq_val = user.get('custom_equity_value')
                    equity = actual_equity
                    if eq_type == 'amount' and eq_val is not None:
                        equity = min(float(eq_val), actual_equity)
                    elif eq_type == 'pct' and eq_val is not None:
                        equity = actual_equity * (float(eq_val) / 100.0)

                    # Cap maximum total capital risk across 5 positions to 25% (i.e. ~1.5% - 2% risk per trade)
                    user_risk = float(user.get('risk_pct', 1.5))
                    user_risk = min(user_risk, 2.0) # Ensure <= 2% per trade

                    # 3. Iterate recommendations and place orders
                    for rec in active_recs:
                        if len(active_open) >= 5:
                            break

                        raw_sym = rec['symbol']
                        pair = f"{raw_sym}/USDT" if '/' not in raw_sym and 'USDT' not in raw_sym else raw_sym
                        norm_sym = database.normalize_symbol(pair, user_ex.id)

                        if norm_sym in open_symbols_normalized:
                            continue

                        target_price = float(rec.get('target_price') or 0.0)
                        stop_loss = float(rec.get('stop_loss') or 0.0)
                        entry_price = float(rec.get('entry_price') or 0.0)

                        if entry_price <= 0.0 or stop_loss <= 0.0 or target_price <= 0.0:
                            continue

                        sl_dist = abs(entry_price - stop_loss)
                        rr = abs(target_price - entry_price) / sl_dist if sl_dist > 0 else 2.0

                        sig = {
                            "side": "buy",
                            "entry": entry_price,
                            "sl_dist": sl_dist,
                            "rr": rr
                        }

                        # Cap leverage at conservative 3x max for AI recommendations
                        res = await live_bot_multi.place_order(
                            user_ex,
                            norm_sym,
                            sig,
                            equity,
                            risk_pct=user_risk,
                            is_manual=True, # allows immediate entry at market
                            return_details=True,
                            max_leverage_cap=3
                        )

                        if res and not res.get("error"):
                            active_open.append({"symbol": norm_sym})
                            open_symbols_normalized.add(norm_sym)
                            database.update_position_status(chat_id, True, web_user_id=web_user_id)

                            # Record in TheoreticalTrades for live resolution
                            try:
                                with database.db_session() as conn:
                                    c = conn.cursor()
                                    c.execute("""
                                        INSERT INTO TheoreticalTrades (symbol, side, entry_price, tp_price, sl_price, open_time, status, strategy)
                                        VALUES (?, 'BUY', ?, ?, ?, ?, 'open', 'AI Recommendations Autopilot')
                                    """, (pair, res.get('entry', entry_price), target_price, stop_loss, int(time.time() * 1000)))
                                    conn.commit()
                            except Exception as dbe:
                                logger.error(f"Autopilot: failed recording theoretical trade: {dbe}")

                            # Notify via Telegram if user has connected bot
                            if chat_id and application:
                                try:
                                    from bot.ui.keyboards import get_nav_buttons
                                    is_adm = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
                                    kb = get_nav_buttons(True, is_admin=is_adm)
                                    msg = (
                                        f"💡 *AI RECOMMENDATION AUTOPILOT ENTRY*\n\n"
                                        f"Symbol: `{raw_sym}`\n"
                                        f"Direction: LONG 📈\n"
                                        f"Strategy: *Conservative Income (63% Win Rate)*\n"
                                        f"Leverage: `{res.get('leverage', 3)}x` (Conservative)\n"
                                        f"Target Price: `${target_price:,.2f}`\n"
                                        f"Stop Loss: `${stop_loss:,.2f}`\n\n"
                                        f"_The trading engine will actively monitor this trade until TP or SL is reached._"
                                    )
                                    await application.bot.send_message(
                                        chat_id=chat_id,
                                        text=msg,
                                        parse_mode="Markdown",
                                        reply_markup=InlineKeyboardMarkup(kb)
                                    )
                                except Exception as ne:
                                    logger.warning(f"Autopilot: Telegram notification failed for {chat_id}: {ne}")

                            logger.info(f"✅ Autopilot successfully entered {raw_sym} for user {chat_id or web_user_id}.")
                        else:
                            err_reason = res.get('message') if res else 'Unknown order failure'
                            logger.warning(f"Autopilot skipped/failed for {raw_sym} (User {chat_id or web_user_id}): {err_reason}")

            except Exception as ue:
                logger.error(f"Autopilot error for user {chat_id or web_user_id} on {ex_id}: {ue}")

    except Exception as e:
        logger.error(f"Critical error in execute_ai_recommendations_autopilot: {e}")

