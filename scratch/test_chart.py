import asyncio
import pandas as pd
import time
import os
import sys

# Add root directory to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import charting
import live_bot_multi

async def main():
    print("Testing chart generation...")
    mdm = live_bot_multi.MarketDataManager()
    symbol = "LINK/USDT:USDT"
    df = await mdm.fetch_ohlcv(symbol, "15m")
    if df is None:
        print("Failed to fetch candles.")
        await mdm.close()
        return
        
    print(f"Fetched {len(df)} candles.")
    entry = 9.57
    tp = 9.4888
    sl = 9.6715
    side_str = "SHORT"
    open_ts = int(time.time() * 1000) # Current time
    
    try:
        path = charting.generate_trade_chart(symbol, df, entry, tp, sl, side_str, open_ts=open_ts)
        print(f"Success! Chart saved to: {path}")
        print(f"File exists: {os.path.exists(path)}")
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        
    await mdm.close()

if __name__ == "__main__":
    asyncio.run(main())
