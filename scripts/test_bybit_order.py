import sys
import os
import time

# Add parent directory to path to allow importing local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
from web_api.db_web import get_web_user_by_id

def find_bybit_user():
    # 1. Search WebUsers table
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT id, email FROM WebUsers WHERE api_key IS NOT NULL AND exchange_id = 'bybit'")
        rows = c.fetchall()
        for r in rows:
            user = get_web_user_by_id(r[0])
            if user and user.get("api_key"):
                return user, f"WebUser (ID: {r[0]}, Email: {r[1]})"

    # 2. Search Telegram Users table
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id, full_name FROM Users WHERE api_key IS NOT NULL AND exchange_id = 'bybit'")
        rows = c.fetchall()
        for r in rows:
            user = database.get_user(r[0])
            if user and user.get("api_key"):
                return user, f"Telegram User (Chat ID: {r[0]}, Name: {r[1]})"

    return None, None

def run_test_order():
    print("=== Bybit Test Order Script ===")
    user, user_desc = find_bybit_user()
    if not user:
        print("❌ Error: No active Bybit credentials found in the database.")
        return

    print(f"Found active Bybit credentials for: {user_desc}")
    
    # Instantiate the client (automatically routes through the London Squid proxy)
    client = database.get_exchange_client(user, is_async=False)
    client.timeout = 10000
    
    try:
        symbol = 'BTC/USDT:USDT'
        print(f"\n1. Fetching market price for {symbol}...")
        ticker = client.fetch_ticker(symbol)
        last_price = ticker['last']
        print(f"   Current Price: {last_price} USDT")

        # Set TP/SL 2% away from market price
        tp_price = round(last_price * 1.02, 1)
        sl_price = round(last_price * 0.98, 1)
        amount = 0.001 # Minimum size for BTC/USDT on Bybit

        print(f"\n2. Placing Market BUY order of {amount} BTC with TP={tp_price} and SL={sl_price}...")
        order = client.create_order(
            symbol=symbol,
            type='market',
            side='buy',
            amount=amount,
            params={
                'takeProfit': str(tp_price),
                'stopLoss': str(sl_price),
            }
        )
        print("   ✅ BUY Order Placed successfully!")
        print(f"   Order ID: {order.get('id')}")

        print("\n3. Waiting 3 seconds...")
        time.sleep(3)

        print(f"\n4. Placing Market SELL order (reduceOnly) to close the position...")
        close_order = client.create_order(
            symbol=symbol,
            type='market',
            side='sell',
            amount=amount,
            params={
                'reduceOnly': True
            }
        )
        print("   ✅ SELL Close Order Placed successfully!")
        print(f"   Order ID: {close_order.get('id')}")

        print("\n5. Checking for any remaining open trigger/limit orders to clean up...")
        time.sleep(1)
        open_orders = client.fetch_open_orders(symbol)
        if open_orders:
            print(f"   Found {len(open_orders)} remaining open orders. Cancelling them...")
            for o in open_orders:
                print(f"   - Cancelling {o['id']} ({o.get('info', {}).get('orderType') or o['type']} {o['side']})...")
                client.cancel_order(o['id'], symbol)
            print("   ✅ Cleanup complete.")
        else:
            print("   No remaining open orders found.")

        print("\n🎉 Test order completed successfully! Proxy routing, auth, and order execution are working flawlessly.")

    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            client.close()
        except:
            pass

if __name__ == "__main__":
    run_test_order()
