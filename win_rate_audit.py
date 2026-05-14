import sqlite3
import pandas as pd
import numpy as np
import os

# 🏛️ Symbol-by-Symbol Win Rate Audit (H1 / 5x / 10%)
INITIAL_CASH = 10000.0
PCT_PER_TRADE = 0.10 
LEVERAGE = 5
DB_PATH = "data/blofin_stock_cache.db"
SUPERTREND_CONFIG = {"period": 10, "multiplier": 4, "ema_trend": 200}
FEE_RATE = 0.0006 

def calculate_indicators(df, cfg):
    df = df.resample('1h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    df['ema_200'] = df['close'].ewm(span=cfg['ema_trend'], adjust=False).mean()
    atr = (pd.concat([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())], axis=1).max(axis=1)).rolling(10).mean()
    hl2 = (df['high'] + df['low']) / 2
    f_up, f_low, st = hl2 + (cfg['multiplier'] * atr), hl2 - (cfg['multiplier'] * atr), [True] * len(df)
    for i in range(1, len(df)):
        f_low.iloc[i] = max(f_low.iloc[i], f_low.iloc[i-1]) if df['close'].iloc[i-1] > f_low.iloc[i-1] else f_low.iloc[i]
        f_up.iloc[i] = min(f_up.iloc[i], f_up.iloc[i-1]) if df['close'].iloc[i-1] < f_up.iloc[i-1] else f_up.iloc[i]
        st[i] = True if df['close'].iloc[i] > f_up.iloc[i] else (False if df['close'].iloc[i] < f_low.iloc[i] else st[i-1])
    df['supertrend'] = st
    return df

def main():
    conn = sqlite3.connect(DB_PATH)
    symbols = [row[0] for row in conn.execute("SELECT DISTINCT symbol FROM BlofinData").fetchall()]
    all_data = {s: calculate_indicators(pd.read_sql_query(f"SELECT * FROM BlofinData WHERE symbol = '{s}' ORDER BY timestamp ASC", conn).assign(timestamp=lambda d: pd.to_datetime(d['timestamp'], unit='ms')).set_index('timestamp'), SUPERTREND_CONFIG) for s in symbols}
    conn.close()
    
    cdf = pd.concat(all_data.values(), axis=1, keys=all_data.keys()).sort_index().ffill()
    cash, active, history = INITIAL_CASH, {}, []
    symbol_stats = {s: {'wins': 0, 'losses': 0, 'pnl': 0} for s in symbols}
    
    for ts, row in cdf.iterrows():
        equity = cash + sum((t['notional'] * ((row[s]['close']-t['entry'])/t['entry'] if t['type']=="LONG" else (t['entry']-row[s]['close'])/t['entry'])) for s,t in active.items())
        history.append({"ts": ts, "equity": equity})
        
        to_close = [s for s,t in active.items() if (t['type']=="LONG" and not row[s]['supertrend']) or (t['type']=="SHORT" and row[s]['supertrend'])]
        for s in to_close:
            t = active.pop(s)
            p = (row[s]['open']-t['entry'])/t['entry'] if t['type']=="LONG" else (t['entry']-row[s]['open'])/t['entry']
            pnl = (t['notional'] * p) - (t['notional'] * FEE_RATE * 2)
            cash += pnl
            if pnl > 0: symbol_stats[s]['wins'] += 1
            else: symbol_stats[s]['losses'] += 1
            symbol_stats[s]['pnl'] += pnl

        for s in symbols:
            if s not in active:
                # 🕵️ NYSE Market Hours Filter
                if 13 <= ts.hour <= 20:
                    p_bar = cdf.loc[:ts].iloc[-2][s] if len(cdf.loc[:ts]) > 1 else None
                    if p_bar is not None:
                        t_type = "LONG" if row[s]['supertrend'] and not p_bar['supertrend'] and row[s]['close'] > row[s]['ema_200'] else ("SHORT" if not row[s]['supertrend'] and p_bar['supertrend'] and row[s]['close'] < row[s]['ema_200'] else None)
                        if t_type: active[s] = {"type": t_type, "entry": row[s]['close'], "notional": equity * PCT_PER_TRADE * LEVERAGE, "time": ts}

    print("\n" + "═"*70)
    print(f"{'SYMBOL':<10} | {'WIN RATE':<10} | {'TRADES':<8} | {'NET PNL':<10}")
    print("═"*70)
    
    sorted_stats = sorted(symbol_stats.items(), key=lambda x: (x[1]['wins']/(x[1]['wins']+x[1]['losses']) if (x[1]['wins']+x[1]['losses']) > 0 else 0), reverse=True)
    
    for s, st in sorted_stats:
        total = st['wins'] + st['losses']
        wr = (st['wins'] / total * 100) if total > 0 else 0
        if total > 0:
            print(f"{s:<10} | {wr:>8.1f}% | {total:<8} | ${st['pnl']:>9.2f}")
    
    print("═"*70)

if __name__ == "__main__":
    main()
