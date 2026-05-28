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
            award_web_referral(referred_by)
            
        return user_id

def create_web_user_google(email, google_id, full_name=None, referred_by=None, avatar_url=None):
    with db_session() as conn:
        c = conn.cursor()
        created_at = int(time.time())
        c.execute('''
            INSERT INTO WebUsers (email, google_id, full_name, referred_by, avatar_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email.strip().lower(), google_id, full_name, referred_by, avatar_url, created_at))
        user_id = c.lastrowid
        
        if referred_by:
            award_web_referral(referred_by)
            
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
        
        # Sync to Telegram bot if linked
        c.execute('SELECT telegram_chat_id FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0]:
            c.execute('UPDATE Users SET source_wallet = ? WHERE telegram_chat_id = ?', (source_wallet, row[0]))

def update_web_user_telegram(user_id, telegram_chat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET telegram_chat_id = ? WHERE id = ?', (telegram_chat_id, user_id))
        
        if telegram_chat_id:
            # 1. Fetch Web Settings
            c.execute('''
                SELECT source_wallet, api_key, api_secret, api_password, exchange_id, 
                       alpaca_api_key, alpaca_api_secret, alpaca_endpoint,
                       referral_count, referral_credits, premium_expiry, premium_referrals
                FROM WebUsers WHERE id = ?
            ''', (user_id,))
            web_row = c.fetchone()
            
            # 2. Fetch Bot Settings
            c.execute('''
                SELECT source_wallet, blofin_api_key, blofin_api_secret, blofin_api_password, exchange_id,
                       alpaca_api_key, alpaca_api_secret, alpaca_endpoint,
                       referral_count, referral_credits, premium_expiry, premium_referrals
                FROM Users WHERE telegram_chat_id = ?
            ''', (telegram_chat_id,))
            bot_row = c.fetchone()
            
            if web_row and bot_row:
                w_wallet, w_ak, w_as, w_ap, w_exc, w_alk, w_als, w_ale, w_ref_count, w_credits, w_expiry, w_premium_ref = web_row
                b_wallet, b_ak, b_as, b_ap, b_exc, b_alk, b_als, b_ale, b_ref_count, b_credits, b_expiry, b_premium_ref = bot_row
                
                # Merge logic: Web takes precedence if it exists, otherwise Bot
                f_wallet = w_wallet or b_wallet
                f_ak = w_ak or b_ak
                f_as = w_as or b_as
                f_ap = w_ap or b_ap
                f_exc = w_exc or b_exc
                f_alk = w_alk or b_alk
                f_als = w_als or b_als
                f_ale = w_ale or b_ale
                
                # Referral / Premium Sync
                f_ref_count = max(w_ref_count or 0, b_ref_count or 0)
                f_credits = max(w_credits or 0.0, b_credits or 0.0)
                f_expiry = max(w_expiry or 0, b_expiry or 0)
                f_premium_ref = max(w_premium_ref or 0, b_premium_ref or 0)
                
                # Update WebUsers with merged
                c.execute('''
                    UPDATE WebUsers 
                    SET source_wallet = ?, api_key = ?, api_secret = ?, api_password = ?, exchange_id = ?,
                        alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?,
                        referral_count = ?, referral_credits = ?, premium_expiry = ?, premium_referrals = ?
                    WHERE id = ?
                ''', (f_wallet, f_ak, f_as, f_ap, f_exc, f_alk, f_als, f_ale,
                      f_ref_count, f_credits, f_expiry, f_premium_ref, user_id))
                
                # Update Users (Bot) with merged
                c.execute('''
                    UPDATE Users 
                    SET source_wallet = ?, blofin_api_key = ?, blofin_api_secret = ?, blofin_api_password = ?, exchange_id = ?,
                        alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?,
                        referral_count = ?, referral_credits = ?, premium_expiry = ?, premium_referrals = ?
                    WHERE telegram_chat_id = ?
                ''', (f_wallet, f_ak, f_as, f_ap, f_exc, f_alk, f_als, f_ale,
                      f_ref_count, f_credits, f_expiry, f_premium_ref, telegram_chat_id))

def award_web_referral(referrer_id):
    """Increments referral counts/credits on web and synchronizes to bot if linked."""
    with db_session() as conn:
        c = conn.cursor()
        
        # Increment referral stats for WebUser
        c.execute('''
            UPDATE WebUsers 
            SET referral_count = referral_count + 1,
                premium_referrals = premium_referrals + 1
            WHERE id = ?
        ''', (referrer_id,))
        
        # Check if they reached a multiple of 3 to award 30 days
        c.execute('SELECT premium_referrals, premium_expiry, telegram_chat_id FROM WebUsers WHERE id = ?', (referrer_id,))
        row = c.fetchone()
        if row:
            p_ref, p_expiry, tg_chat_id = row
            if p_ref > 0 and p_ref % 3 == 0:
                now = int(time.time())
                current_expiry = max(p_expiry or 0, now)
                new_expiry = current_expiry + (30 * 24 * 60 * 60)
                
                c.execute('UPDATE WebUsers SET premium_expiry = ? WHERE id = ?', (new_expiry, referrer_id))
                
                # If Telegram is linked, synchronize it directly in Users (Bot)
                if tg_chat_id:
                    c.execute('''
                        UPDATE Users 
                        SET premium_expiry = ?, 
                            premium_referrals = ?, 
                            referral_count = referral_count + 1 
                        WHERE telegram_chat_id = ?
                    ''', (new_expiry, p_ref, tg_chat_id))
            else:
                # If not a multiple of 3 but Telegram is linked, just sync the count
                if tg_chat_id:
                    c.execute('''
                        UPDATE Users 
                        SET premium_referrals = ?, 
                            referral_count = referral_count + 1 
                        WHERE telegram_chat_id = ?
                    ''', (p_ref, tg_chat_id))
