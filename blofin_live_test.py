import os
import ccxt
import time
from dotenv import load_dotenv

def main():
    load_dotenv()
    print("🏔️ Starting Blofin Live Trade Audit...")
    
    # 1. Initialize Client (Local Test Keys)
    exchange = ccxt.blofin({
        'apiKey': os.getenv('BLOFIN_API_LOCAL_KEY'),
        'secret': os.getenv('BLOFIN_API_LOCAL_SECRET'),
        'password': os.getenv('BLOFIN_API_PASSWORD'),
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })
    
    symbol = 'AAPL/USDT:USDT'
    leverage = 10
    
    try:
        # 2. Set Leverage
        print(f"⚙️ Setting leverage to {leverage}x for {symbol}...")
        exchange.set_leverage(leverage, symbol)
        
        # 3. Fetch Balance
        balance = exchange.fetch_balance()
        usdt_free = balance['USDT']['free']
        print(f"💰 Available USDT: ${usdt_free:.2f}")
        
        # 4. Calculate Position Size (1% of balance @ 10x)
        # Position Notional = (Account * 0.01) * 10
        risk_pct = 0.01
        account_val = balance['USDT']['total']
        target_notional = account_val * risk_pct * leverage
        
        # Fetch current price
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        
        # Amount in shares = Notional / Price
        # Blofin uses 'contracts' where 1 contract = 0.01 shares (based on our audit)
        market = exchange.market(symbol)
        contract_size = market['contractSize']
        
        amount_shares = target_notional / price
        amount_contracts = int(amount_shares / contract_size)
        
        if amount_contracts < market['limits']['amount']['min']:
            amount_contracts = market['limits']['amount']['min']
            
        print(f"📊 Calculated Order: {amount_contracts} contracts (~{amount_contracts * contract_size:.2f} shares) @ ${price}")
        
        # 5. Execute Trade
        print(f"🚀 Executing Market LONG on {symbol}...")
        order = exchange.create_market_buy_order(symbol, amount_contracts)
        print(f"✅ Order Placed! ID: {order['id']}")
        
        time.sleep(2)
        
        # 6. Verify Position
        positions = exchange.fetch_positions([symbol])
        if positions:
            pos = positions[0]
            print("\n" + "═"*50)
            print("🕵️ LIVE POSITION AUDIT")
            print("═"*50)
            print(f"Symbol    : {pos['symbol']}")
            print(f"Size      : {pos['contracts']} contracts")
            print(f"Entry     : ${pos['entryPrice']}")
            print(f"Unreal PnL: ${pos['unrealizedPnl']}")
            print(f"Leverage  : {pos['leverage']}x")
            print("═"*50)
            
        # 7. Close Trade (Automated for the test)
        print("\n⏳ Waiting 5 seconds for position stabilization...")
        time.sleep(5)
        
        print(f"📉 Executing Market CLOSE on {symbol}...")
        close_order = exchange.create_market_sell_order(symbol, amount_contracts, {'reduceOnly': True})
        print(f"✅ Position Closed! ID: {close_order['id']}")
        print("\n🏆 Blofin Live Trade Test: SUCCESSFUL")

    except Exception as e:
        print(f"❌ Critical Failure: {e}")

if __name__ == "__main__":
    main()
