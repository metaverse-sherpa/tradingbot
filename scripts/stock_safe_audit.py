import sqlite3
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

# 🏛️ Safe Diversified Power Audit (29 Symbols / 1.5-Year History)
INITIAL_CASH = 10000.0
PCT_PER_TRADE = 0.03 # Restoring safety
LEVERAGE = 5
DB_PATH = "data/stock_cache.db"
SYMBOLS = [
    "AAPL", "GOOGL", "META", "NVDA", "AMZN", "TSLA", "MSFT", "QQQ", "SPY", "ARM",
    "MRVL", "CRWD", "LITE", "XLE", "USO", "MU", "ORCL", "QCOM", "AMD", "AVGO", 
    "IWM", "TSM", "PYPL", "EWJ", "PLTR", "COIN", "MSTR", "HOOD", "INTC"
]
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
    all_data = {s: calculate_indicators(pd.read_sql_query(f"SELECT * FROM StockData WHERE symbol = '{s}' ORDER BY timestamp ASC", conn).assign(timestamp=lambda d: pd.to_datetime(d['timestamp'], unit='ms')).set_index('timestamp'), SUPERTREND_CONFIG) for s in SYMBOLS}
    conn.close()
    
    cdf = pd.concat(all_data.values(), axis=1, keys=all_data.keys()).sort_index().ffill()
    cash, active, history, wins, losses = INITIAL_CASH, {}, [], 0, 0
    
    for ts, row in cdf.iterrows():
        equity = cash + sum((t['notional'] * ((row[s]['close']-t['entry'])/t['entry'] if t['type']=="LONG" else (t['entry']-row[s]['close'])/t['entry'])) for s,t in active.items())
        history.append({"ts": ts, "equity": equity})
        
        to_close = [s for s,t in active.items() if (t['type']=="LONG" and not row[s]['supertrend']) or (t['type']=="SHORT" and row[s]['supertrend'])]
        for s in to_close:
            t = active.pop(s)
            p = (row[s]['open']-t['entry'])/t['entry'] if t['type']=="LONG" else (t['entry']-row[s]['open'])/t['entry']
            pnl = (t['notional'] * p) - (t['notional'] * FEE_RATE * 2)
            cash += pnl
            if pnl > 0: wins += 1
            else: losses += 1

        for s in SYMBOLS:
            if s not in active:
                if 13 <= ts.hour <= 20: # NYSE Hours
                    p_bar = cdf.loc[:ts].iloc[-2][s] if len(cdf.loc[:ts]) > 1 else None
                    if p_bar is not None:
                        t_type = "LONG" if row[s]['supertrend'] and not p_bar['supertrend'] and row[s]['close'] > row[s]['ema_200'] else ("SHORT" if not row[s]['supertrend'] and p_bar['supertrend'] and row[s]['close'] < row[s]['ema_200'] else None)
                        if t_type: active[s] = {"type": t_type, "entry": row[s]['close'], "notional": equity * PCT_PER_TRADE * LEVERAGE, "time": ts}

    h = pd.DataFrame(history).set_index('ts')
    daily_rets = h['equity'].resample('D').last().pct_change().dropna()
    sharpe = (daily_rets.mean() / (daily_rets.std() + 1e-10)) * np.sqrt(252)
    dd = (h['equity'].expanding().max() - h['equity']) / h['equity'].expanding().max()
    
    total_t = wins + losses
    print("\n" + "═"*70)
    print(f"🌍 SAFE DIVERSIFIED POWER AUDIT (29 Symbols / 1.5-Year)")
    print("═"*70)
    print(f"Final Balance     : ${h['equity'].iloc[-1]:,.2f}")
    print(f"Total PnL %       : {(h['equity'].iloc[-1]/INITIAL_CASH - 1)*100:.2f}%")
    print(f"Max Drawdown      : {dd.max():.2%}")
    print(f"Sharpe Ratio      : {sharpe:.2f}")
    print(f"Win Rate          : {(wins/total_t*100):.1f}%")
    print(f"Avg Trades/Day    : {total_t / ((h.index[-1]-h.index[0]).days * (5/7)):.2f}")
    print("═"*70)

    plt.figure(figsize=(12, 6))
    plt.plot(h.index, h['equity'], color='#16a085', linewidth=2)
    plt.title('Safe Diversified Power Curve (29 Symbols)', fontweight='bold')
    plt.tight_layout()
    plt.savefig('safe_diversified_audit.png')

if __name__ == "__main__":
    main()
