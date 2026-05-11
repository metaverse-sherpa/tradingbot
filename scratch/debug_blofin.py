import os
import sys
import ccxt
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append("/Users/johngiles/projects/tradingbot")

import database

load_dotenv(dotenv_path="/Users/johngiles/projects/tradingbot/.env")

def debug_blofin():
    # Get the first user's credentials from the database to test with
    user = database.get_user(1567788633) # Correct chat_id found in DB
    if not user:
        print("User not found in database.")
        return

    print(f"Connecting to Blofin...")
    
    ex = ccxt.blofin({
        "apiKey": user['api_key'],
        "secret": user['api_secret'],
        "password": user['api_password'],
        "options": {"defaultType": "swap"},
    })
    
    # 1. Fetch ALL open orders for the entire account
    print(f"\n--- Fetching ALL Open Orders (Account Wide) ---")
    try:
        all_open = ex.fetch_open_orders()
        for o in all_open:
            print(f"Order: Symbol={o['symbol']}, Type={o['type']}, Side={o['side']}, Stop={o.get('stopPrice')}, Trig={o.get('triggerPrice')}, Info={o.get('info')}")
    except Exception as e: print(f"Error: {e}")

    # 2. Fetch ALL Plan/Algo orders specifically
    print(f"\n--- Fetching ALL Plan/Algo Orders ---")
    try:
        # Blofin often puts TP/SL in 'plan'
        plan_orders = ex.fetch_open_orders(params={'type': 'plan'})
        for o in plan_orders:
            print(f"Plan Order: Symbol={o['symbol']}, Side={o['side']}, Price={o['price']}, Stop={o.get('stopPrice')}, Info={o.get('info')}")
    except Exception as e: print(f"Error: {e}")

    # 3. Check for any 'stop' orders explicitly
    print(f"\n--- Fetching ALL Stop Orders ---")
    try:
        stop_orders = ex.fetch_open_orders(params={'stop': True})
        for o in stop_orders:
            print(f"Stop Order: Symbol={o['symbol']}, Side={o['side']}, Stop={o.get('stopPrice')}")
    except Exception as e: print(f"Error: {e}")

    print(f"\n--- Fetching Positions for {symbol} ---")
    positions = ex.fetch_positions([symbol])
    for p in positions:
        print(f"Position: Symbol={p['symbol']}, Size={p['contracts']}, Entry={p['entryPrice']}, Info={p.get('info')}")

if __name__ == "__main__":
    debug_blofin()
