from flask import Blueprint, request, jsonify, g
import database
from web_api.auth import require_auth, require_premium
from web_api.db_web import (
    update_web_user_keys,
    update_web_user_alpaca_keys,
    update_web_user_preferences,
    update_web_user_telegram,
    update_web_user_symbols,
    update_web_user_status,
    update_web_user_strategy,
    delete_web_user_keys,
    delete_web_user_alpaca_keys
)

settings_bp = Blueprint('settings', __name__)

def _get_telegram_user(web_user):
    """If the web user has linked a Telegram chat ID, load the bot's User record."""
    tg_id = web_user.get("telegram_chat_id")
    if tg_id:
        try:
            return database.get_user(int(tg_id))
        except Exception as e:
            pass
    return None

import re
def _clean_pem(secret):
    """Clean up PEM keys that might have been mangled by copy/paste or JSON formatting."""
    if not secret:
        return secret
    secret = secret.replace('\\n', '\n')
    match = re.search(r'-----BEGIN EC PRIVATE KEY-----(.*?)-----END EC PRIVATE KEY-----', secret, re.DOTALL)
    if match:
        body = match.group(1)
        body = re.sub(r'\s+', '', body)
        return f"-----BEGIN EC PRIVATE KEY-----\n{body}\n-----END EC PRIVATE KEY-----\n"
    return secret

@settings_bp.route('/api/settings/exchange', methods=['POST'])
@require_auth
def settings_exchange():
    data = request.json or {}
    exchange_id = data.get("exchange_id", "blofin").strip()
    api_key = data.get("api_key", "").strip()
    api_secret = _clean_pem(data.get("api_secret", "").strip())
    api_password = data.get("api_password", "").strip()
    bingx_futures_type = data.get("bingx_futures_type", "perpetual").strip()
    coinbase_sandbox = data.get("coinbase_sandbox", False)
    if exchange_id == "bingx":
        bingx_futures_type = "perpetual"
    
    if not api_key or not api_secret:
        return jsonify({"error": "API Key and Secret are required"}), 400
        
    update_web_user_keys(g.user["id"], exchange_id, api_key, api_secret, api_password, bingx_futures_type, coinbase_sandbox=coinbase_sandbox)
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
    
    risk_profile = data.get("risk_profile")
    investment_goal = data.get("investment_goal")
    
    update_web_user_preferences(
        g.user["id"], risk_pct, stock_risk_pct, custom_equity_type, custom_equity_value, hide_dollars,
        email_notifications, email_frequency, browser_notifications, risk_profile, investment_goal
    )

    # Sync with linked Telegram account
    tg_user = _get_telegram_user(g.user)
    if tg_user:
        try:
            database.update_user_preference(tg_user["telegram_chat_id"], "hide_dollars", bool(hide_dollars))
            database.update_user_preference(tg_user["telegram_chat_id"], "risk_pct", risk_pct)
            database.update_user_preference(tg_user["telegram_chat_id"], "stock_risk_pct", stock_risk_pct)
        except Exception as e:
            print(f"Error syncing settings to Telegram Users table: {e}")
            from utils_error import send_telegram_alert
            user_info = f"Web User: {g.user.get('id')}, TG: {tg_user['telegram_chat_id']}"
            send_telegram_alert(f"DB Sync Error (Settings) [{user_info}]", e)
            
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
        try:
            crypto = float(database.decrypt(r[1])) if r[1] else 0
        except Exception:
            crypto = 0
            
        try:
            stock = float(database.decrypt(r[2])) if r[2] else 0
        except Exception:
            stock = 0
            
        history.append({
            "timestamp": r[0],
            "crypto": crypto,
            "stock": stock
        })
    return jsonify(history), 200

@settings_bp.route('/api/settings/exchange', methods=['DELETE'])
@require_auth
def delete_exchange():
    delete_web_user_keys(g.user["id"])
    return jsonify({"message": "Exchange API keys deleted successfully"}), 200

@settings_bp.route('/api/settings/alpaca', methods=['DELETE'])
@require_auth
def delete_alpaca():
    delete_web_user_alpaca_keys(g.user["id"])
    return jsonify({"message": "Alpaca Stock API keys deleted successfully"}), 200

