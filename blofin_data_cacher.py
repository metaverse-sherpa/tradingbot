import os
import ccxt
import sqlite3
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

def main():
    load_dotenv()
    print("🏔️ Starting Blofin Historical Data Cacher (Since March 2026)...")
    
    # 1. Initialize Client
    exchange = ccxt.blofin({
        'apiKey': os.getenv('BLOFIN_API_LOCAL_KEY'),
        'secret': os.getenv('BLOFIN_API_LOCAL_SECRET'),
        'password': os.getenv('BLOFIN_API_PASSWORD'),
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })
    
    SYMBOLS = [
        "AAPL", "GOOGL", "META", "NVDA", "AMZN", "TSLA", "MSFT", "QQQ", "SPY", "ARM",
        "MRVL", "CRWD", "LITE", "XLE", "USO", "MU", "ORCL", "QCOM", "AMD", "AVGO", 
        "IWM", "TSM", "PYPL", "EWJ", "PLTR", "COIN", "MSTR", "HOOD", "INTC"
    ]
    
    DB_PATH = "data/blofin_stock_cache.db"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS BlofinData
                 (symbol TEXT, timestamp INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL,
                  PRIMARY KEY (symbol, timestamp))''')
    
    start_ts = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp() * 1000)
    
    for s in SYMBOLS:
        try:
            blofin_sym = f"{s}/USDT:USDT"
            print(f"🛰️ Fetching Blofin data for {s}...")
            # Fetch as much as possible (Blofin usually 1000-1440 bars)
            ohlcv = exchange.fetch_ohlcv(blofin_sym, timeframe='15m', since=start_ts, limit=1440)
            
            if ohlcv:
                for bar in ohlcv:
                    c.execute('INSERT OR IGNORE INTO BlofinData VALUES (?, ?, ?, ?, ?, ?, ?)',
                              (s, bar[0], bar[1], bar[2], bar[3], bar[4], bar[5]))
                conn.commit()
                print(f"✅ Saved {len(ohlcv)} bars for {s}.")
            else:
                print(f"⚠️ No data returned for {s}.")
                
        except Exception as e:
            print(f"❌ Error for {s}: {e}")
            
    conn.close()
    print("\n🏆 Blofin Data Caching Complete.")

if __name__ == "__main__":
    main()
