import requests
import json

def check_usdt_trc20_payments(my_address):
    """
    Diagnostic script to check incoming USDT (TRC-20) transfers to a specific address.
    Uses the official TronScan API.
    """
    url = f"https://apilist.tronscan.org/api/token_trc20/transfers"
    params = {
        "limit": 10,
        "start": 0,
        "direction": 1, # 1 = Incoming, 0 = Outgoing
        "db_version": 1,
        "address": my_address,
        "relatedAddress": my_address
    }
    
    print(f"🕵️‍♂️ Auditing Institutional Wallet: {my_address}...")
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        transfers = data.get('token_transfers', [])
        print(f"✅ Found {len(transfers)} recent incoming transfers.\n")
        
        for tx in transfers:
            # USDT on Tron is this specific contract
            if tx.get('token_address') == 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':
                from_addr = tx.get('from_address')
                amount = float(tx.get('quant')) / 10**6 # USDT has 6 decimals
                tx_id = tx.get('transaction_id')
                status = tx.get('status')
                
                print(f"💰 Amount: ${amount:,.2f}")
                print(f"👤 From: {from_addr}")
                print(f"📄 TXID: {tx_id}")
                print(f"🔄 Status: {status}")
                print("-" * 50)
                
    except Exception as e:
        print(f"❌ Error querying TronScan: {e}")

if __name__ == "__main__":
    # Replace this with your actual USDT (TRC-20) address to test
    SAMPLE_ADDRESS = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t" # This is actually the USDT contract address, just for demo
    check_usdt_trc20_payments(SAMPLE_ADDRESS)
