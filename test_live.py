import requests
import jwt
import datetime
from web_api.db_web import get_web_user_by_id
import utils_gcp

user = get_web_user_by_id(1)
secret = utils_gcp.get_secret("JWT_SECRET") or "fallback-secret"
payload = {
    "user_id": 1,
    "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
}
token = jwt.encode(payload, secret, algorithm="HS256")

headers = {
    "Authorization": f"Bearer {token}"
}
resp = requests.get("http://127.0.0.1:5000/api/trades/history?limit=10", headers=headers)
print("Status:", resp.status_code)
print("Response:", resp.text)

