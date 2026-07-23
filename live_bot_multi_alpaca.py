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

import utils_gcp

ALPACA_API_KEY = utils_gcp.get_secret("ALPACA_API_KEY")
ALPACA_API_SECRET = utils_gcp.get_secret("ALPACA_API_SECRET")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_DB_PATH = os.path.join(BASE_DIR, "data", "stock_daily_cache.db")
USER_DB_PATH = os.path.join(BASE_DIR, "data", "bot_users.db")
TELEGRAM_TOKEN = utils_gcp.get_secret("TELEGRAM_BOT_TOKEN")

async def send_telegram_message(chat_id, text, entities=None):
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not found in environment.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if entities:
        # entities is a list of MessageEntity objects — serialise to dicts for the raw HTTP call
        payload["entities"] = [e.to_dict() for e in entities]
    else:
        payload["parse_mode"] = "Markdown"
        
    def _do_send():
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Telegram API Error {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _do_send)
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")

def update_stock_daily_cache():
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        logger.error("ALPACA_API_KEY or ALPACA_API_SECRET is not set.")
        return
    
    import stock_data_cache_daily
    stock_data_cache_daily.init_db()
    
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    # Gather all stock symbols to update
    tickers = set(stock_data_cache_daily.SYMBOLS)
    try:
        import database
        with database.db_session() as conn_user:
            c_user = conn_user.cursor()
            c_user.execute("SELECT DISTINCT symbol FROM AlpacaActiveTrades WHERE status = 'open'")
            for r in c_user.fetchall():
                if r[0] and "/" not in r[0] and ":" not in r[0]:
                    tickers.add(r[0])
            c_user.execute("SELECT DISTINCT symbol FROM TheoreticalTrades WHERE status = 'open'")
            for r in c_user.fetchall():
                if r[0] and "/" not in r[0] and ":" not in r[0]:
                    tickers.add(r[0])
    except Exception as e:
        logger.error(f"Error gathering active trade symbols for cache update: {e}")
        
    logger.info(f"Updating stock daily cache for {len(tickers)} symbols up to {today_str}...")
    
    for ticker in sorted(list(tickers)):
        # Dynamic lookback: check the latest date in DB
        db_latest_date = None
        try:
            conn_stock = sqlite3.connect(STOCK_DB_PATH)
            c_stock = conn_stock.cursor()
            c_stock.execute("SELECT MAX(date) FROM StockDailyData WHERE symbol = ?", (ticker,))
            row = c_stock.fetchone()
            conn_stock.close()
            if row and row[0]:
                db_latest_date = row[0]
        except Exception as e:
            logger.error(f"Error querying latest date for {ticker}: {e}")
            
        # Helper to check if the date is already up to date
        def is_date_up_to_date(latest_date_str):
            if not latest_date_str:
                return False
            try:
                latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d").date()
                today = datetime.today().date()
                diff_days = (today - latest_dt).days
                if diff_days <= 1:
                    return True
                today_weekday = datetime.today().weekday()
                if today_weekday == 6 and diff_days <= 2: # Sunday, latest is Friday/Saturday
                    return True
                if today_weekday == 0 and diff_days <= 3: # Monday, latest is Friday/Saturday/Sunday
                    return True
                return False
            except Exception:
                return False

        if is_date_up_to_date(db_latest_date):
            logger.debug(f"Cache for {ticker} is already up to date ({db_latest_date}). Skipping.")
            continue
            
        if not db_latest_date:
            from datetime import timedelta
            fetch_start = (datetime.today() - timedelta(days=120)).strftime('%Y-%m-%d')
        else:
            from datetime import timedelta
            fetch_start = (datetime.strptime(db_latest_date, "%Y-%m-%d") + timedelta(days=1)).strftime('%Y-%m-%d')
            
        logger.debug(f"Fetching {ticker} daily bars from {fetch_start} to {today_str}...")
        data = stock_data_cache_daily.fetch_daily_data(ticker, ALPACA_API_KEY, ALPACA_API_SECRET, start_date=fetch_start, end_date=today_str)
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
    
    # Calculate indicators
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Calculate SuperTrend (10, 3)
    hl2 = (df['high'] + df['low']) / 2
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr_st = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr_st = tr_st.rolling(window=10).mean()
    
    upper_band = hl2 + (3.0 * atr_st)
    lower_band = hl2 - (3.0 * atr_st)
    st = [True] * len(df)
    c_vals = df['close'].values
    lb_vals = lower_band.values
    ub_vals = upper_band.values
    flow_arr = np.zeros(len(df))
    fup_arr = np.zeros(len(df))
    
    flow_arr[0] = lb_vals[0]
    fup_arr[0] = ub_vals[0]
    
    for i in range(1, len(df)):
        flow_arr[i] = max(lb_vals[i], flow_arr[i-1]) if c_vals[i-1] > flow_arr[i-1] else lb_vals[i]
        fup_arr[i] = min(ub_vals[i], fup_arr[i-1]) if c_vals[i-1] < fup_arr[i-1] else ub_vals[i]
        st[i] = True if c_vals[i] > fup_arr[i] else (False if c_vals[i] < flow_arr[i] else st[i-1])
    df['supertrend'] = st
    
    # ATR(14)
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()
    
    # RSI(4)
    rsi_period = 4
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
    is_uptrend = yesterday['supertrend'] == True and yesterday['close'] > yesterday['ema_200']
    # RSI Pullback
    is_pullback = yesterday['rsi'] < 26
    
    signal = None
    if is_uptrend and is_pullback:
        signal = "LONG"
        
    res = yesterday.to_dict()
    res['date'] = str(yesterday.name.date()) if hasattr(yesterday.name, 'date') else str(yesterday.name)
    return res, signal

