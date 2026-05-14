import sqlite3
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

# 🏛️ High-Confidence Precision Audit (29 Symbols / 1.5-Year)
INITIAL_CASH = 10000.0
PCT_PER_TRADE = 0.025 # Safe Institutional Level
LEVERAGE = 5
DB_PATH = "data/stock_cache.db"
SYMBOLS = [
    "AAPL", "GOOGL", "META", "NVDA", "AMZN", "TSLA", "MSFT", "QQQ", "SPY", "ARM",
    "MRVL", "CRWD", "LITE", "XLE", "USO", "MU", "ORCL", "QCOM", "AMD", "AVGO", 
    "IWM", "TSM", "PYPL", "EWJ", "PLTR", "COIN", "MSTR", "HOOD", "INTC"
]
FEE_RATE = 0.0006 

def calculate_indicators(df):
    df = df.resample('1h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    
    # 1. EMA & RSI
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 2. ADX (Trend Strength)
    plus_dm = df['high'].diff().where(lambda x: (x > 0) & (x > -df['low'].diff()), 0)
    minus_dm = (-df['low'].diff()).where(lambda x: (x > 0) & (x > df['high'].diff()), 0)
    tr = pd.concat([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / (atr_14 + 1e-10))
    minus_di = 100 * (minus_dm.rolling(14).mean() / (atr_14 + 1e-10))
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    df['adx'] = dx.rolling(14).mean()
    
    # 3. SuperTrend (Hardened Multiplier 4)
    multiplier = 4
    period = 10
    atr = tr.rolling(period).mean()
    hl2 = (df['high'] + df['low']) / 2
    f_up, f_low, st = hl2 + (multiplier * atr), hl2 - (multiplier * atr), [True] * len(df)
    for i in range(1, len(df)):
        f_low.iloc[i] = max(f_low.iloc[i], f_low.iloc[i-1]) if df['close'].iloc[i-1] > f_low.iloc[i-1] else f_low.iloc[i]
        f_up.iloc[i] = min(f_up.iloc[i], f_up.iloc[i-1]) if df['close'].iloc[i-1] < f_up.iloc[i-1] else f_up.iloc[i]
        st[i] = True if df['close'].iloc[i] > f_up.iloc[i] else (False if df['close'].iloc[i] < f_low.iloc[i] else st[i-1])
    df['supertrend'] = st
    return df

def main():
    conn = sqlite3.connect(DB_PATH)
    all_data = {s: calculate_indicators(pd.read_sql_query(f"SELECT * FROM StockData WHERE symbol = '{s}' ORDER BY timestamp ASC", conn).assign(timestamp=lambda d: pd.to_datetime(d['timestamp'], unit='ms')).set_index('timestamp')) for s in SYMBOLS}
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
                if 13 <= ts.hour <= 20: # Market Hours
                    p_bar = cdf.loc[:ts].iloc[-2][s] if len(cdf.loc[:ts]) > 1 else None
                    if p_bar is not None:
                        # 🕵️ Triple Confirmation Entry Logic
                        st_flip_long = row[s]['supertrend'] and not p_bar['supertrend']
                        st_flip_short = not row[s]['supertrend'] and p_bar['supertrend']
                        
                        trend_strong = row[s]['adx'] > 25 # Strong Trend Confirmation
                        
                        if st_flip_long and trend_strong and row[s]['rsi'] > 50 and row[s]['close'] > row[s]['ema_200']:
                            active[s] = {"type": "LONG", "entry": row[s]['close'], "notional": equity * PCT_PER_TRADE * LEVERAGE, "time": ts}
                        elif st_flip_short and trend_strong and row[s]['rsi'] < 50 and row[s]['close'] < row[s]['ema_200']:
                            active[s] = {"type": "SHORT", "entry": row[s]['close'], "notional": equity * PCT_PER_TRADE * LEVERAGE, "time": ts}

    h = pd.DataFrame(history).set_index('ts')
    daily_rets = h['equity'].resample('D').last().pct_change().dropna()
    sharpe = (daily_rets.mean() / (daily_rets.std() + 1e-10)) * np.sqrt(252)
    dd = (h['equity'].expanding().max() - h['equity']) / h['equity'].expanding().max()
    
    total_t = wins + losses
    print("\n" + "═"*70)
    print(f"🌍 HIGH-CONFIDENCE PRECISION AUDIT (29 Symbols / 1.5-Year)")
    print("═"*70)
    print(f"Final Balance     : ${h['equity'].iloc[-1]:,.2f}")
    print(f"Total PnL %       : {(h['equity'].iloc[-1]/INITIAL_CASH - 1)*100:.2f}%")
    print(f"Max Drawdown      : {dd.max():.2%}")
    print(f"Sharpe Ratio      : {sharpe:.2f}")
    print(f"Win Rate          : {(wins/total_t*100):.1f}%")
    print(f"Avg Trades/Day    : {total_t / ((h.index[-1]-h.index[0]).days * (5/7)):.2f}")
    print("═"*70)

    plt.figure(figsize=(12, 6))
    plt.plot(h.index, h['equity'], color='#8e44ad', linewidth=2)
    plt.title('High-Confidence Precision Curve (ADX + RSI + ST)', fontweight='bold')
    plt.tight_layout()
    plt.savefig('high_confidence_audit.png')

if __name__ == "__main__":
    main()
