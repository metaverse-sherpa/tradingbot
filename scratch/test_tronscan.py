import requests
import json

# CORRECTED CASING: Lowercase 'b' in PWBbr
address = "TUhiPWBbrJKV7cyrnSawZ7JUdLN8Qcg6u3"
url = f"https://apilist.tronscan.org/api/account?address={address}"
print(f"Querying: {url}")

try:
    resp = requests.get(url, timeout=10)
    data = resp.json()
    
    trc20_tokens = data.get('trc20token_balances', [])
    print(f"Found {len(trc20_tokens)} TRC-20 tokens.")
    
    for token in trc20_tokens:
        symbol = token.get('symbol')
        balance = token.get('balance')
        decimals = token.get('decimals')
        
        if symbol == 'USDT':
            final_balance = float(balance) / 10**float(decimals)
            print(f"\n>>> SUCCESS: USDT Balance is ${final_balance:,.2f}")

except Exception as e:
    print(f">>> ERROR: {e}")