def fetch_today_open_prices():
    """
    Fetches real-time prices for all 40 symbols to get today's open price.
    """
    import stock_data_cache_daily
    tickers_str = ",".join(stock_data_cache_daily.SYMBOLS)
    url = "https://data.alpaca.markets/v2/stocks/bars/latest"
    params = {
        "symbols": tickers_str,
        "feed": "iex",
    }
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    
    opens = {}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            bars = data.get("bars", {})
            for ticker, item in bars.items():
                open_price = item.get("o") or item.get("c")
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
    import database
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM Users WHERE is_active = 1 AND alpaca_api_key IS NOT NULL AND alpaca_api_key != '' AND active_stock_strategy != 'None' LIMIT 1")
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

async def run_theoretical_tally_engine(today_opens):
    logger.info("Running Theoretical Tally Engine...")
    
    # 1. Update/check open trades using yesterday's high/low
    import database
    with database.db_session() as conn:
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
        position_size = trade.get('position_size')
        if position_size is None:
            position_size = 1000.0
        
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
                # Dynamic exit: yesterday's RSI(4) > 75
                is_dynamic_exit = indicator_dict['rsi'] > 75
                
                if is_dynamic_exit:
                    # Close trade at today's open!
                    today_open = today_opens.get(sym, y_close)
                    pnl_raw = today_open - entry_price
                    pnl_pct = (pnl_raw / entry_price) * 100
                    pnl_usdt = position_size * (pnl_pct / 100)
                    
                    with database.db_session() as update_conn:
                        uc = update_conn.cursor()
                        uc.execute("""
                            UPDATE TheoreticalTrades 
                            SET close_time = ?, status = 'dynamic_exit', pnl_raw = ?, pnl_pct = ?, pnl_usdt = ?
                            WHERE id = ?
                        """, (int(datetime.now().timestamp()), pnl_raw, pnl_pct, pnl_usdt, trade_id))
                        
                        uc.execute("SELECT value FROM Config WHERE key = 'theoretical_balance'")
                        bal_row = uc.fetchone()
                        bal = float(bal_row[0]) if bal_row else 1000.0
                        new_bal = bal + pnl_usdt
                        uc.execute("UPDATE Config SET value = ? WHERE key = 'theoretical_balance'", (str(new_bal),))
                        
                    logger.info(f"Theoretical Trade CLOSED (Dynamic Exit) for {sym}: PnL = {pnl_usdt:+.2f} USDT. New Balance: {new_bal:.2f}")
                    
                    # Broadcast dynamic exit to all targets
                    try:
                        from telegram import MessageEntity
                        from datetime import timezone
                        import database
                        all_targets = database.get_all_broadcast_targets()
                        now_ts = int(time.time())
                        close_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
                        
                        exit_text_before = (
                            "📊 *FREE TRADE CLOSED* 📊\n"
                            "───────────────────────────────\n"
                            f"Symbol:        `{sym}`\n"
                            "Strategy:      Sherpa Velocity Pullback\n"
                            "Direction:     LONG 📈\n"
                            "Exit Trigger:  DYNAMIC EXIT (RSI > 75)\n\n"
                            f"Entry Price:   ${entry_price:.2f}\n"
                            f"Exit Price:    ${today_open:.2f}\n"
                            f"Trade PnL:     {pnl_pct:+.2f}%\n"
                            "───────────────────────────────\n\n"
                            "Closed at: "
                        )
                        placeholder = close_dt.strftime("%Y-%m-%d %H:%M UTC")
                        exit_msg = exit_text_before + placeholder
                        for target_id in all_targets:
                            await send_telegram_message(target_id, exit_msg)
                    except Exception as b_err:
                        logger.warning(f"Failed to send free exit broadcast to targets: {b_err}")
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
                
                import database
                with database.db_session() as update_conn:
                    uc = update_conn.cursor()
                    uc.execute("""
                        UPDATE TheoreticalTrades 
                        SET close_time = ?, status = ?, pnl_raw = ?, pnl_pct = ?, pnl_usdt = ?
                        WHERE id = ?
                    """, (close_time_ts, status, pnl_raw, pnl_pct, pnl_usdt, trade_id))
                    
                    uc.execute("SELECT value FROM Config WHERE key = 'theoretical_balance'")
                    bal_row = uc.fetchone()
                    bal = float(bal_row[0]) if bal_row else 1000.0
                    new_bal = bal + pnl_usdt
                    uc.execute("UPDATE Config SET value = ? WHERE key = 'theoretical_balance'", (str(new_bal),))
                
                logger.info(f"Theoretical Trade CLOSED ({status.upper()}) for {sym}: PnL = {pnl_usdt:+.2f} USDT. New Balance: {new_bal:.2f}")
                
                # Broadcast SL/TP exit to all targets
                try:
                    from telegram import MessageEntity
                    from datetime import timezone
                    import database
                    all_targets = database.get_all_broadcast_targets()
                    close_dt = datetime.fromtimestamp(close_time_ts, tz=timezone.utc)
                    
                    exit_text_before = (
                        "📊 *FREE SIGNAL CLOSED* 📊\n"
                        "───────────────────────────────\n"
                        f"Symbol:        `{sym}`\n"
                        "Strategy:      Sherpa Velocity Pullback\n"
                        "Direction:     LONG 📈\n"
                        f"Exit Trigger:  {status.upper()}\n\n"
                        f"Entry Price:   ${entry_price:.2f}\n"
                        f"Exit Price:    ${close_price:.2f}\n"
                        f"Trade PnL:     {pnl_pct:+.2f}%\n"
                        "───────────────────────────────\n\n"
                        "Closed at: "
                    )
                    placeholder = close_dt.strftime("%Y-%m-%d %H:%M UTC")
                    exit_msg = exit_text_before + placeholder
                    for target_id in all_targets:
                        await send_telegram_message(target_id, exit_msg)
                except Exception as b_err:
                    logger.warning(f"Failed to send free exit broadcast to targets: {b_err}")
                
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
                tp_price = o_price + 4.8 * atr
                sl_price = o_price - 3.0 * atr
                
                c.execute("SELECT value FROM Config WHERE key = 'theoretical_balance'")
                bal_row = c.fetchone()
                bal = float(bal_row[0]) if bal_row else 1000.0
                
                risk_amt = bal * 0.02
                shares = risk_amt / (3.0 * atr)
                position_size_usd = shares * o_price
                
                c.execute("""
                    INSERT INTO TheoreticalTrades (symbol, strategy, side, entry_price, tp_price, sl_price, open_time, status, position_size)
                    VALUES (?, 'Sherpa Velocity Pullback', 'LONG', ?, ?, ?, ?, 'open', ?)
                """, (sym, o_price, tp_price, sl_price, int(datetime.now().timestamp()), position_size_usd))
                conn.commit()
                logger.info(f"🆕 Theoretical Trade OPENED: {sym} LONG at ${o_price:.2f} (SL: ${sl_price:.2f}, TP: ${tp_price:.2f}, Size: ${position_size_usd:.2f})")
                
                # Broadcast entry alert to all Telegram targets
                try:
                    from telegram import MessageEntity
                    from datetime import timezone
                    import database
                    all_targets = database.get_all_broadcast_targets()
                    
                    now_ts = int(time.time())
                    now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
                    
                    from web_api.disclaimer import NFA_SHORT_MARKDOWN
                    entry_text_before = (
                        "🏔️ *NEW FREE SIGNAL* 🏔️\n"
                        "───────────────────────────────\n"
                        f"Symbol:        `{sym}`\n"
                        "Strategy:      Sherpa Velocity Pullback\n"
                        "Direction:     LONG 📈\n"
                        "Risk Setting:  2.0%\n\n"
                        f"Free Entry: ${o_price:.2f}\n"
                        f"Take Profit (TP): ${tp_price:.2f}\n"
                        f"Stop Loss (SL):   ${sl_price:.2f}\n\n"
                        f"Free Position Size: {shares:.4f} shares (~${position_size_usd:.2f} USD)\n"
                        "───────────────────────────────\n"
                        f"Current Free Balance: ${bal:,.2f} USD\n\n"
                        "Signal time: "
                    )
                    placeholder = now_dt.strftime("%Y-%m-%d %H:%M UTC")
                    entry_msg = entry_text_before + placeholder + NFA_SHORT_MARKDOWN
                    
                    for target_id in all_targets:
                        await send_telegram_message(target_id, entry_msg)
                        

                except Exception as b_err:
                    logger.warning(f"Failed to send free signal entry broadcast to targets: {b_err}")
                    
            except Exception as e:
                logger.error(f"Failed to open theoretical trade for {sym}: {e}")
                
    conn.close()


