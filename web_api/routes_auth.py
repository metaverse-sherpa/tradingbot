import time
from flask import Blueprint, request, jsonify, make_response, g
import database
from web_api.db_web import (
    get_web_user_by_email,
    get_web_user_by_id
)
from web_api.auth import require_auth

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/auth/sync', methods=['POST'])
@require_auth
def sync_firebase_user():
    """
    Syncs the authenticated Firebase user with the local PostgreSQL database,
    creating a placeholder user and applying referrals if present.
    """
    user = g.user
    data = request.json or {}
    referred_by = data.get("referred_by")
    
    # If the user was newly created in require_auth and has a referrer, apply it
    if referred_by and not user.get("referred_by"):
        try:
            referred_by = int(referred_by)
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute('UPDATE WebUsers SET referred_by = ? WHERE id = ?', (referred_by, user["id"]))
                conn.commit()
            from web_api.db_web import record_web_referral_signup
            record_web_referral_signup(referred_by, user.get("full_name") or user.get("email"))
            # Reload updated user
            user = get_web_user_by_id(user["id"])
        except Exception as e:
            print(f"Error applying referral sync: {e}")
            
    # Mask sensitive fields
    safe_user = dict(user)
    safe_user.pop("password_hash", None)
    safe_user.pop("api_key", None)
    safe_user.pop("api_secret", None)
    safe_user.pop("api_password", None)
    safe_user.pop("alpaca_api_key", None)
    safe_user.pop("alpaca_api_secret", None)
    
    safe_user["disabled_strategies"] = database.get_disabled_strategies()
    safe_user["ai_strategy_builder_enabled"] = database.get_config("ai_strategy_builder_enabled", "true") == "true"
    
    # Sync telegram bot user data if linked
    tg_id = user.get("telegram_chat_id")
    tg_user = None
    if tg_id:
        try:
            tg_user = database.get_user(int(tg_id))
        except Exception:
            pass
            
    safe_user["has_exchange_keys"] = bool((tg_user or {}).get("api_key") or user.get("api_key"))
    safe_user["has_alpaca_keys"] = bool((tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key"))
    
    if tg_user and tg_user.get("api_key"):
        safe_user["exchange_id"] = tg_user.get("exchange_id", "blofin")
    else:
        safe_user["exchange_id"] = user.get("exchange_id", "blofin")
        
    safe_user["alpaca_endpoint"] = user.get("alpaca_endpoint") or (tg_user or {}).get("alpaca_endpoint")
    
    # Determine premium level
    now = int(time.time())
    web_premium_expiry = user.get("premium_expiry") or 0
    bot_premium_expiry = (tg_user.get("premium_expiry") or 0) if tg_user else 0
    max_expiry = max(web_premium_expiry, bot_premium_expiry)
    
    is_super_admin = False
    import utils_gcp
    super_admin_id = utils_gcp.get_secret("SUPER_ADMIN_ID")
    if super_admin_id:
        try:
            super_admin_id = int(super_admin_id)
            if user.get("telegram_chat_id") == super_admin_id or (tg_user and tg_user.get("telegram_chat_id") == super_admin_id) or user.get("email") == "gilesasp@gmail.com":
                is_super_admin = True
        except ValueError:
            pass
            
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    safe_user["is_admin"] = is_admin
    safe_user["is_premium"] = max_expiry > now or is_admin
    
    # Sync hide_dollars setting
    if tg_user:
        safe_user["hide_dollars"] = bool(tg_user.get("hide_dollars") if tg_user.get("hide_dollars") is not None else True)
    else:
        safe_user["hide_dollars"] = bool(user.get("hide_dollars") if user.get("hide_dollars") is not None else True)

    # Fetch payments count
    payments_count = 0
    try:
        from db_adapter import USE_POSTGRES
        with database.db_session() as conn:
            c = conn.cursor()
            if USE_POSTGRES:
                c.execute("SELECT COUNT(*) FROM ProcessedPayments WHERE user_id = %s", (user["id"],))
            else:
                c.execute("SELECT COUNT(*) FROM ProcessedPayments WHERE user_id = ?", (user["id"],))
            row = c.fetchone()
            if row:
                payments_count = row[0]
    except Exception as e:
        print(f"Could not load payments count in auth sync: {e}")
    safe_user["payments_count"] = payments_count


    
    return jsonify({
        "success": True,
        "user": safe_user
    }), 200

@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    response = make_response(jsonify({"message": "Logout successful"}), 200)
    response.set_cookie('session_token', '', expires=0)
    return response
