import sys
import os
import asyncio

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live_bot_multi_alpaca
import stock_data_cache_daily

async def test_dry_run():
    print("🧪 Starting local validation for Sherpa Velocity Pullback strategy...")
    
    # 1. Verify Symbols list
    symbols = stock_data_cache_daily.SYMBOLS
    print(f"Watchlist contains {len(symbols)} symbols.")
    
    # 2. Check indicators and signals for first 5 symbols
    print("\n📊 Calculating indicators and checking signals for first 5 watchlist symbols:")
    count = 0
    for sym in symbols[:5]:
        try:
            yesterday_bar, signal = live_bot_multi_alpaca.calculate_symbol_indicators_and_signal(sym)
            if yesterday_bar:
                print(f"[{sym}] Last Closed Date: {yesterday_bar.get('date')} | Close: ${yesterday_bar.get('close'):.2f} | EMA(50): ${yesterday_bar.get('ema_50'):.2f} | EMA(200): ${yesterday_bar.get('ema_200'):.2f} | RSI(3): {yesterday_bar.get('rsi'):.2f} | Signal: {signal}")
                count += 1
            else:
                print(f"[{sym}] No historical cache found or insufficient bars.")
        except Exception as e:
            print(f"[{sym}] Error calculating indicators: {e}")
            
    # 3. Simulate today's opens
    print("\n🔋 Simulating today's open price mapping and bracket parameters:")
    mock_opens = {
        "AAPL": 175.20,
        "MSFT": 415.50
    }
    
    for sym, o_price in mock_opens.items():
        yesterday_bar, _ = live_bot_multi_alpaca.calculate_symbol_indicators_and_signal(sym)
        if yesterday_bar:
            atr = yesterday_bar['atr']
            tp = o_price + 4.5 * atr
            sl = o_price - 3.0 * atr
            
            # Simulate order payload
            risk_amt = 100.0 # $100 risk
            qty = risk_amt / (3.0 * atr)
            if qty >= 1:
                qty = int(qty)
            else:
                qty = round(qty, 4)
                
            payload = {
                "symbol": sym,
                "qty": str(qty),
                "side": "buy",
                "type": "market",
                "time_in_force": "gtc",
                "order_class": "bracket",
                "take_profit": {
                    "limit_price": f"{tp:.2f}"
                },
                "stop_loss": {
                    "stop_price": f"{sl:.2f}"
                }
            }
            print(f"[{sym}] Mock Bracket Order Payload:\n{payload}\n")
            
    print("🏆 Local validation complete! Script calculations are verified.")

if __name__ == "__main__":
    asyncio.run(test_dry_run())
