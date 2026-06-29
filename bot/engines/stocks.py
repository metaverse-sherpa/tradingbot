import time
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import aiohttp

import database
from bot.config import logger

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

    logger.debug("🦙 Starting Alpaca Stocks Daily Scheduler (9:31 AM EST)...")
    
    # Run cache catch-up update on scheduler startup in a non-blocking background task
    async def run_startup_cache_update():
        try:
            logger.debug("🏔️ Startup: Checking and updating stock daily cache...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, live_bot_multi_alpaca.update_stock_daily_cache)
            logger.debug("🏔️ Startup: Stock daily cache check/update completed.")
        except Exception as startup_err:
            logger.error(f"Error checking daily stock cache on startup: {startup_err}")

    asyncio.create_task(run_startup_cache_update())

    while True:
        try:
            tz = ZoneInfo('US/Eastern')
            now = datetime.now(tz)
            
            # Target is 9:31:00 AM EST today
            target = now.replace(hour=9, minute=31, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
                
            wait_time = (target - now).total_seconds()
            logger.debug(f"Alpaca Stocks Scheduler sleeping for {wait_time:.1f}s until next run at {target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            await asyncio.sleep(wait_time)
            
            logger.debug("🦙 Waking up! Running daily stock swing execution...")
            await live_bot_multi_alpaca.main()
            
            # Prevent double-fire by sleeping 60 seconds
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.debug("🦙 Alpaca Stocks Daily Scheduler task cancelled.")
            break
        except Exception as e:
            logger.error(f"🦙 Alpaca Stocks Daily Scheduler error: {e}")
            await asyncio.sleep(60)

async def alpaca_fractional_monitor_engine(application):
    """
    Monitors active fractional stock trades via Alpaca Data API.
    Checks if the recent High or Low crossed TP/SL, and executes an exit.
    """
    logger.debug("🦙 Starting Alpaca Fractional Shares Monitor Task (5m Loop)...")
    
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
                                    await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                                except Exception as e:
                                    logger.error(f"Failed to close fractional trade {sym} for {chat_id}: {e}")
                                    from utils_error import send_telegram_alert
                                    user_info = f"User: {chat_id}, Symbol: {sym}"
                                    send_telegram_alert(f"Engine Error (Stock Exit Failed) [{user_info}]", e)
                                    
        except asyncio.CancelledError:
            logger.debug("🦙 Alpaca Monitor task cancelled.")
            break
        except Exception as e:
            logger.error(f"Alpaca monitor error: {e}")
            try:
                from utils_error import send_telegram_alert
                send_telegram_alert("Engine Error (Fractional Stock Exit Loop)", e)
            except: pass
            await asyncio.sleep(60)

async def alpaca_hourly_sync_engine(application):
    import live_bot_multi_alpaca
    logger.debug("🦙 Starting Alpaca Hourly Sync Engine...")
    
    while True:
        try:
            tz = ZoneInfo('US/Eastern')
            now = datetime.now(tz)
            
            # Target next top of the hour
            target = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            wait_time = (target - now).total_seconds()
            
            logger.debug(f"Hourly Sync sleeping for {wait_time:.1f}s until {target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            await asyncio.sleep(wait_time)
            
            now = datetime.now(tz)
            # Only run during market hours (9:30 AM to 4:00 PM EST)
            # Since it runs on the hour, active times are 10:00, 11:00, 12:00, 13:00, 14:00, 15:00, 16:00
            if now.weekday() < 5 and (9 < now.hour <= 16):
                logger.debug("🦙 Waking up! Running hourly portfolio sync...")
                await live_bot_multi_alpaca.run_hourly_portfolio_sync()
            else:
                logger.debug("Hourly Sync: Market is closed or outside active hours. Skipping.")
                
            await asyncio.sleep(60) # Prevent double firing
        except asyncio.CancelledError:
            logger.debug("🦙 Alpaca Hourly Sync Engine task cancelled.")
            break
        except Exception as e:
            logger.error(f"Alpaca Hourly Sync error: {e}")
            await asyncio.sleep(60)
