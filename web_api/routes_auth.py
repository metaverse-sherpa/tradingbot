import time
import secrets
from flask import Blueprint, request, jsonify, make_response
import database
import utils_gcp
from web_api.db_web import (
    get_web_user_by_email,
    get_web_user_by_google_id,
    create_web_user_email,
    create_web_user_google,
    get_web_user_by_id
)
from web_api.auth import (
    hash_password,
    check_password,
    generate_token,
    verify_google_token
)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/auth/register', methods=['POST'])
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

@auth_bp.route('/api/auth/login', methods=['POST'])
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

@auth_bp.route('/api/auth/forgot-password', methods=['POST'])
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
        
    token = secrets.token_urlsafe(32)
    expiry = int(time.time()) + 3600 # 1 hour
    
    with database.db_session() as conn:
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

@auth_bp.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.json or {}
    token = data.get("token")
    new_password = data.get("password")
    
    if not token or not new_password:
        return jsonify({"error": "Token and new password are required."}), 400
        
    with database.db_session() as conn:
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

@auth_bp.route('/api/auth/google', methods=['POST'])
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

@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    response = make_response(jsonify({"message": "Logout successful"}), 200)
    response.set_cookie('session_token', '', expires=0)
    return response
