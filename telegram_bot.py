import os
import logging
import asyncio
import ccxt
import pandas as pd
import live_bot_multi
import media_gen
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import database

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Setup Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Quick reply buttons for daily monitoring
    keyboard = [['/opentrades', '/list', '/balance', '/stats'], ['/strategy', '/docs', '/setup']]
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
    chat_id = update.message.chat_id
    user = database.get_user(chat_id)
    if not user:
        await update.message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
    
    await update.message.reply_text("📊 Calculating your performance stats...")

    # Calculate Daily PnL from Exchange (Realized + Unrealized)
    realized_daily_pnl = 0.0
    total_unrealized_pnl = 0.0
    open_positions_count = 0
    import ccxt
    import time
    import live_bot_multi
    
    try:
        user_ex = ccxt.blofin({
            "apiKey": user['api_key'],
            "secret": user['api_secret'],
            "password": user['api_password'],
            "options": {"defaultType": "swap"},
        })
        
        now_ms = int(time.time() * 1000)
        twenty_four_hours_ago = now_ms - (24 * 60 * 60 * 1000)
        
        # 1. Get Realized PnL for last 24h
        for sym in live_bot_multi.SYMBOLS:
            try:
                trades = user_ex.fetch_my_trades(sym, since=twenty_four_hours_ago)
                for t in trades:
                    info = t.get("info", {})
                    gross_pnl = float(info.get("fillPnl") or 0)
                    if gross_pnl != 0:
                        fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                        net_pnl = gross_pnl - (fee * 2)
                        realized_daily_pnl += net_pnl
            except: pass
            
        # 2. Get Total Unrealized PnL from positions
        try:
            positions = user_ex.fetch_positions(live_bot_multi.SYMBOLS)
            for p in positions:
                contracts = float(p.get("contracts", 0) or 0)
                if contracts != 0:
                    open_positions_count += 1
                    total_unrealized_pnl += float(p.get("unrealizedPnl", 0) or 0)
        except: pass
            
    except Exception as e:
        logger.error(f"PnL calculation failed: {e}")

    wins = user['wins']
    losses = user['losses']
    cum_pnl_realized = user.get('cum_pnl', 0.0)
    equity = user.get('equity', 200.0)
    
    # Combined Totals
    overall_pnl_usdt = cum_pnl_realized + total_unrealized_pnl
    daily_pnl_usdt = realized_daily_pnl + total_unrealized_pnl
    
    total_closed = wins + losses
    wr = (wins / total_closed * 100) if total_closed > 0 else 0
    overall_pnl_pct = (overall_pnl_usdt / equity) * 100 if equity > 0 else 0
    daily_pnl_pct = (daily_pnl_usdt / equity) * 100 if equity > 0 else 0
    upnl_pct = (total_unrealized_pnl / equity) * 100 if equity > 0 else 0
    
    overall_pnl_usdt_str = f"${overall_pnl_usdt:+.2f}" if not user['hide_dollars'] else "****"
    daily_pnl_usdt_str = f"${daily_pnl_usdt:+.2f}" if not user['hide_dollars'] else "****"
    
    msg = f"📊 *Your Trading Performance*\n"
    msg += "_(Includes Open Positions PnL)_\n\n"
    msg += f"Overall PnL: *{overall_pnl_pct:+.2f}% ({overall_pnl_usdt_str})*\n"
    msg += f"Daily PnL: *{daily_pnl_pct:+.2f}% ({daily_pnl_usdt_str})*\n"
    flame = " 🔥" if wr > 50 else ""
    msg += f"Win Rate: *{wr:.1f}%{flame} ({wins} wins | {losses} losses)*\n\n"
    msg += f"Status: {'🟢 Active' if user['is_active'] else '🔴 Paused'}\n"
    msg += f"Open Positions: *{open_positions_count} ({upnl_pct:+.2f}%)*\n"
    msg += f"Closed Trades: *{total_closed}*\n"
    
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
        import charting
        import os
        
        positions = user_ex.fetch_positions(live_bot_multi.SYMBOLS)
        active = [p for p in positions if float(p.get("contracts", 0) or 0) != 0]
        
        if not active:
            await update.message.reply_text("You have no open trades at the moment.")
            return
            
        await update.message.reply_text(f"🛰 *Active Positions Found: {len(active)}*\nGenerating charts...")

        for p in active:
            sym = p['symbol']
            side = p['side'].upper()
            entry = float(p['entryPrice'] or 0)
            mark_price = float(p.get('markPrice') or 0)
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

            # 3. Generate the Chart
            chart_path = None
            try:
                open_ts = int(p.get('info', {}).get('createTime') or 0)
                ohlcv = user_ex.fetch_ohlcv(sym, timeframe='15m', limit=100)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                chart_path = charting.generate_trade_chart(sym, df, entry, tp_price, sl_price, side, open_ts)
            except Exception as e:
                logger.error(f"Chart generation failed for {sym}: {e}")

            if chart_path and os.path.exists(chart_path):
                # Prepare Share Button (Compressed to stay under 64-byte Telegram limit)
                # Format: sh_{sym}_{side}_{roe}_{entry}_{mark}_{pnl}
                # Using short prefixes and rounded numbers to save space
                s_side = "l" if side.lower() == "long" else "s"
                callback_data = f"sh_{sym}_{s_side}_{roe:.1f}_{entry:.6g}_{mark_price:.6g}_{upnl:.1f}"
                keyboard = [[InlineKeyboardButton("Share 📸", callback_data=callback_data)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                pnl_str = f"${upnl:+.2f}" if not user['hide_dollars'] else "****"
                caption = (
                    f"{'🟢' if side == 'long' else '🔴'} *{sym} ({side.upper()})*\n"
                    f"Entry: `{entry:.8f}`\n"
                    f"TP: `{tp_price:.8f}` | SL: `{sl_price:.8f}`\n"
                    f"PnL: *{pnl_str}* | ROE: *{roe:+.2f}%*"
                )
                
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(photo, caption=caption, parse_mode="Markdown", reply_markup=reply_markup)
                os.remove(chart_path) # Cleanup
            else:
                pnl_str = f"${upnl:+.2f}" if not user['hide_dollars'] else "****"
                msg = (
                    f"{'🟢' if side == 'long' else '🔴'} *{sym} ({side.upper()})*\n"
                    f"Entry: `{entry:.8f}`\n"
                    f"PnL: *{pnl_str}* | ROE: *{roe:+.2f}%*"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching positions: {e}")

async def strategy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = database.get_user(chat_id)
    if not user:
        await update.message.reply_text("Please run /setup first.")
        return
        
    keyboard = [
        [InlineKeyboardButton("Mean Reversion Scalper (Active)", callback_data="set_strat_mean")],
        [InlineKeyboardButton("Crypto Chart Patterns (Coming Soon)", callback_data="set_strat_soon")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current = user.get('strategy', 'Mean Reversion Scalper')
    await update.message.reply_text(
        f"🎯 *Strategy Selection*\n\n"
        f"Your current strategy: *{current}*\n\n"
        f"Choose a strategy for your account:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def strategy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "set_strat_mean":
        database.update_user_strategy(query.message.chat.id, "Mean Reversion Scalper")
        await query.edit_message_text("✅ Strategy set to: *Mean Reversion Scalper*", parse_mode="Markdown")
    elif query.data == "set_strat_soon":
        await query.answer("🚧 This strategy is coming soon!", show_alert=True)

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = database.get_user(chat_id)
    
    privacy_status = "🔒 HIDDEN" if user['hide_dollars'] else "👁️ SHOWN"
    
    msg = (
        f"⚙️ *User Settings*\n\n"
        f"Strategy: *{user['strategy']}*\n"
        f"Dollar PnL: *{privacy_status}*\n\n"
        f"Handle: @metaversesherpa_trading_bot\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"Toggle Privacy ({'Show' if user['hide_dollars'] else 'Hide'})", callback_data="toggle_privacy")],
        [InlineKeyboardButton("Change Strategy", callback_data="strategy_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user = database.get_user(chat_id)
    
    if query.data == "toggle_privacy":
        new_val = not user['hide_dollars']
        database.update_user_preference(chat_id, "hide_dollars", 1 if new_val else 0)
        await query.answer("✅ Privacy Mode updated!")
        
        # Refresh the menu
        privacy_status = "🔒 HIDDEN" if new_val else "👁️ SHOWN"
        msg = (
            f"⚙️ *User Settings*\n\n"
            f"Strategy: *{user['strategy']}*\n"
            f"Dollar PnL: *{privacy_status}*\n\n"
            f"Handle: @metaversesherpa_trading_bot\n"
        )
        keyboard = [
            [InlineKeyboardButton(f"Toggle Privacy ({'Show' if new_val else 'Hide'})", callback_data="toggle_privacy")],
            [InlineKeyboardButton("Change Strategy", callback_data="strategy_menu")]
        ]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif query.data == "strategy_menu":
        await strategy_command(update, context) # Re-use existing strategy menu logic

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = database.get_user(chat_id)
    new_val = not user['hide_dollars']
    database.update_user_preference(chat_id, "hide_dollars", 1 if new_val else 0)
    status = "HIDDEN 🔒" if new_val else "SHOWN 👁️"
    await update.message.reply_text(f"✅ Privacy Mode: Dollar amounts are now *{status}*.", parse_mode="Markdown")

async def share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Compressed Format: sh_{sym}_{side}_{roe}_{entry}_{mark}_{pnl}
    parts = query.data.split("_")
    sym = parts[1]
    side = "long" if parts[2] == "l" else "short"
    roe, entry, mark, pnl = float(parts[3]), float(parts[4]), float(parts[5]), float(parts[6])
    
    user = database.get_user(query.message.chat.id)
    card_path = media_gen.generate_pnl_card(sym, side, roe, entry, mark, hide_dollars=user['hide_dollars'], pnl_usdt=pnl)
    
    if card_path:
        with open(card_path, 'rb') as photo:
            await query.message.reply_photo(photo, caption=f"🚀 My *{sym}* trade results! Powered by Metaverse Sherpa.", parse_mode="Markdown")
    else:
        await query.answer("❌ Error generating card.", show_alert=True)

async def docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a brief tutorial of all bot commands."""
    help_text = (
        "📖 *Metaverse Sherpa Bot - User Manual*\n\n"
        "Welcome! Here is a guide to everything your bot can do:\n\n"
        
        "📊 *Trading & Performance*\n"
        "• /stats - Your dashboard. Shows Overall PnL, Daily PnL (last 24h), and Win Rate (including live trades).\n"
        "• /opentrades - Visual check. Fetches all live positions and generates *1H Candlestick Charts* with TP/SL zones.\n"
        "• /list - History. Shows your last 10 closed trades directly from the exchange.\n\n"
        
        "💰 *Account Management*\n"
        "• /balance - Check your wallet. Shows available USDT and *Total Account Value* (Cash + Margin + PnL).\n"
        "• /setup - The engine room. Connect or update your Blofin API keys securely.\n\n"
        
        "🎯 *Control & Strategy*\n"
        "• /strategy - Swap brains. Switch between different trading algorithms (e.g., Mean Reversion).\n"
        "• /stop - Emergency brake. Pauses the trading engine for your account.\n"
        "• /resume - Green light. Restarts the automated engine.\n\n"
        
        "_Need more help? Just tap any command to try it out!_"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.set_active(update.message.chat_id, False)
    await update.message.reply_text("🔴 Trading is now paused for your account. The engine will skip you.")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.set_active(update.message.chat_id, True)
    await update.message.reply_text("🟢 Trading is resumed! The engine will pick you up on the next cycle.")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_data = database.get_user(chat_id)
    
    if not user_data:
        await update.message.reply_text("❌ No API keys found. Please run /setup first.")
        return
        
    await update.message.reply_text("💰 Fetching your live balance...")
    
    try:
        # Note: database.get_user already returns decrypted keys
        api_key = user_data['api_key']
        api_secret = user_data['api_secret']
        api_pass = user_data['api_password']
        
        user_ex = ccxt.blofin({
            "apiKey": api_key,
            "secret": api_secret,
            "password": api_pass,
            "options": {"defaultType": "swap"},
        })
        
        balance = user_ex.fetch_balance(params={"type": "futures"})
        free = float(balance.get("USDT", {}).get("free", 0))
        
        # True Equity Calculation: Available + Margin + Unrealized PnL
        total_value = free
        try:
            positions = user_ex.fetch_positions()
            for p in positions:
                margin = float(p.get('info', {}).get('margin', 0))
                upnl = float(p.get('info', {}).get('unrealizedPnl', 0))
                total_value += (margin + upnl)
        except: pass
        
        msg = (
            "💰 *Your Account Balance*\n\n"
            f"Available Cash: *${free:.2f}* USDT\n"
            f"Total Account Value: *${total_value:.2f}* USDT\n\n"
            "_Total Value = Available + Margin + PnL_"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching balance: {e}")

async def trading_engine(application):
    logger.info("Starting Multi-Tenant Engine Task...")
    while True:
        try:
            # 1. Get all active users
            active_users = database.get_all_active_users()
            if not active_users:
                await asyncio.sleep(60)
                continue
            
            # 2. Group users by strategy to optimize API calls
            strategy_groups = {}
            for user in active_users:
                strat = user.get('strategy', 'Mean Reversion Scalper')
                if strat not in strategy_groups:
                    strategy_groups[strat] = []
                strategy_groups[strat].append(user)
            
            logger.info(f"Engine Pass: Processing {len(active_users)} users across {len(strategy_groups)} strategies...")
            
            # 3. Process each strategy group
            public_ex = ccxt.blofin({"options": {"defaultType": "swap"}})
            public_ex.load_markets()
            
            for strat_name, users in strategy_groups.items():
                signals = {}
                # Calculate signals once for this strategy
                for symbol in live_bot_multi.SYMBOLS:
                    try:
                        ohlcv = public_ex.fetch_ohlcv(symbol, "15m", limit=100)
                        df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                        sig = live_bot_multi.compute_signal(df, symbol.split("/")[0], strategy_name=strat_name)
                        if sig:
                            signals[symbol] = sig
                    except: pass
                
                # Execute for all users in this group
                for user in users:
                    try:
                        chat_id = user['chat_id']
                        user_ex = ccxt.blofin({
                            "apiKey": user['api_key'],
                            "secret": user['api_secret'],
                            "password": user['api_password'],
                            "options": {"defaultType": "swap"},
                        })
                        
                        balance = user_ex.fetch_balance(params={"type": "futures"})
                        equity = float(balance.get("USDT", {}).get("total", 0))
                        
                        # Sync stats and history
                        # We use the existing helper but need to handle the returns
                        # (The helper already sends notifications for closed trades)
                        database.update_user_stats_from_engine(chat_id, equity, user_ex, application)
                        
                        # Execute signals
                        if signals:
                            for symbol, sig in signals.items():
                                pos = user_ex.fetch_positions([symbol])
                                if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                                    if live_bot_multi.DRY_RUN:
                                        logger.info(f"DRY RUN: skipping order for {chat_id}")
                                        continue
                                        
                                    res = live_bot_multi.place_order(user_ex, symbol, sig, equity)
                                    if res:
                                        database.increment_opened(chat_id)
                                        msg = (
                                            f"🚀 *{strat_name}* SIGNAL!\n\n"
                                            f"Symbol: *{res['symbol']}*\n"
                                            f"Entry: `{res['entry']:.8f}`\n"
                                            f"TP: `{res['tp']:.8f}`\n"
                                            f"SL: `{res['sl']:.8f}`"
                                        )
                                        await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Error for user {user.get('chat_id')}: {e}")
            
            # Wait 5 minutes before next pass
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Engine pass critical failure: {e}")
            await asyncio.sleep(60)

async def post_init(application: ApplicationBuilder):
    # Set the bot's command menu (the button in the bottom left of Telegram)
    await application.bot.set_my_commands([
        ("privacy", "🔒 Toggle hide/show dollar PnL"),
        ("settings", "⚙️ Bot settings & privacy"),
        ("docs", "📖 View user manual & tutorials"),
        ("help", "❓ Get help & command guide"),
        ("stats", "📊 View account performance"),
        ("opentrades", "🛰 View live active positions"),
        ("list", "📜 List last 10 closed trades"),
        ("balance", "💰 Check available USDT balance"),
        ("strategy", "🎯 Select trading strategy"),
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
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("docs", docs))
    app.add_handler(CommandHandler("help", docs))
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("opentrades", open_trades))
    app.add_handler(CommandHandler("list", list_trades))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("strategy", strategy_command))
    app.add_handler(CallbackQueryHandler(strategy_callback, pattern="^set_strat_"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^toggle_privacy|^strategy_menu"))
    app.add_handler(CallbackQueryHandler(share_callback, pattern="^sh_"))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("resume", resume_bot))
    
    # Catch all non-command messages (used for the setup step flow)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    logger.info("Starting Telegram Bot Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