async def run_hourly_portfolio_sync(today_opens=None):
    logger.info("Running Hourly Portfolio Sync & Dynamic Exits...")
    if today_opens is None:
        today_opens = fetch_today_open_prices()
    
    import database
    import time
    from telegram import MessageEntity
    from datetime import datetime, timezone
    
    active_users = database.get_all_active_stock_users()
    if not active_users:
        return
        
    for user in active_users:
        chat_id = user.get('telegram_chat_id')
        web_user_id = user.get('web_user_id')
        strategy_name = user.get("active_stock_strategy", "None")
        if not user or strategy_name == "None":
            continue
            
        try:
            positions = await database.make_alpaca_request_async(user, "GET", "/v2/positions")
            active_positions = {p['symbol']: p for p in positions if float(p.get("qty", 0)) != 0}
            
            # Reconcile external closures
            import database
            with database.db_session() as conn_active:
                c_active = conn_active.cursor()
                if chat_id:
                    c_active.execute("SELECT id, symbol, entry_price, tp_price, sl_price, qty FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'open'", (chat_id,))
                else:
                    c_active.execute("SELECT id, symbol, entry_price, tp_price, sl_price, qty FROM AlpacaActiveTrades WHERE web_user_id = ? AND status = 'open'", (web_user_id,))
                open_db_trades = c_active.fetchall()
            
            for row in open_db_trades:
                trade_db_id = row[0]
                sym = row[1]
                entry_price_db = float(row[2]) if row[2] else 0.0
                tp_price = float(row[3]) if row[3] else None
                sl_price = float(row[4]) if row[4] else None
                qty_db = float(row[5]) if row[5] else 0.0
                
                if sym not in active_positions:
                    # Missing from Alpaca - manually closed!
                    orders = await database.make_alpaca_request_async(user, "GET", f"/v2/orders?status=closed&symbols={sym}&limit=1")
                    close_price = entry_price_db
                    if orders and len(orders) > 0:
                        cp = float(orders[0].get('filled_avg_price') or orders[0].get('limit_price') or entry_price_db)
                        if cp > 0: close_price = cp
                    else:
                        close_price = today_opens.get(sym, entry_price_db)
                        
                    pnl_raw = (close_price - entry_price_db) * qty_db
                    pnl_pct = ((close_price - entry_price_db) / entry_price_db) * 100 if entry_price_db > 0 else 0
                    now_ts = int(time.time())
                    
                    database.close_alpaca_trade(trade_id=trade_db_id, close_time=now_ts * 1000, close_price=close_price, pnl_raw=pnl_raw, pnl_pct=pnl_pct)
                    
                    msg = (
                        f"🔄 *Alpaca Portfolio Sync*\n\n"
                        f"Detected external closure of **{sym}** LONG position.\n"
                        f"• Est. Exit Price: `${close_price:.2f}`\n"
                        f"• Estimated Trade PnL: *{pnl_pct:+.2f}%* (${pnl_raw:+.2f})\n"
                        "Database updated to reflect closed status."
                    )
                    if chat_id:
                        await send_telegram_message(chat_id, msg)
                    logger.info(f"Marked {sym} as externally closed for {chat_id or web_user_id}.")
                    continue
                
                # Exists in active positions, run Phase 1 Dynamic Exits
                pos = active_positions[sym]
                
                db_conn = sqlite3.connect(STOCK_DB_PATH)
                db_c = db_conn.cursor()
                db_c.execute("SELECT high, low FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 1", (sym,))
                y_row = db_c.fetchone()
                db_conn.close()
                y_high = y_row[0] if y_row else 0.0
                y_low = y_row[1] if y_row else 999999.0

                is_custom = strategy_name not in ["Mean Reversion Scalper", "Valkyrie Elite Scalper", "Sherpa Velocity Pullback"]
                exit_reason = None
                
                if is_custom:
                    strategy_config = database.get_custom_strategy_config(user_id=web_user_id, name=strategy_name)
                    if strategy_config:
                        from custom_strategy_interpreter import CustomStrategyInterpreter
                        import pandas as pd
                        interpreter = CustomStrategyInterpreter(strategy_config)
                        
                        db_conn_2 = sqlite3.connect(STOCK_DB_PATH)
                        df = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", db_conn_2, params=(sym,))
                        db_conn_2.close()
                        if len(df) >= 60:
                            df['date'] = pd.to_datetime(df['date'])
                            df.set_index('date', inplace=True)
                            df.sort_index(inplace=True)
                            processed_df = interpreter.build_indicators(df)
                            signal = interpreter.check_signal(processed_df, len(processed_df)-1)
                            if signal == "CLOSE_LONG" or signal == "SHORT":
                                exit_reason = f"Dynamic Exit ({strategy_name})"
                else:
                    indicator_dict, _ = calculate_symbol_indicators_and_signal(sym)
                    if indicator_dict and indicator_dict['rsi'] > 75:
                        exit_reason = "Dynamic Exit (RSI > 75)"
                
                if not exit_reason:
                    if sl_price and y_low <= sl_price:
                        exit_reason = "STOP LOSS"
                    elif tp_price and y_high >= tp_price:
                        exit_reason = "TAKE PROFIT"
                
                if exit_reason:
                    logger.info(f"{exit_reason} triggered for real user {chat_id or f'web_{web_user_id}'} symbol {sym}. Liquidating...")
                    try:
                        await database.make_alpaca_request_async(user, "DELETE", f"/v2/positions/{sym}")
                        
                        entry_price = float(pos['avg_entry_price']) if pos.get('avg_entry_price') else entry_price_db
                        close_price = float(pos.get('current_price', today_opens.get(sym, entry_price)))
                        qty_val = float(pos['qty'])
                        
                        pnl_raw = float(pos.get('unrealized_pl', (close_price - entry_price) * qty_val))
                        pnl_pct = float(pos.get('unrealized_plpc', ((close_price - entry_price) / entry_price if entry_price > 0 else 0))) * 100
                        
                        now_ts = int(time.time())
                        database.close_alpaca_trade(
                            trade_id=trade_db_id,
                            close_time=now_ts * 1000,
                            close_price=close_price,
                            pnl_raw=pnl_raw,
                            pnl_pct=pnl_pct
                        )
                        logger.info(f"Closed trade in local DB for {sym} (ID: {trade_db_id}). PnL: {pnl_pct:+.2f}%")
                        
                        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
                        close_text_before = (
                            "🦙 *Alpaca Stock Strategy: Exit Triggered* 🦙\n\n"
                            f"Exited **{sym}** LONG position.\n"
                            f"• Trigger: `{exit_reason}`\n"
                            f"• Symbol: `{sym}`\n"
                            f"• Qty: `{pos['qty']}` shares\n"
                            f"• Entry Price: `${entry_price:.2f}`\n"
                            f"• Approximate Exit Price: `${close_price:.2f}`\n"
                            "🚀 _Associated Stop-Loss and Take-Profit orders have been automatically cancelled._\n\n"
                            "Closed at: "
                         )
                        placeholder = now_dt.strftime("%Y-%m-%d %H:%M UTC")
                        msg_close = close_text_before + placeholder
                        if chat_id:
                            await send_telegram_message(chat_id, msg_close)
                        
                    except Exception as e:
                        logger.error(f"Failed to liquidate real user {chat_id or f'web_{web_user_id}'} position {sym}: {e}")
                        if chat_id:
                            await send_telegram_message(chat_id, f"⚠️ *Alpaca Alert*: Failed to close position for {sym} ({exit_reason}): {e}")

        except Exception as u_err:
            logger.error(f"Error processing hourly sync for user {chat_id}: {u_err}")

