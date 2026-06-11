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
            await asyncio.sleep(3600)

async def email_summary_engine(application):
    """
    Daily loop to compile and email daily summaries of trading signals
    to users who have selected 'daily' frequency.
    Runs once a day at 18:00 (6:00 PM) EST.
    """
    import utils_gcp
    
    logger.info("⏳ Starting Daily Email Summary Engine...")
    
    while True:
        try:
            tz = ZoneInfo('US/Eastern')
            now = datetime.now(tz)
            
            # Target is 6:00:00 PM EST today
            target = now.replace(hour=18, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
                
            wait_time = (target - now).total_seconds()
            logger.info(f"Daily Email Summary Scheduler sleeping for {wait_time:.1f}s until next run at {target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            await asyncio.sleep(wait_time)
            
            logger.info("📧 Compiling daily signals summary...")
            
            # Fetch all signals from the last 24 hours
            now_ms = int(time.time() * 1000)
            since_ms = now_ms - (24 * 60 * 60 * 1000)
            
            # Fetch from database
            with database.db_session() as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM TheoreticalTrades WHERE open_time >= ? OR (close_time >= ? AND status != 'open')", (since_ms, since_ms))
                rows = c.fetchall()
            
            signals = [dict(r) for r in rows]
            
            if not signals:
                logger.info("No trading signals to summarize in the last 24 hours.")
                await asyncio.sleep(60) # Avoid instant refires
                continue
                
            signals_opened = [s for s in signals if (s.get('open_time') or 0) >= since_ms and s['status'] == 'open']
            signals_closed = [s for s in signals if (s.get('close_time') or 0) >= since_ms and s['status'] != 'open']
            
            open_symbols = list(set([s['symbol'] for s in signals_opened]))
            live_prices = {}
            if open_symbols:
                try:
                    # Fetch crypto prices
                    crypto_syms = [sym for sym in open_symbols if not is_stock(sym)]
                    if crypto_syms:
                        r = requests.get("https://api.binance.us/api/v3/ticker/price", timeout=2)
                        if r.status_code != 200:
                            r = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=2)
                        if r.status_code == 200:
                            binance_prices = {item['symbol']: float(item['price']) for item in r.json()}
                            for sym in crypto_syms:
                                clean = sym.split(':')[0].replace('/', '')
                                if clean in binance_prices:
                                    live_prices[sym] = binance_prices[clean]
                        
                        remaining_crypto = [sym for sym in crypto_syms if sym not in live_prices]
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
                    logger.error(f"Error fetching crypto prices for daily digest: {pe}")

                try:
                    # Fetch stock prices
                    stock_syms = [sym for sym in open_symbols if is_stock(sym)]
                    if stock_syms:
                        alpaca_key = utils_gcp.get_secret("ALPACA_API_KEY") or os.getenv("ALPACA_API_KEY")
                        alpaca_secret = utils_gcp.get_secret("ALPACA_API_SECRET") or os.getenv("ALPACA_API_SECRET")
                        if alpaca_key and alpaca_secret:
                            headers = {"APCA-API-KEY-ID": alpaca_key, "APCA-API-SECRET-KEY": alpaca_secret}
                            sym_str = ",".join(stock_syms)
                            resp = requests.get(f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}", headers=headers, timeout=3)
                            if resp.status_code == 200:
                                for sym, snapshot in resp.json().items():
                                    live_prices[sym] = snapshot.get('latestTrade', {}).get('p', 0.0)
                except Exception as pe:
                    logger.error(f"Error fetching stock prices for daily digest: {pe}")

            # Compute current_pnl_pct and target_tp_pct for each opened signal
            for s in signals_opened:
                sym = s['symbol']
                entry_price = s['entry_price']
                tp_price = s.get('tp_price') or 0.0
                curr_price = live_prices.get(sym, entry_price)
                
                # Check direction (side)
                is_long = s['side'].upper() in ['BUY', 'LONG']
                
                # Calculate base percentage
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
                
                # Apply leverage to crypto
                if not is_stock(sym):
                    pnl *= CRYPTO_LEVERAGE
                    tp *= CRYPTO_LEVERAGE
                    
                s['current_pnl_pct'] = pnl
                s['target_tp_pct'] = tp

            # Dispatch to daily subscribers
            from web_api.db_web import get_users_for_email_alerts
            from web_api.email_service import send_alert_email, get_daily_summary_html
            
            daily_users = get_users_for_email_alerts("daily")
            if daily_users:
                subject = f"🏔️ Metaverse Sherpa Daily Signals Digest - {datetime.now(tz).strftime('%Y-%m-%d')}"
                
                for ru in daily_users:
                    if not ru.get("email"):
                        continue
                    
                    is_prem = ru.get("is_premium_user", False)
                    user_stats = {}
                    
                    if is_prem:
                        from database import get_user
                        tg_id = ru.get('telegram_chat_id')
                        tg_user = get_user(tg_id) if tg_id else None
                        
                        if tg_user:
                            # 1. Crypto stats
                            crypto_api_key = tg_user.get("api_key")
                            crypto_api_secret = tg_user.get("api_secret")
                            crypto_linked = bool(crypto_api_key and crypto_api_secret)
                            crypto_data = {"linked": crypto_linked}
                            
                            if crypto_linked:
                                crypto_equity = tg_user.get("equity", 1000.0) or 1000.0
                                crypto_cum_pnl = tg_user.get("cum_pnl", tg_user.get("cumulative_pnl", 0.0)) or 0.0
                                crypto_unrealized = 0.0
                                crypto_open_count = 0
                                
                                crypto_api_password = tg_user.get("api_password")
                                crypto_exchange_id = tg_user.get("exchange_id", "blofin")
                                try:
                                    import ccxt
                                    default_type = 'future' if crypto_exchange_id == 'bingx' else 'swap'
                                    config = {
                                        "apiKey": crypto_api_key,
                                        "secret": crypto_api_secret,
                                        "password": crypto_api_password or "",
                                        "options": {"defaultType": default_type},
                                        "timeout": 3000
                                    }
                                    client = getattr(ccxt, crypto_exchange_id)(config)
                                    try:
                                        positions = client.fetch_positions()
                                        for p in positions:
                                            contracts = float(p.get("contracts", 0) or 0)
                                            if contracts != 0:
                                                crypto_open_count += 1
                                                crypto_unrealized += float(p.get("unrealizedPnl", 0) or 0)
                                    finally:
                                        try: client.close()
                                        except: pass
                                except Exception as ce:
                                    logger.error(f"CCXT fetch error in daily summary for {tg_id}: {ce}")
                                
                                c_wins = tg_user.get("wins", tg_user.get("total_wins", 0)) or 0
                                c_losses = tg_user.get("losses", tg_user.get("total_losses", 0)) or 0
                                c_total = c_wins + c_losses
                                c_wr = (c_wins / c_total) * 100 if c_total > 0 else 0.0
                                
                                realized_daily_pnl = 0.0
                                daily_pnl = realized_daily_pnl + crypto_unrealized
                                daily_pnl_pct = (daily_pnl / crypto_equity) * 100 if crypto_equity > 0 else 0.0
                                
                                crypto_data.update({
                                    "equity": crypto_equity + crypto_unrealized,
                                    "daily_pnl_pct": daily_pnl_pct,
                                    "daily_pnl_usd": daily_pnl,
                                    "open_trades": crypto_open_count,
                                    "win_rate": c_wr,
                                    "wins": c_wins,
                                    "losses": c_losses
                                })
                            user_stats["crypto"] = crypto_data
                            
                            # 2. Stock stats
                            stock_api_key = tg_user.get("alpaca_api_key")
                            stock_api_secret = tg_user.get("alpaca_api_secret")
                            stock_linked = bool(stock_api_key and stock_api_secret)
                            stock_data = {"linked": stock_linked}
                            
                            if stock_linked:
                                stock_equity = 10000.0
                                stock_last_equity = 10000.0
                                stock_open_count = 0
                                try:
                                    acc = database.make_alpaca_request(tg_user, "GET", "/v2/account")
                                    if acc:
                                        stock_equity = float(acc.get("equity", 0) or acc.get("portfolio_value", 0))
                                        stock_last_equity = float(acc.get("last_equity", 0) or stock_equity)
                                    
                                    positions = database.make_alpaca_request(tg_user, "GET", "/v2/positions")
                                    if isinstance(positions, list):
                                        stock_open_count = len(positions)
                                except Exception as se:
                                    logger.error(f"Alpaca fetch error in daily summary for {tg_id}: {se}")
                                
                                stock_wins = 0
                                stock_losses = 0
                                try:
                                    orders = database.make_alpaca_request(tg_user, "GET", "/v2/orders", params={"status": "closed", "limit": 100})
                                    if isinstance(orders, list):
                                        for o in orders:
                                            qty = float(o.get("filled_qty", 0) or 0)
                                            if qty > 0 and o.get("side") == "sell":
                                                price = float(o.get("filled_avg_price", 0))
                                                entry = price
                                                for prev in orders:
                                                    if prev["symbol"] == o["symbol"] and prev["side"] == "buy":
                                                        entry = float(prev.get("filled_avg_price", price))
                                                        break
                                                pnl_raw = (price - entry) * qty
                                                if pnl_raw > 0:
                                                    stock_wins += 1
                                                else:
                                                    stock_losses += 1
                                except Exception as se:
                                    logger.error(f"Alpaca orders error in daily summary: {se}")
                                    
                                if stock_wins == 0 and stock_losses == 0:
                                    try:
                                        with database.db_session() as conn:
                                            c = conn.cursor()
                                            c.execute("SELECT COUNT(*) FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'closed' AND pnl_raw > 0", (tg_id,))
                                            stock_wins = c.fetchone()[0] or 0
                                            c.execute("SELECT COUNT(*) FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'closed' AND pnl_raw <= 0", (tg_id,))
                                            stock_losses = c.fetchone()[0] or 0
                                    except: pass
                                    
                                stock_total = stock_wins + stock_losses
                                s_wr = (stock_wins / stock_total) * 100 if stock_total > 0 else 0.0
                                
                                stock_daily_pnl = stock_equity - stock_last_equity
                                stock_daily_pnl_pct = (stock_daily_pnl / stock_last_equity) * 100 if stock_last_equity > 0 else 0.0
                                
                                stock_data.update({
                                    "equity": stock_equity,
                                    "daily_pnl_pct": stock_daily_pnl_pct,
                                    "daily_pnl_usd": stock_daily_pnl,
                                    "open_trades": stock_open_count,
                                    "win_rate": s_wr,
                                    "wins": stock_wins,
                                    "losses": stock_losses
                                })
                            user_stats["stock"] = stock_data
                            
                            # Record daily balance history for premium user using ZK public key
                            pub_key = ru.get("public_key")
                            if pub_key:
                                encrypted_crypto = ""
                                encrypted_stock = ""
                                if crypto_linked:
                                    raw_crypto_bal = str(crypto_equity + crypto_unrealized)
                                    encrypted_crypto = database.encrypt_with_public_key(pub_key, raw_crypto_bal)
                                if stock_linked:
                                    raw_stock_bal = str(stock_equity)
                                    encrypted_stock = database.encrypt_with_public_key(pub_key, raw_stock_bal)
                                    
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
                    
                    html_content = get_daily_summary_html(signals_opened, signals_closed, is_premium_user=is_prem, user_stats=user_stats)
                    send_alert_email(ru["email"], subject, html_content)
                logger.info(f"✅ Daily summary emails dispatched to {len(daily_users)} subscribers.")
            
            # Sleep 60 seconds to prevent double firing on exact boundary
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("⏳ Daily Email Summary Engine cancelled.")
            break
        except Exception as e:
            logger.error(f"⏳ Daily Email Summary Engine error: {e}")
            await asyncio.sleep(3600)
