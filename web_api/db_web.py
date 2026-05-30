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

def update_web_user_preferences(user_id, risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, hide_dollars, email_notifications=1, email_frequency='realtime', browser_notifications=1):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE WebUsers
            SET risk_pct = ?, stock_risk_pct = ?, custom_equity_type = ?, custom_equity_value = ?, hide_dollars = ?,
                email_notifications = ?, email_frequency = ?, browser_notifications = ?
            WHERE id = ?
        ''', (risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, hide_dollars, int(email_notifications), email_frequency, int(browser_notifications), user_id))
        
        # Sync to Telegram bot if linked
        c.execute('SELECT telegram_chat_id FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0]:
            c.execute('''
                UPDATE Users
                SET risk_pct = ?, stock_risk_pct = ?, custom_equity_type = ?, custom_equity_value = ?, hide_dollars = ?
                WHERE telegram_chat_id = ?
            ''', (risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, hide_dollars, row[0]))

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
        c.execute('UPDATE WebUsers SET is_active = ? WHERE id = ?', (is_active, user_id))
        
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
        c.execute('UPDATE WebUsers SET telegram_chat_id = ? WHERE id = ?', (telegram_chat_id, user_id))
        
        if telegram_chat_id:
            # 1. Fetch Web Settings
            c.execute('''
                SELECT source_wallet, api_key, api_secret, api_password, exchange_id, 
                       alpaca_api_key, alpaca_api_secret, alpaca_endpoint,
                       referral_count, referral_credits, premium_expiry, premium_referrals, referral_reward_triggered
                FROM WebUsers WHERE id = ?
            ''', (user_id,))
            web_row = c.fetchone()
            
            # 2. Fetch Bot Settings
            c.execute('''
                SELECT source_wallet, blofin_api_key, blofin_api_secret, blofin_api_password, exchange_id,
                       alpaca_api_key, alpaca_api_secret, alpaca_endpoint,
                       referral_count, referral_credits, premium_expiry, premium_referrals, referral_reward_triggered
                FROM Users WHERE telegram_chat_id = ?
            ''', (telegram_chat_id,))
            bot_row = c.fetchone()
            
            if web_row and bot_row:
                w_wallet, w_ak, w_as, w_ap, w_exc, w_alk, w_als, w_ale, w_ref_count, w_credits, w_expiry, w_premium_ref, w_reward_triggered = web_row
                b_wallet, b_ak, b_as, b_ap, b_exc, b_alk, b_als, b_ale, b_ref_count, b_credits, b_expiry, b_premium_ref, b_reward_triggered = bot_row
                
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
                f_reward_triggered = max(w_reward_triggered or 0, b_reward_triggered or 0)
                
                # Update WebUsers with merged
                c.execute('''
                    UPDATE WebUsers 
                    SET source_wallet = ?, api_key = ?, api_secret = ?, api_password = ?, exchange_id = ?,
                         alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?,
                         referral_count = ?, referral_credits = ?, premium_expiry = ?, premium_referrals = ?,
                         referral_reward_triggered = ?
                    WHERE id = ?
                ''', (f_wallet, f_ak, f_as, f_ap, f_exc, f_alk, f_als, f_ale,
                      f_ref_count, f_credits, f_expiry, f_premium_ref, f_reward_triggered, user_id))
                
                # Update Users (Bot) with merged
                c.execute('''
                    UPDATE Users 
                    SET source_wallet = ?, blofin_api_key = ?, blofin_api_secret = ?, blofin_api_password = ?, exchange_id = ?,
                         alpaca_api_key = ?, alpaca_api_secret = ?, alpaca_endpoint = ?,
                         referral_count = ?, referral_credits = ?, premium_expiry = ?, premium_referrals = ?,
                         referral_reward_triggered = ?
                    WHERE telegram_chat_id = ?
                ''', (f_wallet, f_ak, f_as, f_ap, f_exc, f_alk, f_als, f_ale,
                      f_ref_count, f_credits, f_expiry, f_premium_ref, f_reward_triggered, telegram_chat_id))

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
                c.execute("UPDATE WebUsers SET premium_expiry = ? WHERE id = ?", (new_expiry, web_user_id))
            if tg_chat_id:
                c.execute("UPDATE Users SET premium_expiry = ? WHERE telegram_chat_id = ?", (new_expiry, tg_chat_id))
                
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
    if emails_prem_only:
        users = [u for u in users if is_premium(u)]
        
    return users

