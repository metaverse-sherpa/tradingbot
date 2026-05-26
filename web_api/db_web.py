import sqlite3
import time
from database import db_session, encrypt, decrypt

def get_web_user_by_email(email):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE email = ?', (email.strip().lower(),))
        row = c.fetchone()
        return dict(row) if row else None

def get_web_user_by_google_id(google_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE google_id = ?', (google_id,))
        row = c.fetchone()
        return dict(row) if row else None

def get_web_user_by_id(user_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row:
            user = dict(row)
            # Decrypt exchange keys if they exist
            if user.get("api_key"):
                try: user["api_key"] = decrypt(user["api_key"])
                except Exception: pass
            if user.get("api_secret"):
                try: user["api_secret"] = decrypt(user["api_secret"])
                except Exception: pass
            if user.get("api_password"):
                try: user["api_password"] = decrypt(user["api_password"])
                except Exception: pass
            if user.get("alpaca_api_key"):
                try: user["alpaca_api_key"] = decrypt(user["alpaca_api_key"])
                except Exception: pass
            if user.get("alpaca_api_secret"):
                try: user["alpaca_api_secret"] = decrypt(user["alpaca_api_secret"])
                except Exception: pass
            return user
        return None

def create_web_user_email(email, password_hash, full_name=None, referred_by=None):
    with db_session() as conn:
        c = conn.cursor()
        created_at = int(time.time())
        c.execute('''
            INSERT INTO WebUsers (email, password_hash, full_name, referred_by, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (email.strip().lower(), password_hash, full_name, referred_by, created_at))
        user_id = c.lastrowid
        
        if referred_by:
            # Increment referrer count
            c.execute('UPDATE WebUsers SET referral_count = referral_count + 1 WHERE id = ?', (referred_by,))
            
        return user_id

def create_web_user_google(email, google_id, full_name=None, referred_by=None):
    with db_session() as conn:
        c = conn.cursor()
        created_at = int(time.time())
        c.execute('''
            INSERT INTO WebUsers (email, google_id, full_name, referred_by, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (email.strip().lower(), google_id, full_name, referred_by, created_at))
        user_id = c.lastrowid
        
        if referred_by:
            c.execute('UPDATE WebUsers SET referral_count = referral_count + 1 WHERE id = ?', (referred_by,))
            
        return user_id

def update_web_user_keys(user_id, exchange_id, api_key, api_secret, api_password):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE WebUsers
            SET exchange_id = ?, api_key = ?, api_secret = ?, api_password = ?
            WHERE id = ?
        ''', (exchange_id, encrypt(api_key), encrypt(api_secret), encrypt(api_password), user_id))

def update_web_user_alpaca_keys(user_id, api_key, api_secret, endpoint):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE WebUsers
            SET alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?
            WHERE id = ?
        ''', (encrypt(api_key), encrypt(api_secret), endpoint, user_id))

def update_web_user_preferences(user_id, risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, hide_dollars):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE WebUsers
            SET risk_pct = ?, stock_risk_pct = ?, custom_equity_type = ?, custom_equity_value = ?, hide_dollars = ?
            WHERE id = ?
        ''', (risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, hide_dollars, user_id))

def update_web_user_symbols(user_id, symbols_str):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET enabled_symbols = ? WHERE id = ?', (symbols_str, user_id))

def update_web_user_status(user_id, is_active):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET is_active = ? WHERE id = ?', (is_active, user_id))

def update_web_user_strategy(user_id, strategy_type, strategy_name):
    with db_session() as conn:
        c = conn.cursor()
        if strategy_type == "crypto":
            c.execute('UPDATE WebUsers SET active_crypto_strategy = ? WHERE id = ?', (strategy_name, user_id))
        else:
            c.execute('UPDATE WebUsers SET active_stock_strategy = ? WHERE id = ?', (strategy_name, user_id))

def update_web_user_wallet(user_id, source_wallet):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET source_wallet = ? WHERE id = ?', (source_wallet, user_id))

def update_web_user_telegram(user_id, telegram_chat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET telegram_chat_id = ? WHERE id = ?', (telegram_chat_id, user_id))
