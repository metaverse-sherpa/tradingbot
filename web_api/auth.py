import os
from functools import wraps
import jwt
import datetime
import bcrypt
from flask import request, jsonify, g
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from web_api.db_web import get_web_user_by_id
import utils_gcp

JWT_SECRET = utils_gcp.get_secret("JWT_SECRET") or "default-fallback-jwt-secret-key-1234567"
GOOGLE_CLIENT_ID = utils_gcp.get_secret("GOOGLE_CLIENT_ID") or ""

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def generate_token(user_id: int) -> str:
    payload = {
        'sub': str(user_id),
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return int(payload['sub'])
    except Exception as e:
        print(f"[AUTH DEBUG] verify_token EXCEPTION: {type(e).__name__}: {e}")
        return None

def verify_google_token(token: str) -> dict:
    try:
        # Verify the ID token against Google's OAuth2 endpoints
        id_info = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        # Check issuer
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
        return id_info
    except Exception as e:
        print(f"Google Token Verification Error: {e}")
        return None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('session_token')
        print(f"[AUTH DEBUG] Cookie token: {token[:10] if token else None}")
        
        if not token:
            # Fallback to Authorization header
            auth_header = request.headers.get('Authorization')
            print(f"[AUTH DEBUG] Auth header: {auth_header[:15] if auth_header else None}")
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        print(f"[AUTH DEBUG] Final token to verify: {token[:10] if token else None}")
        
        if not token:
            print("[AUTH DEBUG] No token found, returning 401")
            return jsonify({"error": "Authentication required"}), 401
            
        user_id = verify_token(token)
        print(f"[AUTH DEBUG] verify_token result: {user_id}")
        if not user_id:
            return jsonify({"error": "Invalid or expired session"}), 401
            
        user = get_web_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 401
            
        g.user = user
        return f(*args, **kwargs)
    return decorated
