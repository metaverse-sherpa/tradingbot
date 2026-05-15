import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Blofin Deep Fetcher Config
# ---------------------------------------------------------------------------
BASE_URL = "https://openapi.blofin.com"
ENDPOINT = "/api/v1/market/candles"
CSV_DIR  = "csv_blofin"
LIMIT    = 1440  # Max per request
TIMEFRAME = "15m"

# 20 Symbols from Production live_bot_multi.py
SYMBOLS = [
    "BTC", "ETH", "SOL", "DOGE", "ADA", "LINK", "DOT", "TON", "ZEC", "PEPE",
    "BNB", "NEAR", "SUI", "NOT", "TAO", "ONDO", "ENA", "FET", "WIF", "SHIB"
]

os.makedirs(CSV_DIR, exist_ok=True)

def fetch_candles(symbol, before_ts=None):
    """Fetch one batch of 1440 candles."""
    params = {
        "instId": f"{symbol}-USDT",
        "bar": TIMEFRAME,
        "limit": LIMIT
    }
    if before_ts:
        params["after"] = before_ts
    
    url = f"{BASE_URL}{ENDPOINT}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == "0":
            return data.get("data", [])
        else:
            print(f"  [!] API Error for {symbol}: {data}")
            return []
    except Exception as e:
        print(f"  [!] Request Error: {e}")
        return []

def scrape_symbol(symbol, target_years=3):
    """Scrape up to X years of history for a symbol."""
    print(f"🚀 Deep Scraping {symbol}...")
    
    all_data = []
    # Approx bars needed: 3 years * 365 days * 24 hours * 4 bars/hr
    target_bars = target_years * 365 * 24 * 4
    
    before_ts = None
    total_fetched = 0
    
    while total_fetched < target_bars:
        batch = fetch_candles(symbol, before_ts)
        if not batch:
            print(f"  [√] Reached end of history for {symbol} at {total_fetched} bars.")
            break
        
        all_data.extend(batch)
        total_fetched += len(batch)
        
        # The API returns bars in DESCENDING order (newest first)
        # before_ts should be the timestamp of the OLDEST bar in the batch
        # data format: [ts, o, h, l, c, v, vol, volCurrency, state]
        oldest_bar_ts = batch[-1][0]
        before_ts = oldest_bar_ts
        
        print(f"  [+] Fetched {total_fetched}/{target_bars} bars... (Oldest: {datetime.fromtimestamp(int(oldest_bar_ts)/1000, tz=timezone.utc).strftime('%Y-%m-%d')})")
        
        # Respect rate limits (500/min)
        time.sleep(0.2) 
        
    if not all_data:
        return

    # Process into DataFrame
    # Columns: [ts, o, h, l, c, v, vol, volCurrency, state]
    df = pd.DataFrame(all_data, columns=["ts", "open", "high", "low", "close", "v_base", "v_quote", "v_curr", "state"])
    df["datetime"] = pd.to_datetime(df["ts"].astype(float), unit='ms')
    df = df.set_index("datetime").sort_index()
    
    # Cast to float
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    
    # Save to CSV
    save_path = os.path.join(CSV_DIR, f"blofin_{symbol}_15m.csv")
    df[["open", "high", "low", "close"]].to_csv(save_path)
    print(f"  [SUCCESS] Saved {len(df)} bars to {save_path}\n")

def run():
    print("="*60)
    print(" 🏔️  METAVERSE SHERPA: DEEP BLOFIN SCRAPER")
    print("="*60)
    for s in SYMBOLS:
        scrape_symbol(s)
        time.sleep(1) # Gap between symbols

if __name__ == "__main__":
    run()
