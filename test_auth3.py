import database
from web_api import db_web
from flask import Flask

app = Flask(__name__)

email = "metaversesherpa@gmail.com"
user = db_web.get_web_user_by_email(email)

safe_user = dict(user)
safe_user.pop("password_hash", None)
safe_user.pop("api_key", None)
safe_user.pop("api_secret", None)
safe_user.pop("api_password", None)
safe_user.pop("alpaca_api_key", None)
safe_user.pop("alpaca_api_secret", None)

safe_user["disabled_strategies"] = []

tg_id = user.get("telegram_chat_id")
tg_user = None
if tg_id:
    try:
        tg_user = database.get_user(int(tg_id))
    except Exception as e:
        print("Exception fetching tg_user:", e)

safe_user["has_exchange_keys"] = bool((tg_user or {}).get("api_key") or user.get("api_key"))
safe_user["has_alpaca_keys"] = bool((tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key"))

print("has_exchange_keys:", safe_user["has_exchange_keys"])
print("safe_user api_key present?", "api_key" in safe_user)
import json
print("JSON encode test:", json.dumps(safe_user)[:100])
