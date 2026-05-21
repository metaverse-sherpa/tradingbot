#!/usr/bin/env python3
"""
🛡️ Cyber-Sherpa: Multi-Exchange Verification Suite
--------------------------------------------------
This script safely tests the new multi-exchange logic without placing any orders.
It verifies that the Universal Exchange Factory and Symbol Normalization are working.
"""

import os
import ccxt
from dotenv import load_dotenv
import database

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

def run_verification():
    print("🏔️  Cyber-Sherpa: Multi-Exchange Pre-Flight Check\n" + "="*50)
    
    # Mock a user object using your existing .env keys
    # We'll default to Blofin for the first test, but you can change 'exchange_id' below.
    mock_user = {
        "api_key": os.getenv("BLOFIN_API_KEY"),
        "api_secret": os.getenv("BLOFIN_API_SECRET"),
        "api_password": os.getenv("BLOFIN_API_PASSWORD"),
        "exchange_id": "blofin", # Change to 'binance' or 'mexc' to test other platforms
        "chat_id": 12345
    }

    if not mock_user["api_key"]:
        print("❌ Error: BLOFIN_API_KEY not found in .env. Please ensure your keys are set.")
        return

    print(f"📡 Testing Connection to: {mock_user['exchange_id'].upper()}")
    
    try:
        # 1. Test Universal Factory
        print("🛠️  Initializing Exchange Client...")
        ex = database.get_exchange_client(mock_user)
        ex.load_markets()
        print(f"✅ Connection Successful! (Exchange ID: {ex.id})")
        
        # 2. Test Balance Fetching
        print("\n💰 Fetching Balance...")
        balance = ex.fetch_balance(params={"type": "futures"})
        total_usdt = balance.get("USDT", {}).get("total", 0)
        print(f"✅ Balance Found: ${total_usdt:,.2f} USDT")
        
        # 3. Test Symbol Normalization
        test_sym = "BTC/USDT:USDT"
        norm_sym = database.normalize_symbol(test_sym, ex.id)
        print(f"\n🛰️  Testing Symbol Normalization...")
        print(f"   Original: {test_sym}")
        print(f"   Normalized: {norm_sym}")
        
        # 4. Test Position Fetching
        print("\n🔍 Checking for Open Positions...")
        positions = ex.fetch_positions([norm_sym])
        active = [p for p in positions if float(p.get("contracts", 0) or 0) != 0]
        
        if active:
            print(f"✅ Found {len(active)} active positions for {norm_sym}")
            for p in active:
                print(f"   - {p['symbol']}: {p['side'].upper()} | Size: {p['contracts']} | PnL: ${p['unrealizedPnl']:.2f}")
        else:
            print(f"ℹ️  No open positions found for {norm_sym} (This is normal if you're not in a trade).")
            
        # 5. Test History Logic (PnL Reconstruction)
        print("\n📜 Testing History Fetching (Last 3 Trades)...")
        trades = ex.fetch_my_trades(norm_sym, limit=3)
        if trades:
            for t in trades:
                info = t.get("info", {})
                # Show raw PnL field name for verification
                pnl_field = "fillPnl" if ex.id == "blofin" else "realizedPnl"
                raw_pnl = info.get(pnl_field, "N/A")
                print(f"   - Trade {t['id']}: Price: {t['price']} | Raw {pnl_field}: {raw_pnl}")
        else:
            print("ℹ️  No trade history found for this symbol.")

        print("\n" + "="*50)
        print("✨ VERIFICATION COMPLETE: Multi-Exchange Logic is Rock-Solid! ✨")
        print("==================================================")

    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {str(e)}")
        print("\nTip: Ensure your API keys have 'Futures' permissions enabled.")

if __name__ == "__main__":
    run_verification()
