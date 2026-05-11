import sqlite3
import os
import time
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    with open(".env", "a") as f:
        f.write(f"\nENCRYPTION_KEY={ENCRYPTION_KEY}\n")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt(data):
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt(data):
    return cipher_suite.decrypt(data.encode()).decode()

DB_PATH = '/Users/johngiles/projects/tradingbot/bot_users.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Users
                 (telegram_chat_id INTEGER PRIMARY KEY,
                  blofin_api_key TEXT,
                  blofin_api_secret TEXT,
                  blofin_api_password TEXT,
                  starting_equity REAL,
                  is_active BOOLEAN,
                  total_wins INTEGER DEFAULT 0,
                  total_losses INTEGER DEFAULT 0,
                  total_trades_opened INTEGER DEFAULT 0,
                  cumulative_pnl REAL DEFAULT 0.0,
                  last_fetch_timestamp INTEGER DEFAULT 0,
                  strategy TEXT DEFAULT 'Mean Reversion Scalper')''')
    
    # Ensure columns exist for older databases
    try: c.execute("ALTER TABLE Users ADD COLUMN cumulative_pnl REAL DEFAULT 0.0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN last_fetch_timestamp INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN strategy TEXT DEFAULT 'Mean Reversion Scalper'")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN hide_dollars BOOLEAN DEFAULT 0")
    except: pass
    
    conn.commit()
    conn.close()

def upsert_user(chat_id, api_key, api_secret, api_pass, equity):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO Users (telegram_chat_id, blofin_api_key, blofin_api_secret, blofin_api_password, starting_equity, is_active)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT(telegram_chat_id) DO UPDATE SET
                 blofin_api_key=excluded.blofin_api_key,
                 blofin_api_secret=excluded.blofin_api_secret,
                 blofin_api_password=excluded.blofin_api_password,
                 starting_equity=excluded.starting_equity,
                 is_active=excluded.is_active''',
              (chat_id, encrypt(api_key), encrypt(api_secret), encrypt(api_pass), equity, True))
    conn.commit()
    conn.close()

def get_user(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT blofin_api_key, blofin_api_secret, blofin_api_password, starting_equity, is_active, total_wins, total_losses, total_trades_opened, cumulative_pnl, last_fetch_timestamp, strategy FROM Users WHERE telegram_chat_id = ?', (chat_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "api_key": decrypt(row[0]),
            "api_secret": decrypt(row[1]),
            "api_password": decrypt(row[2]),
            "equity": row[3],
            "is_active": row[4],
            "wins": row[5],
            "losses": row[6],
            "opened": row[7],
            "cum_pnl": row[8] or 0.0,
            "last_ts": row[9] or 0,
            "strategy": row[10] or 'Mean Reversion Scalper',
            "hide_dollars": bool(row[11]) if len(row) > 11 else False,
            "chat_id": chat_id
        }
    return None

def get_all_active_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT telegram_chat_id FROM Users WHERE is_active = 1')
    chat_ids = [row[0] for row in c.fetchall()]
    conn.close()
    return [get_user(cid) for cid in chat_ids]

def set_active(chat_id, is_active):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Users SET is_active = ? WHERE telegram_chat_id = ?", (1 if is_active else 0, chat_id))
    conn.commit()
    conn.close()

def update_user_preference(chat_id, key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Map key to column name
    cols = {"strategy": "strategy", "hide_dollars": "hide_dollars"}
    if key in cols:
        c.execute(f"UPDATE Users SET {cols[key]} = ? WHERE telegram_chat_id = ?", (value, chat_id))
    conn.commit()
    conn.close()

def increment_opened(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE Users SET total_trades_opened = total_trades_opened + 1 WHERE telegram_chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def update_user_stats_from_engine(chat_id, equity, exchange, application):
    """
    Syncs trades from exchange and updates DB stats.
    Sends Telegram notifications for closed trades.
    """
    user = get_user(chat_id)
    if not user: return
    
    last_ts = user['last_ts']
    if last_ts == 0:
        last_ts = int((time.time() - 172800) * 1000) # 48h
        
    wins = user['wins']
    losses = user['losses']
    cum_pnl = user['cum_pnl']
    now_ts = int(time.time() * 1000)
    
    import live_bot_multi
    new_closed = []
    
    for sym in live_bot_multi.SYMBOLS:
        try:
            trades = exchange.fetch_my_trades(sym, last_ts)
            for t in trades:
                if t['timestamp'] <= last_ts: continue
                
                info = t.get("info", {})
                gross_pnl = float(info.get("fillPnl") or 0)
                
                if gross_pnl != 0:
                    fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                    net_pnl = gross_pnl - (fee * 2)
                    
                    try:
                        market = exchange.market(sym)
                        contract_size = float(market.get('contractSize', 1))
                        initial_margin = (float(t['price']) * float(t['amount']) * contract_size) / 20
                        roe_pct = (net_pnl / initial_margin) * 100 if initial_margin > 0 else 0
                    except: roe_pct = 0
                    
                    cum_pnl += net_pnl
                    if net_pnl > 0:
                        wins += 1
                        header = "🚀 *Trade Won!*"
                    else:
                        losses += 1
                        header = "❌ *Trade Lost*"
                        
                    new_closed.append({
                        "msg": f"{header}\n\nSymbol: `{sym}`\nPnL: *${net_pnl:.2f}*\nROE: *{roe_pct:+.2f}%*"
                    })
        except: pass
        
    # Update DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE Users SET total_wins = ?, total_losses = ?, cumulative_pnl = ?, last_fetch_timestamp = ?, starting_equity = ?
                 WHERE telegram_chat_id = ?''', (wins, losses, cum_pnl, now_ts, equity, chat_id))
    conn.commit()
    conn.close()
    
    # Notify User
    import asyncio
    for nc in new_closed:
        asyncio.create_task(application.bot.send_message(chat_id=chat_id, text=nc['msg'], parse_mode="Markdown"))
