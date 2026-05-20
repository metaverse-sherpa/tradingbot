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
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS StockDailyData
                 (symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
                  PRIMARY KEY (symbol, date))''')
    conn.commit()
    conn.close()

def fetch_daily_data(ticker, api_key, start_date="2023-05-19", end_date="2026-05-19"):
    """Fetches daily historical prices from Tiingo daily endpoint using adjusted columns."""
    print(f"🛰️ Fetching daily data for {ticker} from {start_date} to {end_date}...")
    url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
    params = {
        "startDate": start_date,
        "endDate": end_date,
        "token": api_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
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
        date_str = bar['date'].split('T')[0]
        
        # VERY IMPORTANT: Use adjusted prices to avoid splits/dividends distortion
        open_val = bar.get('adjOpen', bar['open'])
        high_val = bar.get('adjHigh', bar['high'])
        low_val = bar.get('adjLow', bar['low'])
        close_val = bar.get('adjClose', bar['close'])
        vol_val = bar.get('adjVolume', bar['volume'])
        
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

def main():
    api_key = os.getenv("TIINGO_API_KEY")
    if not api_key:
        print("❌ Error: TIINGO_API_KEY not found in .env.")
        return

    init_db()
    print("🏔️ Starting Daily Stock Data Caching (Last 3 Years)...")
    print(f"Target Symbols: {', '.join(SYMBOLS)}")
    
    for i, ticker in enumerate(SYMBOLS):
        data = fetch_daily_data(ticker, api_key)
        if data:
            save_to_db(ticker, data)
        else:
            print(f"⚠️ Failed to fetch data for {ticker}")
            
        # Respect Tiingo rate limits (small sleep)
        if i < len(SYMBOLS) - 1:
            time.sleep(1)

    print(f"\n🏆 Daily Caching Complete. Data stored in {DB_PATH}")

if __name__ == "__main__":
    main()
