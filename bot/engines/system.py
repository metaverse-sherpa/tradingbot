import os
import time
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
import sqlite3

import database
from bot.config import logger, is_stock, CRYPTO_LEVERAGE

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
            try:
                from utils_error import send_telegram_alert
                send_telegram_alert("Engine Error (Premium Expiration Loop)", e)
            except: pass
            await asyncio.sleep(3600)

async def fetch_weekly_stock_stats(tg_user):
    equity = 0.0
    weekly_pnl_pct = 0.0
    weekly_pnl_usd = 0.0
    try:
        loop = asyncio.get_event_loop()
        acc = await loop.run_in_executor(None, lambda: database.make_alpaca_request(tg_user, "GET", "/v2/account"))
        if acc:
            equity = float(acc.get("equity", 0) or acc.get("portfolio_value", 0))
        
        hist = await loop.run_in_executor(None, lambda: database.make_alpaca_request(tg_user, "GET", "/v2/account/portfolio/history", params={"period": "1W", "timeframe": "1D"}))
        if hist and hist.get("equity"):
            equities = [float(e) for e in hist["equity"] if e is not None]
            if len(equities) >= 2:
                start_eq = equities[0]
                if start_eq > 0:
                    weekly_pnl_usd = equity - start_eq
                    weekly_pnl_pct = (weekly_pnl_usd / start_eq) * 100
    except Exception as e:
        logger.error(f"Error fetching weekly stock stats for {tg_user.get('telegram_chat_id')}: {e}")
    return {
        "equity": equity,
        "weekly_pnl_pct": weekly_pnl_pct,
        "weekly_pnl_usd": weekly_pnl_usd
    }

