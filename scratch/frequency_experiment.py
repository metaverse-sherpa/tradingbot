import sqlite3
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

INITIAL_CASH = 10000.0
PCT_PER_TRADE = 0.01
FEE_RATE = 0.0005
DB_PATH = "data/stock_daily_cache.db"
SYMBOLS = [
    "NVDA", "GOOGL", "AAPL", "MSFT", "AMZN", "TSM", "AVGO", "META", "TSLA", "WMT"
]

def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM StockDailyData ORDER BY date ASC", conn)
    conn.close()
    data_dict = {}
    for sym in SYMBOLS:
        sym_df = df[df['symbol'] == sym].copy()
        if not sym_df.empty:
            sym_df['date'] = pd.to_datetime(sym_df['date'])
            sym_df.set_index('date', inplace=True)
            sym_df.sort_index(inplace=True)
            data_dict[sym] = sym_df
    return data_dict

def calculate_indicators(df, params):
    df = df.copy()
    df['ema_150'] = df['close'].ewm(span=150, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    # ATR (14)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()
    
    # RSI (3)
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=3).mean()
    avg_loss = loss.rolling(window=3).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    df['rsi_3'] = 100 - (100 / (1 + rs))
    
    return df

def run_backtest_exp(data_dict, strategy_type, params):
    processed = {sym: calculate_indicators(df, params) for sym, df in data_dict.items()}
    all_dates = sorted(list(set().union(*(df.index for df in processed.values()))))
    
    cash = INITIAL_CASH
    active = {}
    history = []
    equity_hist = []
    
    atr_mult = params.get("atr_sl_mult", 3.0)
    rr = 1.5
    
    sym_indices = {sym: {date: i for i, date in enumerate(df.index)} for sym, df in processed.items()}
    
    for t_idx, date in enumerate(all_dates):
        # 1. Update exits
        to_close = []
        for sym, t in active.items():
            df = processed[sym]
            if date not in df.index: continue
            bar = df.loc[date]
            o, h, l, c = bar['open'], bar['high'], bar['low'], bar['close']
            sl, tp = t['sl'], t['tp']
            
            exited = False
            exit_price = None
            
            if o <= sl:
                exited, exit_price = True, o
            elif o >= tp:
                exited, exit_price = True, o
            elif l <= sl and h >= tp:
                exited, exit_price = True, sl
            elif l <= sl:
                exited, exit_price = True, sl
            elif h >= tp:
                exited, exit_price = True, tp
                
            if exited:
                gross = (exit_price - t['entry']) * t['shares']
                val = exit_price * t['shares']
                fee = val * FEE_RATE
                pnl = gross - fee - t['fee']
                cash += val - fee
                history.append({
                    "symbol": sym, "pnl": pnl, "pnl_pct": (pnl/t['notional'])*100, "win": pnl > 0
                })
                to_close.append(sym)
                
        for sym in to_close: active.pop(sym)
        
        # 2. Equity
        calc_equity = cash
        for sym, t in active.items():
            df = processed[sym]
            c_p = df.loc[date, 'close'] if date in df.index else t['entry']
            calc_equity += t['shares'] * c_p
            
        equity_hist.append({"date": date, "equity": calc_equity})
        
        # 3. Entries
        if t_idx == 0: continue
        prev_date = all_dates[t_idx - 1]
        
        signals = []
        for sym in SYMBOLS:
            if sym in active: continue
            df = processed[sym]
            if prev_date not in df.index or date not in df.index: continue
            
            row = df.loc[prev_date]
            
            # Strategy checks
            sig = False
            if strategy_type == "RSI_State":
                # State based RSI (just being below threshold is enough)
                if row['close'] > row['ema_150'] and row['rsi_3'] < params['rsi_threshold']:
                    sig = True
            elif strategy_type == "EMA_20_Pullback":
                # Price is in uptrend and low dipped below the 20-day EMA
                if row['close'] > row['ema_150'] and row['low'] < row['ema_20'] and row['close'] > row['ema_20']:
                    sig = True
                    
            if sig:
                signals.append(sym)
                
        signals.sort()
        for sym in signals:
            df = processed[sym]
            bar = df.loc[date]
            entry_price = bar['open']
            prev_bar = df.loc[prev_date]
            atr = prev_bar['atr']
            
            if np.isnan(atr) or atr <= 0: continue
            
            D = atr_mult * atr
            if D < entry_price * 0.005: D = entry_price * 0.005
            
            sl = entry_price - D
            tp = entry_price + (rr * D)
            
            risk = calc_equity * PCT_PER_TRADE
            shares = risk / D
            notional = shares * entry_price
            
            if notional > cash:
                shares = cash / entry_price
                notional = shares * entry_price
                
            fee = notional * FEE_RATE
            
            if shares > 0.01 and notional > 100.0 and cash >= (notional + fee):
                cash -= (notional + fee)
                active[sym] = {
                    "entry": entry_price, "sl": sl, "tp": tp, "shares": shares, "notional": notional, "fee": fee
                }
                
    h_df = pd.DataFrame(equity_hist).set_index('date')
    if not history: return 0, 0, 0, 0
    t_df = pd.DataFrame(history)
    
    pnl_pct = (h_df['equity'].iloc[-1]/INITIAL_CASH - 1)*100
    win_rate = (t_df['win'].sum()/len(t_df))*100
    peak = h_df['equity'].cummax()
    dd = ((peak - h_df['equity'])/peak).max()*100
    
    daily_rets = h_df['equity'].pct_change().dropna()
    sharpe = (daily_rets.mean() / (daily_rets.std() + 1e-10)) * np.sqrt(252)
    trades_per_day = len(t_df) / (h_df.index[-1] - h_df.index[0]).days
    
    return len(t_df), trades_per_day, win_rate, pnl_pct, dd, sharpe

