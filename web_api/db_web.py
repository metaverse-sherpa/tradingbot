import sqlite3
import time
from database import db_session, encrypt, decrypt

_ENCRYPTED_KEY_FIELDS = ("api_key", "api_secret", "api_password", "alpaca_api_key", "alpaca_api_secret")

import threading
_USER_BY_EMAIL_CACHE = {}
_USER_BY_EMAIL_CACHE_LOCK = threading.Lock()

def invalidate_cache_by_user_id(user_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT email FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row:
            email_clean = row[0].strip().lower()
            with _USER_BY_EMAIL_CACHE_LOCK:
                if email_clean in _USER_BY_EMAIL_CACHE:
                    del _USER_BY_EMAIL_CACHE[email_clean]

def _decrypt_user_keys(user):
    """Decrypt all encrypted API key fields on a user dict in-place."""
    if not user:
        return user
    if "hide_dollars" in user and user["hide_dollars"] is not None:
        user["hide_dollars"] = bool(user["hide_dollars"])
    for field in _ENCRYPTED_KEY_FIELDS:
        if user.get(field):
            try:
                user[field] = decrypt(user[field])
            except Exception as e:
                print(f"[DECRYPT ERROR] Failed to decrypt {field} for user {user.get('id', '?')}: {e}")
                from utils_error import send_telegram_alert
                user_info = f"Web User: {user.get('id', '?')}"
                send_telegram_alert(f"Decryption Error ({field}) [{user_info}]", e)
    return user

def get_web_user_by_email(email):
    email_clean = email.strip().lower()
    now = time.time()
    with _USER_BY_EMAIL_CACHE_LOCK:
        if email_clean in _USER_BY_EMAIL_CACHE:
            expiry, cached_user = _USER_BY_EMAIL_CACHE[email_clean]
            if now < expiry:
                return cached_user

    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE email = ?', (email_clean,))
        row = c.fetchone()
        user = _decrypt_user_keys(dict(row)) if row else None

    if user:
        with _USER_BY_EMAIL_CACHE_LOCK:
            _USER_BY_EMAIL_CACHE[email_clean] = (now + 5, user)
            
    return user

def get_web_user_by_google_id(google_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE google_id = ?', (google_id,))
        row = c.fetchone()
        return _decrypt_user_keys(dict(row)) if row else None

def get_web_user_by_developer_api_key(api_key):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE developer_api_key = ?', (api_key,))
        row = c.fetchone()
        return _decrypt_user_keys(dict(row)) if row else None

def get_web_user_by_id(user_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row:
            user = dict(row)
            if "hide_dollars" in user and user["hide_dollars"] is not None:
                user["hide_dollars"] = bool(user["hide_dollars"])
            # Decrypt exchange keys if they exist
            for key_field in ("api_key", "api_secret", "api_password", "alpaca_api_key", "alpaca_api_secret"):
                if user.get(key_field):
                    try:
                        user[key_field] = decrypt(user[key_field])
                    except Exception as e:
                        print(f"[DECRYPT ERROR] Failed to decrypt {key_field} for user {user_id}: {e}")
                        from utils_error import send_telegram_alert
                        user_info = f"Web User: {user_id}"
                        send_telegram_alert(f"Decryption Error ({key_field}) [{user_info}]", e)
                        # Leave the raw encrypted value — it will fail at the exchange
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
            record_web_referral_signup(referred_by, full_name or email)
            
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
            record_web_referral_signup(referred_by, full_name or email)
            
        return user_id

def reconstruct_pem(flat_key):
    if not flat_key: return flat_key
    if "-----BEGIN" in flat_key and "-----END" in flat_key and "\n" not in flat_key:
        import re as r
        match = r.match(r'(-----BEGIN.*?-----)(.*?)(-----END.*?-----)', flat_key)
        if match:
            header, body, footer = match.groups()
            body = body.replace(" ", "")
            wrapped_body = "\n".join([body[i:i+64] for i in range(0, len(body), 64)])
            return f"{header}\n{wrapped_body}\n{footer}"
    return flat_key

def update_web_user_keys(user_id, exchange_id, api_key, api_secret, api_password, bingx_futures_type='standard', coinbase_sandbox=False):
    api_secret = reconstruct_pem(api_secret)
    cb_sb_val = 1 if coinbase_sandbox else 0
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE WebUsers
            SET exchange_id = ?, api_key = ?, api_secret = ?, api_password = ?, bingx_futures_type = ?, coinbase_sandbox = ?, history_cache = NULL, has_open_positions = 0
            WHERE id = ?
        ''', (exchange_id, encrypt(api_key), encrypt(api_secret), encrypt(api_password), bingx_futures_type or 'standard', cb_sb_val, user_id))
        
        # Sync to Telegram bot if linked
        c.execute('SELECT telegram_chat_id FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0]:
            try:
                c.execute('''
                    UPDATE Users
                    SET exchange_id = ?, blofin_api_key = ?, blofin_api_secret = ?, blofin_api_password = ?, bingx_futures_type = ?, coinbase_sandbox = ?, history_cache = NULL, has_open_positions = 0
                    WHERE telegram_chat_id = ?
                ''', (exchange_id, encrypt(api_key), encrypt(api_secret), encrypt(api_password), bingx_futures_type or 'standard', cb_sb_val, row[0]))
            except Exception as e:
                print(f"Telegram sync error for exchange keys / sandbox: {e}")
                from utils_error import send_telegram_alert
                user_info = f"Web User: {user_id}, TG: {row[0]}"
                send_telegram_alert(f"DB Sync Error (Exchange Keys) [{user_info}]", e)
    update_web_user_status(user_id, 1)
    invalidate_cache_by_user_id(user_id)

def delete_web_user_keys(user_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT telegram_chat_id, alpaca_api_key FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        
        has_alpaca = False
        tg_chat_id = None
        if row:
            tg_chat_id = row[0]
            has_alpaca = bool(row[1])
            
        is_active = 1 if has_alpaca else 0
        
        c.execute('''
            UPDATE WebUsers
            SET api_key = NULL, api_secret = NULL, api_password = NULL, exchange_id = 'blofin', is_active = ?
            WHERE id = ?
        ''', (is_active, user_id))
        
        if tg_chat_id:
            try:
                c.execute('''
                    UPDATE Users
                    SET blofin_api_key = NULL, blofin_api_secret = NULL, blofin_api_password = NULL, exchange_id = 'blofin', is_active = ?
                    WHERE telegram_chat_id = ?
                ''', (is_active, tg_chat_id))
            except Exception as e:
                print(f"Telegram sync error for delete exchange keys: {e}")
                from utils_error import send_telegram_alert
                user_info = f"Web User: {user_id}, TG: {tg_chat_id}"
                send_telegram_alert(f"DB Sync Error (Delete Crypto Keys) [{user_info}]", e)
    invalidate_cache_by_user_id(user_id)

def delete_web_user_alpaca_keys(user_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT telegram_chat_id, api_key FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        
        has_crypto = False
        tg_chat_id = None
        if row:
            tg_chat_id = row[0]
            has_crypto = bool(row[1])
            
        is_active = 1 if has_crypto else 0
        
        c.execute('''
            UPDATE WebUsers
            SET alpaca_api_key = NULL, alpaca_api_secret = NULL, alpaca_endpoint = NULL, is_active = ?
            WHERE id = ?
        ''', (is_active, user_id))
        
        if tg_chat_id:
            try:
                c.execute('''
                    UPDATE Users
                    SET alpaca_api_key = NULL, alpaca_api_secret = NULL, alpaca_endpoint = NULL, is_active = ?
                    WHERE telegram_chat_id = ?
                ''', (is_active, tg_chat_id))
            except Exception as e:
                print(f"Telegram sync error for delete alpaca keys: {e}")
                from utils_error import send_telegram_alert
                user_info = f"Web User: {user_id}, TG: {tg_chat_id}"
                send_telegram_alert(f"DB Sync Error (Delete Alpaca Keys) [{user_info}]", e)
    invalidate_cache_by_user_id(user_id)

def update_web_user_alpaca_keys(user_id, api_key, api_secret, endpoint):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE WebUsers
            SET alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?
            WHERE id = ?
        ''', (encrypt(api_key), encrypt(api_secret), endpoint, user_id))
        
        # Sync to Telegram bot if linked
        c.execute('SELECT telegram_chat_id FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0]:
            try:
                c.execute('''
                    UPDATE Users
                    SET alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?
                    WHERE telegram_chat_id = ?
                ''', (encrypt(api_key), encrypt(api_secret), endpoint, row[0]))
            except Exception as e:
                print(f"Telegram sync error for Alpaca keys: {e}")
                from utils_error import send_telegram_alert
                user_info = f"Web User: {user_id}, TG: {row[0]}"
                send_telegram_alert(f"DB Sync Error (Alpaca Keys) [{user_info}]", e)
    update_web_user_status(user_id, 1)
    invalidate_cache_by_user_id(user_id)

def update_web_user_preferences(user_id, risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, hide_dollars, email_notifications=1, email_frequency='realtime', browser_notifications=1, risk_profile=None, investment_goal=None):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE WebUsers
            SET risk_pct = ?, stock_risk_pct = ?, custom_equity_type = ?, custom_equity_value = ?, hide_dollars = ?,
                email_notifications = ?, email_frequency = ?, browser_notifications = ?,
                risk_profile = COALESCE(?, risk_profile), investment_goal = COALESCE(?, investment_goal)
            WHERE id = ?
        ''', (risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, int(bool(hide_dollars)), int(email_notifications), email_frequency, int(browser_notifications), risk_profile, investment_goal, user_id))
        
        # Sync to Telegram bot if linked
        c.execute('SELECT telegram_chat_id FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0]:
            c.execute('''
                UPDATE Users
                SET risk_pct = ?, stock_risk_pct = ?, custom_equity_type = ?, custom_equity_value = ?, hide_dollars = ?
                WHERE telegram_chat_id = ?
            ''', (risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, int(bool(hide_dollars)), row[0]))

def update_web_user_symbols(user_id, symbols_str):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET enabled_symbols = ? WHERE id = ?', (symbols_str, user_id))
        
        # Sync to Telegram bot if linked
        c.execute('SELECT telegram_chat_id FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0]:
            c.execute('UPDATE Users SET enabled_symbols = ? WHERE telegram_chat_id = ?', (symbols_str, row[0]))

def update_web_user_status(user_id, is_active):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET is_active = ? WHERE id = ?', (1 if is_active else 0, user_id))
        
        # Sync to Telegram bot if linked
        c.execute('SELECT telegram_chat_id FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0]:
            c.execute('UPDATE Users SET is_active = ? WHERE telegram_chat_id = ?', (1 if is_active else 0, row[0]))

def update_web_user_strategy(user_id, strategy_type, strategy_name):
    with db_session() as conn:
        c = conn.cursor()
        if strategy_type == "crypto":
            c.execute('UPDATE WebUsers SET active_crypto_strategy = ? WHERE id = ?', (strategy_name, user_id))
        else:
            c.execute('UPDATE WebUsers SET active_stock_strategy = ? WHERE id = ?', (strategy_name, user_id))
            
        # Sync to Telegram bot if linked
        c.execute('SELECT telegram_chat_id FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0]:
            if strategy_type == "crypto":
                c.execute('UPDATE Users SET active_crypto_strategy = ?, strategy = ? WHERE telegram_chat_id = ?', (strategy_name, strategy_name, row[0]))
            else:
                c.execute('UPDATE Users SET active_stock_strategy = ? WHERE telegram_chat_id = ?', (strategy_name, row[0]))

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
        if telegram_chat_id:
            # Prevent multiple web accounts from using the same telegram chat ID
            c.execute('UPDATE WebUsers SET telegram_chat_id = NULL WHERE telegram_chat_id = ? AND id != ?', (telegram_chat_id, user_id))
            
        c.execute('UPDATE WebUsers SET telegram_chat_id = ? WHERE id = ?', (telegram_chat_id, user_id))
        
        if telegram_chat_id:
            # 1. Fetch Web Settings
            c.execute('''
                SELECT source_wallet, api_key, api_secret, api_password, exchange_id, 
                       alpaca_api_key, alpaca_api_secret, alpaca_endpoint,
                       referral_count, referral_credits, premium_expiry, premium_referrals, referral_reward_triggered,
                       coinbase_sandbox
                FROM WebUsers WHERE id = ?
            ''', (user_id,))
            web_row = c.fetchone()
            
            # 2. Fetch Bot Settings
            c.execute('''
                SELECT source_wallet, blofin_api_key, blofin_api_secret, blofin_api_password, exchange_id,
                       alpaca_api_key, alpaca_api_secret, alpaca_endpoint,
                       referral_count, referral_credits, premium_expiry, premium_referrals, referral_reward_triggered,
                       coinbase_sandbox
                FROM Users WHERE telegram_chat_id = ?
            ''', (telegram_chat_id,))
            bot_row = c.fetchone()
            
            if web_row and bot_row:
                w_wallet, w_ak, w_as, w_ap, w_exc, w_alk, w_als, w_ale, w_ref_count, w_credits, w_expiry, w_premium_ref, w_reward_triggered, w_cb = web_row
                b_wallet, b_ak, b_as, b_ap, b_exc, b_alk, b_als, b_ale, b_ref_count, b_credits, b_expiry, b_premium_ref, b_reward_triggered, b_cb = bot_row
                
                # Merge logic: Web takes precedence if it exists, otherwise Bot
                f_wallet = w_wallet or b_wallet
                f_ak = w_ak or b_ak
                f_as = w_as or b_as
                f_ap = w_ap or b_ap
                f_exc = w_exc or b_exc
                f_alk = w_alk or b_alk
                f_als = w_als or b_als
                f_ale = w_ale or b_ale
                
                # Coinbase Sandbox is an integer 0 or 1. If web has a value, use it. If not, fallback to bot.
                f_cb = w_cb if w_cb is not None else (b_cb if b_cb is not None else 0)
                
                # Referral / Premium Sync
                f_ref_count = max(w_ref_count or 0, b_ref_count or 0)
                f_credits = max(w_credits or 0.0, b_credits or 0.0)
                f_expiry = max(w_expiry or 0, b_expiry or 0)
                f_premium_ref = max(w_premium_ref or 0, b_premium_ref or 0)
                f_reward_triggered = max(w_reward_triggered or 0, b_reward_triggered or 0)
                
                # Update WebUsers with merged
                c.execute('''
                    UPDATE WebUsers 
                    SET source_wallet = ?, api_key = ?, api_secret = ?, api_password = ?, exchange_id = ?,
                         alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?,
                         referral_count = ?, referral_credits = ?, premium_expiry = ?, premium_referrals = ?,
                         referral_reward_triggered = ?, coinbase_sandbox = ?
                    WHERE id = ?
                ''', (f_wallet, f_ak, f_as, f_ap, f_exc, f_alk, f_als, f_ale,
                      f_ref_count, f_credits, f_expiry, f_premium_ref, f_reward_triggered, f_cb, user_id))
                
                # Update Users (Bot) with merged
                c.execute('''
                    UPDATE Users 
                    SET source_wallet = ?, blofin_api_key = ?, blofin_api_secret = ?, blofin_api_password = ?, exchange_id = ?,
                         alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?,
                         referral_count = ?, referral_credits = ?, premium_expiry = ?, premium_referrals = ?,
                         referral_reward_triggered = ?, coinbase_sandbox = ?
                    WHERE telegram_chat_id = ?
                ''', (f_wallet, f_ak, f_as, f_ap, f_exc, f_alk, f_als, f_ale,
                      f_ref_count, f_credits, f_expiry, f_premium_ref, f_reward_triggered, f_cb, telegram_chat_id))

def send_telegram_notification(chat_id, message):
    try:
        from bot.config import TELEGRAM_TOKEN
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to send telegram notification: {e}")

def record_web_referral_signup(referrer_id, referee_name):
    """Increments recruits count for the referrer and notifies them via Telegram bot if linked."""
    with db_session() as conn:
        c = conn.cursor()
        
        # Determine referrer details
        tg_chat_id = None
        web_user_id = None
        
        # 1. Check if referrer_id is a Telegram chat ID
        c.execute("SELECT telegram_chat_id FROM Users WHERE telegram_chat_id = ?", (referrer_id,))
        row = c.fetchone()
        if row:
            tg_chat_id = row[0]
            # See if there's a corresponding WebUser
            c.execute("SELECT id FROM WebUsers WHERE telegram_chat_id = ?", (tg_chat_id,))
            web_row = c.fetchone()
            if web_row:
                web_user_id = web_row[0]
        else:
            # 2. Check if referrer_id is a WebUser id
            c.execute("SELECT id, telegram_chat_id FROM WebUsers WHERE id = ?", (referrer_id,))
            web_row = c.fetchone()
            if web_row:
                web_user_id = web_row[0]
                tg_chat_id = web_row[1]
        
        # Increment counts in whichever tables exist
        if web_user_id:
            c.execute("UPDATE WebUsers SET referral_count = referral_count + 1 WHERE id = ?", (web_user_id,))
        if tg_chat_id:
            c.execute("UPDATE Users SET referral_count = referral_count + 1 WHERE telegram_chat_id = ?", (tg_chat_id,))
            
        # Send Telegram notification to referrer
        if tg_chat_id:
            msg_std = (
                f"🎉 *New Recruit Signed Up!*\n\n"
                f"**{referee_name}** has registered under your referral link.\n\n"
                f"ℹ️ _Note: They must upgrade to a premium subscription for this to count towards your free 1-month reward (you need 3 premium recruits to unlock a free month)._"
            )
            send_telegram_notification(tg_chat_id, msg_std)

def award_premium_referral_on_upgrade(referee_id):
    """Called when referee upgrades to Premium. Awards premium referral credit to the referrer if not already triggered."""
    with db_session() as conn:
        c = conn.cursor()
        
        # Check referee's referred_by and referral_reward_triggered
        c.execute("SELECT referred_by, referral_reward_triggered, email, full_name FROM WebUsers WHERE id = ?", (referee_id,))
        referee = c.fetchone()
        if not referee:
            return
            
        referred_by, reward_triggered, email, full_name = referee
        if not referred_by or reward_triggered:
            return # No referrer or already rewarded
            
        # Set referral_reward_triggered = 1 for referee
        c.execute("UPDATE WebUsers SET referral_reward_triggered = 1 WHERE id = ?", (referee_id,))
        
        # Check if they have a linked Telegram bot user, update there too
        c.execute("SELECT telegram_chat_id FROM WebUsers WHERE id = ?", (referee_id,))
        referee_tg = c.fetchone()
        if referee_tg and referee_tg[0]:
            c.execute("UPDATE Users SET referral_reward_triggered = 1 WHERE telegram_chat_id = ?", (referee_tg[0],))
            
        # Resolve referrer's Web ID and Telegram ID
        tg_chat_id = None
        web_user_id = None
        
        # Check if referred_by is a Telegram chat ID
        c.execute("SELECT telegram_chat_id FROM Users WHERE telegram_chat_id = ?", (referred_by,))
        row = c.fetchone()
        if row:
            tg_chat_id = row[0]
            c.execute("SELECT id FROM WebUsers WHERE telegram_chat_id = ?", (tg_chat_id,))
            web_row = c.fetchone()
            if web_row:
                web_user_id = web_row[0]
        else:
            # Check if referred_by is a WebUser id
            c.execute("SELECT id, telegram_chat_id FROM WebUsers WHERE id = ?", (referred_by,))
            web_row = c.fetchone()
            if web_row:
                web_user_id = web_row[0]
                tg_chat_id = web_row[1]
                
        # Increment premium_referrals count for referrer
        p_ref = 0
        p_expiry = 0
        
        if web_user_id:
            c.execute("UPDATE WebUsers SET premium_referrals = premium_referrals + 1 WHERE id = ?", (web_user_id,))
            c.execute("SELECT premium_referrals, premium_expiry FROM WebUsers WHERE id = ?", (web_user_id,))
            row = c.fetchone()
            if row:
                p_ref, p_expiry = row
                
        if tg_chat_id:
            c.execute("UPDATE Users SET premium_referrals = premium_referrals + 1 WHERE telegram_chat_id = ?", (tg_chat_id,))
            c.execute("SELECT premium_referrals, premium_expiry FROM Users WHERE telegram_chat_id = ?", (tg_chat_id,))
            row = c.fetchone()
            if row:
                if not p_ref:
                    p_ref, p_expiry = row
                    
        # Check if they reached a multiple of 3 to award 30 days of premium
        if p_ref > 0 and p_ref % 3 == 0:
            now = int(time.time())
            current_expiry = max(p_expiry or 0, now)
            new_expiry = current_expiry + (30 * 24 * 60 * 60)
            
            if web_user_id:
                c.execute("UPDATE WebUsers SET premium_expiry = ?, premium_expired_notified = '0', premium_warning_notified = '0' WHERE id = ?", (new_expiry, web_user_id))
            if tg_chat_id:
                c.execute("UPDATE Users SET premium_expiry = ?, premium_expired_notified = '0', premium_warning_notified = '0' WHERE telegram_chat_id = ?", (new_expiry, tg_chat_id))
                
            # Notify referrer of reward extension
            if tg_chat_id:
                msg_reward = (
                    "🎉 *PREMIUM MILESTONE REACHED!*\n\n"
                    "You've successfully recruited 3 Premium members. Your **Premium access** has been activated/extended for 30 days!\n\n"
                    "🏔️ _The Sherpa honors your leadership._"
                )
                send_telegram_notification(tg_chat_id, msg_reward)
        else:
            # Just notify of successful premium upgrade referral
            if tg_chat_id:
                referee_display = full_name or email
                msg_upgrade = (
                    f"🔥 *Premium Referral Activated!*\n\n"
                    f"Your recruit **{referee_display}** has upgraded to Premium!\n\n"
                    f"You have now referred **{p_ref}** Premium members (you need 3 to get 1 month free Premium. Next reward at **{((p_ref // 3) + 1) * 3}**)."
                )
                send_telegram_notification(tg_chat_id, msg_upgrade)

def get_users_for_email_alerts(frequency="realtime"):
    """
    Returns a list of WebUsers who want email alerts for a given frequency.
    Checks if emails_premium_only flag is enabled and filters premium users if true.
    """
    from database import get_config, is_premium
    emails_prem_only = get_config("emails_premium_only", "0") == "1"
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE email_notifications = 1 AND email_frequency = ?', (frequency,))
        rows = c.fetchall()
        
    users = [dict(r) for r in rows]
    
    from database import get_user
    processed_users = []
    for u in users:
        tg_id = u.get('telegram_chat_id')
        u['is_premium_user'] = False
        if tg_id:
            tg_user = get_user(tg_id)
            if tg_user and is_premium(tg_user):
                u['is_premium_user'] = True
                
        if emails_prem_only and not u['is_premium_user']:
            continue
        processed_users.append(u)
        
    return processed_users

def get_users_for_daily_processing():
    """
    Returns a list of WebUsers that require *any* daily processing:
    1. needs_snapshot: Premium user who has connected at least one exchange.
    2. wants_daily_email: User opted into daily summary emails.
    """
    from database import get_config, is_premium, get_user
    emails_prem_only = get_config("emails_premium_only", "0") == "1"
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers')
        rows = c.fetchall()
        
    users = [dict(r) for r in rows]
    processed_users = []
    
    for u in users:
        tg_id = u.get('telegram_chat_id')
        u['is_premium_user'] = False
        if tg_id:
            tg_user = get_user(tg_id)
            if tg_user and is_premium(tg_user):
                u['is_premium_user'] = True
                
        # Determine if they want a daily email
        wants_daily_email = u.get('email_notifications') == 1 and u.get('email_frequency') == 'daily'
        if emails_prem_only and not u['is_premium_user']:
            wants_daily_email = False
            
        u['wants_daily_email'] = wants_daily_email
        
        # Determine if they need a daily portfolio snapshot
        has_crypto = bool(u.get('api_key') and u.get('api_secret'))
        has_stock = bool(u.get('alpaca_api_key') and u.get('alpaca_api_secret'))
        has_exchange = has_crypto or has_stock
        
        u['needs_snapshot'] = u['is_premium_user'] and has_exchange
        
        if u['needs_snapshot'] or u['wants_daily_email']:
            processed_users.append(u)
            
    return processed_users

def get_users_for_weekly_processing():
    """
    Returns a list of WebUsers who want weekly summaries (email_notifications = 1).
    Respects emails_premium_only settings.
    """
    from database import get_config, is_premium, get_user
    emails_prem_only = get_config("emails_premium_only", "0") == "1"
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM WebUsers WHERE email_notifications = 1')
        rows = c.fetchall()
        
    users = [dict(r) for r in rows]
    processed_users = []
    for u in users:
        tg_id = u.get('telegram_chat_id')
        u['is_premium_user'] = False
        if tg_id:
            tg_user = get_user(tg_id)
            if tg_user and is_premium(tg_user):
                u['is_premium_user'] = True
                
        if emails_prem_only and not u['is_premium_user']:
            continue
            
        # Determine if exchange is connected
        has_crypto = bool(u.get('api_key') and u.get('api_secret'))
        has_stock = bool(u.get('alpaca_api_key') and u.get('alpaca_api_secret'))
        u['has_crypto_exchange'] = has_crypto
        u['has_stock_exchange'] = has_stock
        
        processed_users.append(u)
        
    return processed_users


