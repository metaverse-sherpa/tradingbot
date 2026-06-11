from flask import Blueprint, request, jsonify, g
import database
from web_api.auth import require_auth
from web_api.db_web import (
    update_web_user_keys,
    update_web_user_alpaca_keys,
    update_web_user_preferences,
    update_web_user_telegram,
    update_web_user_symbols,
    update_web_user_status,
    update_web_user_strategy
)

settings_bp = Blueprint('settings', __name__)

def _get_telegram_user(web_user):
    """If the web user has linked a Telegram chat ID, load the bot's User record."""
    tg_id = web_user.get("telegram_chat_id")
    if tg_id:
        try:
            return database.get_user(int(tg_id))
        except Exception as e:
            print(f"Could not load Telegram user {tg_id}: {e}")
    return None

@settings_bp.route('/api/settings/exchange', methods=['POST'])
@require_auth
def settings_exchange():
    data = request.json or {}
    exchange_id = data.get("exchange_id", "blofin").strip()
    api_key = data.get("api_key", "").strip()
    api_secret = data.get("api_secret", "").strip()
    api_password = data.get("api_password", "").strip()
    
    bingx_futures_type = data.get("bingx_futures_type", "standard").strip()
    
    if not api_key or not api_secret:
        return jsonify({"error": "API Key and Secret are required"}), 400
        
    update_web_user_keys(g.user["id"], exchange_id, api_key, api_secret, api_password, bingx_futures_type)
    return jsonify({"message": f"{exchange_id.upper()} exchange keys saved successfully"}), 200

@settings_bp.route('/api/settings/alpaca', methods=['POST'])
@require_auth
def settings_alpaca():
    data = request.json or {}
    api_key = data.get("api_key", "").strip()
    api_secret = data.get("api_secret", "").strip()
    endpoint = data.get("endpoint", "https://api.alpaca.markets").strip()
    
    if not api_key or not api_secret:
        return jsonify({"error": "Alpaca API Key and Secret are required"}), 400
        
    update_web_user_alpaca_keys(g.user["id"], api_key, api_secret, endpoint)
    return jsonify({"message": "Alpaca Stock keys saved successfully"}), 200

@settings_bp.route('/api/settings/preferences', methods=['POST'])
@require_auth
def settings_preferences():
    data = request.json or {}
    risk_pct = float(data.get("risk_pct", g.user.get("risk_pct", 1.0)))
    stock_risk_pct = float(data.get("stock_risk_pct", g.user.get("stock_risk_pct", 2.0)))
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
            database.update_user_preference(tg_user["telegram_chat_id"], "hide_dollars", 1 if hide_dollars else 0)
            database.update_user_preference(tg_user["telegram_chat_id"], "risk_pct", risk_pct)
            database.update_user_preference(tg_user["telegram_chat_id"], "stock_risk_pct", stock_risk_pct)
        except Exception as e:
            print(f"Error syncing settings to Telegram Users table: {e}")
            
    return jsonify({"message": "Trading preferences saved successfully"}), 200

@settings_bp.route('/api/settings/telegram', methods=['POST'])
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

@settings_bp.route('/api/settings/symbols', methods=['POST'])
@require_auth
def settings_symbols():
    data = request.json or {}
    symbols = data.get("symbols", [])
    symbols_str = ",".join(symbols)
    update_web_user_symbols(g.user["id"], symbols_str)
    return jsonify({"message": "Symbol basket updated successfully"}), 200

@settings_bp.route('/api/settings/status', methods=['POST'])
@require_auth
def settings_status():
    data = request.json or {}
    is_active = bool(data.get("is_active", False))
    update_web_user_status(g.user["id"], is_active)
    return jsonify({"message": f"Trading bot {'started' if is_active else 'stopped'} successfully"}), 200

@settings_bp.route('/api/settings/strategy', methods=['POST'])
@require_auth
def settings_strategy():
    data = request.json or {}
    strategy_type = data.get("type", "crypto") # "crypto" or "stock"
    strategy_name = data.get("strategy", "")
    
    if not strategy_name:
        return jsonify({"error": "Strategy name required"}), 400
        
    if database.is_strategy_disabled(strategy_name):
        return jsonify({"error": f"The strategy '{strategy_name}' has been disabled by the administrator."}), 400
        
    update_web_user_strategy(g.user["id"], strategy_type, strategy_name)
    return jsonify({"message": f"Active {strategy_type} strategy updated to {strategy_name}"}), 200

@settings_bp.route('/api/settings/zk-keys', methods=['POST'])
@require_auth
def settings_zk_keys():
    data = request.json or {}
    public_key = data.get("public_key", "").strip()
    encrypted_private_key = data.get("encrypted_private_key", "").strip()
    
    if not public_key or not encrypted_private_key:
        return jsonify({"error": "Public key and encrypted private key are required"}), 400
        
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET public_key = ?, encrypted_private_key = ? WHERE id = ?', (public_key, encrypted_private_key, g.user["id"]))
    return jsonify({"message": "Zero-knowledge keys registered successfully"}), 200

@settings_bp.route('/api/settings/zk-keys', methods=['GET'])
@require_auth
def get_zk_keys():
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT public_key, encrypted_private_key FROM WebUsers WHERE id = ?', (g.user["id"],))
        row = c.fetchone()
    
    if not row:
        return jsonify({"public_key": None, "encrypted_private_key": None}), 200
    return jsonify({
        "public_key": row[0],
        "encrypted_private_key": row[1]
    }), 200

@settings_bp.route('/api/user/balance-history', methods=['GET'])
@require_auth
def get_balance_history():
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT timestamp, encrypted_crypto_balance, encrypted_stock_balance FROM PortfolioBalanceHistory WHERE user_id = ? ORDER BY timestamp ASC', (g.user["id"],))
        rows = c.fetchall()
        
    history = []
    for r in rows:
        history.append({
            "timestamp": r[0],
            "encrypted_crypto_balance": r[1],
            "encrypted_stock_balance": r[2]
        })
    return jsonify(history), 200
