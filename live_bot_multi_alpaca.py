import os
import sqlite3
import pandas as pd
import numpy as np
import requests
import asyncio
import logging
import time
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AlpacaLiveBot")

load_dotenv()

TIINGO_API_KEY = os.getenv("TIINGO_API_KEY")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_DB_PATH = os.path.join(BASE_DIR, "data", "stock_daily_cache.db")
USER_DB_PATH = os.path.join(BASE_DIR, "data", "bot_users.db")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def send_telegram_message(chat_id, text):
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not found in environment.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: requests.post(url, json=payload, timeout=10))
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")

def update_stock_daily_cache():
    if not TIINGO_API_KEY:
        logger.error("TIINGO_API_KEY is not set.")
        return
    
    import stock_data_cache_daily
    stock_data_cache_daily.init_db()
    
    # We fetch the last 10 days of daily prices to make sure we don't miss anything (e.g. over weekends or holidays)
    today_str = datetime.today().strftime('%Y-%m-%d')
    from datetime import timedelta
    start_date = (datetime.today() - timedelta(days=10)).strftime('%Y-%m-%d')
    
    logger.info(f"Updating stock daily cache from {start_date} to {today_str}...")
    
    for ticker in stock_data_cache_daily.SYMBOLS:
        data = stock_data_cache_daily.fetch_daily_data(ticker, TIINGO_API_KEY, start_date=start_date, end_date=today_str)
        if data:
            stock_data_cache_daily.save_to_db(ticker, data)
        # Small rate limit sleep
        time.sleep(0.5)

def calculate_symbol_indicators_and_signal(symbol):
    conn = sqlite3.connect(STOCK_DB_PATH)
    query = "SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC"
    df = pd.read_sql_query(query, conn, params=(symbol,))
    conn.close()
    
    if df.empty or len(df) < 60:
        return None, None
        
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df.sort_index(inplace=True)
    
    # Calculate EMA 50 & 200
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['sma_5'] = df['close'].rolling(window=5).mean()
    
    # ATR(14)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()
    
    # RSI(3)
    rsi_period = 3
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=rsi_period).mean()
    avg_loss = loss.rolling(window=rsi_period).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Get yesterday's values (last fully closed bar, index -1)
    yesterday = df.iloc[-1]
    
    # Trend Filter
    is_uptrend = yesterday['close'] > yesterday['ema_50'] and yesterday['ema_50'] > yesterday['ema_200']
    # RSI Pullback
    is_pullback = yesterday['rsi'] < 10
    
    signal = None
    if is_uptrend and is_pullback:
        signal = "LONG"
        
    res = yesterday.to_dict()
    res['date'] = str(yesterday.name.date()) if hasattr(yesterday.name, 'date') else str(yesterday.name)
    return res, signal

def fetch_today_open_prices():
    """
    Fetches real-time IEX prices for all 40 symbols to get today's open price.
    """
    import stock_data_cache_daily
    tickers_str = ",".join(stock_data_cache_daily.SYMBOLS)
    url = "https://api.tiingo.com/iex/"
    params = {
        "tickers": tickers_str,
        "token": TIINGO_API_KEY
    }
    
    opens = {}
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            for item in data:
                ticker = item.get("ticker")
                # Use today's open price. If open is None (e.g. before print), fallback to lastTradePrice or prev close
                open_price = item.get("open") or item.get("lastTradePrice") or item.get("last")
                if open_price:
                    opens[ticker] = float(open_price)
        else:
            logger.error(f"Error fetching real-time prices: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Failed to fetch today's open prices: {e}")
        
    # For any missing, fallback to last close from DB
    for sym in stock_data_cache_daily.SYMBOLS:
        if sym not in opens:
            try:
                conn = sqlite3.connect(STOCK_DB_PATH)
                c = conn.cursor()
                c.execute("SELECT close FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 1", (sym,))
                row = c.fetchone()
                conn.close()
                if row:
                    opens[sym] = float(row[0])
            except Exception as e:
                logger.error(f"Failed to fetch fallback close for {sym}: {e}")
                
    return opens

