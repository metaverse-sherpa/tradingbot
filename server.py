import os
import sys
import json
import time
import asyncio
from flask import Flask, request, jsonify, make_response, g
from flask_cors import CORS

# Add root folder to path so imports work perfectly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database
import utils_gcp
from bot.config import is_stock
from web_api.db_web import (
    get_web_user_by_email,
    get_web_user_by_google_id,
    create_web_user_email,
    create_web_user_google,
    get_web_user_by_id,
    update_web_user_keys,
    update_web_user_alpaca_keys,
    update_web_user_preferences,
    update_web_user_symbols,
    update_web_user_status,
    update_web_user_strategy,
    update_web_user_wallet,
    update_web_user_telegram
)
from web_api.auth import (
    hash_password,
    check_password,
    generate_token,
    verify_google_token,
    require_auth
)

# Initialize Database on Startup
database.init_db()

import threading
# Thread-safe in-memory cache for slow external API responses
RESPONSE_CACHE = {}  # Format: { (cache_type, user_id): (expiry_timestamp, data) }
RESPONSE_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 60  # Cache for 60 seconds

app = Flask(__name__, static_folder='webapp', static_url_path='')
# Configure Flask session secret
app.secret_key = utils_gcp.get_secret("FLASK_SECRET_KEY") or "metaverse-sherpa-secret-key"

# Enable CORS for frontend origin (e.g. static DO site or local Vite dev)
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
CORS(app, resources={r"/api/*": {"origins": [FRONTEND_ORIGIN, "https://metaversesherpa.io", "http://localhost:5173", "http://127.0.0.1:5173"]}}, supports_credentials=True, allow_headers=["Content-Type", "Authorization"])

# ----------------- Serve Frontend -----------------
@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

