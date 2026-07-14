import yfinance as yf
import pandas as pd

symbol = "FIG"
try:
    tkr = yf.Ticker(symbol)
    yf_df = tkr.history(period="3mo")
    if not yf_df.empty:
        yf_df.reset_index(inplace=True)
        yf_df.columns = [c.lower() for c in yf_df.columns]
        if 'date' in yf_df.columns:
            yf_df.rename(columns={'date': 'timestamp'}, inplace=True)
        if 'datetime' in yf_df.columns:
            yf_df.rename(columns={'datetime': 'timestamp'}, inplace=True)
        yf_df['timestamp'] = pd.to_datetime(yf_df['timestamp']).astype('datetime64[ms]').astype('int64')
        print(yf_df.head())
    else:
        print("Empty yf_df")
except Exception as e:
    print(f"yfinance fallback failed for chart: {e}")
