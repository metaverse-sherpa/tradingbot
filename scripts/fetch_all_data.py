import ccxt
import pandas as pd
import os
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CSV_DIR = "csv"
os.makedirs(CSV_DIR, exist_ok=True)
DAYS_BACK = 3 * 365

# The 19 symbols from live_bot_multi.py
SYMBOLS = {
    "BTC/USDT":  "BTC",
    "ETH/USDT":  "ETH",
    "SOL/USDT":  "SOL",
    "DOGE/USDT": "DOGE",
    "ADA/USDT":  "ADA",
    "LINK/USDT": "LINK",
    "DOT/USDT":  "DOT",
    "TON/USDT":  "TON",
    "ZEC/USDT":  "ZEC",
    "PEPE/USDT": "PEPE",
    "BNB/USDT":  "BNB",
    "NEAR/USDT": "NEAR",
    "SUI/USDT":  "SUI",
    "NOT/USDT":  "NOT",
    "TAO/USDT":  "TAO",
    "ONDO/USDT": "ONDO",
    "ENA/USDT":  "ENA",
    "FET/USDT":  "FET",
    "WIF/USDT":  "WIF",
}

def fetch_data():
    exchange = ccxt.binance({"enableRateLimit": True})
    print("=" * 60)
    print(f"  Fetching 3yr Data for {len(SYMBOLS)} Symbols")
    print("=" * 60)

    for sym, name in SYMBOLS.items():
        cache_file = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")
        if os.path.exists(cache_file):
            print(f"  {name:<5}: Already cached.")
            continue

        print(f"  {name:<5}: Downloading...", end="", flush=True)
        end_ms = exchange.milliseconds()
        start_ms = end_ms - DAYS_BACK * 24 * 60 * 60 * 1000
        all_rows = []
        current = start_ms

        while current < end_ms:
            try:
                ohlcv = exchange.fetch_ohlcv(sym, "15m", since=current, limit=1000)
                if not ohlcv: break
                all_rows.extend(ohlcv)
                current = ohlcv[-1][0] + 15 * 60 * 1000
                time.sleep(0.1)
            except Exception as e:
                print(f"\n    Error: {e} - retrying")
                time.sleep(2)

        if not all_rows:
            print(" NO DATA")
            continue

        df = pd.DataFrame(all_rows, columns=["timestamp","open","high","low","close","volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("datetime", inplace=True)
        df = df[~df.index.duplicated(keep="first")]
        df.to_csv(cache_file)
        print(f" {len(df):,} bars ({df.index[0].date()} -> {df.index[-1].date()})")

if __name__ == "__main__":
    fetch_data()
