import sys
sys.path.append('.')
import charting
import pandas as pd
import traceback

dates = pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D')
entry = 0.0
df_chart = pd.DataFrame({
    'timestamp': dates.astype('datetime64[ms]').astype('int64'),
    'open': [entry] * 30,
    'high': [entry * 1.01] * 30,
    'low': [entry * 0.99] * 30,
    'close': [entry] * 30,
    'volume': [1000] * 30
})

try:
    res = charting.generate_trade_chart("INTC", df_chart, 0.0, 0.0, 0.0, "LONG", 0, "1D", "USDT", 0.0, "")
    print("Result:", res)
except Exception as e:
    traceback.print_exc()
