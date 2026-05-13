import requests
import json

address = "TUhiPWBBrJKV7cyrnSawZ7JUdLN8Qcg6u3"
# Endpoint 1: The 'tokens' list endpoint (often most reliable for TRC-20)
url1 = f"https://apilist.tronscan.org/api/account/tokens?address={address}&token=USDT"
# Endpoint 2: The raw TRC-20 balance endpoint
url2 = f"https://apilist.tronscan.org/api/token_balance?address={address}&token=TR7NHqjehp3u3M11K2xv39zSQqyvssF6t"

def test_url(url):
    print(f"\n--- Querying: {url} ---")
    try:
        resp = requests.get(url, timeout=10)
        print(f"Status: {resp.status_code}")
        print(f"RAW: {resp.text[:500]}...") # Show first 500 chars
        data = resp.json()
        return data
    except Exception as e:
        print(f"ERROR: {e}")
        return None

data1 = test_url(url1)
data2 = test_url(url2)

# Analyze results
if data1:
    tokens = data1.get('data', [])
    for t in tokens:
        if t.get('tokenSymbol') == 'USDT':
            bal = float(t.get('balance')) / 10**float(t.get('tokenDecimal'))
            print(f"\n>>> URL1 FOUND USDT: ${bal:,.2f}")

if data2:
    # Handle both list and dict responses
    tokens = data2 if isinstance(data2, list) else [data2]
    for t in tokens:
        if t.get('symbol') == 'USDT' or t.get('tokenSymbol') == 'USDT':
            bal = float(t.get('balance')) / 10**float(t.get('decimals', 6))
            print(f"\n>>> URL2 FOUND USDT: ${bal:,.2f}")
