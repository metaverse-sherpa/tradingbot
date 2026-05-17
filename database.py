import sqlite3
import os
import time
import asyncio
import ccxt.async_support as ccxt
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    with open(".env", "a") as f:
        f.write(f"\nENCRYPTION_KEY={ENCRYPTION_KEY}\n")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

from contextlib import contextmanager

@contextmanager
def db_session():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

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
    with db_session() as conn:
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
        cols = [
            ("exchange_id", "TEXT DEFAULT 'blofin'"),
            ("cumulative_pnl", "REAL DEFAULT 0.0"),
            ("last_fetch_timestamp", "INTEGER DEFAULT 0"),
            ("strategy", "TEXT DEFAULT 'Mean Reversion Scalper'"),
            ("hide_dollars", "BOOLEAN DEFAULT 0"),
            ("risk_pct", "REAL DEFAULT 1.5"),
            ("enabled_symbols", "TEXT"),
            ("referred_by", "INTEGER"),
            ("premium_expiry", "INTEGER DEFAULT 0"),
            ("referral_count", "INTEGER DEFAULT 0"),
            ("has_open_positions", "BOOLEAN DEFAULT 0"),
            ("history_cache", "TEXT"),
            ("source_wallet", "TEXT"),
            ("undercover_mode", "BOOLEAN DEFAULT 0"),
            ("last_audit_stats", "TEXT"),
            ("referral_credits", "REAL DEFAULT 0.0"),
            ("full_name", "TEXT"),
            ("username", "TEXT"),
            ("is_admin", "BOOLEAN DEFAULT 0"),
            ("custom_equity_type", "TEXT DEFAULT 'all'"),
            ("custom_equity_value", "REAL")
        ]
        for col_name, col_def in cols:
            try: c.execute(f"ALTER TABLE Users ADD COLUMN {col_name} {col_def}")
            except: pass
        
        # 💎 Institutional Config Table
        c.execute('''CREATE TABLE IF NOT EXISTS Config
                     (key TEXT PRIMARY KEY, value TEXT)''')
        
        # 🎁 Gift Codes Table
        c.execute('''CREATE TABLE IF NOT EXISTS GiftCodes
                     (code TEXT PRIMARY KEY, 
                      target_chat_id INTEGER, 
                      target_username TEXT,
                      expiry_days INTEGER DEFAULT 30, 
                      is_used BOOLEAN DEFAULT 0,
                      created_at INTEGER)''')
        
        # 🩹 Migration: Ensure target_username column exists
        try: c.execute("ALTER TABLE GiftCodes ADD COLUMN target_username TEXT")
        except: pass
        
        # Set default master wallet if not exists
        c.execute("INSERT OR IGNORE INTO Config (key, value) VALUES ('master_usdt_wallet', 'YOUR_MASTER_TRON_ADDRESS_HERE')")

