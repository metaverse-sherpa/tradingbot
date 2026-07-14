import sys
sys.path.append('.')
import charting
import pandas as pd
import sqlite3
import traceback

conn = sqlite3.connect("data/stock_daily_cache.db")
df_chart = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = 'INTC' ORDER BY date ASC", conn)
df_chart['timestamp'] = pd.to_datetime(df_chart['date']).astype('datetime64[ms]').astype('int64')

try:
    res = charting.generate_trade_chart("INTC", df_chart, 0.0, 0.0, 0.0, "LONG", 0, "1D", "USDT", 0.0, "")
    print("Result:", res)
except Exception as e:
    traceback.print_exc()
