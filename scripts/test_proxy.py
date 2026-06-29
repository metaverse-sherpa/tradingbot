import os
import sys
import ccxt

# Add parent directory to sys.path to enable imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database

PROXY_IP = "130.162.186.47"
PROXY_PORT = "3128"
PROXY_URL = f"http://{PROXY_IP}:{PROXY_PORT}"

def test_bybit_connection(api_key, api_secret, api_password=None):
    # Initialize Bybit with the proxy configuration
    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        **({'password': api_password} if api_password else {}),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
        },
        'proxies': {
            'http': PROXY_URL,
            'https': PROXY_URL,
        },
        'timeout': 10000,
    })

    try:
        print(f"Testing connection to Bybit via London proxy ({PROXY_URL})...")
        
        # 1. Test basic connectivity (public endpoint)
        markets = exchange.load_markets()
        print("✅ Successfully fetched markets (Public API OK)!")
        
        # 2. Test authenticated connectivity (private endpoint)
        balance = exchange.fetch_balance()
        print("✅ Successfully authenticated! Balance fetched successfully (Private API OK).")
        print(f"   Available assets: {list(balance.get('total', {}).keys())[:10]}")
        print("\n🎉 Your bot now safely bypasses the US geo-block using the UK proxy!")
        return True
    except Exception as e:
        print(f"\n❌ Connection Failed: {e}")
        print("\n--- Detailed Error Info ---")
        print(f"Exception Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            exchange.close()
        except:
            pass

def main():
    print("=== Bybit London Proxy Test Script ===")
    
    # Attempt to auto-detect user with Bybit configured
    bybit_user = None
    try:
        print("Scanning database for users with Bybit exchange...")
        users = database.get_all_users()
        bybit_users = [u for u in users if u.get('exchange_id') == 'bybit']
        if bybit_users:
            bybit_user = bybit_users[0]
            print(f"Found Bybit user: {bybit_user.get('email') or bybit_user.get('telegram_chat_id') or 'Unknown'}")
    except Exception as db_err:
        print(f"Could not read database (maybe SQLite only present on VPS): {db_err}")

    if bybit_user:
        api_key = bybit_user.get('api_key')
        api_secret = bybit_user.get('api_secret')
        api_password = bybit_user.get('api_password')
        
        if api_key and api_secret:
            use_detected = input("Use detected database credentials? (y/n): ").strip().lower()
            if use_detected == 'y' or use_detected == '':
                test_bybit_connection(api_key, api_secret, api_password)
                return

    # Fallback to manual entry
    print("\nPlease enter Bybit API credentials manually:")
    api_key = input("API Key: ").strip()
    api_secret = input("API Secret: ").strip()
    api_password = input("Passphrase (optional, press Enter if none): ").strip()
    if not api_password:
        api_password = None
        
    if not api_key or not api_secret:
        print("Error: API Key and Secret are required.")
        return

    test_bybit_connection(api_key, api_secret, api_password)

if __name__ == '__main__':
    main()
