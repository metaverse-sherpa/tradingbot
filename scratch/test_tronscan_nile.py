import requests
import json

address = "TUhiPWBBrJKV7cyrnSawZ7JUdLN8Qcg6u3"
# Query NILE TESTNET
url = f"https://nile.trongrid.io/v1/accounts/{address}/trc20"

print(f"Querying NILE TESTNET: {url}")
try:
    resp = requests.get(url, timeout=10)
    data = resp.json()
    
    tokens = data.get('data', [])
    print(f"Found {len(tokens)} TRC-20 records on Nile.")
    
    for t in tokens:
        # USDT might have a different contract on Nile, but let's check symbols
        for contract, balance in t.items():
            # Common Nile USDT mock addresses: 'TXYZ...', etc.
            # But we can check for symbol if we use a different endpoint
            pass
        
        # Let's just print the raw token data
        print(f"Token Data: {json.dumps(t, indent=2)}")

except Exception as e:
    print(f">>> ERROR: {e}")