async def run_real_trader_execution(today_opens):
    logger.info("Running Real Trader Execution Engine...")
    
    # Run Phase 1 Sync first to clear out closures
    await run_hourly_portfolio_sync(today_opens)
    
    import database
    active_users = database.get_all_active_stock_users()
        
    if not active_users:
        logger.info("No active Alpaca users to execute trades for.")
        return
        
    for user in active_users:
        chat_id = user.get('telegram_chat_id')
        web_user_id = user.get('web_user_id')
        strategy_name = user.get("active_stock_strategy", "None")
        if not user or strategy_name == "None":
            continue
            
        logger.info(f"Processing real trade execution for user chat_id={chat_id} web_user_id={web_user_id}...")
        
        try:
            # 1. Fetch current positions on Alpaca
            positions = await database.make_alpaca_request_async(user, "GET", "/v2/positions")
            active_positions = {p['symbol']: p for p in positions if float(p.get("qty", 0)) != 0}
            
            # Graceful strategy retirement check
            is_disabled = database.is_strategy_disabled(strategy_name)
            if is_disabled and len(active_positions) == 0:
                database.migrate_user_if_no_open_positions(chat_id, web_user_id=web_user_id)
                logger.info(f"User {chat_id or f'web_{web_user_id}'} stock strategy retired gracefully (0 active positions).")
                continue
            
            # --- PHASE 1: PROCESS EXITS & SYNC ---
            # Now handled by hourly portfolio sync. We call it here to ensure it runs during morning sweeps.
            # (Note: we don't need to re-fetch positions since it fetches them inside run_hourly_portfolio_sync, 
            # but we run it anyway for safety)
            
            # --- PHASE 2: PROCESS NEW BUY ENTRIES ---
            if is_disabled:
                logger.info(f"Stock strategy is disabled. Skipping new entries for user {chat_id or f'web_{web_user_id}'}.")
                continue
            
            is_custom = strategy_name not in ["Mean Reversion Scalper", "Valkyrie Elite Scalper", "Sherpa Velocity Pullback"]
            strategy_config = None
            interpreter = None
            if is_custom:
                strategy_config = database.get_custom_strategy_config(user_id=web_user_id, name=strategy_name)
                if not strategy_config:
                    logger.error(f"Strategy config not found for {strategy_name}")
                    continue
                from custom_strategy_interpreter import CustomStrategyInterpreter
                import pandas as pd
                interpreter = CustomStrategyInterpreter(strategy_config)
            
            import stock_data_cache_daily
            for sym in stock_data_cache_daily.SYMBOLS:
                if sym in active_positions:
                    continue
                    
                signal = None
                atr = 0.0
                if is_custom:
                    db_conn = sqlite3.connect(STOCK_DB_PATH)
                    df = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", db_conn, params=(sym,))
                    db_conn.close()
                    if df.empty or len(df) < 60:
                        continue
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    df.sort_index(inplace=True)
                    processed_df = interpreter.build_indicators(df)
                    signal = interpreter.check_signal(processed_df, len(processed_df)-1)
                    if signal == "LONG":
                        atr = float(processed_df.get('atr', processed_df['close']).iloc[-1])
                        o_price = today_opens.get(sym)
                        if not o_price: continue
                        D = strategy_config.get("risk", {}).get("sl_atr_mult", 3.0) * atr
                        tp_price = o_price + (strategy_config.get("risk", {}).get("rr_ratio", 1.5) * D)
                        sl_price = o_price - D
                else:
                    indicator_dict, signal = calculate_symbol_indicators_and_signal(sym)
                    if signal == "LONG":
                        o_price = today_opens.get(sym)
                        if not o_price: continue
                        atr = indicator_dict['atr']
                        tp_price = o_price + 4.8 * atr
                        sl_price = o_price - 3.0 * atr

                if signal == "LONG":
                    
                    try:
                        account = await database.make_alpaca_request_async(user, "GET", "/v2/account")
                        equity = float(account.get("equity", 0) or account.get("portfolio_value", 0))
                        
                        user_risk = float(user.get('stock_risk_pct', 2.0)) / 100.0
                        risk_amt = equity * user_risk
                        
                        qty = risk_amt / (3.0 * atr)
                        qty = round(qty, 4)
                        
                        if qty <= 0:
                            logger.warning(f"Sizing quantity is 0 for {sym} (User: {chat_id or f'web_{web_user_id}'}). Risk amount ${risk_amt:.2f} is too small.")
                            continue
                            
                        order_payload = {
                            "symbol": sym,
                            "qty": str(qty),
                            "side": "buy",
                            "type": "market",
                            "time_in_force": "day"
                        }
                        
                        logger.info(f"Submitting fractional market order for user {chat_id or f'web_{web_user_id}'} symbol {sym}: {order_payload}")
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
                            open_time=open_ts,
                            web_user_id=web_user_id
                        )
                        
                        from telegram import MessageEntity
                        from datetime import datetime, timezone
                        now_ts = int(time.time())
                        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
                        buy_text_before = (
                            "🦙 *Alpaca Stock Strategy: Buy Signal Triggered* 🦙\n\n"
                            f"Entered **{sym}** LONG at today's open.\n"
                            f"• Symbol: `{sym}`\n"
                            f"• Qty: `{qty}` shares\n"
                            f"• Entry Price: `${o_price:.2f}`\n"
                            f"• Take Profit: `${tp_price:.2f}`\n"
                            f"• Stop Loss: `${sl_price:.2f}`\n"
                            f"• Risk Allocated: `${risk_amt:.2f}` ({user.get('stock_risk_pct', 2.0)}% of equity)\n\n"
                            "Signal time: "
                        )
                        placeholder = now_dt.strftime("%Y-%m-%d %H:%M UTC")
                        buy_msg = buy_text_before + placeholder
                        if chat_id:
                            await send_telegram_message(chat_id, buy_msg)
                        else:
                            logger.info(f"Buy trade logged for web user {web_user_id}. Symbol: {sym}")
                        
                    except Exception as e:
                        logger.error(f"Failed to execute real trade for user {chat_id or f'web_{web_user_id}'} symbol {sym}: {e}")
                        if chat_id:
                            await send_telegram_message(chat_id, f"⚠️ *Alpaca Alert*: Buy signal for {sym} failed to execute: {e}")
                        
        except Exception as e:
            logger.error(f"Error executing trades for user {chat_id or f'web_{web_user_id}'}: {e}")

