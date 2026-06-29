import os
import time
import requests
from flask import Blueprint, request, jsonify, g
import database
from web_api.auth import require_auth
from web_api.db_web import update_web_user_wallet

premium_bp = Blueprint('premium', __name__)

def _get_telegram_user(web_user):
    """If the web user has linked a Telegram chat ID, load the bot's User record."""
    tg_id = web_user.get("telegram_chat_id")
    if tg_id:
        try:
            return database.get_user(int(tg_id))
        except Exception as e:
            print(f"Could not load Telegram user {tg_id}: {e}")
    return None

@premium_bp.route('/api/premium/wallet', methods=['POST'])
@require_auth
def set_premium_wallet():
    data = request.json or {}
    source_wallet = data.get("source_wallet", "").strip()
    if not source_wallet:
        return jsonify({"error": "Source wallet address required"}), 400
        
    update_web_user_wallet(g.user["id"], source_wallet)
    return jsonify({"message": "TRON USDT source wallet set successfully"}), 200

@premium_bp.route('/api/premium/check-payment', methods=['POST'])
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
            now = int(time.time())
            current_expiry = user.get("premium_expiry") or 0
            new_expiry = max(now, current_expiry) + (30 * 86400)
            
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("UPDATE WebUsers SET premium_expiry = ?, premium_expired_notified = '0', premium_warning_notified = '0' WHERE id = ?", (new_expiry, user["id"]))
                if credits > 0:
                    c.execute("UPDATE WebUsers SET referral_credits = max(0, referral_credits - 20) WHERE id = ?", (user["id"],))
                    
            if user.get("telegram_chat_id"):
                database.add_premium_days(user["telegram_chat_id"], 30)
                if credits > 0:
                    database.consume_referral_credits(user["telegram_chat_id"], 20.0)
                    
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
        user_info = f"Web User: {user.get('id')} ({user.get('email', 'None')}), TG: {user.get('telegram_chat_id', 'None')}"
        from utils_error import send_telegram_alert
        send_telegram_alert(f"Premium Check Payment [{user_info}]", e)
        return jsonify({"message": "Error querying Tron blockchain. Please try again later."}), 500

@premium_bp.route('/api/premium/redeem-gift', methods=['POST'])
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
        user_info = f"Web User: {user.get('id')} ({user.get('email', 'None')}), TG: {user.get('telegram_chat_id', 'None')}"
        from utils_error import send_telegram_alert
        send_telegram_alert(f"Premium Redeem Gift [{user_info}]", e)
        return jsonify({"error": "Internal server error"}), 500

@premium_bp.route('/api/referral/info', methods=['GET'])
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
        c.execute("SELECT full_name FROM WebUsers WHERE id = ?", (ref_id_int,))
        row = c.fetchone()
        if row and row[0]:
            return jsonify({"name": row[0]}), 200
            
        c.execute("SELECT full_name FROM Users WHERE telegram_chat_id = ?", (ref_id_int,))
        row = c.fetchone()
        if row and row[0]:
            return jsonify({"name": row[0]}), 200
            
    return jsonify({"name": f"Sherpa #{ref_id}"}), 200

@premium_bp.route('/api/referral/stats', methods=['GET'])
@require_auth
def referral_stats():
    user = g.user
    invite_link = f"https://bot.metaversesherpa.io/#/register?ref={user['id']}"
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

@premium_bp.route('/api/admin/deployment', methods=['GET'])
@require_auth
def admin_deployment():
    user = g.user
    tg_user = _get_telegram_user(user)
    
    is_super_admin = (user.get("telegram_chat_id") == 1567788633)
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    
    if not is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    import subprocess
    
    try:
        changelog = subprocess.check_output(['git', 'log', '-n', '3', '--pretty=format:%s (%ar)']).decode('utf-8')
        changelog_lines = changelog.split('\n')
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

