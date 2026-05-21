import os
import ccxt
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from dotenv import load_dotenv

def main():
    load_dotenv()
    print("🚀 Starting Full 29-Symbol Variance Audit (Since March 1, 2026)...")
    
    # 1. Initialize Blofin Client
    exchange = ccxt.blofin({
        'apiKey': os.getenv('BLOFIN_API_LOCAL_KEY'),
        'secret': os.getenv('BLOFIN_API_LOCAL_SECRET'),
        'password': os.getenv('BLOFIN_API_PASSWORD'),
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })
    
    symbols = [
        "AAPL", "GOOGL", "META", "NVDA", "AMZN", "TSLA", "MSFT", "QQQ", "SPY", "ARM",
        "MRVL", "CRWD", "LITE", "XLE", "USO", "MU", "ORCL", "QCOM", "AMD", "AVGO", 
        "IWM", "TSM", "PYPL", "EWJ", "PLTR", "COIN", "MSTR", "HOOD", "INTC"
    ]
    
    # March 1, 2026 timestamp (approx)
    start_ts = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp() * 1000)
    
    conn = sqlite3.connect('data/stock_cache.db')
    results = []

    print(f"{'SYMBOL':<10} | {'SAMPLES':<8} | {'AVG VAR %':<12} | {'MAX VAR %':<12}")
    print("═"*55)
    
    for s in symbols:
        try:
            blofin_sym = f"{s}/USDT:USDT"
            # Fetch Blofin history (Blofin usually allows 1000-1440 bars)
            ohlcv = exchange.fetch_ohlcv(blofin_sym, timeframe='15m', since=start_ts, limit=1440)
            if not ohlcv:
                print(f"{s:<10} | No data returned from Blofin.")
                continue
                
            b_df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Fetch synced Tiingo data
            min_ts, max_ts = b_df['timestamp'].min(), b_df['timestamp'].max()
            t_df = pd.read_sql_query(f"SELECT timestamp, close FROM StockData WHERE symbol = '{s}' AND timestamp >= {min_ts} AND timestamp <= {max_ts}", conn)
            
            # Merge and Compare
            merged = pd.merge(b_df[['timestamp', 'close']], t_df, on='timestamp', suffixes=('_blofin', '_tiingo'))
            
            if not merged.empty:
                merged['variance'] = abs(merged['close_blofin'] - merged['close_tiingo']) / merged['close_tiingo'] * 100
                avg_v, max_v = merged['variance'].mean(), merged['variance'].max()
                results.append({'s': s, 'avg': avg_v, 'max': max_v, 'count': len(merged)})
                print(f"{s:<10} | {len(merged):<8} | {avg_v:>10.4f}% | {max_v:>10.4f}%")
            else:
                print(f"{s:<10} | No synced Tiingo data.")
                
        except Exception as e:
            # print(f"{s:<10} | Error: {str(e)[:50]}")
            pass
            
    conn.close()
    
    if results:
        df_res = pd.DataFrame(results)
        print("═"*55)
        print(f"🌍 PORTFOLIO TRACKING SUMMARY")
        print(f"Overall Avg Variance : {df_res['avg'].mean():.4f}%")
        print(f"Worst Tracker        : {df_res.loc[df_res['avg'].idxmax()]['s']} ({df_res['avg'].max():.4f}%)")
        print(f"Best Tracker         : {df_res.loc[df_res['avg'].idxmin()]['s']} ({df_res['avg'].min():.4f}%)")
        print("═"*55)

if __name__ == "__main__":
    main()
