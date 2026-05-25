import os
import requests
import sqlite3
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Expanded list of 40 Momentum-Growth Symbols
SYMBOLS = [
    # Technology & Megacap growth (15)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "AVGO", "TSM", "NFLX", "AMD", "QCOM", "ORCL", "CRM", "META", "ANET", "NOW",
    # Semiconductors & Tech Hardware (4)
    "ASML", "MU", "LRCX", "PANW",
    # Financials & Tech Hardware (4)
    "GS", "MS", "CSCO", "AXP",
    # Consumer Discretionary & Retail (5)
    "WMT", "COST", "CMG", "TJX", "MELI",
    # Industrials & Infrastructure (5)
    "GE", "CAT", "ETN", "URI", "PH",
    # Healthcare & Biotech (4)
    "LLY", "JNJ", "VRTX", "ISRG",
    # Energy (3)
    "XOM", "CVX", "COP"
]
DB_PATH = "data/stock_daily_cache.db"

def init_db():
    """Initializes the local daily stock database."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    actual_db_path = os.path.join(data_dir, "stock_daily_cache.db")
    
    os.makedirs(data_dir, exist_ok=True)
    conn = sqlite3.connect(actual_db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS StockDailyData
                 (symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
                  PRIMARY KEY (symbol, date))''')
    conn.commit()
    conn.close()

def fetch_daily_data(ticker, api_key, api_secret, start_date="2023-05-19", end_date="2026-05-19"):
    """Fetches daily historical prices from Alpaca daily endpoint using adjusted columns."""
    print(f"🛰️ Fetching daily data for {ticker} from {start_date} to {end_date}...")
    url = f"https://data.alpaca.markets/v2/stocks/bars"
    # Ensure start/end dates are RFC-3339 for Alpaca if needed, but YYYY-MM-DD usually works.
    params = {
        "symbols": ticker,
        "timeframe": "1Day",
        "start": start_date,
        "end": end_date,
        "adjustment": "all" # Splits and dividends
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
    """Saves adjusted OHLCV daily data to SQLite."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    count = 0
    for bar in data:
        # Extract date string (YYYY-MM-DD)
        date_str = bar['t'].split('T')[0]
        
        # Alpaca already provides adjusted prices when adjustment='all' is passed
        open_val = bar['o']
        high_val = bar['h']
        low_val = bar['l']
        close_val = bar['c']
        vol_val = bar['v']
        
        try:
            c.execute('''INSERT OR REPLACE INTO StockDailyData 
                         (symbol, date, open, high, low, close, volume) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (ticker, date_str, open_val, high_val, low_val, close_val, vol_val))
            count += 1
        except Exception as e:
            print(f"Error inserting bar: {e}")
            
    conn.commit()
    conn.close()
    print(f"✅ Saved {count} adjusted daily bars for {ticker}.")

import utils_gcp

def main():
    api_key = utils_gcp.get_secret("alpaca-api-key")
    api_secret = utils_gcp.get_secret("alpaca-api-secret")
    if not api_key or not api_secret:
        print("❌ Error: ALPACA_API_KEY or ALPACA_API_SECRET not found in .env.")
        return

    init_db()
    print("🏔️ Starting Daily Stock Data Caching (Last 3 Years)...")
    print(f"Target Symbols: {', '.join(SYMBOLS)}")
    
    for i, ticker in enumerate(SYMBOLS):
        data = fetch_daily_data(ticker, api_key, api_secret)
        if data:
            save_to_db(ticker, data)
        else:
            print(f"⚠️ Failed to fetch data for {ticker}")
            
        # Respect Alpaca rate limits (200/min on free tier)
        if i < len(SYMBOLS) - 1:
            time.sleep(0.35)

    print(f"\n🏆 Daily Caching Complete. Data stored in {DB_PATH}")

if __name__ == "__main__":
    main()