@premium_bp.route('/api/admin/generate-gift', methods=['POST'])
@require_auth
def admin_generate_gift():
    user = g.user
    tg_user = _get_telegram_user(user)
    
    is_super_admin = (user.get("telegram_chat_id") == 1567788633)
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    
    if not is_admin:
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json() or {}
        try:
            months = int(data.get("months", 1))
            if months < 1 or months > 12:
                months = 1
        except (ValueError, TypeError):
            months = 1
            
        days = months * 30
        code = database.create_gift_code(target_chat_id=None, target_username=None, days=days)
        bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "metaverse_sherpa_bot")
        
        web_gift_url = f"https://bot.metaversesherpa.io/#/landing?gift={code}"
        tg_gift_url = f"https://t.me/{bot_username}?start=gift_{code}"
        
        return jsonify({
            "code": code,
            "web_gift_url": web_gift_url,
            "tg_gift_url": tg_gift_url
        }), 200
    except Exception as e:
        print(f"Error generating admin gift: {e}")
        return jsonify({"error": "Internal server error"}), 500

@premium_bp.route('/api/admin/logs', methods=['GET'])
@require_auth
def admin_logs():
    user = g.user
    tg_user = _get_telegram_user(user)
    
    is_super_admin = (user.get("telegram_chat_id") == 1567788633)
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    
    if not is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    service = request.args.get("service")
    if service not in ["tradingbot", "webapi"]:
        return jsonify({"error": "Invalid service"}), 400

    import subprocess
    import re
    try:
        if service == 'tradingbot':
            logs = subprocess.check_output(['journalctl', '-u', service, '-n', '500', '--no-pager', '-o', 'cat']).decode('utf-8', errors='replace')
        else:
            logs = subprocess.check_output(['journalctl', '-u', service, '-n', '500', '--no-pager']).decode('utf-8', errors='replace')
            # Strip out ' cyber-sherpa-vps process: ' to just leave the timestamp and message
            logs = re.sub(r' cyber-sherpa-vps [^:]+:\s*', ' - ', logs)
            
        return jsonify({"logs": logs}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch logs: {str(e)}"}), 500

@premium_bp.route('/api/admin/restart', methods=['POST'])
@require_auth
def admin_restart():
    user = g.user
    tg_user = _get_telegram_user(user)
    
    is_super_admin = (user.get("telegram_chat_id") == 1567788633)
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    
    if not is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json() or {}
    service = data.get("service")
    if service not in ["tradingbot", "webapi"]:
        return jsonify({"error": "Invalid service"}), 400

    import subprocess
    try:
        # We start the subprocess but we shouldn't wait if restarting webapi will kill our own request!
        # Actually, if we are webapi, restarting ourself will drop the connection. 
        # But we still trigger it.
        if service == 'webapi':
            subprocess.Popen(['sudo', 'systemctl', 'reload-or-restart', service])
        else:
            subprocess.Popen(['sudo', 'systemctl', 'restart', service])
        return jsonify({"message": f"{service} restart/reload initiated."}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to restart {service}: {str(e)}"}), 500

@premium_bp.route('/api/admin/config', methods=['GET'])
@require_auth
def get_admin_config():
    user = g.user
    tg_user = _get_telegram_user(user)
    is_super_admin = (user.get("telegram_chat_id") == 1567788633)
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    if not is_admin:
        return jsonify({"error": "Unauthorized"}), 403
        
    excluded = database.get_config("excluded_symbols", "")
    return jsonify({"excluded_symbols": excluded}), 200

@premium_bp.route('/api/admin/config', methods=['POST'])
@require_auth
def update_admin_config():
    user = g.user
    tg_user = _get_telegram_user(user)
    is_super_admin = (user.get("telegram_chat_id") == 1567788633)
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    if not is_admin:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json() or {}
    excluded = data.get("excluded_symbols", "").strip()
    database.update_config("excluded_symbols", excluded)
    return jsonify({"message": "Configuration updated successfully."}), 200
