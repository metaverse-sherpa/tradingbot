import sqlite3
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

# 🏛️ Master Audit Configuration (15m / 5x / 1%)
INITIAL_CASH = 10000.0
PCT_PER_TRADE = 0.01 
LEVERAGE = 5
SYMBOLS = [
    "AAPL", "GOOGL", "META", "NVDA", "AMZN", "TSLA", "MSFT", "QQQ", "SPY", "ARM",
    "MRVL", "CRWD", "LITE", "XLE", "USO", "MU", "ORCL", "QCOM", "AMD", "AVGO", 
    "IWM", "TSM", "PYPL", "EWJ", "PLTR", "COIN", "MSTR", "HOOD", "INTC"
]
SUPERTREND_CONFIG = {"period": 10, "multiplier": 3, "ema_trend": 200}
FEE_RATE = 0.0006 
DB_PATH = "data/stock_cache.db"

def load_data(symbol):
    conn = sqlite3.connect(DB_PATH)
    query = f"SELECT * FROM StockData WHERE symbol = '{symbol}' ORDER BY timestamp ASC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    if df.empty: return None
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def calculate_indicators(df, cfg):
    # 🕵️ Resample to 15m
    df = df.resample('15min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    df['ema_200'] = df['close'].ewm(span=cfg['ema_trend'], adjust=False).mean()
    
    period, multiplier = cfg['period'], cfg['multiplier']
    tr = pd.concat([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    hl2 = (df['high'] + df['low']) / 2
    upper_band, lower_band = hl2 + (multiplier * atr), hl2 - (multiplier * atr)
    f_up, f_low = upper_band.copy(), lower_band.copy()
    st = [True] * len(df)
    for i in range(1, len(df)):
        f_low.iloc[i] = max(lower_band.iloc[i], f_low.iloc[i-1]) if df['close'].iloc[i-1] > f_low.iloc[i-1] else lower_band.iloc[i]
        f_up.iloc[i] = min(upper_band.iloc[i], f_up.iloc[i-1]) if df['close'].iloc[i-1] < f_up.iloc[i-1] else upper_band.iloc[i]
        st[i] = True if df['close'].iloc[i] > f_up.iloc[i] else (False if df['close'].iloc[i] < f_low.iloc[i] else st[i-1])
    df['supertrend'] = st
    return df

def main():
    print(f"🚀 Starting 29-Symbol Master Audit (15m / 5x / 1%)...")
    
    # Load and process all symbols
    all_data = {}
    valid_symbols = []
    for sym in SYMBOLS:
        data = load_data(sym)
        if data is not None:
            all_data[sym] = calculate_indicators(data, SUPERTREND_CONFIG)
            valid_symbols.append(sym)
    
    cdf = pd.concat(all_data.values(), axis=1, keys=all_data.keys()).sort_index().ffill()
    
    cash, active, history, symbol_stats = INITIAL_CASH, {}, [], {s: {'pnl': 0, 'trades': 0, 'wins': 0} for s in valid_symbols}
    
    for ts, row in cdf.iterrows():
        equity = cash + sum((t['notional'] * ((row[s]['close']-t['entry'])/t['entry'] if t['type']=="LONG" else (t['entry']-row[s]['close'])/t['entry'])) for s,t in active.items())
        history.append({"ts": ts, "equity": equity})
        
        # Close logic
        to_close = [s for s,t in active.items() if (t['type']=="LONG" and row[s]['supertrend']==False) or (t['type']=="SHORT" and row[s]['supertrend']==True)]
        for s in to_close:
            t = active.pop(s)
            p = (row[s]['open']-t['entry'])/t['entry'] if t['type']=="LONG" else (t['entry']-row[s]['open'])/t['entry']
            pnl_val = (t['notional'] * p) - (t['notional'] * FEE_RATE * 2)
            cash += pnl_val
            symbol_stats[s]['pnl'] += pnl_val
            symbol_stats[s]['trades'] += 1
            if pnl_val > 0: symbol_stats[s]['wins'] += 1

        # Open logic
        for s in valid_symbols:
            if s not in active:
                p_bar = cdf.loc[:ts].iloc[-2][s] if len(cdf.loc[:ts]) > 1 else None
                if p_bar is not None:
                    t_type = "LONG" if row[s]['supertrend'] and not p_bar['supertrend'] and row[s]['close'] > row[s]['ema_200'] else ("SHORT" if not row[s]['supertrend'] and p_bar['supertrend'] and row[s]['close'] < row[s]['ema_200'] else None)
                    if t_type: active[s] = {"type": t_type, "entry": row[s]['close'], "notional": equity * PCT_PER_TRADE * LEVERAGE, "time": ts}

    h = pd.DataFrame(history).set_index('ts')
    daily_rets = h['equity'].resample('D').last().pct_change().dropna()
    sharpe = (daily_rets.mean() / (daily_rets.std() + 1e-10)) * np.sqrt(252)
    dd = (h['equity'].expanding().max() - h['equity']) / h['equity'].expanding().max()
    
    # 🕵️ Symbol-by-Symbol Report
    print("\n" + "═"*80)
    print(f"{'SYMBOL':<10} | {'TRADES':<8} | {'WIN RATE':<10} | {'TOTAL PNL':<12}")
    print("═"*80)
    
    sorted_stats = sorted(symbol_stats.items(), key=lambda x: x[1]['pnl'], reverse=True)
    for s, st in sorted_stats:
        wr = (st['wins']/st['trades']*100) if st['trades'] > 0 else 0
        print(f"{s:<10} | {st['trades']:<8} | {wr:>8.1f}% | ${st['pnl']:>10.2f}")
    
    print("═"*80)
    print(f"🌍 PORTFOLIO SUMMARY (5x / 1%)")
    print("═"*80)
    print(f"Final Balance     : ${h['equity'].iloc[-1]:,.2f}")
    print(f"Annualized Return : {(h['equity'].iloc[-1]/INITIAL_CASH - 1)/1.5*100:.2f}%") # 1.5 year duration
    print(f"Max Drawdown      : {dd.max():.2%}")
    print(f"Sharpe Ratio      : {sharpe:.2f}")
    print("═"*80)

    plt.figure(figsize=(12, 6))
    plt.plot(h.index, h['equity'], color='#3498db', linewidth=2)
    plt.title(f'Sherpa 29-Symbol Master Audit | Sharpe: {sharpe:.2f}', fontweight='bold')
    plt.tight_layout()
    plt.savefig('stock_master_audit.png')

if __name__ == "__main__":
    main()
