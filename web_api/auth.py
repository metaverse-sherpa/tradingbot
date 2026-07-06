import os
from functools import wraps
import time
import database
from flask import request, jsonify, g
from web_api.db_web import get_web_user_by_email, get_web_user_by_id
import utils_gcp
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

cred_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firebase-adminsdk.json")
if not firebase_admin._apps:
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        # Fallback to default credentials inside GCP environment
        firebase_admin.initialize_app()

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # 1. Developer API Key check
        developer_api_key = request.headers.get('X-API-Key')
        if not developer_api_key:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer sk_'):
                developer_api_key = auth_header.split(' ')[1]
                
        if developer_api_key:
            from web_api.db_web import get_web_user_by_developer_api_key
            user = get_web_user_by_developer_api_key(developer_api_key)
            if user:
                now = int(time.time())
                expiry = user.get('premium_expiry') or 0
                if expiry > now:
                    g.user = user
                    return f(*args, **kwargs)
                else:
                    return jsonify({"error": "API Key is valid but your premium membership has expired."}), 403
            else:
                return jsonify({"error": "Invalid API Key."}), 401
                
        # 2. Firebase Session Token check
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            
        if not token:
            token = request.cookies.get('session_token')
        
        if not token:
            return jsonify({"error": "Authentication required"}), 401
            
        try:
            # Symmetrically verify the Firebase ID Token
            decoded_token = firebase_auth.verify_id_token(token)
            email = decoded_token.get("email")
            uid = decoded_token.get("uid")
            
            if not email:
                return jsonify({"error": "Invalid token: Email missing"}), 401
                
            # Fetch user from PostgreSQL
            user = get_web_user_by_email(email)
            if not user:
                # Dynamically provision user record locally in PostgreSQL if they exist in Firebase but not in DB
                with database.db_session() as conn:
                    c = conn.cursor()
                    created_at = int(time.time())
                    full_name = decoded_token.get("name") or email.split("@")[0]
                    c.execute('''
                        INSERT INTO WebUsers (email, google_id, full_name, created_at, is_active)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (email.strip().lower(), uid, full_name, created_at, 1))
                    conn.commit()
                user = get_web_user_by_email(email)
                
            g.user = user
        except Exception as e:
            err_msg = str(e)
            if "expired" in err_msg.lower():
                logger.debug(f"Firebase token expired")
            else:
                logger.error(f"Firebase verify_id_token failed: {e}")
            return jsonify({"error": "Invalid or expired session"}), 401
            
        return f(*args, **kwargs)
    return decorated

def require_premium(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, 'user', None)
        if not user:
            return jsonify({"error": "Authentication required"}), 401
            
        now = int(time.time())
        expiry = user.get('premium_expiry') or 0
        if expiry <= now:
            return jsonify({"error": "Premium subscription required to access this resource"}), 403
            
        return f(*args, **kwargs)
    return decorated

def require_auth_web(f):
    from flask import redirect
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            
        if not token:
            token = request.cookies.get('session_token')
        
        if not token:
            return redirect('/')
            
        try:
            # Symmetrically verify the Firebase ID Token
            decoded_token = firebase_auth.verify_id_token(token)
            email = decoded_token.get("email")
            uid = decoded_token.get("uid")
            
            if not email:
                return redirect('/')
                
            # Fetch user from PostgreSQL
            user = get_web_user_by_email(email)
            if not user:
                # Dynamically provision user record locally in PostgreSQL if they exist in Firebase but not in DB
                with database.db_session() as conn:
                    c = conn.cursor()
                    created_at = int(time.time())
                    full_name = decoded_token.get("name") or email.split("@")[0]
                    c.execute('''
                        INSERT INTO WebUsers (email, google_id, full_name, created_at, is_active)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (email.strip().lower(), uid, full_name, created_at, 1))
                    conn.commit()
                user = get_web_user_by_email(email)
                
            g.user = user
        except Exception as e:
            return redirect('/')
            
        return f(*args, **kwargs)
    return decorated

def require_premium_web(f):
    from flask import redirect
    @wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, 'user', None)
        if not user:
            return redirect('/')
            
        now = int(time.time())
        expiry = user.get('premium_expiry') or 0
        if expiry <= now:
            return redirect('/')
            
        return f(*args, **kwargs)
    return decorated