def upsert_user(chat_id, api_key, api_secret, api_pass, exchange_id, is_active=False, full_name=None, username=None):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT 1 FROM Users WHERE telegram_chat_id = ?', (chat_id,))
        if c.fetchone():
            c.execute('''
                UPDATE Users 
                SET blofin_api_key = ?, blofin_api_secret = ?, blofin_api_password = ?, exchange_id = ?, is_active = ?, full_name = ?, username = ?
                WHERE telegram_chat_id = ?
            ''', (encrypt(api_key), encrypt(api_secret), encrypt(api_pass), exchange_id, is_active, full_name, username, chat_id))
        else:
            c.execute('''
                INSERT INTO Users (telegram_chat_id, blofin_api_key, blofin_api_secret, blofin_api_password, exchange_id, is_active, full_name, username)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chat_id, encrypt(api_key), encrypt(api_secret), encrypt(api_pass), exchange_id, is_active, full_name, username))

def get_user(chat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT blofin_api_key, blofin_api_secret, blofin_api_password, starting_equity, is_active, total_wins, total_losses, total_trades_opened, cumulative_pnl, last_fetch_timestamp, strategy, hide_dollars, risk_pct, enabled_symbols, exchange_id, referred_by, premium_expiry, referral_count, has_open_positions, undercover_mode, source_wallet, last_audit_stats, referral_credits, full_name, username, is_admin, custom_equity_type, custom_equity_value FROM Users WHERE telegram_chat_id = ?', (chat_id,))
        row = c.fetchone()
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
            "telegram_chat_id": chat_id,
            "undercover_mode": row[19] if len(row) > 19 else 0,
            "source_wallet": row[20] if len(row) > 20 else None,
            "last_audit_stats": row[21] if len(row) > 21 else None,
            "referral_credits": row[22] if len(row) > 22 else 0.0,
            "full_name": row[23] if len(row) > 23 else None,
            "username": row[24] if len(row) > 24 else None,
            "is_admin": bool(row[25]) if len(row) > 25 else False,
            "custom_equity_type": row[26] if len(row) > 26 and row[26] is not None else 'all',
            "custom_equity_value": row[27] if len(row) > 27 else None
        }
    return None

def update_last_audit(chat_id, stats_dict):
    import json
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET last_audit_stats = ? WHERE telegram_chat_id = ?", (json.dumps(stats_dict), chat_id))

def add_referral_credit(chat_id, amount=5.0):
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET referral_credits = referral_credits + ? WHERE telegram_chat_id = ?", (amount, chat_id))

def consume_referral_credits(chat_id, amount):
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET referral_credits = MAX(0, referral_credits - ?) WHERE telegram_chat_id = ?", (amount, chat_id))

def get_all_active_users():
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT telegram_chat_id FROM Users WHERE is_active = 1 AND blofin_api_key IS NOT NULL AND blofin_api_key != ""')
        chat_ids = [row[0] for row in c.fetchall()]
    return [get_user(cid) for cid in chat_ids]

def set_active(chat_id, is_active):
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET is_active = ? WHERE telegram_chat_id = ?", (1 if is_active else 0, chat_id))

def update_user_preference(chat_id, key, value):
    with db_session() as conn:
        c = conn.cursor()
        # Map key to column name (Whitelist)
        cols = {
            "strategy": "strategy", 
            "hide_dollars": "hide_dollars", 
            "risk_pct": "risk_pct", 
            "enabled_symbols": "enabled_symbols", 
            "exchange_id": "exchange_id",
            "custom_equity_type": "custom_equity_type",
            "custom_equity_value": "custom_equity_value"
        }
        if key in cols:
            col_name = cols[key]
            if key == "enabled_symbols" and isinstance(value, list):
                value = ",".join(value)
            # Use parameter substitution for the value, but we still have to format the column name
            # since SQL parameters don't work for column/table names. Whitelist ensures safety.
            c.execute(f"UPDATE Users SET {col_name} = ? WHERE telegram_chat_id = ?", (value, chat_id))

def increment_opened(chat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE Users SET total_trades_opened = total_trades_opened + 1 WHERE telegram_chat_id = ?', (chat_id,))

async def update_user_stats_from_engine(chat_id, equity, exchange, application):
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
    
    try:
        # 🕵️ Smart UI: Sync Position Status
        try:
            positions = await exchange.fetch_positions()
            has_active = any(float(p.get("contracts", 0) or 0) != 0 for p in positions)
            # We'll update this in the DB at the end of the function with the other stats
        except:
            has_active = False

        new_closed = []
        
        # We'll process all symbols in parallel for this user
        async def process_symbol_trades(sym):
            nonlocal wins, losses, cum_pnl
            try:
                norm_sym = normalize_symbol(sym, exchange.id)
                trades = await exchange.fetch_my_trades(norm_sym, since=last_ts, params={'instType': 'SWAP'})
                symbol_new_closed = []
                for t in trades:
                    if t['timestamp'] <= last_ts: continue
                    
                    try:
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
                            except:
                                roe_pct = 0
                            
                            cum_pnl += net_pnl
                            share_data = None
                            if net_pnl > 0:
                                wins += 1
                                header = "🏆 *Trade Won!*"
                                # assume long for notification if side is missing from raw info
                                side_code = "l"
                                share_data = f"sh_{sym}_{side_code}_{roe_pct:.2f}_{t.get('price', 0)}_{t.get('price', 0)}_{net_pnl:.2f}"
                            else:
                                losses += 1
                                header = "❌ *Trade Lost*"
                                
                            symbol_new_closed.append({
                                "msg": f"{header}\n\nSymbol: `{sym}`\nPnL: *${net_pnl:.2f}*\nROE: *{roe_pct:+.2f}%*",
                                "share_data": share_data
                            })
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).error(f"Error processing trade {t.get('id', 'unknown')}: {e}")
                return symbol_new_closed
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error fetching trades for {sym}: {e}")
                return []

        results = await asyncio.gather(*(process_symbol_trades(sym) for sym in live_bot_multi.SYMBOLS))
        for r in results:
            new_closed.extend(r)
            
        if new_closed:
            clear_history_cache(chat_id)
            
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        # Update DB
        with db_session() as conn:
            c = conn.cursor()
            c.execute('''UPDATE Users SET total_wins = ?, total_losses = ?, cumulative_pnl = ?, last_fetch_timestamp = ?, starting_equity = ?, has_open_positions = ?
                         WHERE telegram_chat_id = ?''', (wins, losses, cum_pnl, now_ts, equity, 1 if has_active else 0, chat_id))
        
        # Notify User
        for nc in new_closed:
            markup = None
            if nc.get("share_data"):
                btn = InlineKeyboardButton("📸 Share Result", callback_data=nc["share_data"])
                markup = InlineKeyboardMarkup([[btn]])
            
            await application.bot.send_message(
                chat_id=chat_id, 
                text=nc['msg'], 
                reply_markup=markup,
                parse_mode="Markdown"
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Critical error in sync_trades_from_exchange for {chat_id}: {e}")

def set_referrer(chat_id, referrer_id):
    """Links a new user to a referrer and increments the referrer's count."""
    if chat_id == referrer_id: return False # No self-referral
    
    reward_granted = False
    with db_session() as conn:
        c = conn.cursor()
        # Check if user already has a referrer
        c.execute("SELECT referred_by FROM Users WHERE telegram_chat_id = ?", (chat_id,))
        row = c.fetchone()
        
        # If user exists and doesn't have a referrer yet
        if row and row[0] is None:
            c.execute("UPDATE Users SET referred_by = ? WHERE telegram_chat_id = ?", (referrer_id, chat_id))
            c.execute("UPDATE Users SET referral_count = referral_count + 1 WHERE telegram_chat_id = ?", (referrer_id,))
            # Check for reward
            reward_granted = check_and_award_referral_bonus(referrer_id)
    
    return reward_granted

def add_premium_days(chat_id, days):
    """Extends a user's premium status by X days."""
    user = get_user(chat_id)
    if not user: return
    
    now = int(time.time())
    current_expiry = max(user['premium_expiry'], now)
    new_expiry = current_expiry + (days * 86400)
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET premium_expiry = ? WHERE telegram_chat_id = ?", (new_expiry, chat_id))

def get_referral_stats(chat_id):
    """Returns the total number of referrals for a user."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT referral_count FROM Users WHERE telegram_chat_id = ?", (chat_id,))
        row = c.fetchone()
    return row[0] if row else 0

def update_user_wallet(chat_id, wallet_address):
    """Updates the user's source wallet address for payment verification."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET source_wallet = ? WHERE telegram_chat_id = ?", (wallet_address, chat_id))

def check_and_award_referral_bonus(referrer_id):
    """Awards 30 days of premium for every 3 referrals."""
    count = get_referral_stats(referrer_id)
    if count > 0 and count % 3 == 0:
        add_premium_days(referrer_id, 30)
        return True # Reward granted
    return False

def update_position_status(chat_id, has_active):
    """Updates the has_open_positions flag in the database."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET has_open_positions = ? WHERE telegram_chat_id = ?", (1 if has_active else 0, chat_id))

def update_user_strategy(chat_id, strategy_name):
    """Updates the user's active trading strategy."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET strategy = ? WHERE telegram_chat_id = ?", (strategy_name, chat_id))

def set_history_cache(chat_id, trades):
    """Stores the last 10 trades as a JSON blob."""
    import json
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET history_cache = ? WHERE telegram_chat_id = ?", (json.dumps(trades), chat_id))

def clear_history_cache(chat_id):
    """Clears the trade history cache."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET history_cache = NULL WHERE telegram_chat_id = ?", (chat_id,))

def is_premium(user):
    """Returns True if the user has an active premium subscription or is the Admin."""
    if not user: return False
    # 👑 Overlord Privilege (Suspended in Undercover Mode)
    if user.get('telegram_chat_id') == 1567788633 and not user.get('undercover_mode'):
        return True
    return user.get('premium_expiry', 0) > time.time()

def set_admin_status(chat_id, status: bool):
    """Promotes or demotes a user to Admin status."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET is_admin = ? WHERE telegram_chat_id = ?", (1 if status else 0, chat_id))

def is_admin(chat_id):
    """Returns True if the user is an Admin in the database."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM Users WHERE telegram_chat_id = ?", (chat_id,))
        row = c.fetchone()
        return bool(row[0]) if row else False

def get_all_admins():
    """Returns a list of all telegram_chat_ids for users with is_admin=1."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM Users WHERE is_admin = 1")
        return [row[0] for row in c.fetchall()]

def toggle_undercover(chat_id):
    """Toggles the undercover mode for the founder."""
    with db_session() as conn:
        c = conn.cursor()
        # Robust toggle logic: if 1 then 0, else 1 (handles NULLs)
        c.execute("""
            UPDATE Users 
            SET undercover_mode = CASE WHEN undercover_mode = 1 THEN 0 ELSE 1 END 
            WHERE telegram_chat_id = ?
        """, (chat_id,))

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
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM Config WHERE key = ?", (key,))
        row = c.fetchone()
    return row[0] if row else default

def update_config(key, value):
    """Updates a global configuration value."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO Config (key, value) VALUES (?, ?)", (key, value))

def get_platform_stats():
    """Returns high-level platform analytics for the admin."""
    with db_session() as conn:
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM Users")
        total_users = c.fetchone()[0]
        
        c.execute("SELECT SUM(referral_count) FROM Users")
        total_referrals = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM Users WHERE premium_expiry > ?", (time.time(),))
        premium_users = c.fetchone()[0]
    
    return {
        "total_users": total_users,
        "total_referrals": total_referrals,
        "premium_users": premium_users
    }
def get_detailed_user_report():
    """Returns a list of all users with their institutional status and referral info."""
    with db_session() as conn:
        # We need to manually set row_factory because db_session already sets it,
        # but let's be explicit if we wanted something else.
        # Actually sqlite3.Row is already set in db_session.
        c = conn.cursor()
        c.execute('''
            SELECT 
                telegram_chat_id,
                premium_expiry,
                referral_count,
                referred_by,
                is_active,
                full_name,
                username
            FROM Users
        ''')
        rows = c.fetchall()
        report = []
        now = time.time()
        for r in rows:
            item = dict(r)
            item['is_premium'] = r['premium_expiry'] > now
            
            # 🤝 Map Recruits (Fetch their names/IDs)
            c.execute("SELECT full_name, username, telegram_chat_id FROM Users WHERE referred_by = ?", (r['telegram_chat_id'],))
            recruits = c.fetchall()
            item['recruit_list'] = [dict(rec) for rec in recruits]
            
            report.append(item)
    return report

def get_all_users():
    """Returns all unique users for global reports."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM Users")
        rows = c.fetchall()
    return [dict(r) for r in rows]

def get_all_broadcast_targets():
    """Returns all unique chat IDs for global announcements."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM Users")
        rows = c.fetchall()
    return [r[0] for r in rows]
def create_gift_code(target_chat_id=None, target_username=None, days=30):
    """Generates a unique gift code tied to an ID or a proactive username claim."""
    import secrets
    import string
    # Clean username
    if target_username:
        target_username = target_username.lstrip('@')
        
    code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    with db_session() as conn:
        c = conn.cursor()
        c.execute('INSERT INTO GiftCodes (code, target_chat_id, target_username, expiry_days, is_used, created_at) VALUES (?, ?, ?, ?, 0, ?)', 
                  (code, target_chat_id, target_username, days, int(time.time())))
    return code

def redeem_gift_code(chat_id, code, current_username=None):
    """Activates a gift code and grants institutional premium power."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT target_chat_id, target_username, expiry_days, is_used FROM GiftCodes WHERE code = ?', (code,))
        row = c.fetchone()
        if not row:
            return False, "❌ Invalid gift code."
        
        target_id, target_username, days, is_used = row['target_chat_id'], row['target_username'], row['expiry_days'], row['is_used']
        if is_used:
            return False, "❌ This code has already been redeemed."
        
        # Validation Logic
        if target_id and int(target_id) != int(chat_id):
            return False, "❌ This code is tied to a different user ID."
        
        if target_username:
            clean_current = current_username.lstrip('@') if current_username else None
            if target_username.lower() != (clean_current.lower() if clean_current else ""):
                return False, f"❌ This code is reserved for @{target_username}."    
        # Grant premium
        current_time = int(time.time())
        c.execute('SELECT premium_expiry FROM Users WHERE telegram_chat_id = ?', (chat_id,))
        u_row = c.fetchone()
        current_expiry = u_row['premium_expiry'] if u_row else 0
        
        new_expiry = max(current_expiry, current_time) + (days * 86400)
        c.execute('UPDATE Users SET premium_expiry = ? WHERE telegram_chat_id = ?', (new_expiry, chat_id))
        c.execute('UPDATE GiftCodes SET is_used = 1 WHERE code = ?', (code,))
        
    return True, f"✅ Success! You have been granted {days} days of Premium Institutional access."
def get_chat_id_by_username(username):
    """Resolves a @username to a telegram_chat_id from the database."""
    # Strip @ if present
    username = username.lstrip('@')
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT telegram_chat_id FROM Users WHERE username = ? OR full_name LIKE ?', (username, f"%{username}%"))
        row = c.fetchone()
    return row[0] if row else None
