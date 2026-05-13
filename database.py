import sqlite3
import os
import time
import ccxt
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    with open(".env", "a") as f:
        f.write(f"\nENCRYPTION_KEY={ENCRYPTION_KEY}\n")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def get_exchange_client(user):
    """
    Factory function to create a CCXT exchange client for a specific user.
    """
    ex_id = user.get('exchange_id', 'blofin')
    config = {
        "apiKey": user["api_key"],
        "secret": user["api_secret"],
        "password": user["api_password"],
        "options": {"defaultType": "swap"},
        "enableRateLimit": True,
    }
    client = getattr(ccxt, ex_id)(config)
    return client

def normalize_symbol(symbol, exchange_id):
    """
    Handles exchange-specific symbol dialects.
    """
    if exchange_id == 'mexc':
        return symbol.split(":")[0]
    return symbol

def encrypt(data):
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt(data):
    return cipher_suite.decrypt(data.encode()).decode()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'bot_users.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Users
                 (telegram_chat_id INTEGER PRIMARY KEY,
                  blofin_api_key TEXT,
                  blofin_api_secret TEXT,
                  blofin_api_password TEXT,
                  exchange_id TEXT DEFAULT 'blofin',
                  starting_equity REAL,
                  is_active BOOLEAN,
                  total_wins INTEGER DEFAULT 0,
                  total_losses INTEGER DEFAULT 0,
                  total_trades_opened INTEGER DEFAULT 0,
                  cumulative_pnl REAL DEFAULT 0.0,
                  last_fetch_timestamp INTEGER DEFAULT 0,
                  strategy TEXT DEFAULT 'Mean Reversion Scalper',
                  source_wallet TEXT)''')
    
    # Ensure columns exist for older databases
    try: c.execute("ALTER TABLE Users ADD COLUMN exchange_id TEXT DEFAULT 'blofin'")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN cumulative_pnl REAL DEFAULT 0.0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN last_fetch_timestamp INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN strategy TEXT DEFAULT 'Mean Reversion Scalper'")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN hide_dollars BOOLEAN DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN risk_pct REAL DEFAULT 1.5")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN enabled_symbols TEXT")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN referred_by INTEGER")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN premium_expiry INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN referral_count INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN has_open_positions BOOLEAN DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN history_cache TEXT")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN source_wallet TEXT")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN undercover_mode BOOLEAN DEFAULT 0")
    except: pass
    
    # 💎 Institutional Config Table
    c.execute('''CREATE TABLE IF NOT EXISTS Config
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Set default master wallet if not exists
    c.execute("INSERT OR IGNORE INTO Config (key, value) VALUES ('master_usdt_wallet', 'YOUR_MASTER_TRON_ADDRESS_HERE')")
    
    conn.commit()
    conn.close()

