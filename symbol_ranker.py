import sqlite3
import pandas as pd
import numpy as np

DB_PATH = "data/stock_cache.db"
SYMBOLS = ["AAPL", "GOOGL", "META", "NVDA", "AMZN", "TSLA", "MSFT", "QQQ", "SPY", "ARM", "MRVL", "CRWD", "LITE", "XLE", "USO", "MU", "ORCL", "QCOM", "AMD", "AVGO", "IWM", "TSM", "PYPL", "EWJ", "PLTR", "COIN", "MSTR", "HOOD", "INTC"]
CFG = {"period": 10, "multiplier": 3, "ema_trend": 200}
FEE_RATE = 0.0006

def audit_symbol(s):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM StockData WHERE symbol = '{s}' ORDER BY timestamp ASC", conn)
    conn.close()
    if df.empty: return None
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df.resample('15min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    df['ema_200'] = df['close'].ewm(span=CFG['ema_trend'], adjust=False).mean()
    atr = (pd.concat([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())], axis=1).max(axis=1)).rolling(10).mean()
    hl2 = (df['high'] + df['low']) / 2
    f_up, f_low, st = hl2 + (3 * atr), hl2 - (3 * atr), [True] * len(df)
    for i in range(1, len(df)):
        f_low.iloc[i] = max(f_low.iloc[i], f_low.iloc[i-1]) if df['close'].iloc[i-1] > f_low.iloc[i-1] else f_low.iloc[i]
        f_up.iloc[i] = min(f_up.iloc[i], f_up.iloc[i-1]) if df['close'].iloc[i-1] < f_up.iloc[i-1] else f_up.iloc[i]
        st[i] = True if df['close'].iloc[i] > f_up.iloc[i] else (False if df['close'].iloc[i] < f_low.iloc[i] else st[i-1])
    df['st'] = st
    pnl, trades, wins = 0, 0, 0
    active = None
    for i in range(1, len(df)):
        row, p_row = df.iloc[i], df.iloc[i-1]
        if active:
            if (active['type']=='LONG' and not row['st']) or (active['type']=='SHORT' and row['st']):
                p = (row['open']-active['entry'])/active['entry'] if active['type']=='LONG' else (active['entry']-row['open'])/active['entry']
                p_val = (100 * p) - (100 * FEE_RATE * 2) # Normalized $100 notional
                pnl += p_val
                trades += 1
                if p_val > 0: wins += 1
                active = None
        if not active:
            t_type = "LONG" if row['st'] and not p_row['st'] and row['close'] > row['ema_200'] else ("SHORT" if not row['st'] and p_row['st'] and row['close'] < row['ema_200'] else None)
            if t_type: active = {"type": t_type, "entry": row['close']}
    return {'pnl': pnl, 'trades': trades, 'wr': (wins/trades*100) if trades>0 else 0}

results = []
for s in SYMBOLS:
    res = audit_symbol(s)
    if res: results.append((s, res['pnl'], res['trades'], res['wr']))

print(f"{'SYMBOL':<10} | {'PNL ($100 Not)':<15} | {'TRADES':<8} | {'WIN RATE':<10}")
for s, p, t, wr in sorted(results, key=lambda x: x[1], reverse=True):
    print(f"{s:<10} | {p:>15.2f} | {t:<8} | {wr:>8.1f}%")
