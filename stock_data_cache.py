import requests
import sqlite3
import time
import os
import argparse
from datetime import datetime
from dotenv import load_dotenv

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

def fetch_stock_data(ticker, api_key, start_date="2026-03-01"):
    """Fetches 15m intraday data from Tiingo IEX endpoint."""
    print(f"🛰️ Fetching 15m data for {ticker} starting from {start_date}...")
    
    # Tiingo IEX Intraday Endpoint
    url = f"https://api.tiingo.com/iex/{ticker}/prices"
    params = {
        "startDate": start_date,
        "resampleFreq": "15min",
        "token": api_key,
        "columns": "open,high,low,close,volume"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data
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
        # Convert Tiingo ISO timestamp to unix ms
        ts = int(datetime.fromisoformat(bar['date'].replace('Z', '+00:00')).timestamp() * 1000)
        
        try:
            c.execute('INSERT OR IGNORE INTO StockData (symbol, timestamp, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)',
                      (ticker, ts, bar['open'], bar['high'], bar['low'], bar['close'], bar['volume']))
            count += 1
        except: pass
        
    conn.commit()
    conn.close()
    print(f"✅ Saved {count} new bars for {ticker}.")

def main():
    parser = argparse.ArgumentParser(description="Sherpa Stock Data Cacher")
    parser.add_argument("--key", default=os.getenv("TIINGO_API_KEY"), help="Your Tiingo API Key (defaults to .env)")
    parser.add_argument("--start", default="2023-01-01", help="Start date (YYYY-MM-DD)")
    args = parser.parse_args()

    if not args.key:
        print("❌ Error: TIINGO_API_KEY not found in .env or provided via --key.")
        return

    init_db()
    
    print("🏔️ Starting Institutional Stock Data Caching...")
    print(f"Target Symbols: {', '.join(SYMBOLS)}")
    
    for i, ticker in enumerate(SYMBOLS):
        data = fetch_stock_data(ticker, args.key, args.start)
        if data:
            save_to_db(ticker, data)
        
        # 🛡️ Rate Limit Shield: Respect the 5-calls-per-minute limit
        if i < len(SYMBOLS) - 1:
            print("⏳ Respecting Tiingo Rate Limits (12s cooldown)...")
            time.sleep(12)

    print("\n🏆 Caching Complete. Data stored in data/stock_cache.db")

if __name__ == "__main__":
    main()
