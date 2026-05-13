import requests
import json

address = "TUhiPWBBrJKV7cyrnSawZ7JUdLN8Qcg6u3"
# Official USDT Contract on TRON
usdt_contract = "TR7NHqjehp3u3M11K2xv39zSQqyvssF6t"
url = f"https://apilist.tronscan.org/api/account/token_balance?address={address}&token={usdt_contract}"
print(f"Querying: {url}")

try:
    resp = requests.get(url, timeout=10)
    data = resp.json()
    print(f"RAW DATA: {json.dumps(data, indent=2)}")
    
    # TronScan token_balance endpoint returns a list
    if isinstance(data, list) and len(data) > 0:
        token = data[0]
        balance = token.get('balance', '0')
        decimals = token.get('decimals', 6)
        final_balance = float(balance) / 10**float(decimals)
        print(f">>> SUCCESS: USDT Balance is ${final_balance:,.2f}")
    else:
        print(">>> INFO: No USDT balance found (Wallet is likely empty).")

except Exception as e:
    print(f">>> ERROR: {e}")
