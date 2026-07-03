import database
from web_api import db_web

email = "metaversesherpa@gmail.com"
user = db_web.get_web_user_by_email(email)
print("web user api_key:", user.get("api_key")[:10] if user.get("api_key") else None)

tg_id = user.get("telegram_chat_id")
print("tg_id:", tg_id)
tg_user = None
if tg_id:
    tg_user = database.get_user(int(tg_id))
    print("tg_user api_key:", tg_user.get("api_key")[:10] if tg_user.get("api_key") else None)

has_keys = bool((tg_user or {}).get("api_key") or user.get("api_key"))
print("has_keys:", has_keys)
