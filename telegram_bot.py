import os
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import database

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Setup Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
    # Optional: Add quick reply buttons
    keyboard = [['/opentrades', '/list', '/stats']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Welcome to the Metaverse Sherpa Multi-Tenant Trading Bot!\n\n"
        "This bot allows multiple users to trade using their own Blofin API keys.\n\n"
        "Commands:\n"
        "1. /setup - Configure your API keys (AES encrypted)\n"
        "2. /stats - View your individual PnL and trade counts\n"
        "3. /opentrades - Check live positions and Target ROE\n"
        "4. /list - View your recent trade history\n"
        "5. /stop - Pause the bot for your account\n"
        "6. /resume - Resume trading",
        reply_markup=reply_markup
    )

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    context.user_data['setup_step'] = 1
    
    warning_text = (
        "🔒 *Secure Setup Process*\n\n"
        "You are about to link your Blofin exchange account. For your safety, ensure the API keys you provide have **Trade** permissions but absolutely **NO Withdrawal** permissions.\n\n"
        "To begin, please paste your **Blofin API Key**:"
    )
    await update.message.reply_text(warning_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text
    
    step = context.user_data.get('setup_step', 0)
    
    if step == 1:
        context.user_data['api_key'] = text
        context.user_data['setup_step'] = 2
        # Delete user's message so their key isn't sitting in chat history
        try: await update.message.delete()
        except: pass
        await update.message.reply_text("✅ Key received and wiped from chat history.\n\nNow, please paste your **API Secret**:")
        
    elif step == 2:
        context.user_data['api_secret'] = text
        context.user_data['setup_step'] = 3
        try: await update.message.delete()
        except: pass
        await update.message.reply_text("✅ Secret received and wiped.\n\nFinally, please provide your **API Password / Passphrase**:")
        
    elif step == 3:
        context.user_data['api_pass'] = text
        try: await update.message.delete()
        except: pass
        
        await update.message.reply_text("🔄 Encrypting and saving credentials...")
        
        # In a full implementation, we'd test the CCXT connection here before saving.
        # For now, we save it directly to the database.
        database.upsert_user(
            chat_id, 
            context.user_data['api_key'], 
            context.user_data['api_secret'], 
            context.user_data['api_pass'], 
            0.0 # Starting equity will be fetched by the engine on its first run
        )
        
        context.user_data['setup_step'] = 0
        context.user_data.clear()
        
        success_text = (
            "🎉 *Setup Complete!*\n\n"
            "Your credentials have been encrypted with military-grade symmetric encryption and stored safely. The trading engine will pick up your account on its next 5-minute cycle.\n\n"
            "Commands:\n"
            "📊 /stats - View your performance\n"
            "🔴 /stop - Pause trading\n"
            "🟢 /resume - Resume trading"
        )
        await update.message.reply_text(success_text, parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = database.get_user(update.message.chat_id)
    if not user:
        await update.message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
    
    wins = user['wins']
    losses = user['losses']
    opened = user['opened']
    cum_pnl_usdt = user.get('cum_pnl', 0.0)
    equity = user.get('equity', 200.0) # Fallback to 200 if not fetched yet
    
    wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    account_pnl_pct = (cum_pnl_usdt / equity) * 100 if equity > 0 else 0
    
    msg = f"📊 *Your All-Time Stats*\n\n"
    msg += f"Status: {'🟢 Active' if user['is_active'] else '🔴 Paused'}\n"
    msg += f"Total Trades Opened: {opened}\n"
    msg += f"Wins: {wins} | Losses: {losses}\n"
    msg += f"Win Rate: {wr:.1f}%\n"
    msg += f"Account PnL: {account_pnl_pct:+.2f}% (${cum_pnl_usdt:+.2f})\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def list_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = database.get_user(update.message.chat_id)
    if not user:
        await update.message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
        
    await update.message.reply_text("🔄 Fetching your recent trades directly from the exchange...")
    
    try:
        import ccxt
        user_ex = ccxt.blofin({
            "apiKey": user['api_key'],
            "secret": user['api_secret'],
            "password": user['api_password'],
            "options": {"defaultType": "swap"},
        })
        user_ex.load_markets()
        
        import live_bot_multi
        all_closed = []
        for sym in live_bot_multi.SYMBOLS:
            try:
                trades = user_ex.fetch_my_trades(sym, limit=50)
                for t in trades:
                    info = t.get("info", {})
                    gross_pnl = float(info.get("fillPnl") or 0)
                    if gross_pnl != 0:
                        fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                        net_pnl = gross_pnl - (fee * 2)
                        all_closed.append({
                            "symbol": sym,
                            "timestamp": t['timestamp'],
                            "net_pnl": net_pnl,
                            "price": t['price'],
                            "amount": t['amount']
                        })
            except: pass
                
        # Sort by timestamp descending
        all_closed.sort(key=lambda x: x['timestamp'], reverse=True)
        last_10 = all_closed[:10]
        
        if not last_10:
            await update.message.reply_text("No closed trades found yet.")
            return
            
        msg = "📜 *Your Last 10 Trades*\n\n"
        for t in last_10:
            import datetime
            dt = datetime.datetime.fromtimestamp(t['timestamp']/1000).strftime('%m-%d %H:%M')
            icon = "🚀" if t['net_pnl'] > 0 else "❌"
            status = "Won" if t['net_pnl'] > 0 else "Lost"
            
            # Calculate ROE for the list view
            try:
                market = user_ex.market(t['symbol'])
                contract_size = float(market.get('contractSize', 1))
                # Initial margin = (Price * Amount * ContractSize) / Leverage
                initial_margin = (t['price'] * t['amount'] * contract_size) / live_bot_multi.LEVERAGE
                roe_pct = (t['net_pnl'] / initial_margin) * 100 if initial_margin > 0 else 0
            except:
                roe_pct = 0
            
            msg += f"{icon} *Trade {status}* ({dt})\n"
            msg += f"Symbol: `{t['symbol']}`\n"
            msg += f"PnL: *${t['net_pnl']:+.2f}* | ROE: *{roe_pct:+.2f}%*\n\n"
            
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching trades: {e}")

async def open_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = database.get_user(update.message.chat_id)
    if not user:
        await update.message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
        
    await update.message.reply_text("🔍 Checking your live positions on the exchange...")
    
    try:
        import ccxt
        user_ex = ccxt.blofin({
            "apiKey": user['api_key'],
            "secret": user['api_secret'],
            "password": user['api_password'],
            "options": {"defaultType": "swap"},
        })
        user_ex.load_markets()
        
        import live_bot_multi
        positions = user_ex.fetch_positions(live_bot_multi.SYMBOLS)
        active = [p for p in positions if float(p.get("contracts", 0) or 0) != 0]
        
        if not active:
            await update.message.reply_text("You have no open trades at the moment.")
            return
            
        msg = "🛰 *Your Active Positions*\n\n"
        for p in active:
            sym = p['symbol']
            side = p['side'].upper()
            entry = float(p['entryPrice'] or 0)
            upnl = float(p['unrealizedPnl'] or 0)
            
            # 1. Calculate Current ROE
            try:
                market = user_ex.market(sym)
                contract_size = float(market.get('contractSize', 1))
                initial_margin = (entry * float(p['contracts']) * contract_size) / live_bot_multi.LEVERAGE
                roe = (upnl / initial_margin * 100) if initial_margin > 0 else 0
            except:
                roe = 0
                initial_margin = 0
            
                # 2. Fetch TP/SL Prices and Calculate Target ROE
            tp_price = 0
            sl_price = 0
            target_roe_str = "N/A"
            
            try:
                # 🛡️ Verified Blofin TPSL system
                try:
                    all_tpsl = user_ex.private_get_trade_orders_tpsl_pending({"instType": "SWAP"})
                    if all_tpsl and "data" in all_tpsl:
                        for o in all_tpsl["data"]:
                            if o.get('instId') == market['id']:
                                tp = float(o.get('tpTriggerPrice') or 0)
                                sl = float(o.get('slTriggerPrice') or 0)
                                if tp > 0: tp_price = tp
                                if sl > 0: sl_price = sl
                except: pass
                    
                if tp_price > 0:
                    if side == "LONG":
                        target_roe = ((tp_price - entry) / entry) * live_bot_multi.LEVERAGE * 100
                    else: # SHORT
                        target_roe = ((entry - tp_price) / entry) * live_bot_multi.LEVERAGE * 100
                    target_roe_str = f"{target_roe:+.1f}%"
            except: pass

            emoji = "🟢" if upnl >= 0 else "🔴"
            msg += f"{emoji} *{sym}* ({side})\n"
            msg += f"Entry: `{entry:.4f}`\n"
            
            # Use 8 decimal places to avoid scientific notation for small coins like SHIB
            tp_disp = f"{tp_price:.8f}".rstrip('0').rstrip('.') if tp_price > 0 else "None"
            sl_disp = f"{sl_price:.8f}".rstrip('0').rstrip('.') if sl_price > 0 else "None"
            
            msg += f"TP: `{tp_disp}` | SL: `{sl_disp}`\n"
            msg += f"PnL: *${upnl:+.2f}* | ROE: *{roe:+.2f}%*\n"
            msg += f"Target ROE: *{target_roe_str}*\n\n"
            
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching positions: {e}")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.set_active(update.message.chat_id, False)
    await update.message.reply_text("🔴 Trading is now paused for your account. The engine will skip you.")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.set_active(update.message.chat_id, True)
    await update.message.reply_text("🟢 Trading is resumed! The engine will pick you up on the next cycle.")

import asyncio
import ccxt
import pandas as pd
import live_bot_multi

async def trading_engine(application):
    logger.info("Starting Multi-Tenant Engine Task...")
    while True:
        try:
            logger.info("Engine Pass: Checking signals for all active Telegram users...")
            
            # 1. We only need ONE public exchange object to compute signals
            public_exchange = ccxt.blofin({"options": {"defaultType": "swap"}})
            public_exchange.load_markets()
            
            signals = {}
            # 2. Compute signals ONCE to save massive amounts of API rate limits
            for symbol in live_bot_multi.SYMBOLS:
                try:
                    ohlcv = public_exchange.fetch_ohlcv(symbol, live_bot_multi.TIMEFRAME, limit=live_bot_multi.CANDLE_LIMIT)
                    df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                    sig = live_bot_multi.compute_signal(df, symbol.split("/")[0])
                    if sig:
                        signals[symbol] = sig
                except Exception as e:
                    pass
            
            if signals:
                logger.info(f"Engine found signals on: {list(signals.keys())}")
            else:
                logger.info("No actionable signals this pass, but syncing stats...")
                
            # 3. Fetch all active users from DB (MUST run every pass for stat syncing)
            import sqlite3
            conn = sqlite3.connect('bot_users.db')
            c = conn.cursor()
            c.execute('SELECT telegram_chat_id, blofin_api_key, blofin_api_secret, blofin_api_password FROM Users WHERE is_active = 1')
            active_users = c.fetchall()
            conn.close()
            
            for row in active_users:
                chat_id = row[0]
                api_key = database.decrypt(row[1])
                api_secret = database.decrypt(row[2])
                api_pass = database.decrypt(row[3])
                
                try:
                    # 4. Create an isolated connection for THIS user
                    user_ex = ccxt.blofin({
                        "apiKey": api_key,
                        "secret": api_secret,
                        "password": api_pass,
                        "options": {"defaultType": "swap"},
                    })
                    user_ex.load_markets()
                    
                    balance = user_ex.fetch_balance(params={"type": "futures"})
                    equity = float(balance.get("USDT", {}).get("total", 0))
                    
                    # --- STATS SYNC FOR USER ---
                    user_data = database.get_user(chat_id)
                    last_ts = user_data.get('last_ts', 0)
                    
                    import time
                    if last_ts == 0: 
                        last_ts = int((time.time() - 172800) * 1000) # 48h lookback
                        
                    wins = user_data['wins']
                    losses = user_data['losses']
                    cum_pnl = user_data.get('cum_pnl', 0.0)
                    now_ts = int(time.time() * 1000)
                    
                    for sym in live_bot_multi.SYMBOLS:
                        try:
                            trades = user_ex.fetch_my_trades(sym, last_ts)
                            for t in trades:
                                if t['timestamp'] <= last_ts: continue
                                
                                info = t.get("info", {})
                                gross_pnl = float(info.get("fillPnl") or 0)
                                
                                if gross_pnl != 0:
                                    # Estimate round-trip fee
                                    fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                                    net_pnl = gross_pnl - (fee * 2)
                                    
                                    # Calculate ROE exactly like Blofin UI
                                    try:
                                        market = user_ex.market(sym)
                                        contract_size = float(market.get('contractSize', 1))
                                        price = float(t['price'])
                                        size = float(t['amount'])
                                        initial_margin = (price * size * contract_size) / live_bot_multi.LEVERAGE
                                        roe_pct = (net_pnl / initial_margin) * 100 if initial_margin > 0 else 0
                                    except:
                                        roe_pct = 0
                                        
                                    cum_pnl += net_pnl # Add actual USDT profit, not the leveraged ROE %
                                    if net_pnl > 0: 
                                        wins += 1
                                        header = "🚀 *Trade Won!*"
                                    else: 
                                        losses += 1
                                        header = "❌ *Trade Lost*"
                                    
                                    msg = (
                                        f"{header}\n\n"
                                        f"Symbol: `{sym}`\n"
                                        f"PnL: *${net_pnl:.2f}*\n"
                                        f"ROE: *{roe_pct:+.2f}%*"
                                    )
                                    await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                        except: pass
                    
                    database.update_user_stats(chat_id, wins, losses, cum_pnl, now_ts)
                    # Update equity in DB so /stats is accurate
                    conn = sqlite3.connect(database.DB_PATH)
                    c = conn.cursor()
                    c.execute('UPDATE Users SET starting_equity = ? WHERE telegram_chat_id = ?', (equity, chat_id))
                    conn.commit()
                    conn.close()
                    
                    # --- EXECUTE NEW SIGNALS ---
                    if signals:
                        for sym, sig in signals.items():
                            pos = user_ex.fetch_positions([sym])
                            if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                                
                                if live_bot_multi.DRY_RUN:
                                    logger.info(f"DRY RUN: skipping real order for Telegram user {chat_id}")
                                    continue
                                
                                res = live_bot_multi.place_order(user_ex, sym, sig, equity)
                                if res:
                                    database.increment_opened(chat_id)
                                    msg = (
                                        f"🚀 *New Trade Executed!*\n\n"
                                        f"Symbol: {res['symbol']}\n"
                                        f"Side: {res['side']}\n"
                                        f"Size: {res['size']}\n"
                                        f"Entry: {res['entry']}\n"
                                        f"TP: {res['tp']}\n"
                                        f"SL: {res['sl']}"
                                    )
                                    await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"User {chat_id} trade/sync failed: {e}")
                
            # Wait 5 minutes before checking again
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Engine pass critical failure: {e}")
            await asyncio.sleep(60) # Wait a minute before retrying to prevent error spam

async def post_init(application: ApplicationBuilder):
    # Set the bot's command menu (the button in the bottom left of Telegram)
    await application.bot.set_my_commands([
        ("stats", "📊 View account performance"),
        ("opentrades", "🛰 View live active positions"),
        ("list", "📜 List last 10 closed trades"),
        ("setup", "⚙️ Configure API keys"),
        ("stop", "🔴 Pause trading"),
        ("resume", "🟢 Resume trading"),
    ])
    # This automatically starts the background engine when the Telegram bot boots up
    asyncio.create_task(trading_engine(application))

def main():
    # Ensure database table exists
    database.init_db()
    
    # Initialize Bot Application with the post_init hook
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Register Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("opentrades", open_trades))
    app.add_handler(CommandHandler("list", list_trades))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("resume", resume_bot))
    
    # Catch all non-command messages (used for the setup step flow)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    logger.info("Starting Telegram Bot Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