async def fetch_premium_crypto_stats(tg_user):
    equity = 0.0
    weekly_pnl_pct = 0.0
    weekly_pnl_usd = 0.0
    
    crypto_api_key = tg_user.get("api_key")
    crypto_api_secret = tg_user.get("api_secret")
    crypto_api_password = tg_user.get("api_password") or ""
    crypto_exchange_id = tg_user.get("exchange_id", "blofin")
    
    if crypto_api_key and crypto_api_secret:
        try:
            import ccxt
            default_type = "swap"
            config = {
                "apiKey": crypto_api_key,
                "secret": crypto_api_secret,
                **({"password": crypto_api_password} if crypto_api_password else {}),
                "options": {"defaultType": default_type},
                "enableRateLimit": False,
                "timeout": 4000,
            }
            client = getattr(ccxt, crypto_exchange_id)(config)
            
            # Check for sandbox
            cb_sandbox = tg_user.get("coinbase_sandbox")
            if cb_sandbox in (1, True, '1', 'true', 'True') and crypto_exchange_id == 'coinbase':
                client.urls['api']['rest'] = 'https://api-sandbox.coinbase.com'
                
            loop = asyncio.get_event_loop()
            
            # Fetch balance
            futures_type = tg_user.get("bingx_futures_type", "standard") or "standard"
            bal_params = database.get_exchange_balance_params(crypto_exchange_id, futures_type=futures_type)
            
            bal = await loop.run_in_executor(None, lambda: client.fetch_balance(params=bal_params))
            
            if crypto_exchange_id == 'coinbase':
                usd_bal = bal.get('USD', {})
                usdc_bal = bal.get('USDC', {})
                free_usd = float(usd_bal.get('free') or usd_bal.get('total') or bal.get('free', {}).get('USD') or bal.get('total', {}).get('USD') or 0.0)
                free_usdc = float(usdc_bal.get('free') or usdc_bal.get('total') or bal.get('free', {}).get('USDC') or bal.get('total', {}).get('USDC') or 0.0)
                free_asset = free_usd + free_usdc
            else:
                asset = 'USDT'
                asset_bal = bal.get(asset, {})
                free_asset = float(asset_bal.get('free') or asset_bal.get('total') or bal.get('free', {}).get(asset) or bal.get('total', {}).get(asset) or 0.0)
            
            total_equity = free_asset
            try:
                positions = await loop.run_in_executor(None, client.fetch_positions)
                for p in positions:
                    margin = float(p.get('initialMargin') or p.get('margin') or p.get('info', {}).get('margin') or 0)
                    upnl = float(p.get('unrealizedPnl') or p.get('info', {}).get('unrealizedPnl') or 0)
                    total_equity += (margin + upnl)
            except Exception as pos_err:
                if crypto_exchange_id != 'coinbase':
                    logger.error(f"Error fetching positions for balance in weekly engine: {pos_err}")
                    
            equity = total_equity
            
            # Estimate weekly PnL using the user's historical balance snapshots in PortfolioBalanceHistory
            one_week_ago = int(time.time()) - 7 * 24 * 3600
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT encrypted_crypto_balance FROM PortfolioBalanceHistory 
                    WHERE user_id = (SELECT id FROM WebUsers WHERE telegram_chat_id = ?) 
                      AND encrypted_crypto_balance IS NOT NULL AND encrypted_crypto_balance != ''
                    ORDER BY ABS(timestamp - ?) ASC LIMIT 1
                """, (tg_user.get("telegram_chat_id"), one_week_ago))
                row = c.fetchone()
                if row and row[0]:
                    try:
                        # Decrypt
                        decrypted_str = database.decrypt(row[0])
                        start_eq = float(decrypted_str)
                        if start_eq > 0:
                            weekly_pnl_usd = equity - start_eq
                            weekly_pnl_pct = (weekly_pnl_usd / start_eq) * 100
                    except Exception as dec_err:
                        logger.error(f"Error decrypting historical balance: {dec_err}")
            
            try: client.close()
            except: pass
        except Exception as e:
            logger.error(f"Error fetching CCXT weekly crypto stats: {e}")
            
    return {
        "equity": equity,
        "weekly_pnl_pct": weekly_pnl_pct,
        "weekly_pnl_usd": weekly_pnl_usd
    }

async def fetch_premium_open_trades(tg_user, asset_class):
    open_positions = []
    
    if asset_class == "stock":
        alpaca_key = tg_user.get("alpaca_api_key")
        alpaca_secret = tg_user.get("alpaca_api_secret")
        if alpaca_key and alpaca_secret:
            try:
                loop = asyncio.get_event_loop()
                positions = await loop.run_in_executor(
                    None,
                    lambda: database.make_alpaca_request(tg_user, "GET", "/v2/positions")
                )
                if isinstance(positions, list):
                    for p in positions:
                        tp_price = 0.0
                        sl_price = 0.0
                        open_time = 0
                        try:
                            with database.db_session() as conn:
                                c = conn.cursor()
                                c.execute("SELECT tp_price, sl_price, open_time FROM AlpacaActiveTrades WHERE symbol = ? AND status = 'open' LIMIT 1", (p.get("symbol"),))
                                row = c.fetchone()
                                if row:
                                    tp_price = float(row[0] or 0.0)
                                    sl_price = float(row[1] or 0.0)
                                    open_time = int(row[2] or 0)
                                else:
                                    c.execute("SELECT tp_price, sl_price, open_time FROM TheoreticalTrades WHERE symbol = ? AND status = 'open' LIMIT 1", (p.get("symbol"),))
                                    row_t = c.fetchone()
                                    if row_t:
                                        tp_price = float(row_t[0] or 0.0)
                                        sl_price = float(row_t[1] or 0.0)
                                        open_time = int(row_t[2] or 0)
                        except Exception as db_err:
                            logger.error(f"Alpaca DB lookup error in weekly engine: {db_err}")
                        
                        entry_price = float(p.get("avg_entry_price", 0.0) or 0.0)
                        current_price = float(p.get("current_price", 0.0) or 0.0)
                        roe = float(p.get("unrealized_plpc", 0.0) or 0.0) * 100
                        
                        open_positions.append({
                            "symbol": p.get("symbol"),
                            "entry_price": entry_price,
                            "sl_price": sl_price,
                            "tp_price": tp_price,
                            "current_pnl_pct": roe,
                            "target_pnl_pct": abs(((tp_price - entry_price) / entry_price) * 100) if entry_price > 0 else 0.0,
                            "open_time": open_time
                        })
            except Exception as e:
                logger.error(f"Alpaca positions fetch error in weekly engine: {e}")
                
    elif asset_class == "crypto":
        crypto_api_key = tg_user.get("api_key")
        crypto_api_secret = tg_user.get("api_secret")
        crypto_api_password = tg_user.get("api_password") or ""
        crypto_exchange_id = tg_user.get("exchange_id", "blofin")
        
        if crypto_api_key and crypto_api_secret:
            try:
                import ccxt
                default_type = "swap"
                config = {
                    "apiKey": crypto_api_key,
                    "secret": crypto_api_secret,
                    **({"password": crypto_api_password} if crypto_api_password else {}),
                    "options": {"defaultType": default_type},
                    "enableRateLimit": False,
                    "timeout": 4000,
                }
                client = getattr(ccxt, crypto_exchange_id)(config)
                
                # Check for sandbox
                cb_sandbox = tg_user.get("coinbase_sandbox")
                if cb_sandbox in (1, True, '1', 'true', 'True') and crypto_exchange_id == 'coinbase':
                    client.urls['api']['rest'] = 'https://api-sandbox.coinbase.com'
                
                async def fetch_positions_async():
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, client.fetch_positions)
                
                positions = await fetch_positions_async()
                try: client.close()
                except: pass
                
                if isinstance(positions, list):
                    for pos in positions:
                        contracts = float(pos.get("contracts", 0.0) or 0.0)
                        if contracts != 0:
                            tp_price = 0.0
                            sl_price = 0.0
                            open_time = 0
                            try:
                                with database.db_session() as conn:
                                    c = conn.cursor()
                                    symbol_clean = pos.get('symbol', '').split(':')[0].replace('-', '/')
                                    import re
                                    symbol_clean = re.sub(r'^(\d+)', '', symbol_clean)
                                    symbol_clean = symbol_clean.replace('TONCOIN', 'TON')
                                    c.execute("SELECT tp_price, sl_price, open_time FROM TheoreticalTrades WHERE (symbol = ? OR symbol LIKE ?) AND status = 'open' LIMIT 1", (pos.get('symbol'), f"%{symbol_clean}%"))
                                    row = c.fetchone()
                                    if row:
                                        tp_price = float(row[0] or 0.0)
                                        sl_price = float(row[1] or 0.0)
                                        open_time = int(row[2] or 0)
                            except Exception as db_err:
                                logger.error(f"Crypto DB lookup error in weekly engine: {db_err}")
                            
                            entry_price = float(pos.get("entryPrice", 0.0) or 0.0)
                            tp_price_val = tp_price or entry_price
                            open_positions.append({
                                "symbol": pos.get("symbol"),
                                "entry_price": entry_price,
                                "sl_price": sl_price,
                                "tp_price": tp_price,
                                "current_pnl_pct": float(pos.get("percentage") or 0.0),
                                "target_pnl_pct": abs(((tp_price_val - entry_price) / entry_price) * 100) * CRYPTO_LEVERAGE if entry_price > 0 else 0.0,
                                "open_time": open_time
                            })
            except Exception as e:
                logger.error(f"Crypto positions fetch error in weekly engine: {e}")
                
    return open_positions

async def daily_stock_email_engine(application):
    """
    Daily loop to compile and email daily summaries of stock trading signals
    to users who have selected 'daily' frequency.
    Runs once a day at 18:00 (6:00 PM) EST.
    Also handles recording daily portfolio snapshots.
    """
    import utils_gcp
    logger.info("⏳ Starting Daily Stock Email Engine...")
    
    while True:
        try:
            tz = ZoneInfo('US/Eastern')
            now = datetime.now(tz)
            target = now.replace(hour=18, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
                
            wait_time = (target - now).total_seconds()
            logger.info(f"Daily Stock Email Scheduler sleeping for {wait_time:.1f}s until next run at {target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            await asyncio.sleep(wait_time)
            
            logger.info("📧 Compiling daily stock signals summary...")
            now_ms = int(time.time() * 1000)
            since_ms = now_ms - (24 * 60 * 60 * 1000)
            
            with database.db_session() as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM TheoreticalTrades WHERE open_time >= ? OR (close_time >= ? AND status != 'open')", (since_ms, since_ms))
                rows = c.fetchall()
            
            signals = [dict(r) for r in rows]
            stock_signals = [s for s in signals if is_stock(s['symbol'])]
            
            # 1. Capture snapshots first
            from web_api.db_web import get_users_for_daily_processing
            daily_users = get_users_for_daily_processing()
            for ru in daily_users:
                needs_snapshot = ru.get("needs_snapshot", False)
                is_prem = ru.get("is_premium_user", False)
                if is_prem and needs_snapshot:
                    from database import get_user
                    tg_id = ru.get('telegram_chat_id')
                    tg_user = get_user(tg_id) if tg_id else None
                    if tg_user:
                        crypto_api_key = tg_user.get("api_key")
                        crypto_api_secret = tg_user.get("api_secret")
                        crypto_linked = bool(crypto_api_key and crypto_api_secret)
                        stock_api_key = tg_user.get("alpaca_api_key")
                        stock_api_secret = tg_user.get("alpaca_api_secret")
                        stock_linked = bool(stock_api_key and stock_api_secret)
                        
                        crypto_equity = 0.0
                        if crypto_linked:
                            # Simple estimate from DB
                            crypto_equity = tg_user.get("equity", 1000.0) or 1000.0
                            
                        stock_equity = 0.0
                        if stock_linked:
                            try:
                                acc = database.make_alpaca_request(tg_user, "GET", "/v2/account")
                                if acc:
                                    stock_equity = float(acc.get("equity", 0) or acc.get("portfolio_value", 0))
                            except:
                                pass
                                
                        pub_key = ru.get("public_key")
                        if pub_key:
                            encrypted_crypto = database.encrypt_with_public_key(pub_key, str(crypto_equity)) if crypto_linked else ""
                            encrypted_stock = database.encrypt_with_public_key(pub_key, str(stock_equity)) if stock_linked else ""
                            try:
                                with database.db_session() as conn:
                                    c = conn.cursor()
                                    now_sec = int(time.time())
                                    twelve_hours_ago = now_sec - 12 * 3600
                                    c.execute("SELECT id FROM PortfolioBalanceHistory WHERE user_id = ? AND timestamp >= ?", (ru["id"], twelve_hours_ago))
                                    existing_history = c.fetchone()
                                    if existing_history:
                                        c.execute("UPDATE PortfolioBalanceHistory SET timestamp = ?, encrypted_crypto_balance = ?, encrypted_stock_balance = ? WHERE id = ?", (now_sec, encrypted_crypto, encrypted_stock, existing_history[0]))
                                    else:
                                        c.execute("INSERT INTO PortfolioBalanceHistory (user_id, timestamp, encrypted_crypto_balance, encrypted_stock_balance) VALUES (?, ?, ?, ?)", (ru["id"], now_sec, encrypted_crypto, encrypted_stock))
                            except Exception as db_err:
                                logger.error(f"Error saving portfolio balance history: {db_err}")

            if not stock_signals:
                logger.info("No stock trading signals to summarize. Skipping daily stock emails.")
                await asyncio.sleep(60)
                continue
                
            signals_opened = [s for s in stock_signals if (s.get('open_time') or 0) >= since_ms and s['status'] == 'open']
            signals_closed = [s for s in stock_signals if (s.get('close_time') or 0) >= since_ms and s['status'] != 'open']
            
            open_symbols = list(set([s['symbol'] for s in signals_opened]))
            live_prices = {}
            if open_symbols:
                try:
                    alpaca_key = utils_gcp.get_secret("ALPACA_API_KEY") or os.getenv("ALPACA_API_KEY")
                    alpaca_secret = utils_gcp.get_secret("ALPACA_API_SECRET") or os.getenv("ALPACA_API_SECRET")
                    if alpaca_key and alpaca_secret:
                        headers = {"APCA-API-KEY-ID": alpaca_key, "APCA-API-SECRET-KEY": alpaca_secret}
                        sym_str = ",".join(open_symbols)
                        resp = requests.get(f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}", headers=headers, timeout=3)
                        if resp.status_code == 200:
                            for sym, snapshot in resp.json().items():
                                live_prices[sym] = snapshot.get('latestTrade', {}).get('p', 0.0)
                except Exception as pe:
                    logger.error(f"Error fetching stock prices for daily stock digest: {pe}")

            for s in signals_opened:
                sym = s['symbol']
                entry_price = s['entry_price']
                tp_price = s.get('tp_price') or 0.0
                curr_price = live_prices.get(sym, entry_price)
                is_long = s['side'].upper() in ['BUY', 'LONG']
                if entry_price > 0:
                    if is_long:
                        pnl = ((curr_price - entry_price) / entry_price) * 100
                        tp = ((tp_price - entry_price) / entry_price) * 100 if tp_price > 0 else 0.0
                    else:
                        pnl = ((entry_price - curr_price) / entry_price) * 100
                        tp = ((entry_price - tp_price) / entry_price) * 100 if tp_price > 0 else 0.0
                else:
                    pnl = 0.0
                    tp = 0.0
                s['current_pnl_pct'] = pnl
                s['target_tp_pct'] = tp

            from web_api.email_service import send_alert_email, get_daily_stock_summary_html
            daily_stock_users = [ru for ru in daily_users if ru.get("wants_daily_email")]
            if daily_stock_users:
                subject = f"🏔️ Metaverse Sherpa Stock Session Summary - {datetime.now(tz).strftime('%Y-%m-%d')}"
                for ru in daily_stock_users:
                    if ru.get("email"):
                        is_prem = ru.get("is_premium_user", False)
                        html_content = get_daily_stock_summary_html(signals_opened, signals_closed, is_premium=is_prem)
                        send_alert_email(ru["email"], subject, html_content)
                logger.info(f"✅ Daily Stock summary emails dispatched to {len(daily_stock_users)} subscribers.")
            
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("⏳ Daily Stock Email Engine cancelled.")
            break
        except Exception as e:
            logger.error(f"⏳ Daily Stock Email Engine error: {e}")
            try:
                from utils_error import send_telegram_alert
                send_telegram_alert("Engine Error (Daily Stock Email Summary Loop)", e)
            except: pass
            await asyncio.sleep(3600)

async def daily_crypto_email_engine(application):
    """
    Daily loop to compile and email daily summaries of crypto trading signals
    to users who have selected 'daily' frequency.
    Runs once a day at 8:00 AM London time (Europe/London).
    """
    logger.info("⏳ Starting Daily Crypto Email Engine...")
    
    while True:
        try:
            tz = ZoneInfo('Europe/London')
            now = datetime.now(tz)
            target = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
                
            wait_time = (target - now).total_seconds()
            logger.info(f"Daily Crypto Email Scheduler sleeping for {wait_time:.1f}s until next run at {target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            await asyncio.sleep(wait_time)
            
            logger.info("📧 Compiling daily crypto signals summary...")
            now_ms = int(time.time() * 1000)
            since_ms = now_ms - (24 * 60 * 60 * 1000)
            
            with database.db_session() as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM TheoreticalTrades WHERE open_time >= ? OR (close_time >= ? AND status != 'open')", (since_ms, since_ms))
                rows = c.fetchall()
            
            signals = [dict(r) for r in rows]
            crypto_signals = [s for s in signals if not is_stock(s['symbol'])]
            
            if not crypto_signals:
                logger.info("No crypto trading signals to summarize. Skipping daily crypto emails.")
                await asyncio.sleep(60)
                continue
                
            signals_opened = [s for s in crypto_signals if (s.get('open_time') or 0) >= since_ms and s['status'] == 'open']
            signals_closed = [s for s in crypto_signals if (s.get('close_time') or 0) >= since_ms and s['status'] != 'open']
            
            open_symbols = list(set([s['symbol'] for s in signals_opened]))
            live_prices = {}
            if open_symbols:
                try:
                    r = requests.get("https://api.binance.us/api/v3/ticker/price", timeout=2)
                    if r.status_code != 200:
                        r = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=2)
                    if r.status_code == 200:
                        binance_prices = {item['symbol']: float(item['price']) for item in r.json()}
                        for sym in open_symbols:
                            clean = sym.split(':')[0].replace('/', '')
                            if clean in binance_prices:
                                live_prices[sym] = binance_prices[clean]
                    
                    remaining_crypto = [sym for sym in open_symbols if sym not in live_prices]
                    if remaining_crypto:
                        resp = requests.get("https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP", timeout=5)
                        if resp.status_code == 200:
                            data = resp.json().get('data', [])
                            price_map = {item['instId']: float(item['last']) for item in data}
                            for sym in remaining_crypto:
                                clean_sym = sym.split(':')[0].replace('/', '-')
                                if clean_sym in price_map:
                                    live_prices[sym] = price_map[clean_sym]
                except Exception as pe:
                    logger.error(f"Error fetching crypto prices for daily crypto digest: {pe}")

            for s in signals_opened:
                sym = s['symbol']
                entry_price = s['entry_price']
                tp_price = s.get('tp_price') or 0.0
                curr_price = live_prices.get(sym, entry_price)
                is_long = s['side'].upper() in ['BUY', 'LONG']
                if entry_price > 0:
                    if is_long:
                        pnl = ((curr_price - entry_price) / entry_price) * 100
                        tp = ((tp_price - entry_price) / entry_price) * 100 if tp_price > 0 else 0.0
                    else:
                        pnl = ((entry_price - curr_price) / entry_price) * 100
                        tp = ((entry_price - tp_price) / entry_price) * 100 if tp_price > 0 else 0.0
                else:
                    pnl = 0.0
                    tp = 0.0
                
                pnl *= CRYPTO_LEVERAGE
                tp *= CRYPTO_LEVERAGE
                s['current_pnl_pct'] = pnl
                s['target_tp_pct'] = tp

            from web_api.db_web import get_users_for_daily_processing
            from web_api.email_service import send_alert_email, get_daily_crypto_summary_html
            daily_users = get_users_for_daily_processing()
            daily_crypto_users = [ru for ru in daily_users if ru.get("wants_daily_email")]
            
            if daily_crypto_users:
                subject = f"🏔️ Metaverse Sherpa Crypto Daily Summary - {datetime.now(tz).strftime('%Y-%m-%d')}"
                for ru in daily_crypto_users:
                    if ru.get("email"):
                        is_prem = ru.get("is_premium_user", False)
                        html_content = get_daily_crypto_summary_html(signals_opened, signals_closed, is_premium=is_prem)
                        send_alert_email(ru["email"], subject, html_content)
                logger.info(f"✅ Daily Crypto summary emails dispatched to {len(daily_crypto_users)} subscribers.")
            
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("⏳ Daily Crypto Email Engine cancelled.")
            break
        except Exception as e:
            logger.error(f"⏳ Daily Crypto Email Engine error: {e}")
            try:
                from utils_error import send_telegram_alert
                send_telegram_alert("Engine Error (Daily Crypto Email Summary Loop)", e)
            except: pass
            await asyncio.sleep(3600)

async def weekly_stock_email_engine(application):
    """
    Weekly loop to compile and email weekly stock audits to all users.
    Runs on Fridays at 18:00 (6:00 PM) EST.
    """
    logger.info("⏳ Starting Weekly Stock Email Engine...")
    
    while True:
        try:
            tz = ZoneInfo('US/Eastern')
            now = datetime.now(tz)
            
            # Find next Friday 18:00 EST
            days_ahead = 4 - now.weekday()
            if days_ahead < 0 or (days_ahead == 0 and now.hour >= 18):
                days_ahead += 7
            target = (now + timedelta(days=days_ahead)).replace(hour=18, minute=0, second=0, microsecond=0)
            wait_time = (target - now).total_seconds()
            logger.info(f"Weekly Stock Email Scheduler sleeping for {wait_time:.1f}s until next run at {target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            await asyncio.sleep(wait_time)
            
            logger.info("📧 Compiling weekly stock audits...")
            from web_api.db_web import get_users_for_weekly_processing
            from web_api.email_service import send_alert_email, get_weekly_stock_summary_html
            
            weekly_users = get_users_for_weekly_processing()
            hypothetical_data = database.get_theoretical_stats()
            
            for ru in weekly_users:
                is_prem = ru.get("is_premium_user", False)
                has_exch = ru.get("has_stock_exchange", False)
                portfolio_data = None
                open_trades = None
                
                if is_prem and has_exch:
                    from database import get_user
                    tg_id = ru.get('telegram_chat_id')
                    tg_user = get_user(tg_id) if tg_id else None
                    if tg_user:
                        portfolio_data = await fetch_weekly_stock_stats(tg_user)
                        open_trades = await fetch_premium_open_trades(tg_user, "stock")
                        
                if ru.get("email"):
                    subject = f"🏔️ Metaverse Sherpa Weekly Stock Performance Audit - {datetime.now(tz).strftime('%Y-%m-%d')}"
                    html_content = get_weekly_stock_summary_html(
                        is_premium=is_prem,
                        has_exchange=has_exch,
                        portfolio_data=portfolio_data,
                        open_trades=open_trades,
                        hypothetical_data=hypothetical_data
                    )
                    send_alert_email(ru["email"], subject, html_content)
                    
            logger.info(f"✅ Weekly Stock summary emails dispatched to {len(weekly_users)} subscribers.")
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("⏳ Weekly Stock Email Engine cancelled.")
            break
        except Exception as e:
            logger.error(f"⏳ Weekly Stock Email Engine error: {e}")
            try:
                from utils_error import send_telegram_alert
                send_telegram_alert("Engine Error (Weekly Stock Email Audit Loop)", e)
            except: pass
            await asyncio.sleep(3600)

async def weekly_crypto_email_engine(application):
    """
    Weekly loop to compile and email weekly crypto audits to all users.
    Runs on Fridays at 18:30 (6:30 PM) EST.
    This runs 30 minutes after the stock weekly audit to avoid server overload.
    """
    logger.info("⏳ Starting Weekly Crypto Email Engine...")
    
    while True:
        try:
            tz = ZoneInfo('US/Eastern')
            now = datetime.now(tz)
            
            # Find next Friday 18:30 EST
            days_ahead = 4 - now.weekday()
            if days_ahead < 0 or (days_ahead == 0 and (now.hour > 18 or (now.hour == 18 and now.minute >= 30))):
                days_ahead += 7
            target = (now + timedelta(days=days_ahead)).replace(hour=18, minute=30, second=0, microsecond=0)
            wait_time = (target - now).total_seconds()
            logger.info(f"Weekly Crypto Email Scheduler sleeping for {wait_time:.1f}s until next run at {target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            await asyncio.sleep(wait_time)
            
            logger.info("📧 Compiling weekly crypto audits...")
            from web_api.db_web import get_users_for_weekly_processing
            from web_api.email_service import send_alert_email, get_weekly_crypto_summary_html
            
            weekly_users = get_users_for_weekly_processing()
            hypothetical_data = database.get_theoretical_stats()
            
            for ru in weekly_users:
                is_prem = ru.get("is_premium_user", False)
                has_exch = ru.get("has_crypto_exchange", False)
                portfolio_data = None
                open_trades = None
                
                if is_prem and has_exch:
                    from database import get_user
                    tg_id = ru.get('telegram_chat_id')
                    tg_user = get_user(tg_id) if tg_id else None
                    if tg_user:
                        portfolio_data = await fetch_premium_crypto_stats(tg_user)
                        open_trades = await fetch_premium_open_trades(tg_user, "crypto")
                        
                if ru.get("email"):
                    subject = f"🏔️ Metaverse Sherpa Weekly Crypto Performance Audit - {datetime.now(tz).strftime('%Y-%m-%d')}"
                    html_content = get_weekly_crypto_summary_html(
                        is_premium=is_prem,
                        has_exchange=has_exch,
                        portfolio_data=portfolio_data,
                        open_trades=open_trades,
                        hypothetical_data=hypothetical_data
                    )
                    send_alert_email(ru["email"], subject, html_content)
                    
            logger.info(f"✅ Weekly Crypto summary emails dispatched to {len(weekly_users)} subscribers.")
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("⏳ Weekly Crypto Email Engine cancelled.")
            break
        except Exception as e:
            logger.error(f"⏳ Weekly Crypto Email Engine error: {e}")
            try:
                from utils_error import send_telegram_alert
                send_telegram_alert("Engine Error (Weekly Crypto Email Audit Loop)", e)
            except: pass
            await asyncio.sleep(3600)
    await asyncio.sleep(3600)
