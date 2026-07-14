import requests
import json
import jwt
from datetime import datetime, timedelta
import os

from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key-for-dev")

token = jwt.encode({
    "user_id": 1,
    "exp": datetime.utcnow() + timedelta(hours=24)
}, SECRET_KEY, algorithm="HS256")

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

data = {
    "quantity": 10.0,
    "avg_entry_price": 50000.0,
    "purchase_date": "2024-01-01",
    "dividend_yield": 0.0,
    "category": "stock",
    "symbol": "BTC"
}

print("Sending PUT request...")
res = requests.put("http://localhost:5000/api/portfolio/position/31", headers=headers, json=data)
print("Status:", res.status_code)
print("Response:", res.text)
