import requests
import json

address = "TUhiPWBBrJKV7cyrnSawZ7JUdLN8Qcg6u3"
# Official TRON Node API
url = "https://api.tronstack.io/wallet/getaccount"
payload = {"address": address, "visible": True}

print(f"Querying Node: {url}")
try:
    resp = requests.post(url, json=payload, timeout=10)
    data = resp.json()
    
    # TRC-20 tokens are in 'trc20' list as {contract_address: balance}
    trc20 = data.get('trc20', [])
    print(f"Found {len(trc20)} TRC-20 records.")
    
    # USDT Contract: TR7NHqjehp3u3M11K2xv39zSQqyvssF6t
    usdt_contract = "TR7NHqjehp3u3M11K2xv39zSQqyvssF6t"
    
    for item in trc20:
        for contract, balance in item.items():
            if contract == usdt_contract:
                # USDT has 6 decimals
                final_balance = float(balance) / 10**6
                print(f"\n>>> SUCCESS: TRON NODE FOUND USDT: ${final_balance:,.2f}")
                exit(0)

    print(">>> INFO: USDT not found in node response.")

except Exception as e:
    print(f">>> ERROR: {e}")
