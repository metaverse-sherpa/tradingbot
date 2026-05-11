import os
import ccxt
from dotenv import load_dotenv

load_dotenv()
exchange = ccxt.blofin({
    "apiKey": os.getenv("BLOFIN_API_KEY"),
    "secret": os.getenv("BLOFIN_API_SECRET"),
    "password": os.getenv("BLOFIN_API_PASSWORD"),
    "options": {"defaultType": "swap"},
})

print("Fetching Ledger...")
try:
    ledger = exchange.fetch_ledger(limit=10)
    for l in ledger:
        print(f"Type: {l['type']}, Amount: {l['amount']}, Info: {l['info']}")
except Exception as e:
    print(f"Ledger Error: {e}")

print("\nFetching Trades for BTC/USDT:USDT...")
try:
    trades = exchange.fetch_my_trades("BTC/USDT:USDT", limit=5)
    for t in trades:
        print(f"Side: {t['side']}, Price: {t['price']}, Info: {t['info']}")
except Exception as e:
    print(f"Trades Error: {e}")
