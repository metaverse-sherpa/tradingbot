import sys
import json
sys.path.append('/Users/johngiles/projects/tradingbot')
import database
from web_api.routes_settings import _clean_pem
import ccxt

user = database.get_user(10) # Assuming ID 10 based on earlier logs
if not user:
    print("User not found")
    sys.exit(1)

crypto_api_key = user.get("api_key")
crypto_api_secret = _clean_pem(user.get("api_secret"))

if not crypto_api_key:
    print("No api key")
    sys.exit(1)

config = {
    "apiKey": crypto_api_key,
    "secret": crypto_api_secret,
    "enableRateLimit": False,
}
client = ccxt.coinbase(config)
try:
    bal = client.fetch_balance()
    print("KEYS:", bal.keys())
    print("FREE USD:", bal.get('free', {}).get('USD'))
    print("TOTAL USD:", bal.get('total', {}).get('USD'))
    print("USD DICT:", bal.get('USD'))
except Exception as e:
    print("ERROR:", e)
