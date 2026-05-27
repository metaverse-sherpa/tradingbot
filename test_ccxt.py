import ccxt
import database
from web_api.db_web import get_web_user_by_id

user = get_web_user_by_id(1)
tg_user = database.get_user(int(user["telegram_chat_id"]))

config = {
    "apiKey": tg_user["api_key"],
    "secret": tg_user["api_secret"],
    "password": tg_user["api_password"],
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
}
client = ccxt.blofin(config)
try:
    print("Fetching trades...")
    trades = client.fetch_my_trades("TAO/USDT:USDT", limit=5)
    print(len(trades), "trades found.")
except Exception as e:
    print("Error:", e)