def main():
    data = load_data()
    print("🏔️ Starting Higher-Frequency Strategy Experiment...")
    print(f"Top 10 MarketCap Tickers, 1d candles, 3 years.\n")
    
    print("Test 1: Strategy Logic and ATR Multiplier Sweep (at 1.0% Risk)")
    experiments = [
        ("RSI_State (RSI < 20)", "RSI_State", {"rsi_threshold": 20, "atr_sl_mult": 3.0}),
        ("RSI_State (RSI < 25)", "RSI_State", {"rsi_threshold": 25, "atr_sl_mult": 3.0}),
        ("RSI_State (RSI < 25, ATR 2.5)", "RSI_State", {"rsi_threshold": 25, "atr_sl_mult": 2.5}),
        ("EMA_20_Pullback (ATR 3.0)", "EMA_20_Pullback", {"atr_sl_mult": 3.0}),
        ("EMA_20_Pullback (ATR 2.5)", "EMA_20_Pullback", {"atr_sl_mult": 2.5}),
        ("EMA_20_Pullback (ATR 2.0)", "EMA_20_Pullback", {"atr_sl_mult": 2.0}),
    ]
    
    print("═"*100)
    print(f"{'STRATEGY SETUP':<32} | {'TRADES':<6} | {'FREQ (/DAY)':<12} | {'WIN RATE':<10} | {'TOTAL PNL':<10} | {'MAX DD':<8} | {'SHARPE':<6}")
    print("═"*100)
    
    for label, stype, params in experiments:
        global PCT_PER_TRADE
        PCT_PER_TRADE = 0.01 # Reset to 1%
        trades, freq, wr, pnl, dd, sharpe = run_backtest_exp(data, stype, params)
        print(f"{label:<32} | {trades:<6} | {freq:>11.3f} | {wr:>8.1f}% | {pnl:>9.1f}% | {dd:>7.1f}% | {sharpe:>6.2f}")
        
    print("═"*100)
    
    print("\nTest 2: Risk-per-Trade Sizing Sweep on Winning Strategy RSI_State (RSI < 20, ATR 3.0)")
    print("═"*100)
    print(f"{'RISK % PER TRADE':<32} | {'TRADES':<6} | {'FREQ (/DAY)':<12} | {'WIN RATE':<10} | {'TOTAL PNL':<10} | {'MAX DD':<8} | {'SHARPE':<6}")
    print("═"*100)
    
    for r_pct in [0.01, 0.0075, 0.005, 0.003, 0.0025]:
        PCT_PER_TRADE = r_pct
        trades, freq, wr, pnl, dd, sharpe = run_backtest_exp(data, "RSI_State", {"rsi_threshold": 20, "atr_sl_mult": 3.0})
        label = f"RSI_State (Risk: {r_pct*100:.2f}%)"
        print(f"{label:<32} | {trades:<6} | {freq:>11.3f} | {wr:>8.1f}% | {pnl:>9.1f}% | {dd:>7.1f}% | {sharpe:>6.2f}")
    print("═"*100)

if __name__ == "__main__":
    main()
