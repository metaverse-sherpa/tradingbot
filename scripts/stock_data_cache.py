import requests
import sqlite3
import time
import os
import argparse
from datetime import datetime
from dotenv import load_dotenv

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils_gcp

load_dotenv()

# 🏔️ Sherpa Stock Basket (Expanded)
SYMBOLS = [
    "AAPL", "GOOGL", "META", "NVDA", "AMZN", "TSLA", "MSFT", "QQQ", "SPY", "ARM",
    "MRVL", "CRWD", "LITE", "XLE", "USO", "MU", "ORCL", "QCOM", "AMD", "AVGO", 
    "IWM", "TSM", "PYPL", "EWJ", "PLTR", "COIN", "MSTR", "HOOD", "INTC"
]
DB_PATH = "data/stock_cache.db"

def init_db():
    """Initializes the local stock database."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS StockData
                 (symbol TEXT, timestamp INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL,
                  PRIMARY KEY (symbol, timestamp))''')
    conn.commit()
    conn.close()

def fetch_stock_data(ticker, api_key, api_secret, start_date="2026-03-01"):
    """Fetches 15m intraday data from Alpaca."""
    print(f"🛰️ Fetching 15m data for {ticker} starting from {start_date}...")
    
    url = f"https://data.alpaca.markets/v2/stocks/bars"
    params = {
        "symbols": ticker,
        "timeframe": "15Min",
        "start": start_date,
        "adjustment": "all"
    }
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data.get('bars', {}).get(ticker, [])
        else:
            print(f"❌ Error fetching {ticker}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Critical failure for {ticker}: {e}")
        return None

def save_to_db(ticker, data):
    """Saves OHLCV data to local SQLite database."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    count = 0
    for bar in data:
        # Convert Alpaca ISO timestamp to unix ms
        ts = int(datetime.fromisoformat(bar['t'].replace('Z', '+00:00')).timestamp() * 1000)
        
        try:
            c.execute('INSERT OR IGNORE INTO StockData (symbol, timestamp, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)',
                      (ticker, ts, bar['o'], bar['h'], bar['l'], bar['c'], bar['v']))
            count += 1
        except: pass
        
    conn.commit()
    conn.close()
    print(f"✅ Saved {count} new bars for {ticker}.")

def main():
    parser = argparse.ArgumentParser(description="Sherpa Stock Data Cacher")
    parser.add_argument("--key", default=utils_gcp.get_secret("ALPACA_API_KEY"), help="Your Alpaca API Key ID (defaults to GCP/env)")
    parser.add_argument("--secret", default=utils_gcp.get_secret("ALPACA_API_SECRET"), help="Your Alpaca API Secret Key (defaults to GCP/env)")
    parser.add_argument("--start", default="2023-01-01", help="Start date (YYYY-MM-DD)")
    args = parser.parse_args()

    if not args.key or not args.secret:
        print("❌ Error: ALPACA_API_KEY or ALPACA_API_SECRET not found in .env or provided via args.")
        return

    init_db()
    
    print("🏔️ Starting Institutional Stock Data Caching...")
    print(f"Target Symbols: {', '.join(SYMBOLS)}")
    
    for i, ticker in enumerate(SYMBOLS):
        data = fetch_stock_data(ticker, args.key, args.secret, args.start)
        if data:
            save_to_db(ticker, data)
        
        # 🛡️ Rate Limit Shield: Respect Alpaca's 200 calls/min limit
        if i < len(SYMBOLS) - 1:
            print("⏳ Respecting Alpaca Rate Limits (0.35s cooldown)...")
            time.sleep(0.35)

    print("\n🏆 Caching Complete. Data stored in data/stock_cache.db")

if __name__ == "__main__":
    main()