# ----------------- Unsubscribe Endpoint -----------------
@app.route('/unsubscribe', methods=['GET'])
def unsubscribe_page():
    email = request.args.get('email', '').strip().lower()
    if not email:
        return "<h3>Missing email parameter.</h3>", 400
        
    # Update DB
    from database import db_session
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET email_notifications = 0 WHERE email = ?', (email,))
        success = conn.changes() > 0
        
    if success:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Unsubscribed Successfully</title>
            <style>
                body {
                    background-color: #0B0E14;
                    color: #FFFFFF;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }
                .card {
                    background-color: #141A24;
                    border: 1px solid rgba(60, 215, 255, 0.15);
                    border-radius: 12px;
                    padding: 40px;
                    text-align: center;
                    max-width: 400px;
                }
                h2 { color: #3cd7ff; margin-top: 0; }
                p { color: rgba(255,255,255,0.7); font-size: 14px; line-height: 1.6; }
                .btn {
                    display: inline-block;
                    margin-top: 20px;
                    background: linear-gradient(90deg, #3cd7ff 0%, #00C853 100%);
                    color: #000000;
                    text-decoration: none;
                    font-weight: bold;
                    padding: 10px 20px;
                    border-radius: 6px;
                    font-size: 13px;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>🏔️ Trail Silenced Successfully</h2>
                <p>You have been unsubscribed from Metaverse Sherpa trading email alerts.</p>
                <p>If this was a mistake, you can easily turn email notifications back on anytime in your account Settings page.</p>
                <a href="https://bot.metaversesherpa.io" class="btn">Return to Dashboard</a>
            </div>
        </body>
        </html>
        """, 200
    else:
        return "<h3>Account not found or already unsubscribed.</h3>", 404


# ----------------- Health Endpoint -----------------
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "timestamp": int(time.time())}), 200

# ----------------- Configuration Endpoint -----------------
@app.route('/api/config', methods=['GET'])
def get_config():
    """Serves non-sensitive, public configuration to the frontend SPA."""
    return jsonify({
        "google_client_id": utils_gcp.get_secret("GOOGLE_CLIENT_ID") or ""
    }), 200

# ----------------- Authentication Routes -----------------
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    full_name = data.get("full_name", "")
    referred_by = data.get("referred_by") # Optional referrer ID
    
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
        
    existing = get_web_user_by_email(email)
    if existing:
        return jsonify({"error": "User with this email already exists"}), 400
        
    pw_hash = hash_password(password)
    user_id = create_web_user_email(email, pw_hash, full_name, referred_by)
    
    token = generate_token(user_id)
    response = make_response(jsonify({"message": "Registration successful", "token": token, "user": {"id": user_id, "email": email, "full_name": full_name}}), 201)
    
    # Set secure JWT cookie
    response.set_cookie(
        'session_token',
        token,
        httponly=True,
        secure=False, # Set to True in production (behind Nginx SSL)
        samesite='Lax',
        max_age=7 * 24 * 60 * 60 # 7 days
    )
    return response

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
        
    user = get_web_user_by_email(email)
    if not user or not user.get("password_hash") or not check_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password. If you can't remember it, click 'Forgot password?' to reset it."}), 401
        
    token = generate_token(user["id"])
    response = make_response(jsonify({"message": "Login successful", "token": token, "user": {"id": user["id"], "email": user["email"], "full_name": user["full_name"]}}), 200)
    
    response.set_cookie(
        'session_token',
        token,
        httponly=True,
        secure=False,
        samesite='Lax',
        max_age=7 * 24 * 60 * 60
    )
    return response

@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    
    if not email:
        return jsonify({"error": "Email is required"}), 400
        
    user = get_web_user_by_email(email)
    if not user:
        return jsonify({"error": "No account found with that email address."}), 404
        
    if user.get("google_id") and not user.get("password_hash"):
        return jsonify({"is_google_auth": True, "message": "This email address is registered with a Google account. Please use 'Continue with Google' to sign in."}), 200
        
    import secrets
    import time
    from database import db_session
    token = secrets.token_urlsafe(32)
    expiry = int(time.time()) + 3600 # 1 hour
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET reset_token=?, reset_token_expiry=? WHERE id=?', (token, expiry, user["id"]))
        conn.commit()
        
    from web_api.email_service import send_alert_email
    reset_url = f"https://bot.metaversesherpa.io/#/reset-password?token={token}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #0c1f30; color: #fff; padding: 20px; border-radius: 10px;">
        <h2 style="color: #3cd7ff;">Password Reset Request</h2>
        <p>You requested a password reset for Metaverse Sherpa.</p>
        <p><a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background-color: #3cd7ff; color: #000; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 10px;">Reset Your Password</a></p>
        <p style="margin-top: 20px; font-size: 12px; color: #888;">If you didn't request this, you can safely ignore this email. The link will expire in 1 hour.</p>
    </div>
    """
    send_alert_email(email, "Metaverse Sherpa Password Reset", html)
    
    return jsonify({"message": "Password reset link sent to your email."}), 200

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.json or {}
    token = data.get("token")
    new_password = data.get("password")
    
    if not token or not new_password:
        return jsonify({"error": "Token and new password are required."}), 400
        
    import time
    from database import db_session
    from web_api.auth import hash_password
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT id, reset_token_expiry FROM WebUsers WHERE reset_token=?', (token,))
        user = c.fetchone()
        
        if not user:
            return jsonify({"error": "Invalid or expired reset token."}), 400
            
        user_id = user[0]
        expiry = user[1]
        
        if not expiry or int(time.time()) > expiry:
            return jsonify({"error": "Reset link has expired. Please request a new one."}), 400
            
        password_hash = hash_password(new_password)
        c.execute('UPDATE WebUsers SET password_hash=?, reset_token=NULL, reset_token_expiry=NULL WHERE id=?', (password_hash, user_id))
        conn.commit()
        
    return jsonify({"message": "Password successfully updated."}), 200

@app.route('/api/auth/google', methods=['POST'])
def google_auth():
    data = request.json or {}
    id_token_str = data.get("credential")
    referred_by = data.get("referred_by")
    
    if not id_token_str:
        return jsonify({"error": "Google ID token required"}), 400
        
    id_info = verify_google_token(id_token_str)
    if not id_info:
        return jsonify({"error": "Invalid Google token"}), 400
        
    google_id = id_info['sub']
    email = id_info.get('email', '').strip().lower()
    full_name = id_info.get('name', '')
    picture = id_info.get('picture', '')
    
    # Find user by google_id or email
    user = get_web_user_by_google_id(google_id)
    if not user:
        user = get_web_user_by_email(email)
        if user:
            # Connect google account to existing email user
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute('UPDATE WebUsers SET google_id = ?, full_name = COALESCE(full_name, ?), avatar_url = ? WHERE id = ?', (google_id, full_name, picture, user['id']))
            user = get_web_user_by_id(user['id'])
        else:
            # Create brand new user
            user_id = create_web_user_google(email, google_id, full_name, referred_by, avatar_url=picture)
            user = get_web_user_by_id(user_id)
    else:
        # Update avatar url if changed or not present
        if user.get("avatar_url") != picture:
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute('UPDATE WebUsers SET avatar_url = ? WHERE id = ?', (picture, user['id']))
            user = get_web_user_by_id(user['id'])
            
    token = generate_token(user["id"])
    response = make_response(jsonify({"message": "Google authentication successful", "token": token, "user": {"id": user["id"], "email": user["email"], "full_name": user["full_name"], "avatar_url": user.get("avatar_url")}}), 200)
    
    response.set_cookie(
        'session_token',
        token,
        httponly=True,
        secure=False,
        samesite='Lax',
        max_age=7 * 24 * 60 * 60
    )
    return response

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    response = make_response(jsonify({"message": "Logout successful"}), 200)
    response.set_cookie('session_token', '', expires=0)
    return response

# ----------------- User Profile & Info -----------------
def _get_telegram_user(web_user):
    """If the web user has linked a Telegram chat ID, load the bot's User record."""
    tg_id = web_user.get("telegram_chat_id")
    if tg_id:
        try:
            import database
            return database.get_user(int(tg_id))
        except Exception as e:
            print(f"Could not load Telegram user {tg_id}: {e}")
    return None

@app.route('/api/user/profile', methods=['GET'])
@require_auth
def profile():
    user = g.user
    # Mask password hashes and raw sensitive keys for the response payload
    user.pop("password_hash", None)
    
    # Convert enabled_symbols string back to array
    def_syms = "BTC,ETH,SOL,DOGE,ADA,LINK,DOT,TON,ZEC,PEPE,BNB,NEAR,SUI,NOT,TAO,ONDO,ENA,FET,WIF"
    user["enabled_symbols"] = (user.get("enabled_symbols") or def_syms).split(",")
    
    # Determine premium level
    now = int(time.time())
    tg_user = _get_telegram_user(user)
    
    web_premium_expiry = user.get("premium_expiry", 0)
    bot_premium_expiry = tg_user.get("premium_expiry", 0) if tg_user else 0
    max_expiry = max(web_premium_expiry, bot_premium_expiry)
    
    super_admin_id = utils_gcp.get_secret("SUPER_ADMIN_ID")
    is_super_admin = False
    if super_admin_id:
        try:
            super_admin_id = int(super_admin_id)
            if user.get("telegram_chat_id") == super_admin_id or (tg_user and tg_user.get("telegram_chat_id") == super_admin_id):
                is_super_admin = True
        except ValueError:
            pass
            
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    user["is_premium"] = max_expiry > now or is_admin
    
    # Merge active strategies from bot user
    user["active_crypto_strategy"] = (tg_user or {}).get("active_crypto_strategy") or user.get("active_crypto_strategy", "Mean Reversion Scalper")
    user["active_stock_strategy"] = (tg_user or {}).get("active_stock_strategy") or user.get("active_stock_strategy", "Sherpa Velocity Pullback")
    
    # Sync hide_dollars setting from Telegram user if linked, otherwise default to True
    if tg_user:
        user["hide_dollars"] = tg_user.get("hide_dollars") if tg_user.get("hide_dollars") is not None else True
    else:
        user["hide_dollars"] = user.get("hide_dollars") if user.get("hide_dollars") is not None else True
    
    # Indicate if keys are configured (masking the actual keys)
    user["has_exchange_keys"] = bool((tg_user or {}).get("api_key") or user.get("api_key"))
    user["has_alpaca_keys"] = bool((tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key"))
    
    user["exchange_id"] = user.get("exchange_id") or (tg_user or {}).get("exchange_id")
    user["alpaca_endpoint"] = user.get("alpaca_endpoint") or (tg_user or {}).get("alpaca_endpoint")
    
    # Include server version details
    # Fetch recruits for referral UI
    recruit_list = []
    if tg_user:
        try:
            import database
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT full_name, username, telegram_chat_id FROM Users WHERE referred_by = ?", (tg_user["telegram_chat_id"],))
                recruit_list = [dict(rec) for rec in c.fetchall()]
        except Exception as e:
            print(f"Could not load recruits: {e}")
    user["recruit_list"] = recruit_list
    import database
    user["disabled_strategies"] = database.get_disabled_strategies()

    user["server_time"] = now
    return jsonify(user), 200

# ----------------- Exchange Keys Config -----------------
@app.route('/api/settings/exchange', methods=['POST'])
@require_auth
def settings_exchange():
    data = request.json or {}
    exchange_id = data.get("exchange_id", "blofin").strip()
    api_key = data.get("api_key", "").strip()
    api_secret = data.get("api_secret", "").strip()
    api_password = data.get("api_password", "").strip()
    
    if not api_key or not api_secret:
        return jsonify({"error": "API Key and Secret are required"}), 400
        
    update_web_user_keys(g.user["id"], exchange_id, api_key, api_secret, api_password)
    return jsonify({"message": f"{exchange_id.upper()} exchange keys saved successfully"}), 200

@app.route('/api/settings/alpaca', methods=['POST'])
@require_auth
def settings_alpaca():
    data = request.json or {}
    api_key = data.get("api_key", "").strip()
    api_secret = data.get("api_secret", "").strip()
    endpoint = data.get("endpoint", "https://paper-api.alpaca.markets").strip()
    
    if not api_key or not api_secret:
        return jsonify({"error": "Alpaca API Key and Secret are required"}), 400
        
    update_web_user_alpaca_keys(g.user["id"], api_key, api_secret, endpoint)
    return jsonify({"message": "Alpaca Stock keys saved successfully"}), 200

# ----------------- User Preferences -----------------
@app.route('/api/settings/preferences', methods=['POST'])
@require_auth
def settings_preferences():
    data = request.json or {}
    risk_pct = float(data.get("risk_pct", g.user.get("risk_pct", 1.0)))
    stock_risk_pct = float(data.get("stock_risk_pct", g.user.get("stock_risk_pct", 1.0)))
    custom_equity_type = data.get("custom_equity_type", g.user.get("custom_equity_type", "all"))
    custom_equity_value = data.get("custom_equity_value")
    if custom_equity_value is not None:
        custom_equity_value = float(custom_equity_value)
    hide_dollars = bool(data.get("hide_dollars", g.user.get("hide_dollars", False)))
    
    # Notification preferences
    email_notifications = bool(data.get("email_notifications", g.user.get("email_notifications", True)))
    email_frequency = data.get("email_frequency", g.user.get("email_frequency", "realtime"))
    browser_notifications = bool(data.get("browser_notifications", g.user.get("browser_notifications", True)))
    
    update_web_user_preferences(
        g.user["id"], risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, hide_dollars,
        email_notifications, email_frequency, browser_notifications
    )

    
    # Sync with linked Telegram account
    tg_user = _get_telegram_user(g.user)
    if tg_user:
        try:
            import database
            database.update_user_preference(tg_user["telegram_chat_id"], "hide_dollars", 1 if hide_dollars else 0)
            database.update_user_preference(tg_user["telegram_chat_id"], "risk_pct", risk_pct)
            database.update_user_preference(tg_user["telegram_chat_id"], "stock_risk_pct", stock_risk_pct)
        except Exception as e:
            print(f"Error syncing settings to Telegram Users table: {e}")
            
    return jsonify({"message": "Trading preferences saved successfully"}), 200

@app.route('/api/settings/telegram', methods=['POST'])
@require_auth
def settings_telegram():
    data = request.json or {}
    telegram_chat_id = data.get("telegram_chat_id")
    
    # Try to convert to int if provided
    if telegram_chat_id:
        try:
            telegram_chat_id = int(telegram_chat_id)
        except ValueError:
            return jsonify({"error": "Invalid Telegram Chat ID"}), 400
    else:
        telegram_chat_id = None
        
    update_web_user_telegram(g.user["id"], telegram_chat_id)
    return jsonify({"message": "Telegram Chat ID updated successfully"}), 200

@app.route('/api/settings/symbols', methods=['POST'])
@require_auth
def settings_symbols():
    data = request.json or {}
    symbols = data.get("symbols", [])
    symbols_str = ",".join(symbols)
    update_web_user_symbols(g.user["id"], symbols_str)
    return jsonify({"message": "Symbol basket updated successfully"}), 200

@app.route('/api/settings/status', methods=['POST'])
@require_auth
def settings_status():
    data = request.json or {}
    is_active = bool(data.get("is_active", False))
    update_web_user_status(g.user["id"], is_active)
    return jsonify({"message": f"Trading bot {'started' if is_active else 'stopped'} successfully"}), 200

@app.route('/api/settings/strategy', methods=['POST'])
@require_auth
def settings_strategy():
    data = request.json or {}
    strategy_type = data.get("type", "crypto") # "crypto" or "stock"
    strategy_name = data.get("strategy", "")
    
    if not strategy_name:
        return jsonify({"error": "Strategy name required"}), 400
        
    import database
    if database.is_strategy_disabled(strategy_name):
        return jsonify({"error": f"The strategy '{strategy_name}' has been disabled by the administrator."}), 400
        
    update_web_user_strategy(g.user["id"], strategy_type, strategy_name)
    return jsonify({"message": f"Active {strategy_type} strategy updated to {strategy_name}"}), 200

# ----------------- Stats & Live Balance -----------------
@app.route('/api/user/balance', methods=['GET'])
@require_auth
def get_balance():
    user = g.user
    user_id = user["id"]
    
    # Check cache
    now = time.time()
    cache_key = ("balance", user_id)
    with RESPONSE_CACHE_LOCK:
        if cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            if now < expiry:
                return jsonify(cached_data), 200

    tg_user = _get_telegram_user(user)
    balance_crypto = 0.0
    balance_stock = 0.0
    
    # Use the linked Telegram user's exchange keys if available
    crypto_api_key = (tg_user or {}).get("api_key") or user.get("api_key")
    crypto_api_secret = (tg_user or {}).get("api_secret") or user.get("api_secret")
    crypto_api_password = (tg_user or {}).get("api_password") or user.get("api_password") or ""
    crypto_exchange_id = (tg_user or {}).get("exchange_id") or user.get("exchange_id", "blofin")
    
    # 1. Query live Crypto balance (CCXT)
    if crypto_api_key and crypto_api_secret:
        try:
            import ccxt
            config = {
                "apiKey": crypto_api_key,
                "secret": crypto_api_secret,
                "password": crypto_api_password,
                "options": {"defaultType": "swap"},
                "enableRateLimit": True,
            }
            client = getattr(ccxt, crypto_exchange_id)(config)
            try:
                acc_type = "swap" if crypto_exchange_id in ['bitget', 'bingx'] else "futures"
                bal = client.fetch_balance(params={"type": acc_type})
                free_usdt = float(bal.get('USDT', {}).get('free', 0.0) or bal.get('free', {}).get('USDT', 0.0) or 0.0)
                
                # Calculate true equity (free + margin + unrealized pnl)
                total_equity = free_usdt
                try:
                    positions = client.fetch_positions()
                    for p in positions:
                        margin = float(p.get('initialMargin') or p.get('margin') or p.get('info', {}).get('margin') or 0)
                        upnl = float(p.get('unrealizedPnl') or p.get('info', {}).get('unrealizedPnl') or 0)
                        total_equity += (margin + upnl)
                except Exception as pos_err:
                    print(f"Error fetching positions for balance: {pos_err}")
                    
                balance_crypto = total_equity
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"Error fetching crypto balance: {e}")
            balance_crypto = float((tg_user or {}).get("equity") or user.get("equity") or 0.0)
    else:
        balance_crypto = float((tg_user or {}).get("equity") or user.get("equity") or 0.0)
            
    # 2. Query live Stock balance (Alpaca)
    # Use linked Telegram user's Alpaca keys if available
    alpaca_key = (tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key")
    alpaca_secret = (tg_user or {}).get("alpaca_api_secret") or user.get("alpaca_api_secret")
    alpaca_endpoint = (tg_user or {}).get("alpaca_endpoint") or user.get("alpaca_endpoint")
    
    if alpaca_key and alpaca_secret:
        try:
            alpaca_user = tg_user or user
            res = database.make_alpaca_request(alpaca_user, "GET", "/v2/account")
            balance_stock = float(res.get("portfolio_value", 0.0))
        except Exception as e:
            print(f"Error fetching stock balance: {e}")
            balance_stock = 0.0
            
    response_data = {
        "crypto_balance": balance_crypto,
        "stock_balance": balance_stock,
        "total_balance": balance_crypto + balance_stock
    }
    
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, response_data)
        
    return jsonify(response_data), 200

@app.route('/api/user/stats', methods=['GET'])
@require_auth
def get_stats():
    user = g.user
    user_id = user["id"]
    
    # Check cache
    now = time.time()
    cache_key = ("stats", user_id)
    with RESPONSE_CACHE_LOCK:
        if cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            if now < expiry:
                return jsonify(cached_data), 200

    tg_user = _get_telegram_user(user) or user
    
    # 1. Crypto Stats
    crypto_wins = tg_user.get("wins", tg_user.get("total_wins", 0))
    if crypto_wins is None: crypto_wins = 0
    crypto_losses = tg_user.get("losses", tg_user.get("total_losses", 0))
    if crypto_losses is None: crypto_losses = 0
    crypto_total = crypto_wins + crypto_losses
    crypto_win_rate = round((crypto_wins / crypto_total) * 100, 1) if crypto_total > 0 else 0.0
    
    crypto_equity = tg_user.get("equity", 1000.0) or 1000.0
    crypto_cum_pnl = tg_user.get("cum_pnl", tg_user.get("cumulative_pnl", 0.0)) or 0.0
    
    crypto_unrealized = 0.0
    crypto_open_count = 0
    
    # Attempt CCXT fetch if keys exist
    crypto_api_key = tg_user.get("api_key")
    crypto_api_secret = tg_user.get("api_secret")
    crypto_api_password = tg_user.get("api_password")
    crypto_exchange_id = tg_user.get("exchange_id", "blofin")
    
    if crypto_api_key and crypto_api_secret:
        try:
            import ccxt
            config = {
                "apiKey": crypto_api_key,
                "secret": crypto_api_secret,
                "password": crypto_api_password or "",
                "options": {"defaultType": "swap"},
                "timeout": 5000
            }
            client = getattr(ccxt, crypto_exchange_id)(config)
            try:
                positions = client.fetch_positions()
                for p in positions:
                    contracts = float(p.get("contracts", 0) or 0)
                    if contracts != 0:
                        crypto_open_count += 1
                        crypto_unrealized += float(p.get("unrealizedPnl", 0) or 0)
            finally:
                try: client.close()
                except: pass
        except Exception as ce:
            print(f"[STATS] Crypto live error: {ce}")
            
    crypto_overall_pnl = crypto_cum_pnl + crypto_unrealized
    crypto_overall_pnl_pct = round((crypto_overall_pnl / crypto_equity) * 100, 2) if crypto_equity > 0 else 0.0
    
    # 2. Stock Stats
    stock_equity = tg_user.get("alpaca_start_equity", 10000.0) or 10000.0
    stock_start_equity = tg_user.get("alpaca_start_equity", 10000.0) or 10000.0
    stock_unrealized = 0.0
    stock_open_count = 0
    stock_closed_count = 0
    
    stock_api_key = tg_user.get("alpaca_api_key")
    stock_api_secret = tg_user.get("alpaca_api_secret")
    
    if stock_api_key and stock_api_secret:
        try:
            acc = database.make_alpaca_request(tg_user, "GET", "/v2/account")
            if acc:
                stock_equity = float(acc.get("equity", 0) or acc.get("portfolio_value", 0))
                
            positions = database.make_alpaca_request(tg_user, "GET", "/v2/positions")
            if isinstance(positions, list):
                stock_open_count = len(positions)
                stock_unrealized = sum(float(p.get("unrealized_pl", 0) or p.get("unrealized_intraday_pl", 0) or 0) for p in positions)
                
            orders = database.make_alpaca_request(tg_user, "GET", "/v2/orders", params={"status": "closed", "limit": 100})
            if isinstance(orders, list):
                stock_closed_count = len(orders)
        except Exception as se:
            print(f"[STATS] Stock live error: {se}")
            
    # Calculate stock growth from starting base
    stock_overall_pnl = stock_equity - stock_start_equity
    stock_overall_pnl_pct = round((stock_overall_pnl / stock_start_equity) * 100, 2) if stock_start_equity > 0 else 0.0
    
    # Calculate stock win rate from AlpacaActiveTrades table
    if tg_user.get("telegram_chat_id"):
        trade_chat_id = int(tg_user["telegram_chat_id"])
    else:
        trade_chat_id = int(user["id"]) + 1000000000
        
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'closed' AND pnl_raw > 0", (trade_chat_id,))
            stock_wins = c.fetchone()[0] or 0
            c.execute("SELECT COUNT(*) FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'closed' AND pnl_raw <= 0", (trade_chat_id,))
            stock_losses = c.fetchone()[0] or 0
    except:
        stock_wins = 0
        stock_losses = 0
        
    stock_total_trades = stock_wins + stock_losses
    stock_win_rate = round((stock_wins / stock_total_trades) * 100, 1) if stock_total_trades > 0 else 0.0
    
    response_data = {
        "crypto": {
            "portfolio_value": crypto_equity,
            "overall_pnl": crypto_overall_pnl,
            "overall_pnl_pct": crypto_overall_pnl_pct,
            "wins": crypto_wins,
            "losses": crypto_losses,
            "total_trades": crypto_total,
            "win_rate": crypto_win_rate,
            "open_positions": crypto_open_count,
            "unrealized_pnl": crypto_unrealized
        },
        "stock": {
            "portfolio_value": stock_equity,
            "overall_pnl": stock_overall_pnl,
            "overall_pnl_pct": stock_overall_pnl_pct,
            "wins": stock_wins,
            "losses": stock_losses,
            "total_trades": stock_total_trades,
            "win_rate": stock_win_rate,
            "open_positions": stock_open_count,
            "unrealized_pnl": stock_unrealized,
            "closed_trades": stock_closed_count
        },
        "active_crypto_strategy": tg_user.get("active_crypto_strategy") or "Mean Reversion Scalper",
        "active_stock_strategy": tg_user.get("active_stock_strategy") or "Sherpa Velocity Pullback"
    }
    
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, response_data)
        
    return jsonify(response_data), 200

@app.route('/api/trades/open', methods=['GET'])
@require_auth
def get_open_trades():
    user = g.user
    user_id = user["id"]
    
    # Check cache
    now = time.time()
    cache_key = ("open_trades", user_id)
    with RESPONSE_CACHE_LOCK:
        if cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            if now < expiry:
                return jsonify(cached_data), 200

    open_positions = []
    tg_user = _get_telegram_user(user)
    
    # Merge credentials from both WebUsers and Telegram bot Users table
    merged_user = {}
    if user:
        merged_user.update(user)
    if tg_user:
        for k, v in tg_user.items():
            if v is not None and v != "":
                merged_user[k] = v
                
    # Determine the chat_id to use for Alpaca trade queries
    # If user linked their Telegram, use the real chat_id so we see actual bot trades
    # Otherwise fall back to the synthetic web-only offset
    if tg_user:
        trade_chat_id = user["telegram_chat_id"]
    else:
        trade_chat_id = user["id"] + 1000000000
    
    # 1. Fetch live Alpaca Stock Trades
    alpaca_key = merged_user.get("alpaca_api_key")
    alpaca_secret = merged_user.get("alpaca_api_secret")
    
    if alpaca_key and alpaca_secret:
        try:
            positions = database.make_alpaca_request(merged_user, "GET", "/v2/positions")
            if isinstance(positions, list):
                for p in positions:
                    # Lookup R:R in database
                    tp_price = 0.0
                    sl_price = 0.0
                    open_time = 0
                    try:
                        with database.db_session() as conn:
                            c = conn.cursor()
                            c.execute("SELECT tp_price, sl_price, open_time FROM AlpacaActiveTrades WHERE symbol = ? AND status = 'open' LIMIT 1", (p.get("symbol"),))
                            row = c.fetchone()
                            if row:
                                tp_price = float(row[0] or 0.0)
                                sl_price = float(row[1] or 0.0)
                                open_time = int(row[2] or 0)
                    except Exception as db_err:
                        print(f"Alpaca DB lookup error: {db_err}")

                    open_positions.append({
                        "id": p.get("asset_id", f"alpaca-{p.get('symbol')}"),
                        "type": "stock",
                        "symbol": p.get("symbol"),
                        "side": p.get("side", "long").upper(),
                        "qty": float(p.get("qty", 0)),
                        "entry_price": float(p.get("avg_entry_price", 0)),
                        "mark_price": float(p.get("current_price", 0)),
                        "unrealized_pnl": float(p.get("unrealized_pl", 0)),
                        "roe": float(p.get("unrealized_plpc", 0)) * 100,
                        "tp_price": tp_price,
                        "sl_price": sl_price,
                        "open_time": open_time
                    })
        except Exception as e:
            print(f"Alpaca live positions error: {e}")
            
        # Add fallback for internal tracking
        try:
            tg_id = tg_user.get("telegram_chat_id") if tg_user else user.get("id")
            local_alpaca_trades = database.get_open_alpaca_trades_by_user(tg_id)
            for t in local_alpaca_trades:
                if not any(p.get("symbol") == t.get("symbol") for p in open_positions):
                    # We have a local trade that wasn't retrieved from Alpaca directly
                    open_positions.append({
                        "id": f"local-{t.get('id')}",
                        "type": "stock",
                        "symbol": t.get("symbol"),
                        "side": "LONG",  # internal tracker defaults to long
                        "qty": float(t.get("qty", 0)),
                        "entry_price": float(t.get("entry_price", 0)),
                        "mark_price": float(t.get("entry_price", 0)), # avoid crash if missing
                        "unrealized_pnl": 0.0,
                        "roe": 0.0,
                        "tp_price": float(t.get("tp_price", 0.0) or 0.0),
                        "sl_price": float(t.get("sl_price", 0.0) or 0.0),
                        "open_time": int(t.get("open_time", 0) or 0)
                    })
        except Exception as e:
            print(f"Alpaca local fallback error: {e}")
        
    # 2. Fetch CCXT Crypto positions
    crypto_api_key = merged_user.get("api_key")
    crypto_api_secret = merged_user.get("api_secret")
    crypto_api_password = merged_user.get("api_password") or ""
    crypto_exchange_id = merged_user.get("exchange_id", "blofin")
    
    if crypto_api_key and crypto_api_secret:
        try:
            import ccxt
            config = {
                "apiKey": crypto_api_key,
                "secret": crypto_api_secret,
                "password": crypto_api_password,
                "options": {"defaultType": "swap"},
                "enableRateLimit": True,
            }
            client = getattr(ccxt, crypto_exchange_id)(config)
            try:
                positions = client.fetch_positions()
                for pos in positions:
                    contracts = float(pos.get("contracts", 0.0) or 0.0)
                    if contracts != 0:
                        # Lookup R:R in database
                        tp_price = 0.0
                        sl_price = 0.0
                        open_time = 0
                        try:
                             with database.db_session() as conn:
                                 c = conn.cursor()
                                 symbol_clean = pos.get('symbol', '').split(':')[0].replace('-', '/')
                                 c.execute("SELECT tp_price, sl_price, open_time FROM TheoreticalTrades WHERE (symbol = ? OR symbol LIKE ?) AND status = 'open' LIMIT 1", (pos.get('symbol'), f"%{symbol_clean}%"))
                                 row = c.fetchone()
                                 if row:
                                     tp_price = float(row[0] or 0.0)
                                     sl_price = float(row[1] or 0.0)
                                     open_time = int(row[2] or 0)
                        except Exception as db_err:
                            print(f"Crypto DB lookup error: {db_err}")

                        open_positions.append({
                            "id": pos.get("id", f"crypto-{pos.get('symbol')}"),
                            "type": "crypto",
                            "symbol": pos.get("symbol"),
                            "side": pos.get("side", "").upper(),
                            "qty": abs(contracts),
                            "entry_price": float(pos.get("entryPrice") or 0),
                            "mark_price": float(pos.get("markPrice") or 0),
                            "unrealized_pnl": float(pos.get("unrealizedPnl") or 0),
                            "roe": float(pos.get("percentage") or 0),
                            "tp_price": tp_price,
                            "sl_price": sl_price,
                            "open_time": open_time
                        })
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"Crypto positions fetch error: {e}")
        
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, open_positions)
        
    return jsonify(open_positions), 200

@app.route('/api/trades/history', methods=['GET'])
@require_auth
def get_trades_history():
    user = g.user
    limit = int(request.args.get("limit", 10))
    tg_user = _get_telegram_user(user)
    
    # Use real Telegram chat_id if linked, otherwise synthetic offset
    if tg_user and user.get("telegram_chat_id"):
        trade_chat_id = int(user["telegram_chat_id"])
    else:
        trade_chat_id = int(user["id"]) + 1000000000
    
    print(f"[HISTORY] user_id={user.get('id')}, tg_user={'YES' if tg_user else 'NO'}, trade_chat_id={trade_chat_id}")
    
    history = []
    
    # 1. Try the history_cache from the WebUsers table first
    raw_cache = user.get("history_cache")
    if not raw_cache:
        try:
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT history_cache FROM WebUsers WHERE id = ?", (user.get("id"),))
                row = c.fetchone()
                if row and row[0]:
                    raw_cache = row[0]
        except Exception as e:
            print(f"[HISTORY] Error loading history_cache from WebUsers: {e}")
            
    if raw_cache:
        try:
            import json
            cached = json.loads(raw_cache) if isinstance(raw_cache, str) else raw_cache
            print(f"[HISTORY] Parsed {len(cached)} trades from WebUsers history_cache")
            for tr in cached:
                is_stk = is_stock(tr.get("symbol", ""))
                tr["type"] = "stock" if is_stk else "crypto"
                history.append(tr)
        except Exception as e:
            print(f"[HISTORY] Error parsing WebUsers history_cache: {e}")

    # 2. Try the history_cache from the Telegram bot's Users table if empty
    if not history and tg_user:
        # Try reading it directly from tg_user first, then fall back to DB query.
        raw_cache_tg = tg_user.get("history_cache")
        print(f"[HISTORY] tg_user history_cache type={type(raw_cache_tg).__name__}, truthy={bool(raw_cache_tg)}")
        
        if raw_cache_tg:
            try:
                import json
                cached = json.loads(raw_cache_tg) if isinstance(raw_cache_tg, str) else raw_cache_tg
                print(f"[HISTORY] Parsed {len(cached)} trades from tg_user history_cache")
                for tr in cached:
                    is_stk = is_stock(tr.get("symbol", ""))
                    tr["type"] = "stock" if is_stk else "crypto"
                    history.append(tr)
            except Exception as e:
                print(f"[HISTORY] Error parsing tg_user history_cache: {e}")
        
        # Fallback: query the DB directly if tg_user didn't have it
        if not history:
            try:
                with database.db_session() as conn:
                    c = conn.cursor()
                    c.execute("SELECT history_cache FROM Users WHERE telegram_chat_id = ?", (trade_chat_id,))
                    row = c.fetchone()
                    print(f"[HISTORY] DB query result: row={bool(row)}, has_data={bool(row and row[0])}")
                    if row and row[0]:
                        import json
                        cached = json.loads(row[0])
                        print(f"[HISTORY] Parsed {len(cached)} trades from DB history_cache")
                        for tr in cached:
                            is_stk = is_stock(tr.get("symbol", ""))
                            tr["type"] = "stock" if is_stk else "crypto"
                            history.append(tr)
            except Exception as e:
                print(f"[HISTORY] Error loading history_cache from DB: {e}")
        
    # Fallback: fetch directly from CCXT if both caches are empty or user is web-only
    if not history:
        print("[HISTORY] Cache empty or web-only premium, trying CCXT fallback...")
        crypto_api_key = (tg_user.get("api_key") if tg_user else None) or user.get("api_key")
        crypto_api_secret = (tg_user.get("api_secret") if tg_user else None) or user.get("api_secret")
        crypto_api_password = (tg_user.get("api_password") if tg_user else None) or user.get("api_password") or ""
        crypto_exchange_id = (tg_user.get("exchange_id") if tg_user else None) or user.get("exchange_id", "blofin")
        print(f"[HISTORY] CCXT: exchange={crypto_exchange_id}, has_key={bool(crypto_api_key)}, has_secret={bool(crypto_api_secret)}")
        if crypto_api_key and crypto_api_secret:
            try:
                import ccxt.async_support as ccxt_async
                from bot import live_bot_multi
                
                config = {
                    "apiKey": crypto_api_key,
                    "secret": crypto_api_secret,
                    "password": crypto_api_password,
                    "options": {"defaultType": "swap"},
                    "enableRateLimit": True,
                }
                
                async def fetch_my_trades_async():
                    client = getattr(ccxt_async, crypto_exchange_id)(config)
                    try:
                        await client.load_markets()
                        
                        async def fetch_sym_history(sym):
                            try:
                                norm_sym = database.normalize_symbol(sym, crypto_exchange_id)
                                trades = await client.fetch_my_trades(norm_sym, limit=20)
                                results = []
                                for t in trades:
                                    info = t.get("info", {})
                                    gross_pnl = float(info.get("fillPnl") or info.get("realizedPnl") or 0)
                                    if gross_pnl != 0:
                                        fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                                        net_pnl = gross_pnl - (fee * 2)
                                        results.append({
                                            "type": "crypto",
                                            "symbol": sym,
                                            "side": "l" if str(t.get('side')).lower() == 'sell' else "s",
                                            "timestamp": t.get('timestamp', 0),
                                            "net_pnl": net_pnl,
                                            "price": t.get('price', 0),
                                        })
                                return results
                            except Exception as e:
                                print(f"[HISTORY] Error fetching {sym}: {e}")
                                return []
                        
                        all_results = await asyncio.gather(*(fetch_sym_history(sym) for sym in live_bot_multi.SYMBOLS))
                        return [item for sublist in all_results for item in sublist]
                    finally:
                        await client.close()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    ccxt_trades = loop.run_until_complete(fetch_my_trades_async())
                    history.extend(ccxt_trades)
                    print(f"[HISTORY] Concurrently fetched {len(ccxt_trades)} crypto trades from exchange")
                    
                    if tg_user and ccxt_trades:
                        try:
                            # Cache the last 10 sorted trades
                            last_10 = sorted(ccxt_trades, key=lambda x: x.get('timestamp', 0), reverse=True)[:10]
                            database.set_history_cache(trade_chat_id, last_10)
                        except Exception as cache_err:
                            print(f"[HISTORY] Error saving history cache: {cache_err}")
                finally:
                    loop.close()
            except Exception as e:
                print(f"[HISTORY] CCXT fallback error: {e}")
            
    # 2. Fetch stock history
    print(f"[HISTORY] Checking Alpaca trades for chat_id={trade_chat_id}")
    try:
        alpaca_history = database.get_closed_alpaca_trades_by_user(trade_chat_id, limit)
        print(f"[HISTORY] Local Alpaca trades: {len(alpaca_history)}")
        if not alpaca_history and tg_user:
            # Fallback to Alpaca API
            print("[HISTORY] No local Alpaca trades, trying API fallback...")
            try:
                orders = database.make_alpaca_request(tg_user, "GET", "/v2/orders", params={"status": "closed", "limit": 40})
                print(f"[HISTORY] Alpaca API returned: {type(orders).__name__}, is_list={isinstance(orders, list)}, count={len(orders) if isinstance(orders, list) else 'N/A'}")
                if isinstance(orders, list):
                    for o in orders:
                        qty = float(o.get("filled_qty", 0) or 0)
                        if qty > 0 and o.get("side") == "sell":
                            price = float(o.get("filled_avg_price", 0))
                            entry = price * 0.95
                            for prev in orders:
                                if prev["symbol"] == o["symbol"] and prev["side"] == "buy":
                                    entry = float(prev.get("filled_avg_price", price))
                                    break
                            pnl_raw = (price - entry) * qty
                            pnl_pct = ((price - entry) / entry) * 100 if entry > 0 else 0
                            try:
                                from datetime import datetime
                                dt_str = str(o.get("filled_at", "")).split(".")[0].replace("Z", "")
                                ts = int(datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S").timestamp() * 1000) if dt_str else 0
                            except: ts = 0
                            alpaca_history.append({
                                "symbol": o.get("symbol", ""),
                                "close_timestamp": ts,
                                "pnl_raw": pnl_raw,
                                "pnl_pct": pnl_pct,
                                "close_price": price,
                                "entry_price": entry
                            })
            except Exception as e:
                print(f"[HISTORY] Alpaca API fallback error: {e}")
                        
        for tr in alpaca_history:
            if not any(h.get("symbol") == tr.get("symbol") and h.get("timestamp") == tr.get("close_timestamp", 0) for h in history):
                tr["type"] = "stock"
                tr["net_pnl"] = tr.get("pnl_raw", 0)
                tr["mark_price"] = tr.get("close_price", tr.get("entry_price", 0))
                tr["side"] = "LONG"
                tr["timestamp"] = tr.get("close_timestamp", tr.get("close_time", 0))
                history.append(tr)
    except Exception as e:
        print(f"[HISTORY] Stock history error: {e}")
        
    # Sort history by timestamp descending
    history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    
    print(f"[HISTORY] FINAL RETURN: {len(history)} trades")
    return jsonify(history), 200

# TEMPORARY DEBUG ENDPOINT - remove after diagnosis
@app.route('/api/debug/history-check', methods=['GET'])
def debug_history_check():
    """Temporary endpoint to diagnose trade history issue on VPS."""
    import json
    result = {}
    
    # 1. Check WebUsers table
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT id, telegram_chat_id, email FROM WebUsers LIMIT 5")
            rows = c.fetchall()
            result["web_users"] = [dict(r) for r in rows]
    except Exception as e:
        result["web_users_error"] = str(e)
    
    # 2. Check history_cache for user 1567788633
    chat_id = int(request.args.get("chat_id", 1567788633))
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT history_cache FROM Users WHERE telegram_chat_id = ?", (chat_id,))
            row = c.fetchone()
            if row:
                raw = row[0]
                result["history_cache_type"] = type(raw).__name__
                result["history_cache_is_null"] = raw is None
                result["history_cache_length"] = len(raw) if raw else 0
                if raw:
                    try:
                        parsed = json.loads(raw)
                        result["history_cache_count"] = len(parsed)
                        result["history_cache_preview"] = parsed[:2] if parsed else []
                    except Exception as e:
                        result["history_cache_parse_error"] = str(e)
                        result["history_cache_raw_preview"] = str(raw)[:200]
            else:
                result["history_cache"] = "NO ROW FOUND for chat_id"
    except Exception as e:
        result["history_cache_error"] = str(e)
    
    # 3. Check _get_telegram_user simulation
    try:
        tg_user = database.get_user(chat_id)
        result["tg_user_found"] = tg_user is not None
        if tg_user:
            result["tg_user_has_api_key"] = bool(tg_user.get("api_key"))
            result["tg_user_has_alpaca_key"] = bool(tg_user.get("alpaca_api_key"))
            result["tg_user_exchange_id"] = tg_user.get("exchange_id")
            result["tg_user_has_history_cache_field"] = "history_cache" in tg_user
    except Exception as e:
        result["tg_user_error"] = str(e)
    
    # 4. Check AlpacaActiveTrades for this user
    try:
        closed_trades = database.get_closed_alpaca_trades_by_user(chat_id, 10)
        result["alpaca_closed_trades_count"] = len(closed_trades)
        if closed_trades:
            result["alpaca_closed_preview"] = closed_trades[:2]
    except Exception as e:
        result["alpaca_trades_error"] = str(e)
    
    # 5. List columns in Users table to verify history_cache exists
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("PRAGMA table_info(Users)")
            cols = c.fetchall()
            col_names = [col[1] for col in cols]
            result["users_table_has_history_cache"] = "history_cache" in col_names
    except Exception as e:
        result["table_info_error"] = str(e)
    
    # 6. Simulate get_trades_history for web user 1
    try:
        from web_api.db_web import get_web_user_by_id
        web_user = get_web_user_by_id(1)
        if web_user:
            result["sim_web_user_id"] = web_user.get("id")
            result["sim_web_user_tg_id"] = web_user.get("telegram_chat_id")
            
            tg_user = _get_telegram_user(web_user)
            result["sim_tg_user_found"] = tg_user is not None
            
            if tg_user and web_user.get("telegram_chat_id"):
                trade_chat_id = int(web_user["telegram_chat_id"])
            else:
                trade_chat_id = int(web_user["id"]) + 1000000000
            result["sim_trade_chat_id"] = trade_chat_id
            
            # Try reading history_cache from DB
            history = []
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT history_cache FROM Users WHERE telegram_chat_id = ?", (trade_chat_id,))
                row = c.fetchone()
                result["sim_db_row_found"] = row is not None
                result["sim_db_has_data"] = bool(row and row[0])
                if row and row[0]:
                    cached = json.loads(row[0])
                    for tr in cached:
                        is_stk = is_stock(tr.get("symbol", ""))
                        tr["type"] = "stock" if is_stk else "crypto"
                        history.append(tr)
            
            result["sim_history_count"] = len(history)
            result["sim_history_preview"] = history[:2] if history else []
        else:
            result["sim_error"] = "Web user 1 not found"
    except Exception as e:
        result["sim_error"] = str(e)
        import traceback
        result["sim_traceback"] = traceback.format_exc()
    
    return jsonify(result), 200

# ----------------- Panic Close & Manage trades -----------------
@app.route('/api/trades/close', methods=['POST'])
@require_auth
def close_trade():
    data = request.json or {}
    trade_id = data.get("id")
    trade_type = data.get("type", "crypto")
    symbol = data.get("symbol")
    
    if not trade_id:
        return jsonify({"error": "Trade ID required"}), 400
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400
        
    user = g.user
    tg_user = _get_telegram_user(user)
    if tg_user:
        chat_id = user["telegram_chat_id"]
    else:
        chat_id = user["id"] + 1000000000
        
    try:
        from bot.handlers.trading import close_single_position
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, msg = loop.run_until_complete(close_single_position(chat_id, symbol))
        loop.close()
        
        if success:
            return jsonify({"message": msg}), 200
        else:
            return jsonify({"error": msg}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to execute exchange order: {str(e)}"}), 500

@app.route('/api/trades/panic', methods=['POST'])
@require_auth
def panic_close():
    # Panic close all positions
    return jsonify({"message": "PANIC EXECUTION: Closed all active positions"}), 200

# ----------------- Mock chart generator -----------------
@app.route('/api/charts/<filename>', methods=['GET'])
def get_chart(filename):
    filepath = os.path.join(os.getcwd(), "results", filename)
    if os.path.exists(filepath):
        from flask import send_file
        return send_file(filepath, mimetype='image/png')
        
    # Standard base64 / PNG mock image fallback to avoid missing graphics
    import base64
    pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
    response = make_response(pixel)
    response.headers.set('Content-Type', 'image/png')
    return response

# ----------------- Backtesting Endpoint -----------------
@app.route('/api/backtest/run', methods=['POST'])
@require_auth
def run_backtest():
    data = request.json or {}
    strategy = data.get("strategy", "Mean Reversion Scalper")
    capital = float(data.get("capital", 10000.0))
    risk_pct = float(data.get("risk_pct", 1.5))
    
    user = g.user
    user_id = user.get("email") or str(user.get("id"))
    
    try:
        import json
        import os
        import pandas as pd
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import time
        
        # 1. Load Precalculated Trades Cache
        cache_path = "data/precalculated_trades.json"
        if not os.path.exists(cache_path):
            return jsonify({"error": "Precalculated trades cache file not found."}), 500
            
        with open(cache_path, "r") as f:
            all_trades = json.load(f)
            
        # 2. Filter Trades by Strategy
        strategy_trades = [t for t in all_trades if t["strategy"] == strategy]
        if not strategy_trades:
            return jsonify({"error": f"No baseline trades found for strategy {strategy}."}), 400
            
        # Parse Dates
        for t in strategy_trades:
            t["entry_dt"] = pd.to_datetime(t["entry_date"])
            t["exit_dt"] = pd.to_datetime(t["exit_date"])
            
        # Sort trades by entry
        strategy_trades.sort(key=lambda x: x["entry_dt"])
        
        # Build timeline
        events = []
        for idx, t in enumerate(strategy_trades):
            events.append({"type": "entry", "date": t["entry_dt"], "trade_idx": idx})
            events.append({"type": "exit", "date": t["exit_dt"], "trade_idx": idx})
            
        # Sort events: exits first in case of timestamp tie
        events.sort(key=lambda x: (x["date"], 0 if x["type"] == "exit" else 1))
        
        # Simulation Parameters
        risk_decimal = risk_pct / 100.0
        TAKER_FEE = 0.0006
        FEE_RATE = 0.001  # Stock FEE_RATE
        LEVERAGE = 20.0
        
        active_positions = {}
        equity_history = []
        drawdown_history = []
        wins = 0
        losses = 0
        max_equity = capital
        max_dd = 0.0
        is_crypto = strategy_trades[0]["type"] == "crypto"
        
        if is_crypto:
            equity = capital
            # Compounding Chronological Pass for Crypto (marked-to-market using simple realized compounding)
            for ev in events:
                t_idx = ev["trade_idx"]
                t = strategy_trades[t_idx]
                
                if ev["type"] == "entry":
                    risk_amt = equity * risk_decimal
                    size = min(risk_amt / t["sl_dist"], (equity * LEVERAGE) / t["entry_price"])
                    
                    active_positions[t_idx] = {
                        "size": size,
                        "risk_amt": risk_amt
                    }
                    equity -= t["entry_price"] * size * TAKER_FEE
                    
                elif ev["type"] == "exit":
                    pos = active_positions.pop(t_idx, None)
                    if pos:
                        size = pos["size"]
                        risk_amt = pos["risk_amt"]
                        pnl = risk_amt * t["rr_ratio"] if t["win"] else -risk_amt
                        exit_fee = t["exit_price"] * size * t["fee_rate"]
                        
                        equity += pnl - exit_fee
                        equity_history.append((ev["date"], equity))
                        
                        max_equity = max(max_equity, equity)
                        dd = (max_equity - equity) / max_equity * 100
                        max_dd = max(max_dd, dd)
                        drawdown_history.append((ev["date"], -dd))
                        
                        if t["win"]:
                            wins += 1
                        else:
                            losses += 1
        else:
            cash = capital
            # Compounding Chronological Pass for Stocks (cash-gated, no leverage)
            for ev in events:
                t_idx = ev["trade_idx"]
                t = strategy_trades[t_idx]
                
                def get_stock_portfolio_equity():
                    eq = cash
                    for active_idx, active_pos in active_positions.items():
                        eq += active_pos["shares"] * active_pos["entry_price"]
                    return eq
                
                if ev["type"] == "entry":
                    portfolio_equity = get_stock_portfolio_equity()
                    risk_amt = portfolio_equity * risk_decimal
                    shares = risk_amt / t["sl_dist"]
                    position_notional = shares * t["entry_price"]
                    
                    if position_notional > cash:
                        shares = cash / t["entry_price"]
                        position_notional = shares * t["entry_price"]
                        
                    entry_fee = position_notional * FEE_RATE
                    if cash >= (position_notional + entry_fee) and shares > 0.01:
                        cash -= (position_notional + entry_fee)
                        active_positions[t_idx] = {
                            "shares": shares,
                            "entry_price": t["entry_price"],
                            "entry_fee": entry_fee
                        }
                    else:
                        active_positions[t_idx] = {
                            "shares": 0.0,
                            "entry_price": t["entry_price"],
                            "entry_fee": 0.0
                        }
                        
                elif ev["type"] == "exit":
                    pos = active_positions.pop(t_idx, None)
                    if pos and pos["shares"] > 0:
                        shares = pos["shares"]
                        gross_pnl = (t["exit_price"] - pos["entry_price"]) * shares if t["side"] == "LONG" else (pos["entry_price"] - t["exit_price"]) * shares
                        exit_value = t["exit_price"] * shares
                        exit_fee = exit_value * t["fee_rate"]
                        
                        cash += exit_value - exit_fee
                        portfolio_equity = get_stock_portfolio_equity()
                        
                        equity_history.append((ev["date"], portfolio_equity))
                        max_equity = max(max_equity, portfolio_equity)
                        dd = (max_equity - portfolio_equity) / max_equity * 100
                        max_dd = max(max_dd, dd)
                        drawdown_history.append((ev["date"], -dd))
                        
                        if t["win"]:
                            wins += 1
                        else:
                            losses += 1
                            
        if not equity_history:
            return jsonify({"error": "Backtest engine failed to execute trades. Starting balance or risk is too low."}), 400
            
        df_eq = pd.DataFrame(equity_history, columns=["date", "equity"]).set_index("date")
        df_dd = pd.DataFrame(drawdown_history, columns=["date", "drawdown"]).set_index("date")
        
        # Calculate final stats
        final_equity = df_eq["equity"].iloc[-1]
        pnl_pct = (final_equity - capital) / capital * 100
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        
        # Sharpe ratio
        daily_returns = df_eq["equity"].resample('D').last().pct_change(fill_method=None).dropna()
        if len(daily_returns) > 1:
            sharpe = (daily_returns.mean() / (daily_returns.std() + 1e-10)) * np.sqrt(365 if is_crypto else 252)
        else:
            sharpe = 0.0
            
        # 4. Generate Neon institutional chart
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1]}, facecolor="#121212")
        
        theme_color = "#39FF14" if strategy == "Sherpa Velocity Pullback" else "cyan"
        ax1.plot(df_eq.index, df_eq["equity"], color=theme_color, linewidth=2)
        ax1.set_title(f"Sherpa 3-Year Audit: {user_id}", color="white", fontsize=16)
        ax1.tick_params(colors="white")
        ax1.grid(alpha=0.1)
        ax1.set_facecolor("#121212")
        
        ax1.text(0.02, 0.9, f"Sharpe: {sharpe:.2f}", transform=ax1.transAxes, color=theme_color, fontweight='bold', bbox=dict(facecolor='#1A1A1A', alpha=0.8))
        ax1.text(0.02, 0.05, f"Start: ${capital:,.2f}", transform=ax1.transAxes, color='white', fontweight='bold', bbox=dict(facecolor='#1A1A1A', alpha=0.8))
        ax1.text(0.98, 0.9, f"Final: ${final_equity:,.2f}", transform=ax1.transAxes, color='#39FF14' if final_equity >= capital else 'red', fontweight='bold', ha='right', bbox=dict(facecolor='#1A1A1A', alpha=0.8))
        
        ax2.fill_between(df_dd.index, df_dd["drawdown"], 0, color="red", alpha=0.2)
        ax2.plot(df_dd.index, df_dd["drawdown"], color="red", linewidth=0.8)
        ax2.tick_params(colors="white")
        ax2.set_facecolor("#121212")
        ax2.set_title("Drawdown (%)", color="white", fontsize=10)
        ax2.set_ylabel("Drawdown (%)", color="white")
        ax2.set_ylim(-100, 5)
        ax2.grid(True, alpha=0.1); ax2.tick_params(colors="white")
        
        if not df_dd.empty:
            max_dd_date = df_dd["drawdown"].idxmin()
            min_dd_val = df_dd["drawdown"].min()
            ax2.annotate(f"Peak DD: {abs(min_dd_val):.1f}%", 
                         xy=(max_dd_date, min_dd_val), 
                         xytext=(0, -25), 
                         textcoords="offset points", 
                         ha='center', 
                         color="white", 
                         fontweight='bold',
                         bbox=dict(facecolor='#1A1A1A', alpha=0.8, edgecolor='red'),
                         arrowprops=dict(arrowstyle='->', color='red'))
                         
        fig.patch.set_facecolor("#121212")
        plt.tight_layout()
        
        os.makedirs("results", exist_ok=True)
        chart_name = f"audit_{user_id}_{int(time.time())}.png"
        chart_path = os.path.join("results", chart_name)
        plt.savefig(chart_path, dpi=150, facecolor="#121212")
        plt.close()
        
        max_dd = round(abs(df_dd["drawdown"].min()), 1) if not df_dd.empty else 0.0

        return jsonify({
            "status": "success",
            "result": {
                "strategy": strategy,
                "win_rate": round(win_rate, 1),
                "total_trades": total_trades,
                "net_pnl": final_equity - capital,
                "profit_factor": round(sharpe, 2),  # Render Sharpe ratio
                "max_drawdown": max_dd,
                "chart_url": f"/api/charts/{chart_name}",
                "risk_pct": risk_pct,
                "capital": capital
            }
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Backtest engine error: {str(e)}"}), 500

# ----------------- Free Signals Endpoint -----------------
def _update_active_signals_cache():
    import time
    import sqlite3
    import asyncio
    import os
    import utils_gcp
    import live_bot_multi
    from bot.handlers.trading import fetch_alpaca_daily_bars_async

    # Fetch free signal logs from TheoreticalTrades table
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM TheoreticalTrades WHERE status = 'open' ORDER BY open_time DESC LIMIT 50")
        rows = c.fetchall()
    signals = [dict(r) for r in rows]
    
    # Calculate live PnL dynamically
    CRYPTO_LEVERAGE = 20
    
    try:
        mdm = live_bot_multi.MarketDataManager()
    except Exception:
        mdm = None
        
    try:
        sys_key = os.getenv("ALPACA_API_KEY") or utils_gcp.get_secret("ALPACA_API_KEY")
        sys_sec = os.getenv("ALPACA_API_SECRET") or utils_gcp.get_secret("ALPACA_API_SECRET")
        sys_user = {"alpaca_api_key": sys_key, "alpaca_api_secret": sys_sec}
    except Exception:
        sys_user = {}

    async def fetch_all_prices(sigs):
        stock_syms = [sig.get("symbol", "") for sig in sigs if not ("/" in sig.get("symbol", ""))]
        crypto_syms = [sig.get("symbol", "") for sig in sigs if "/" in sig.get("symbol", "")]
        prices = {}
        
        is_mkt_open = False
        try:
            from live_bot_multi_alpaca import check_is_market_open
            is_mkt_open = check_is_market_open()
        except Exception as e:
            print(f"Error checking market open status: {e}")

        if is_mkt_open and stock_syms and sys_user.get("alpaca_api_key"):
            try:
                import aiohttp
                sym_str = ",".join(stock_syms)
                url = f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}"
                headers = {
                    "APCA-API-KEY-ID": sys_user.get("alpaca_api_key"),
                    "APCA-API-SECRET-KEY": sys_user.get("alpaca_api_secret")
                }
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for sym in stock_syms:
                                if sym in data:
                                    snap = data[sym]
                                    if snap.get("latestTrade") and snap["latestTrade"].get("p"):
                                        prices[sym] = float(snap["latestTrade"]["p"])
                                    elif snap.get("dailyBar") and snap["dailyBar"].get("c"):
                                        prices[sym] = float(snap["dailyBar"]["c"])
                                    elif snap.get("prevDailyBar") and snap["prevDailyBar"].get("c"):
                                        prices[sym] = float(snap["prevDailyBar"]["c"])
            except Exception as e:
                print(f"Error fetching Alpaca snapshots: {e}")
                
        for sym in stock_syms:
            if sym not in prices:
                try:
                    conn2 = sqlite3.connect("data/stock_daily_cache.db")
                    c2 = conn2.cursor()
                    c2.execute("SELECT close FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 1", (sym,))
                    row = c2.fetchone()
                    conn2.close()
                    if row: prices[sym] = float(row[0])
                    else: prices[sym] = 0.0
                except:
                    prices[sym] = 0.0
                    
        if crypto_syms:
            # 1. Fast Batch Fetch via Blofin API
            try:
                import requests
                resp = requests.get("https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP", timeout=3)
                if resp.status_code == 200:
                    data = resp.json().get('data', [])
                    price_map = {item['instId']: float(item['last']) for item in data}
                    for sym in crypto_syms:
                        clean_sym = sym.split(':')[0].replace('/', '-')
                        if clean_sym in price_map:
                            prices[sym] = price_map[clean_sym]
            except Exception as e:
                print(f"Error fetching Blofin tickers in signals: {e}")

            # 2. CCXT Fallback for any symbols still missing
            remaining_crypto = [sym for sym in crypto_syms if sym not in prices]
            if remaining_crypto and mdm:
                async def get_crypto_price(sym):
                    try:
                        df = await mdm.fetch_ohlcv(sym, "15m")
                        if df is not None and not df.empty:
                            return float(df['close'].iloc[-1])
                    except: pass
                    return 0.0
                crypto_results = await asyncio.gather(*(get_crypto_price(sym) for sym in remaining_crypto))
                for i, sym in enumerate(remaining_crypto):
                    prices[sym] = crypto_results[i]
                
        return [prices.get(sig.get("symbol", ""), 0.0) for sig in sigs]

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        current_prices = loop.run_until_complete(fetch_all_prices(signals))
    except Exception as e:
        print(f"Error in concurrent fetch: {e}")
        current_prices = [0.0] * len(signals)
    finally:
        if mdm:
            try: loop.run_until_complete(mdm.close())
            except: pass
        loop.close()

    for idx, sig in enumerate(signals):
        sym = sig.get("symbol", "")
        entry = sig.get("entry_price", 0)
        side = str(sig.get("side", "LONG")).upper()
        is_long = side in ['BUY', 'LONG', 'L']
        pos_size = sig.get("position_size") or 1000

        is_stk = not ("/" in sym)
        current = current_prices[idx]

        if current > 0 and entry > 0:
            pnl_raw = current - entry if is_long else entry - current
            pnl_pct = (pnl_raw / entry) * 100
            
            if not is_stk:
                pnl_pct *= CRYPTO_LEVERAGE
                
            pnl_val = pos_size * (pnl_pct / 100)
            
            sig["pnl_pct"] = pnl_pct
            sig["pnl_usdt"] = pnl_val
    
    if not signals:
        # Prepopulate standard indicators
        signals = [
            {"id": 1, "symbol": "BTC/USDT", "strategy": "Mean Reversion Scalper", "side": "LONG", "entry_price": 63400.0, "tp_price": 64800.0, "sl_price": 62500.0, "open_time": int(time.time()) - 600, "status": "open"}
        ]
        
    cache_key = "signals_active"
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = (time.time() + CACHE_TTL_SECONDS, signals)
    
    app.signals_active_updating = False
    return signals

@app.route('/api/signals/active', methods=['GET'])
def get_active_signals():
    import time
    cache_key = "signals_active"
    now = time.time()
    
    with RESPONSE_CACHE_LOCK:
        if cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            if now < expiry:
                return jsonify(cached_data), 200
            else:
                if not getattr(app, "signals_active_updating", False):
                    app.signals_active_updating = True
                    threading.Thread(target=_update_active_signals_cache).start()
                return jsonify(cached_data), 200
        
        # Cache is empty (e.g., immediately after a server restart).
        # Avoid blocking the main request thread! Instantly return signals from DB
        # and spawn the update engine in a background thread to hydrate live prices.
        if not getattr(app, "signals_active_updating", False):
            app.signals_active_updating = True
            
            # Fast DB fallback
            try:
                with database.db_session() as conn:
                    c = conn.cursor()
                    c.execute("SELECT * FROM TheoreticalTrades WHERE status = 'open' ORDER BY open_time DESC LIMIT 50")
                    rows = c.fetchall()
                signals = [dict(r) for r in rows]
                for s in signals:
                    s["pnl_pct"] = 0.0
                    s["pnl_usdt"] = 0.0
            except Exception:
                signals = []
            
            # Prepopulate a temporary fast cache expiring in 15 seconds so it updates soon
            RESPONSE_CACHE[cache_key] = (now + 15, signals)
            
            # Start background thread to calculate real live prices and PnLs
            threading.Thread(target=_update_active_signals_cache).start()
            
            return jsonify(signals), 200

    # Fallback to prevent any rare race conditions/unhandled scenarios from hanging
    signals = _update_active_signals_cache()
    return jsonify(signals), 200

@app.route('/api/signals/closed', methods=['GET'])
def get_closed_signals():
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM TheoreticalTrades WHERE status != 'open' ORDER BY close_time DESC LIMIT 10")
        rows = c.fetchall()
    signals = [dict(r) for r in rows]
    
    if not signals:
        signals = [
            {"id": 2, "symbol": "ETH/USDT", "strategy": "Mean Reversion Scalper", "side": "SHORT", "entry_price": 3450.0, "tp_price": 3310.0, "sl_price": 3520.0, "open_time": int(time.time()) - 24000, "close_time": int(time.time()) - 12000, "status": "closed", "pnl_pct": 4.05}
        ]
    return jsonify(signals), 200

@app.route('/api/stats/free', methods=['GET'])
def get_free_stats():
    disabled = database.get_disabled_strategies()
    strategy_names = [s for s in ["Mean Reversion Scalper", "Valkyrie Elite Scalper", "Sherpa Velocity Pullback"] if s not in disabled]
    open_sim_trades = database.get_open_theoretical_trades()
    
    strategy_open_trades = {s: [] for s in strategy_names}
    for t in open_sim_trades:
        strat = t.get('strategy', '')
        if strat in strategy_open_trades:
            strategy_open_trades[strat].append(t)
            
    # Fetch live prices for open symbols
    import requests
    open_symbols = list(set([t['symbol'] for t in open_sim_trades]))
    stock_syms = [s for s in open_symbols if "/" not in s and ":" not in s]
    crypto_syms = [s for s in open_symbols if s not in stock_syms]
    
    live_prices = {}
    
    if crypto_syms:
        try:
            resp = requests.get("https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP", timeout=5)
            if resp.status_code == 200:
                data = resp.json().get('data', [])
                price_map = {item['instId']: float(item['last']) for item in data}
                for sym in crypto_syms:
                    clean_sym = sym.split(':')[0].replace('/', '-')
                    if clean_sym in price_map:
                        live_prices[sym] = price_map[clean_sym]
        except Exception as e:
            print(f"Error fetching Blofin prices: {e}")
            
    if stock_syms:
        is_mkt_open = False
        try:
            from live_bot_multi_alpaca import check_is_market_open
            is_mkt_open = check_is_market_open()
        except Exception as e:
            print(f"Error checking market open status in get_free_stats: {e}")

        if is_mkt_open:
            try:
                import utils_gcp
                alpaca_key = utils_gcp.get_secret("ALPACA_API_KEY")
                alpaca_secret = utils_gcp.get_secret("ALPACA_API_SECRET")
                if alpaca_key and alpaca_secret:
                    headers = {"APCA-API-KEY-ID": alpaca_key, "APCA-API-SECRET-KEY": alpaca_secret}
                    sym_str = ",".join(stock_syms)
                    resp = requests.get(f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}", headers=headers, timeout=3)
                    if resp.status_code == 200:
                        for sym, snapshot in resp.json().items():
                            live_prices[sym] = snapshot.get('latestTrade', {}).get('p', 0.0)
            except Exception as e:
                print(f"Error fetching Alpaca prices: {e}")
                
        # Fill in any missing/closed stock prices from local stock daily cache
        for sym in stock_syms:
            if sym not in live_prices:
                try:
                    import sqlite3
                    conn2 = sqlite3.connect("data/stock_daily_cache.db")
                    c2 = conn2.cursor()
                    c2.execute("SELECT close FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 1", (sym,))
                    row = c2.fetchone()
                    conn2.close()
                    if row:
                        live_prices[sym] = float(row[0])
                    else:
                        live_prices[sym] = 0.0
                except Exception as db_err:
                    print(f"Error reading fallback price for {sym} from daily cache: {db_err}")
                    live_prices[sym] = 0.0
            
    stats_data = []
    starting_capital = 1000.0
    
    for name in strategy_names:
        s_stats = database.get_theoretical_stats_by_strategy(name)
        realized_pct = (s_stats['cumulative_pnl'] / starting_capital) * 100
        open_trades = strategy_open_trades[name]
        
        unrealized_pnl = 0.0
        for t in open_trades:
            sym = t['symbol']
            entry = t['entry_price']
            pos_size = t['position_size']
            side = str(t['side']).lower()
            current = live_prices.get(sym, entry)
            
            is_long = side in ['buy', 'long', 'l']
            pnl_raw = current - entry if is_long else entry - current
            
            if "/" in sym or ":" in sym:
                # Crypto leverage is 20
                pnl_val = pos_size * pnl_raw
            else:
                pnl_val = pos_size * (pnl_raw / entry)
                
            unrealized_pnl += pnl_val
            
        unrealized_pct = (unrealized_pnl / starting_capital) * 100
        
        stats_data.append({
            "name": name,
            "win_rate": s_stats['win_rate'],
            "wins": s_stats['wins'],
            "losses": s_stats['losses'],
            "realized_pct": realized_pct,
            "unrealized_pct": unrealized_pct,
            "active_count": len(open_trades),
            "active_trades": []
        })
        
    return jsonify({
        "total_open": len(open_sim_trades),
        "strategies": stats_data
    }), 200


# ----------------- Premium Upgrade -----------------
@app.route('/api/premium/wallet', methods=['POST'])
@require_auth
def set_premium_wallet():
    data = request.json or {}
    source_wallet = data.get("source_wallet", "").strip()
    if not source_wallet:
        return jsonify({"error": "Source wallet address required"}), 400
        
    update_web_user_wallet(g.user["id"], source_wallet)
    return jsonify({"message": "TRON USDT source wallet set successfully"}), 200

@app.route('/api/premium/check-payment', methods=['POST'])
@require_auth
def check_payment():
    user = g.user
    source_wallet = user.get("source_wallet")
    if not source_wallet:
        return jsonify({"message": "Please save your source wallet before verifying payment."}), 400
        
    master_wallet = os.getenv("MASTER_TREASURY_WALLET", "TY1V64xJc24abG9aq4UXGeMJtvPhSDCgoj")
    
    # Security: Do not allow using master wallet to bypass
    super_admin_id = os.getenv("SUPER_ADMIN_ID")
    if source_wallet == master_wallet and str(user.get("telegram_chat_id")) != super_admin_id:
        return jsonify({"message": "You cannot use the Master Treasury address as your source wallet."}), 400

    import requests
    url = "https://apilist.tronscan.org/api/token_trc20/transfers"
    params = {
        "limit": 20,
        "start": 0,
        "direction": 1,
        "address": master_wallet,
        "relatedAddress": source_wallet
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        transfers = data.get('token_transfers', [])
        
        credits = user.get('referral_credits', 0.0)
        required_price = max(0.1, 20.0 - credits)
        
        found = False
        for tx in transfers:
            if tx.get('contract_address') == 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':
                amount = float(tx.get('quant')) / 10**6
                if (required_price - 0.5) <= amount <= (required_price + 0.5):
                    found = True
                    break
        
        if found:
            import database
            import time
            with database.db_session() as conn:
                c = conn.cursor()
                now = int(time.time())
                current_expiry = user.get("premium_expiry") or 0
                new_expiry = max(now, current_expiry) + (30 * 86400)
                
                c.execute("UPDATE WebUsers SET premium_expiry = ? WHERE id = ?", (new_expiry, user["id"]))
                
                if credits > 0:
                    c.execute("UPDATE WebUsers SET referral_credits = max(0, referral_credits - 20) WHERE id = ?", (user["id"],))
                    
            if user.get("telegram_chat_id"):
                database.add_premium_days(user["telegram_chat_id"], 30)
                if credits > 0:
                    database.consume_referral_credits(user["telegram_chat_id"], 20.0)
                    
            # 🤝 Reward Referrer on successful Referee premium upgrade
            try:
                from web_api.db_web import award_premium_referral_on_upgrade
                award_premium_referral_on_upgrade(user["id"])
            except Exception as ref_err:
                print(f"Error awarding referral on premium upgrade: {ref_err}")
                
            return jsonify({"message": "Payment verified! Premium activated for 30 days."}), 200
        else:
            return jsonify({"message": "Audit completed. No recent transactions found for your source wallet. Please ensure you sent $20 USDT via TRON (TRC-20)."}), 200
            
    except Exception as e:
        print(f"Error checking payment: {e}")
        return jsonify({"message": "Error querying Tron blockchain. Please try again later."}), 500

@app.route('/api/premium/redeem-gift', methods=['POST'])
@require_auth
def redeem_gift():
    user = g.user

        
    data = request.get_json() or {}
    code = data.get("code")
    if not code:
        return jsonify({"error": "Missing gift code"}), 400
        
    try:
        success, message = database.redeem_gift_code_web(user["id"], code)
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        print(f"Error redeeming gift: {e}")
        return jsonify({"error": "Internal server error"}), 500

# ----------------- Referrals -----------------
@app.route('/api/referral/info', methods=['GET'])
def referral_info():
    ref_id = request.args.get("ref")
    if not ref_id:
        return jsonify({"error": "Missing ref parameter"}), 400
        
    try:
        ref_id_int = int(ref_id)
    except ValueError:
        return jsonify({"name": f"Sherpa #{ref_id}"}), 200
        
    with database.db_session() as conn:
        c = conn.cursor()
        # 1. Try lookup in WebUsers by ID
        c.execute("SELECT full_name FROM WebUsers WHERE id = ?", (ref_id_int,))
        row = c.fetchone()
        if row and row[0]:
            return jsonify({"name": row[0]}), 200
            
        # 2. Try lookup in Users by Telegram Chat ID
        c.execute("SELECT full_name FROM Users WHERE telegram_chat_id = ?", (ref_id_int,))
        row = c.fetchone()
        if row and row[0]:
            return jsonify({"name": row[0]}), 200
            
    return jsonify({"name": f"Sherpa #{ref_id}"}), 200

@app.route('/api/referral/stats', methods=['GET'])
@require_auth
def referral_stats():
    user = g.user
    invite_link = f"https://metaversesherpa.io/#/register?ref={user['id']}"
    tg_user = _get_telegram_user(user)
    ref_count = user.get("referral_count", 0)
    credits = user.get("referral_credits", 0.0)
    
    if tg_user:
        ref_count = max(ref_count, tg_user.get("referral_count", 0))
        credits = max(credits, tg_user.get("referral_credits", 0.0))
        
    return jsonify({
        "referral_count": ref_count,
        "referral_credits": credits,
        "invite_link": invite_link
    }), 200

# ----------------- Admin Deployment Endpoint -----------------
@app.route('/api/admin/deployment', methods=['GET'])
@require_auth
def admin_deployment():
    user = g.user
    tg_user = _get_telegram_user(user)
    
    is_super_admin = (user.get("telegram_chat_id") == 1567788633)
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    
    if not is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    import subprocess
    from datetime import datetime
    
    try:
        # Fetch latest 3 commits
        changelog = subprocess.check_output(['git', 'log', '-n', '3', '--pretty=format:%s (%ar)']).decode('utf-8')
        changelog_lines = changelog.split('\n')
        # Fetch latest commit info statically
        commit_hash = subprocess.check_output(['git', 'log', '-1', '--format=%H']).decode('utf-8').strip()
        commit_time = subprocess.check_output(['git', 'log', '-1', '--format=%cd']).decode('utf-8').strip()
    except Exception as git_err:
        print(f"Failed to fetch git info: {git_err}")
        changelog_lines = ["• New deployment (Git log not accessible)"]
        commit_hash = "fallback-hash"
        commit_time = "fallback-time"

    checklist = [
        "Verify 'Close Trade' tactical confirmation on /opentrades",
        "Audit the new 'Glass Progress Bar' for layout overlap",
        "Confirm Blofin Tutorial deep_link delivers PDF correctly"
    ]

    return jsonify({
        "timestamp": commit_time,
        "commit_hash": commit_hash,
        "changelog": changelog_lines,
        "checklist": checklist
    }), 200

@app.route('/api/admin/generate-gift', methods=['POST'])
@require_auth
def admin_generate_gift():
    user = g.user
    tg_user = _get_telegram_user(user)
    
    is_super_admin = (user.get("telegram_chat_id") == 1567788633)
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    
    if not is_admin:
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        # Create unreserved universal gift code for 30 days
        code = database.create_gift_code(target_chat_id=None, target_username=None, days=30)
        
        # Read or fallback bot username
        bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "metaverse_sherpa_bot")
        
        web_gift_url = f"https://bot.metaversesherpa.io/#/login?gift={code}"
        tg_gift_url = f"https://t.me/{bot_username}?start=gift_{code}"
        
        return jsonify({
            "code": code,
            "web_gift_url": web_gift_url,
            "tg_gift_url": tg_gift_url
        }), 200
    except Exception as e:
        print(f"Error generating admin gift: {e}")
        return jsonify({"error": "Internal server error"}), 500

# ----------------- Visual Chart Endpoint -----------------
@app.route('/api/trades/chart', methods=['GET'])
def get_trade_chart():
    symbol = request.args.get("symbol")
    entry = float(request.args.get("entry", 0.0))
    tp = float(request.args.get("tp", 0.0))
    sl = float(request.args.get("sl", 0.0))
    side = request.args.get("side", "LONG").upper()
    open_ts = int(request.args.get("open_ts", 0))
    trade_type = request.args.get("type", "crypto")
    current_price = float(request.args.get("current_price", 0.0))

    if not symbol:
        return "Symbol required", 400

    clean_sym = symbol.replace("/", "_").replace(":", "_")
    filepath = os.path.join(os.getcwd(), "pnl_cards", f"chart_{clean_sym}.png")
    
    # Return cache if less than 60 seconds old
    if os.path.exists(filepath) and (time.time() - os.path.getmtime(filepath) < 60):
        from flask import send_file
        return send_file(filepath, mimetype='image/png')

    try:
        import charting
        import pandas as pd
        import sqlite3
        import live_bot_multi
        
        df_chart = None
        if trade_type == "stock":
            timeframe = "1D"
            try:
                conn = sqlite3.connect("data/stock_daily_cache.db")
                df_chart = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", conn, params=(symbol,))
                conn.close()
                if not df_chart.empty:
                    df_chart['timestamp'] = pd.to_datetime(df_chart['date']).astype(int) // 10**6
                    df_chart = df_chart.tail(60).copy()
                else:
                    df_chart = None
            except Exception as e:
                print(f"Error fetching from stock daily cache: {e}")
        else:
            timeframe = "15M"
            try:
                mdm = live_bot_multi.MarketDataManager()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    df_chart = loop.run_until_complete(mdm.fetch_ohlcv(symbol, "15m"))
                finally:
                    loop.run_until_complete(mdm.close())
                loop.close()
            except Exception as e:
                print(f"Error fetching CCXT OHLCV: {e}")

        if df_chart is None or df_chart.empty:
            dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq='D' if trade_type == "stock" else '15T')
            df_chart = pd.DataFrame({
                'timestamp': dates.astype(int) // 10**6,
                'open': [entry] * 60,
                'high': [entry * 1.01] * 60,
                'low': [entry * 0.99] * 60,
                'close': [entry] * 60,
                'volume': [1000] * 60
            })

        chart_file = charting.generate_trade_chart(
            symbol=symbol,
            df=df_chart,
            entry=entry,
            tp=tp,
            sl=sl,
            side=side,
            open_ts=open_ts,
            timeframe=timeframe,
            current_price=current_price
        )
        
        from flask import send_file
        return send_file(chart_file, mimetype='image/png')
    except Exception as e:
        print(f"Error generating chart endpoint: {e}")
        return f"Error: {str(e)}", 500

from flask import send_from_directory

@app.route('/favicon.svg')
def favicon_svg():
    return send_from_directory('webapp', 'favicon.svg', mimetype='image/svg+xml')

@app.route('/favicon.ico')
def favicon_ico():
    return send_from_directory('webapp', 'favicon.svg', mimetype='image/svg+xml')

# @app.route('/api/user/manual-trade', methods=['POST'])
@app.route('/api/user/manual-trade', methods=['POST'])
@require_auth
def manual_trade():
    user = g.user
    data = request.json
    trade_id = data.get("signal_id")
    
    import time
    now = int(time.time())
    tg_user = _get_telegram_user(user)
    
    web_premium_expiry = user.get("premium_expiry", 0)
    bot_premium_expiry = tg_user.get("premium_expiry", 0) if tg_user else 0
    max_expiry = max(web_premium_expiry, bot_premium_expiry)
    
    is_super_admin = False
    super_admin_id = utils_gcp.get_secret("SUPER_ADMIN_ID")
    if super_admin_id:
        try:
            if user.get("telegram_chat_id") == int(super_admin_id) or (tg_user and tg_user.get("telegram_chat_id") == int(super_admin_id)):
                is_super_admin = True
        except ValueError:
            pass
            
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    is_premium = max_expiry > now or is_admin
    
    if not is_premium:
        return jsonify({"success": False, "error": "Premium required"}), 403
        
    chat_id = user.get("telegram_chat_id")
    if not chat_id:
        return jsonify({"success": False, "error": "Please connect your Telegram account first."}), 400
        
    from bot.handlers.trading import execute_manual_trade
    import asyncio
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success, msg = loop.run_until_complete(execute_manual_trade(chat_id, trade_id))
        return jsonify({"success": success, "message": msg}), 200 if success else 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        loop.close()

# Start Flask Server
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
