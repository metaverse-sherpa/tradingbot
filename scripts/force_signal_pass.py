import os
import sys
import time
import asyncio
import ccxt.async_support as ccxt
import logging
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardMarkup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ForcePass")

# Ensure projects directory is in path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path.append(project_root)

# Load explicit .env path
dotenv_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path=dotenv_path)

import database
import live_bot_multi
import charting

# Resolve credentials and config
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN not found in environment!")
    sys.exit(1)

class MockApplication:
    def __init__(self, bot):
        self.bot = bot

def get_nav_buttons(has_open=False, is_admin=False):
    """Duplicates navigation helper for inline keyboards."""
    from telegram_bot import get_nav_buttons as t_nav
    return t_nav(has_open, is_admin)

async def run_force_pass():
    logger.info("🏔️ Initializing forced Institutional Signal and Execution pass...")
    database.init_db()
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    application = MockApplication(bot)
    
    mdm = live_bot_multi.MarketDataManager()
    
    try:
        # Reset MDM cache to get fresh values
        mdm.ohlcv_cache = {}
        
        logger.info("📡 Fetching fresh market data for all symbols...")
        await asyncio.gather(*(mdm.fetch_ohlcv(sym, "15m", limit=100) for sym in live_bot_multi.SYMBOLS))

        # 🧪 A. RESOLVE OPEN THEORETICAL TRADES
        logger.info("🧪 Step A: Resolving Open Theoretical Trades...")
        open_theory_trades = database.get_open_theoretical_trades()
        for t in open_theory_trades:
            symbol = t['symbol']
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
                    logger.info(f"Closed theoretical trade for {symbol} as {status.upper()} (+${pnl_usdt:.2f} PnL)")
                    
                    strategy = t.get('strategy', 'Mean Reversion Scalper')
                    if status == 'tp':
                        cheeky_note = (
                            f"\n\n🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆\n"
                            f"🔥 *Look what you missed out on!* If you had been trading the *{strategy}* strategy, you would've earned *{pnl_pct:+.2f}%*! 🏆\n"
                            f"🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆"
                        )
                    elif status == 'sl':
                        cheeky_note = (
                            f"\n\n🛡️ *No strategy has 100% win rate.* Let's look for the next one!"
                        )
                    else:
                        cheeky_note = ""

                    # Broadcast EXIT alert
                    all_targets = database.get_all_broadcast_targets()
                    exit_msg = (
                        f"🔔 *SIMULATED TRADE CLOSED!* (Forward Test)\n"
                        f"🏔️ _Global strategy tracker resolution_\n\n"
                        f"Symbol: *{symbol}*\n"
                        f"Direction: *{'LONG 📈' if side == 'buy' else 'SHORT 📉'}*\n"
                        f"Exit Trigger: *{status.upper()}*\n\n"
                        f"Entry Price: `{entry_price:.8f}`\n"
                        f"Exit Price: `{exit_price:.8f}`\n"
                        f"Trade PnL: *{pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)*\n\n"
                        f"Simulated Balance: *${new_bal:,.2f} USDT*"
                        f"{cheeky_note}"
                    )
                    for target_id in all_targets:
                        try:
                            is_adm = (target_id == SUPER_ADMIN_ID)
                            u = database.get_user(target_id)
                            if u:
                                is_adm = (target_id == SUPER_ADMIN_ID or u.get('is_admin')) and not u.get('undercover_mode')
                            kb = get_nav_buttons(is_admin=is_adm)
                            await bot.send_message(
                                chat_id=target_id,
                                text=exit_msg,
                                reply_markup=InlineKeyboardMarkup(kb),
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            logger.warning(f"Failed forward test exit broadcast to {target_id}: {e}")

        # 🧪 B. EVALUATE NEW THEORETICAL SIGNALS FOR ALL STRATEGIES
        logger.info("🧪 Step B: Evaluating new signals for all strategies...")
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
                logger.info(f"Opened new simulated forward trade for {symbol} under strategy {strategy_name}")
                
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
                entry_msg = (
                    f"🏔️ *NEW SIMULATED SIGNAL!* (Forward Test)\n"
                    f"🤖 *Strategy:* `{strategy_name}`\n\n"
                    f"Symbol: *{symbol}*\n"
                    f"Direction: *{'LONG 📈' if side == 'buy' else 'SHORT 📉'}*\n"
                    f"Risk Setting: `1.5%`\n"
                    f"Simulated Entry: `{entry:.8f}`\n"
                    f"Take Profit (TP): `{tp:.8f}`\n"
                    f"Stop Loss (SL): `{sl:.8f}`\n\n"
                    f"Simulated Position Size: `{position_size_units:.4f}` units (~${position_size_usd:.2f} USD)\n"
                    f"Current Simulated Balance: *${sim_balance:,.2f} USDT*"
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
                                await bot.send_photo(
                                    chat_id=target_id,
                                    photo=photo,
                                    caption=entry_msg,
                                    reply_markup=InlineKeyboardMarkup(kb),
                                    parse_mode="Markdown"
                                )
                        else:
                            await bot.send_message(
                                chat_id=target_id,
                                text=entry_msg,
                                reply_markup=InlineKeyboardMarkup(kb),
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        logger.warning(f"Failed forward test entry broadcast to {target_id}: {e}")

        # 2. Process Signals (Active Users)
        logger.info("📲 Step 2: Processing Live Signals for Active Users...")
        active_users = database.get_all_active_users()
        if active_users:
            strategy_groups = {}
            for user in active_users:
                strat = user.get('strategy', 'Mean Reversion Scalper')
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
                            
                            balance = await user_ex.fetch_balance(params={"type": "futures"})
                            actual_equity = float(balance.get("USDT", {}).get("total", 0))
                            
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
                                pos = await user_ex.fetch_positions([norm_sym])
                                if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                                    if live_bot_multi.DRY_RUN:
                                        logger.info(f"Dry Run: Would place trade on {norm_sym} for chat {chat_id}")
                                        continue
                                        
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
                                        logger.info(f"Live trade placed successfully on {norm_sym} for user {chat_id}!")
                                        try:
                                            df = await mdm.fetch_ohlcv(symbol, timeframe='15m')
                                            side_str = "LONG" if sig['side'] == 'buy' else "SHORT"
                                            open_ts = int(time.time() * 1000)
                                            chart_file = await asyncio.to_thread(charting.generate_trade_chart, res['symbol'], df, res['entry'], res['tp'], res['sl'], side_str, open_ts=open_ts)
                                            is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
                                            keyboard = get_nav_buttons(True, is_admin=is_admin)
                                            with open(chart_file, 'rb') as photo:
                                                await bot.send_photo(chat_id=chat_id, photo=photo, caption=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                                        except Exception as chart_err:
                                            logger.error(f"Chart generation failed: {chart_err}")
                                            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Signal execution error for {user.get('telegram_chat_id')}: {e}")

                await asyncio.gather(*(execute_user_signals(u) for u in users))
        
        logger.info("✅ Forced pass execution completed successfully!")
    finally:
        await mdm.close()

if __name__ == "__main__":
    asyncio.run(run_force_pass())