def check_is_market_open():
    import database
    # Get all active Alpaca users
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM Users WHERE is_active = 1 AND alpaca_api_key IS NOT NULL AND alpaca_api_key != '' AND active_stock_strategy = 'Sherpa Velocity Pullback' LIMIT 1")
        row = c.fetchone()
        
    if not row:
        # If no active users, check if today is a weekday (Monday-Friday)
        today = datetime.today()
        # 0 = Monday, 4 = Friday
        is_weekday = today.weekday() >= 0 and today.weekday() <= 4
        logger.info(f"No active Alpaca users found. Checking weekday status: {is_weekday}")
        return is_weekday
        
    # We have an active user! Let's get their keys and call /v2/clock
    user = database.get_user(row['telegram_chat_id'])
    try:
        clock = database.make_alpaca_request(user, "GET", "/v2/clock")
        is_open = clock.get("is_open", False)
        logger.info(f"Alpaca clock check: is_open = {is_open}")
        return is_open
    except Exception as e:
        logger.error(f"Failed to check market clock via Alpaca: {e}")
        today = datetime.today()
        return today.weekday() >= 0 and today.weekday() <= 4

def run_theoretical_tally_engine(today_opens):
    logger.info("Running Theoretical Tally Engine...")
    
    # 1. Update/check open trades using yesterday's high/low
    conn = sqlite3.connect(USER_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM TheoreticalTrades WHERE strategy = 'Sherpa Velocity Pullback' AND status = 'open'")
    open_trades = c.fetchall()
    
    colnames = [desc[0] for desc in c.description]
    open_trades_dicts = [dict(zip(colnames, row)) for row in open_trades]
    
    for trade in open_trades_dicts:
        trade_id = trade['id']
        sym = trade['symbol']
        entry_price = trade['entry_price']
        tp_price = trade['tp_price']
        sl_price = trade['sl_price']
        position_size = trade['position_size']
        
        try:
            db_conn = sqlite3.connect(STOCK_DB_PATH)
            db_c = db_conn.cursor()
            db_c.execute("SELECT open, high, low, close, date FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 2", (sym,))
            rows = db_c.fetchall()
            db_conn.close()
            
            if len(rows) < 2:
                continue
                
            y_open, y_high, y_low, y_close, y_date = rows[0]
            
            indicator_dict, _ = calculate_symbol_indicators_and_signal(sym)
            if indicator_dict:
                # Dynamic exit: yesterday's close > SMA(5) or yesterday's RSI(3) > 65
                is_dynamic_exit = indicator_dict['close'] > indicator_dict['sma_5'] or indicator_dict['rsi'] > 65
                
                if is_dynamic_exit:
                    # Close trade at today's open!
                    today_open = today_opens.get(sym, y_close)
                    pnl_raw = today_open - entry_price
                    pnl_pct = (pnl_raw / entry_price) * 100
                    pnl_usdt = position_size * (pnl_pct / 100)
                    
                    c.execute("""
                        UPDATE TheoreticalTrades 
                        SET close_time = ?, status = 'dynamic_exit', pnl_raw = ?, pnl_pct = ?, pnl_usdt = ?
                        WHERE id = ?
                    """, (int(datetime.now().timestamp()), pnl_raw, pnl_pct, pnl_usdt, trade_id))
                    
                    c.execute("SELECT value FROM Config WHERE key = 'theoretical_balance'")
                    bal_row = c.fetchone()
                    bal = float(bal_row[0]) if bal_row else 1000.0
                    new_bal = bal + pnl_usdt
                    c.execute("UPDATE Config SET value = ? WHERE key = 'theoretical_balance'", (str(new_bal),))
                    conn.commit()
                    logger.info(f"Theoretical Trade CLOSED (Dynamic Exit) for {sym}: PnL = {pnl_usdt:+.2f} USDT. New Balance: {new_bal:.2f}")
                    continue
            
            hit_sl = y_low <= sl_price
            hit_tp = y_high >= tp_price
            
            if hit_sl or hit_tp:
                close_time_ts = int(datetime.strptime(y_date, "%Y-%m-%d").timestamp())
                if hit_sl and hit_tp:
                    close_price = sl_price
                    status = 'sl'
                elif hit_sl:
                    close_price = sl_price
                    status = 'sl'
                else:
                    close_price = tp_price
                    status = 'tp'
                    
                pnl_raw = close_price - entry_price
                pnl_pct = (pnl_raw / entry_price) * 100
                pnl_usdt = position_size * (pnl_pct / 100)
                
                c.execute("""
                    UPDATE TheoreticalTrades 
                    SET close_time = ?, status = ?, pnl_raw = ?, pnl_pct = ?, pnl_usdt = ?
                    WHERE id = ?
                """, (close_time_ts, status, pnl_raw, pnl_pct, pnl_usdt, trade_id))
                
                c.execute("SELECT value FROM Config WHERE key = 'theoretical_balance'")
                bal_row = c.fetchone()
                bal = float(bal_row[0]) if bal_row else 1000.0
                new_bal = bal + pnl_usdt
                c.execute("UPDATE Config SET value = ? WHERE key = 'theoretical_balance'", (str(new_bal),))
                conn.commit()
                logger.info(f"Theoretical Trade CLOSED ({status.upper()}) for {sym}: PnL = {pnl_usdt:+.2f} USDT. New Balance: {new_bal:.2f}")
                
        except Exception as e:
            logger.error(f"Error checking exit for theoretical trade {sym}: {e}")
            
    # 2. Check for new buy entries
    import stock_data_cache_daily
    for sym in stock_data_cache_daily.SYMBOLS:
        c.execute("SELECT 1 FROM TheoreticalTrades WHERE symbol = ? AND strategy = 'Sherpa Velocity Pullback' AND status = 'open'", (sym,))
        if c.fetchone():
            continue
            
        indicator_dict, signal = calculate_symbol_indicators_and_signal(sym)
        if signal == "LONG":
            try:
                o_price = today_opens.get(sym)
                if not o_price:
                    continue
                    
                atr = indicator_dict['atr']
                tp_price = o_price + 4.5 * atr
                sl_price = o_price - 3.0 * atr
                
                c.execute("SELECT value FROM Config WHERE key = 'theoretical_balance'")
                bal_row = c.fetchone()
                bal = float(bal_row[0]) if bal_row else 1000.0
                
                risk_amt = bal * 0.01
                shares = risk_amt / (3.0 * atr)
                position_size_usd = shares * o_price
                
                c.execute("""
                    INSERT INTO TheoreticalTrades (symbol, strategy, side, entry_price, tp_price, sl_price, open_time, status, position_size)
                    VALUES (?, 'Sherpa Velocity Pullback', 'LONG', ?, ?, ?, ?, 'open', ?)
                """, (sym, o_price, tp_price, sl_price, int(datetime.now().timestamp()), position_size_usd))
                conn.commit()
                logger.info(f"🆕 Theoretical Trade OPENED: {sym} LONG at ${o_price:.2f} (SL: ${sl_price:.2f}, TP: ${tp_price:.2f}, Size: ${position_size_usd:.2f})")
            except Exception as e:
                logger.error(f"Failed to open theoretical trade for {sym}: {e}")
                
    conn.close()

async def run_real_trader_execution(today_opens):
    logger.info("Running Real Trader Execution Engine...")
    
    import database
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM Users WHERE is_active = 1 AND alpaca_api_key IS NOT NULL AND alpaca_api_key != ''")
        rows = c.fetchall()
        
    if not rows:
        logger.info("No active Alpaca users to execute trades for.")
        return
        
    for r in rows:
        chat_id = r['telegram_chat_id']
        user = database.get_user(chat_id)
        if not user or user.get("active_stock_strategy") != "Sherpa Velocity Pullback":
            continue
            
        logger.info(f"Processing real trade execution for user chat_id={chat_id}...")
        
        try:
            # 1. Fetch current positions on Alpaca
            positions = await database.make_alpaca_request_async(user, "GET", "/v2/positions")
            active_positions = {p['symbol']: p for p in positions if float(p.get("qty", 0)) != 0}
            
            # --- PHASE 1: PROCESS DYNAMIC EXITS ---
            for sym, pos in active_positions.items():
                indicator_dict, _ = calculate_symbol_indicators_and_signal(sym)
                if indicator_dict:
                    # Dynamic exit: yesterday's close > SMA(5) or yesterday's RSI(3) > 65
                    is_dynamic_exit = indicator_dict['close'] > indicator_dict['sma_5'] or indicator_dict['rsi'] > 65
                    
                    if is_dynamic_exit:
                        logger.info(f"Dynamic Exit triggered for real user {chat_id} symbol {sym}. Liquidating...")
                        try:
                            await database.make_alpaca_request_async(user, "DELETE", f"/v2/positions/{sym}")
                            
                            close_price = today_opens.get(sym, float(pos['avg_entry_price']))
                            msg = (
                                "🦙 *Alpaca Stock Strategy: Dynamic Exit Triggered* 🦙\n\n"
                                f"Exited **{sym}** LONG position at today's open.\n"
                                f"• Symbol: `{sym}`\n"
                                f"• Qty: `{pos['qty']}` shares\n"
                                f"• Entry Price: `${float(pos['avg_entry_price']):.2f}`\n"
                                f"• Approximate Exit Price: `${close_price:.2f}`\n"
                                "🚀 _Associated Stop-Loss and Take-Profit orders have been automatically cancelled._"
                            )
                            await send_telegram_message(chat_id, msg)
                        except Exception as e:
                            logger.error(f"Failed to liquidate real user {chat_id} position {sym}: {e}")
                            await send_telegram_message(chat_id, f"⚠️ *Alpaca Alert*: Failed to close position for {sym} dynamically: {e}")
            
            # --- PHASE 2: PROCESS NEW BUY ENTRIES ---
            import stock_data_cache_daily
            for sym in stock_data_cache_daily.SYMBOLS:
                if sym in active_positions:
                    continue
                    
                indicator_dict, signal = calculate_symbol_indicators_and_signal(sym)
                if signal == "LONG":
                    o_price = today_opens.get(sym)
                    if not o_price:
                        continue
                        
                    atr = indicator_dict['atr']
                    tp_price = o_price + 4.5 * atr
                    sl_price = o_price - 3.0 * atr
                    
                    try:
                        account = await database.make_alpaca_request_async(user, "GET", "/v2/account")
                        equity = float(account.get("equity", 0) or account.get("portfolio_value", 0))
                        
                        user_risk = float(user.get('stock_risk_pct', 1.0)) / 100.0
                        risk_amt = equity * user_risk
                        
                        qty = risk_amt / (3.0 * atr)
                        qty = round(qty, 4)
                        
                        if qty <= 0:
                            logger.warning(f"Sizing quantity is 0 for {sym} (Chat ID: {chat_id}). Risk amount ${risk_amt:.2f} is too small.")
                            continue
                            
                        order_payload = {
                            "symbol": sym,
                            "qty": str(qty),
                            "side": "buy",
                            "type": "market",
                            "time_in_force": "day"
                        }
                        
                        logger.info(f"Submitting fractional market order for user {chat_id} symbol {sym}: {order_payload}")
                        res = await database.make_alpaca_request_async(user, "POST", "/v2/orders", json_data=order_payload)
                        
                        # Store in local tracking DB
                        open_ts = int(time.time() * 1000)
                        database.add_alpaca_active_trade(
                            chat_id=chat_id,
                            symbol=sym,
                            qty=qty,
                            entry_price=o_price,
                            tp_price=tp_price,
                            sl_price=sl_price,
                            open_time=open_ts
                        )
                        
                        msg = (
                            "🦙 *Alpaca Stock Strategy: Buy Signal Triggered* 🦙\n\n"
                            f"Entered **{sym}** LONG at today's open.\n"
                            f"• Symbol: `{sym}`\n"
                            f"• Qty: `{qty}` shares\n"
                            f"• Entry Price: `${o_price:.2f}`\n"
                            f"• Take Profit: `${tp_price:.2f}`\n"
                            f"• Stop Loss: `${sl_price:.2f}`\n"
                            f"• Risk Allocated: `${risk_amt:.2f}` ({user.get('stock_risk_pct', 1.0)}% of equity)"
                        )
                        await send_telegram_message(chat_id, msg)
                        
                    except Exception as e:
                        logger.error(f"Failed to execute real trade for user {chat_id} symbol {sym}: {e}")
                        await send_telegram_message(chat_id, f"⚠️ *Alpaca Alert*: Buy signal for {sym} failed to execute: {e}")
                        
        except Exception as e:
            logger.error(f"Error executing trades for user {chat_id}: {e}")

async def main():
    logger.info("Starting Daily stock swing execution...")
    
    # 1. Market clock check
    if not check_is_market_open():
        logger.info("US Equities Market is closed today. Skipping swing execution.")
        return
        
    # 2. Update stock daily cache from Tiingo
    try:
        update_stock_daily_cache()
    except Exception as e:
        logger.error(f"Error updating stock cache: {e}")
        
    # 3. Fetch today's real-time open prices (or fallbacks)
    today_opens = fetch_today_open_prices()
    
    # 4. Run theoretical tally engine
    try:
        run_theoretical_tally_engine(today_opens)
    except Exception as e:
        logger.error(f"Error running theoretical engine: {e}")
        
    # 5. Run real user execution
    try:
        await run_real_trader_execution(today_opens)
    except Exception as e:
        logger.error(f"Error running real trader execution: {e}")
        
    logger.info("Daily stock swing execution completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
