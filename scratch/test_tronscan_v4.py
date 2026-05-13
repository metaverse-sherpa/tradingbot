import requests
import json

address = "TUhiPWBBrJKV7cyrnSawZ7JUdLN8Qcg6u3"
# Gold Standard TRC-20 Balance Endpoint
url = f"https://api.trongrid.io/v1/accounts/{address}/trc20"

print(f"Querying Gold Standard: {url}")
try:
    resp = requests.get(url, timeout=10)
    data = resp.json()
    
    tokens = data.get('data', [])
    print(f"Found {len(tokens)} TRC-20 records.")
    
    for t in tokens:
        for contract, balance in t.items():
            if contract == "TR7NHqjehp3u3M11K2xv39zSQqyvssF6t":
                val = float(balance) / 10**6
                print(f"\n>>> SUCCESS: GOLD STANDARD FOUND USDT: ${val:,.2f}")
                exit(0)

    print(">>> INFO: USDT not found in Gold Standard response.")

except Exception as e:
    print(f">>> ERROR: {e}")
