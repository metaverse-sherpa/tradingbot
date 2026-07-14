import database
from web_api.db_web import get_web_user_by_email

user = get_web_user_by_email("gilesasp@gmail.com")

tg_user = None
tg_id = user.get("telegram_chat_id")
if tg_id:
    try:
        tg_user = database.get_user(int(tg_id))
    except Exception as e:
        pass

has_exchange_keys = bool((tg_user or {}).get("api_key") or user.get("api_key"))
has_alpaca_keys = bool((tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key"))

print(f"has_exchange_keys: {has_exchange_keys}")
print(f"has_alpaca_keys: {has_alpaca_keys}")
