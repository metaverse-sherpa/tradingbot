import os
from functools import wraps
import jwt
import datetime
import bcrypt
from flask import request, jsonify, g
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from web_api.db_web import get_web_user_by_id

JWT_SECRET = os.getenv("JWT_SECRET", "default-fallback-jwt-secret-key-1234567")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

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
        'sub': user_id,
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload['sub']
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
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
        if not token:
            # Fallback to Authorization header
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({"error": "Authentication required"}), 401
            
        user_id = verify_token(token)
        if not user_id:
            return jsonify({"error": "Invalid or expired session"}), 401
            
        user = get_web_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 401
            
        g.user = user
        return f(*args, **kwargs)
    return decorated
