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
            
    return jsonify({
        "success": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name")
        }
    }), 200

@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    response = make_response(jsonify({"message": "Logout successful"}), 200)
    response.set_cookie('session_token', '', expires=0)
    return response