@settings_bp.route('/api/settings/test-connection', methods=['GET'])
@require_auth
def test_connection():
    """Test the user's saved exchange credentials and return detailed status."""
    user = g.user
    segment = request.args.get('segment', 'crypto')  # 'crypto' or 'stock'

    if segment == 'crypto':
        import database
        from web_api.routes_trades import _set_coinbase_sandbox_if_needed

        api_key = user.get('api_key')
        api_secret = _clean_pem(user.get('api_secret') or '')
        api_password = user.get('api_password') or ''
        exchange_id = user.get('exchange_id', 'blofin')

        # Fall back to linked Telegram user's keys if web user has none
        if not api_key or not api_secret:
            tg_chat_id = user.get('telegram_chat_id')
            if tg_chat_id:
                try:
                    tg_user = database.get_user(int(tg_chat_id))
                    if tg_user:
                        api_key = tg_user.get('api_key') or tg_user.get('blofin_api_key')
                        api_secret = _clean_pem(tg_user.get('api_secret') or tg_user.get('blofin_api_secret') or '')
                        api_password = tg_user.get('api_password') or tg_user.get('blofin_api_password') or ''
                        exchange_id = tg_user.get('exchange_id', exchange_id)
                except Exception as e:
                    pass

        if not api_key or not api_secret:
            return jsonify({'success': False, 'error': 'No crypto API keys saved'}), 200

        # Detect old Coinbase Pro keys (UUID key ~36 chars, base64 secret, no PEM header)
        # and redirect to the correct CCXT class
        effective_exchange_id = exchange_id
        if exchange_id == 'coinbase' and len(api_key) < 60 and '-----BEGIN' not in api_secret:
            effective_exchange_id = 'coinbaseexchange'

        diag = {
            'exchange': exchange_id,
            'effective_exchange': effective_exchange_id,
            'api_key_len': len(api_key) if api_key else 0,
            'api_secret_len': len(api_secret) if api_secret else 0,
            'secret_has_pem_header': '-----BEGIN' in (api_secret or ''),
            'secret_has_newlines': '\n' in (api_secret or ''),
            'secret_first_40': (api_secret or '')[:40] + '...',
            'coinbase_sandbox': user.get('coinbase_sandbox'),
        }

        try:
            import ccxt
            config = {
                'apiKey': api_key,
                'secret': api_secret,
                **({'password': api_password} if api_password else {}),
                'enableRateLimit': False,
                'timeout': 8000,
            }
            client = getattr(ccxt, effective_exchange_id)(config)
            _set_coinbase_sandbox_if_needed(client, exchange_id, None, user)
            bal = client.fetch_balance()
            try:
                client.close()
            except Exception:
                pass
            note = None
            if effective_exchange_id != exchange_id:
                note = f'Your credentials look like old Coinbase Pro keys. In the exchange dropdown, try selecting "Coinbase Exchange" instead of "Coinbase Advanced".'
            return jsonify({'success': True, 'exchange': effective_exchange_id, 'diag': diag, 'note': note}), 200
        except Exception as e:
            err = str(e)
            hint = None
            if exchange_id == 'coinbase' and '401' in err:
                if '-----BEGIN' not in (api_secret or ''):
                    hint = 'Your API secret does not look like a CDP private key (missing PEM header). Coinbase Advanced requires new CDP API keys from https://portal.cdp.coinbase.com/. Old Coinbase Pro keys are not supported.'
                else:
                    hint = 'JWT auth failed. Ensure your CDP key has "View" permissions and your private key was copied in full including the -----BEGIN/END lines.'
            return jsonify({'success': False, 'exchange': effective_exchange_id, 'error': err[:500], 'diag': diag, 'hint': hint}), 200


    elif segment == 'stock':
        import database
        alpaca_key = user.get('alpaca_api_key')
        alpaca_secret = user.get('alpaca_api_secret')
        if not alpaca_key or not alpaca_secret:
            return jsonify({'success': False, 'error': 'No Alpaca API keys saved'}), 200
        try:
            res = database.make_alpaca_request(user, 'GET', '/v2/account')
            return jsonify({'success': True, 'portfolio_value': res.get('portfolio_value')}), 200
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)[:300]}), 200

    return jsonify({'error': 'Invalid segment'}), 400

@settings_bp.route("/api/settings/developer-api-key/generate", methods=["POST"])
@require_auth
@require_premium
def generate_developer_api_key():
    import secrets
    import database
    from flask import g, jsonify
    
    user = g.user
    if not user:
        return jsonify({"error": "User not found"}), 404
        
    new_key = "sk_" + secrets.token_urlsafe(32)
    
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("UPDATE WebUsers SET developer_api_key = ? WHERE id = ?", (new_key, user["id"]))
            conn.commit()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
    return jsonify({"developer_api_key": new_key}), 200
