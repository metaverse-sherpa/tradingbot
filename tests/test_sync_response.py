"""Simulate what the /auth/sync endpoint returns for metaversesherpa@gmail.com"""
import time, json, database
from web_api.db_web import get_web_user_by_email

user = get_web_user_by_email("metaversesherpa@gmail.com")

# This is the exact code from routes_auth.py sync_firebase_user
safe_user = dict(user)
safe_user.pop("password_hash", None)
safe_user.pop("api_key", None)
safe_user.pop("api_secret", None)
safe_user.pop("api_password", None)
safe_user.pop("alpaca_api_key", None)
safe_user.pop("alpaca_api_secret", None)

safe_user["disabled_strategies"] = database.get_disabled_strategies()

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

print("=== KEY FIELDS IN SYNC RESPONSE ===")
print(f"  has_exchange_keys: {safe_user['has_exchange_keys']}")
print(f"  has_alpaca_keys: {safe_user['has_alpaca_keys']}")
print(f"  exchange_id: {safe_user['exchange_id']}")
print(f"  alpaca_endpoint: {safe_user['alpaca_endpoint']}")
print(f"  is_premium: {safe_user.get('is_premium')}")

# Verify api_key is NOT in response (was popped)
print(f"  api_key in response: {'api_key' in safe_user}")
print(f"  alpaca_api_key in response: {'alpaca_api_key' in safe_user}")
