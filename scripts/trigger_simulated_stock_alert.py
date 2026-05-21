import os
import sys
import time
import asyncio
import sqlite3
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Ensure projects directory is in path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path.append(project_root)

# Load explicit .env path
dotenv_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path=dotenv_path)

import database
import charting
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

# Resolve super admin id
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))

def get_nav_buttons(has_open=False, is_admin=False):
    """Duplicates navigation helper for inline keyboards."""
    from telegram_bot import get_nav_buttons as t_nav
    return t_nav(has_open, is_admin)

def format_price(price, symbol=""):
    """Formats price beautifully based on symbol type and magnitude."""
    if not isinstance(price, (int, float)):
        try:
            price = float(price)
        except Exception:
            return str(price)
            
    symbol_str = str(symbol).upper()
    if symbol_str and "/" not in symbol_str and ":" not in symbol_str and "USDT" not in symbol_str:
        return f"{price:,.2f}"
        
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:,.4f}"
    else:
        return f"{price:.8f}".rstrip('0').rstrip('.') or "0"

def get_currency(symbol):
    """Determines simulated trade currency base."""
    symbol_str = str(symbol).upper()
    if symbol_str and "/" not in symbol_str and ":" not in symbol_str and "USDT" not in symbol_str:
        return "USD"
    return "USDT"

async def main():
    print("🏔️ Starting manual Stock Forward Test alert trigger script...")
    
    # 1. Initialize DB and gather targets
    database.init_db()
    all_targets = database.get_all_broadcast_targets()
    if not all_targets:
        print("❌ No registered users found in the bot users database!")
        print("💡 Please start your bot and run /start in Telegram first to register your user.")
        return
        
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found in environment!")
        return
        
    bot = Bot(token=token)
    print(f"📡 Found {len(all_targets)} registered target chat(s) to receive alerts.")
    
    # 2. Setup stock mock trade params
    symbol = "AAPL"
    strategy_name = "Sherpa Velocity Pullback"
    side = "buy"  # LONG
    currency = "USD"
    
    # 3. Fetch stock daily candles from cache
    print(f"📊 Fetching {symbol} daily stock bars from database cache...")
    conn = sqlite3.connect("data/stock_daily_cache.db")
    df = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", conn, params=(symbol,))
    conn.close()
    
    if df.empty or len(df) < 60:
        print(f"❌ Not enough daily stock data for {symbol} in data/stock_daily_cache.db! Found {len(df)} bars.")
        return
        
    # Standardize columns for charting.py
    df['timestamp'] = pd.to_datetime(df['date']).astype(int) // 10**6
    
    # Calculate ATR(14) dynamically
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()
    
    # Take the last 60 rows for visualization
    df_chart = df.tail(60).copy()
    
    last_row = df_chart.iloc[-1]
    entry = float(last_row['close'])
    atr = float(last_row['atr'])
    
    # Calculate strategy TP/SL
    tp = entry + 4.5 * atr
    sl = entry - 3.0 * atr
    
    open_ts = int(last_row['timestamp'])
    
    # 4. Size and insert theoretical trade
    sim_balance = database.get_theoretical_balance()
    risk_amt = sim_balance * 0.01  # 1% risk setting
    shares = risk_amt / (3.0 * atr)
    position_size_usd = shares * entry
    
    # Clean previous mock trades on AAPL to avoid state overlap
    open_trades = database.get_open_theoretical_trades()
    for t in open_trades:
        if t['symbol'] == symbol:
            database.close_theoretical_trade(t['id'], entry, open_ts, "cancelled", 0.0, 0.0, 0.0)
            
    database.add_theoretical_trade(
        symbol=symbol,
        strategy=strategy_name,
        side=side,
        entry_price=entry,
        tp_price=tp,
        sl_price=sl,
        open_time=open_ts,
        position_size=position_size_usd
    )
    print(f"📝 Opened mock simulated stock trade {symbol} in database. Entry: {entry:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
    
    chart_file = None
    try:
        chart_file = await asyncio.to_thread(
            charting.generate_trade_chart,
            symbol,
            df_chart,
            entry,
            tp,
            sl,
            "LONG",
            open_ts=open_ts,
            timeframe="1D",
            currency="USD"
        )
        print(f"🎨 Visual chart generated successfully: {chart_file}")
    except Exception as e:
        print(f"⚠️ Chart generation failed (falling back to text-only alert): {e}")

    # 5. Broadcast simulated entry alert
    entry_msg = (
        f"🏔️ *NEW SIMULATED SIGNAL* (Forward Test)\n"
        f"───────────────────────────────\n"
        f"Symbol:        *{symbol}*\n"
        f"Strategy:      *{strategy_name}*\n"
        f"Direction:     *LONG 📈*\n"
        f"Risk Setting:  `1.0%`\n\n"
        f"Simulated Entry: `{format_price(entry, symbol)}`\n"
        f"Take Profit (TP): `{format_price(tp, symbol)}`\n"
        f"Stop Loss (SL):   `{format_price(sl, symbol)}`\n\n"
        f"Simulated Position Size: `{shares:.4f}` shares (~${position_size_usd:.2f} {currency})\n"
        f"───────────────────────────────\n"
        f"Current Simulated Balance: *${sim_balance:,.2f} {currency}*"
    )
    
    print("📣 Broadcasting Entry alert to Telegram...")
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
            print(f"⚠️ Failed send to {target_id}: {e}")

    # 6. Sleep for 8 seconds to let user view entry
    print("⏳ Sleeping 8 seconds before triggering simulated Take Profit (TP)...")
    await asyncio.sleep(8)
    
    # 7. Settle theoretical trade (TP win)
    close_time = int(time.time() * 1000)
    pnl_raw = tp - entry
    pnl_pct = (pnl_raw / entry) * 100
    pnl_usd = shares * pnl_raw
    new_bal = sim_balance + pnl_usd
    
    database.update_theoretical_balance(new_bal)
    
    open_trades = database.get_open_theoretical_trades()
    mock_trade_id = [t['id'] for t in open_trades if t['symbol'] == symbol][-1]
    database.close_theoretical_trade(mock_trade_id, tp, close_time, "tp", pnl_raw, pnl_pct, pnl_usd)
    print("📝 Settled mock stock trade inside database as Take Profit (TP).")
    
    # 8. Broadcast simulated exit resolution alert
    cheeky_note = (
        f"\n\n🏆 *Look what you missed out on!*\n"
        f"If you had been trading the *{strategy_name}* strategy, you would've earned *{pnl_pct:+.2f}%*!"
    )
    
    exit_msg = (
        f"📊 *SIMULATED TRADE CLOSED* (Forward Test)\n"
        f"───────────────────────────────\n"
        f"Symbol:        *{symbol}*\n"
        f"Strategy:      *{strategy_name}*\n"
        f"Direction:     *LONG 📈*\n"
        f"Exit Trigger:  *TAKE PROFIT (TP)*\n\n"
        f"Entry Price:   `{format_price(entry, symbol)}`\n"
        f"Exit Price:    `{format_price(tp, symbol)}`\n"
        f"Trade PnL:     *{pnl_pct:+.2f}%* ({pnl_usd:+.2f} {currency})\n"
        f"───────────────────────────────\n"
        f"Simulated Balance:  *${new_bal:,.2f} {currency}*"
        f"{cheeky_note}"
    )
    
    print("📣 Broadcasting Exit alert to Telegram...")
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
            print(f"⚠️ Failed exit send to {target_id}: {e}")
            
    print("💎 Manual simulated forward test stock alert completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