async def main():
    logger.info("Starting Daily stock swing execution...")
    
    # 1. Market clock check
    if not check_is_market_open():
        logger.info("US Equities Market is closed today. Skipping swing execution.")
        return
        
    # 2. Update stock daily cache from Alpaca
    try:
        update_stock_daily_cache()
    except Exception as e:
        logger.error(f"Error updating stock cache: {e}")
        try:
            from utils_error import send_telegram_alert
            send_telegram_alert("Stock Trading Engine (Cache Update)", e)
        except: pass
        
    # 3. Fetch today's real-time open prices (or fallbacks)
    today_opens = fetch_today_open_prices()
    
    # 4. Run theoretical tally engine
    try:
        await run_theoretical_tally_engine(today_opens)
    except Exception as e:
        logger.error(f"Error running theoretical engine: {e}")
        try:
            from utils_error import send_telegram_alert
            send_telegram_alert("Stock Trading Engine (Theoretical Tally)", e)
        except: pass
        
    # 5. Run real user execution
    try:
        await run_real_trader_execution(today_opens)
    except Exception as e:
        logger.error(f"Error running real trader execution: {e}")
        try:
            from utils_error import send_telegram_alert
            send_telegram_alert("Stock Trading Engine (Real Execution)", e)
        except: pass
        
    logger.info("Daily stock swing execution completed successfully!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error("Fatal exception in stock trading engine: %s", e, exc_info=True)
        try:
            from utils_error import send_telegram_alert
            send_telegram_alert("Stock Trading Engine (live_bot_multi_alpaca.py)", e)
        except Exception as alert_err:
            logger.error("Failed to send Telegram alert for stock engine crash: %s", alert_err)