def upsert_user(chat_id, api_key, api_secret, api_pass, exchange_id='blofin', equity=0.0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Default symbols
    def_syms = "BTC,ETH,SOL,DOGE,ADA,LINK,DOT,TON,ZEC,PEPE,BNB,NEAR,SUI,NOT,TAO,ONDO,ENA,FET,WIF"
    c.execute('''INSERT INTO Users (telegram_chat_id, blofin_api_key, blofin_api_secret, blofin_api_password, exchange_id, starting_equity, is_active, enabled_symbols)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                 ON CONFLICT(telegram_chat_id) DO UPDATE SET
                 blofin_api_key=excluded.blofin_api_key,
                 blofin_api_secret=excluded.blofin_api_secret,
                 blofin_api_password=excluded.blofin_api_password,
                 exchange_id=excluded.exchange_id,
                 starting_equity=excluded.starting_equity,
                 is_active=excluded.is_active''',
               (chat_id, encrypt(api_key), encrypt(api_secret), encrypt(api_pass), exchange_id, equity, True, def_syms))
    conn.commit()
    conn.close()

def get_user(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT blofin_api_key, blofin_api_secret, blofin_api_password, starting_equity, is_active, total_wins, total_losses, total_trades_opened, cumulative_pnl, last_fetch_timestamp, strategy, hide_dollars, risk_pct, enabled_symbols, exchange_id, referred_by, premium_expiry, referral_count, has_open_positions, history_cache FROM Users WHERE telegram_chat_id = ?', (chat_id,))
    row = c.fetchone()
    conn.close()
    if row:
        def_syms = "BTC,ETH,SOL,DOGE,ADA,LINK,DOT,TON,ZEC,PEPE,BNB,NEAR,SUI,NOT,TAO,ONDO,ENA,FET,WIF"
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
            "hide_dollars": bool(row[11]),
            "risk_pct": row[12] if row[12] is not None else 1.5,
            "enabled_symbols": (row[13] if row[13] else def_syms).split(","),
            "exchange_id": row[14] or 'blofin',
            "referred_by": row[15],
            "premium_expiry": row[16] or 0,
            "referral_count": row[17] or 0,
            "has_open_positions": bool(row[18]),
            "chat_id": chat_id,
            "history_cache": row[19] if len(row) > 19 else None
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
    cols = {"strategy": "strategy", "hide_dollars": "hide_dollars", "risk_pct": "risk_pct", "enabled_symbols": "enabled_symbols", "exchange_id": "exchange_id"}
    if key in cols:
        if key == "enabled_symbols" and isinstance(value, list):
            value = ",".join(value)
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
    
    # 🕵️ Smart UI: Sync Position Status
    try:
        positions = exchange.fetch_positions()
        has_active = any(float(p.get("contracts", 0) or 0) != 0 for p in positions)
        # We'll update this in the DB at the end of the function with the other stats
    except:
        has_active = False

    new_closed = []
    
    for sym in live_bot_multi.SYMBOLS:
        try:
            norm_sym = normalize_symbol(sym, exchange.id)
            trades = exchange.fetch_my_trades(norm_sym, last_ts)
            for t in trades:
                if t['timestamp'] <= last_ts: continue
                
                info = t.get("info", {})
                # PnL Reconstruction
                gross_pnl = 0
                if exchange.id == 'blofin':
                    gross_pnl = float(info.get("fillPnl") or 0)
                else:
                    # Binance/MEXC/Bybit
                    gross_pnl = float(info.get("realizedPnl") or 0)
                
                if gross_pnl != 0:
                    fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                    net_pnl = gross_pnl - (fee * 2)
                    
                    try:
                        market = exchange.market(norm_sym)
                        contract_size = float(market.get('contractSize', 1))
                        initial_margin = (float(t['price']) * float(t['amount']) * contract_size) / 20
                        roe_pct = (net_pnl / initial_margin) * 100 if initial_margin > 0 else 0
                    except: roe_pct = 0
                    
                    cum_pnl += net_pnl
                    share_data = None
                    if net_pnl > 0:
                        wins += 1
                        header = "🏆 *Trade Won!*"
                        # sh_{sym}_{side}_{roe}_{entry}_{mark}_{pnl}
                        side_code = "l" # assume long for notification if side is missing from raw info
                        share_data = f"sh_{sym}_{side_code}_{roe_pct:.2f}_{t.get('price', 0)}_{t.get('price', 0)}_{net_pnl:.2f}"
                    else:
                        losses += 1
                        header = "❌ *Trade Lost*"
                        
                    new_closed.append({
                        "msg": f"{header}\n\nSymbol: `{sym}`\nPnL: *${net_pnl:.2f}*\nROE: *{roe_pct:+.2f}%*",
                        "share_data": share_data
                    })
        except: pass
        
    if new_closed:
        clear_history_cache(chat_id)
        
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    # Update DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE Users SET total_wins = ?, total_losses = ?, cumulative_pnl = ?, last_fetch_timestamp = ?, starting_equity = ?, has_open_positions = ?
                 WHERE telegram_chat_id = ?''', (wins, losses, cum_pnl, now_ts, equity, 1 if has_active else 0, chat_id))
    conn.commit()
    conn.close()
    
    # Notify User
    import asyncio
    for nc in new_closed:
        markup = None
        if nc.get("share_data"):
            btn = InlineKeyboardButton("📸 Share Result", callback_data=nc["share_data"])
            markup = InlineKeyboardMarkup([[btn]])
        
        asyncio.create_task(application.bot.send_message(
            chat_id=chat_id, 
            text=nc['msg'], 
            reply_markup=markup,
            parse_mode="Markdown"
        ))

def set_referrer(chat_id, referrer_id):
    """Links a new user to a referrer and increments the referrer's count."""
    if chat_id == referrer_id: return False # No self-referral
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check if user already has a referrer
    c.execute("SELECT referred_by FROM Users WHERE telegram_chat_id = ?", (chat_id,))
    row = c.fetchone()
    
    reward_granted = False
    # If user exists and doesn't have a referrer yet
    if row and row[0] is None:
        c.execute("UPDATE Users SET referred_by = ? WHERE telegram_chat_id = ?", (referrer_id, chat_id))
        c.execute("UPDATE Users SET referral_count = referral_count + 1 WHERE telegram_chat_id = ?", (referrer_id,))
        conn.commit()
        # Check for reward
        reward_granted = check_and_award_referral_bonus(referrer_id)
    
    conn.close()
    return reward_granted

def add_premium_days(chat_id, days):
    """Extends a user's premium status by X days."""
    user = get_user(chat_id)
    if not user: return
    
    now = int(time.time())
    current_expiry = max(user['premium_expiry'], now)
    new_expiry = current_expiry + (days * 86400)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Users SET premium_expiry = ? WHERE telegram_chat_id = ?", (new_expiry, chat_id))
    conn.commit()
    conn.close()

def get_referral_stats(chat_id):
    """Returns the total number of referrals for a user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT referral_count FROM Users WHERE telegram_chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def update_user_wallet(chat_id, wallet_address):
    """Updates the user's source wallet address for payment verification."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Users SET source_wallet = ? WHERE telegram_chat_id = ?", (wallet_address, chat_id))
    conn.commit()
    conn.close()

def check_and_award_referral_bonus(referrer_id):
    """Awards 30 days of premium for every 3 referrals."""
    count = get_referral_stats(referrer_id)
    if count > 0 and count % 3 == 0:
        add_premium_days(referrer_id, 30)
        return True # Reward granted
    return False

def update_position_status(chat_id, has_active):
    """Updates the has_open_positions flag in the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Users SET has_open_positions = ? WHERE telegram_chat_id = ?", (1 if has_active else 0, chat_id))
    conn.commit()
    conn.close()

def update_user_strategy(chat_id, strategy_name):
    """Updates the user's active trading strategy."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Users SET strategy = ? WHERE telegram_chat_id = ?", (strategy_name, chat_id))
    conn.commit()
    conn.close()

def set_history_cache(chat_id, trades):
    """Stores the last 10 trades as a JSON blob."""
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Users SET history_cache = ? WHERE telegram_chat_id = ?", (json.dumps(trades), chat_id))
    conn.commit()
    conn.close()

def clear_history_cache(chat_id):
    """Clears the trade history cache."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Users SET history_cache = NULL WHERE telegram_chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def is_premium(user):
    """Returns True if the user has an active premium subscription or is the Admin."""
    if not user: return False
    # 👑 Overlord Privilege (Suspended in Undercover Mode)
    if user.get('telegram_chat_id') == 1567788633 and not user.get('undercover_mode'):
        return True
    return user.get('premium_expiry', 0) > time.time()

def toggle_undercover(chat_id):
    """Toggles the undercover mode for the founder."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Robust toggle logic: if 1 then 0, else 1 (handles NULLs)
    c.execute("""
        UPDATE Users 
        SET undercover_mode = CASE WHEN undercover_mode = 1 THEN 0 ELSE 1 END 
        WHERE chat_id = ?
    """, (chat_id,))
    conn.commit()
    conn.close()

def get_premium_days_left(user):
    """Returns the number of days remaining in the user's premium subscription."""
    if not user: return 0
    expiry = user.get('premium_expiry', 0)
    now = time.time()
    if expiry <= now: return 0
    return int((expiry - now) / 86400)

# --- Administrative Controls ---

def get_config(key, default=None):
    """Retrieves a global configuration value."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM Config WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def update_config(key, value):
    """Updates a global configuration value."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO Config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_platform_stats():
    """Returns high-level platform analytics for the admin."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM Users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT SUM(referral_count) FROM Users")
    total_referrals = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM Users WHERE premium_expiry > ?", (time.time(),))
    premium_users = c.fetchone()[0]
    
    conn.close()
    return {
        "total_users": total_users,
        "total_referrals": total_referrals,
        "premium_users": premium_users
    }
