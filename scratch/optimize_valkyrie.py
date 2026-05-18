import sys
import os
import pandas as pd
import numpy as np

sys.path.append("/Users/johngiles/projects/tradingbot")
sys.path.append("/Users/johngiles/projects/tradingbot/scripts")

from sherpa_visual_audit import calc_ema, calc_atr, calc_adx, calc_rsi

# Load datasets
symbols = ["SOL", "LINK", "BTC", "ADA", "DOT"]
datasets = {}
for name in symbols:
    path = f"csv_blofin/blofin_{name}_15m.csv"
    if not os.path.exists(path): continue
    df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
    datasets[name] = df

def backtest_single_symbol(df, name, bb_val, atr_val, rr_val, adx_val, rsi_low, rsi_high):
    # Pre-calculate indicators
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    
    mid = df["close"].rolling(20).mean(); std = df["close"].rolling(20).std()
    bb_top = (mid + bb_val * std).values
    bb_bot = (mid - bb_val * std).values
    
    ema = calc_ema(df["close"], 200).values
    rsi = calc_rsi(df["close"], wilder=False).values
    atr = calc_atr(df).values
    adx = calc_adx(df).values
    idx = df.index
    n = len(close)
    
    sub_equity = 2000.0
    TAKER_FEE = 0.0006
    MAKER_FEE = 0.0002
    SLIPPAGE = 0.0005
    LEVERAGE = 20.0
    risk_level_sub = 0.075 # 1.5% * 5
    
    in_trade = False
    side = 0
    sl = 0.0
    tp = 0.0
    size = 0.0
    risk_amt = 0.0
    cooldown = 0
    
    wins = 0
    losses = 0
    
    for i in range(200, n - 1):
        if cooldown > 0:
            cooldown -= 1
            continue
            
        if not in_trade:
            # Check Entry
            bandwidth = (bb_top[i] - bb_bot[i]) / close[i]
            if bandwidth < 0.012 or adx[i] > adx_val:
                continue
            
            # LONG
            if close[i] > ema[i] and low[i] < bb_bot[i] and close[i] >= bb_bot[i] and rsi[i] < rsi_low:
                side = 1
                fill = close[i] * (1 + SLIPPAGE)
                sl_dist = atr[i] * atr_val
                sl = fill - sl_dist
                tp = fill + sl_dist * rr_val
                risk_amt = sub_equity * risk_level_sub
                size = min(risk_amt / sl_dist, (sub_equity * LEVERAGE) / fill)
                sub_equity -= fill * size * TAKER_FEE
                in_trade = True
            # SHORT
            elif close[i] < ema[i] and high[i] > bb_top[i] and close[i] <= bb_top[i] and rsi[i] > rsi_high:
                side = -1
                fill = close[i] * (1 - SLIPPAGE)
                sl_dist = atr[i] * atr_val
                sl = fill + sl_dist
                tp = fill - sl_dist * rr_val
                risk_amt = sub_equity * risk_level_sub
                size = min(risk_amt / sl_dist, (sub_equity * LEVERAGE) / fill)
                sub_equity -= fill * size * TAKER_FEE
                in_trade = True
        else:
            hi, lo, ex = high[i], low[i], close[i]
            hit_sl = hit_tp = False
            
            if side == 1:
                if lo <= sl: hit_sl = True; ex = sl
                elif hi >= tp: hit_tp = True; ex = tp
            else:
                if hi >= sl: hit_sl = True; ex = sl
                elif lo <= tp: hit_tp = True; ex = tp
                
            if hit_sl or hit_tp:
                pnl = risk_amt * rr_val if hit_tp else -risk_amt
                fee_rate = MAKER_FEE if hit_tp else TAKER_FEE
                sub_equity += pnl - ex * size * fee_rate
                if hit_tp: wins += 1
                else: losses += 1
                in_trade = False
                cooldown = 2
                
    total_trades = wins + losses
    return sub_equity, total_trades, wins / total_trades if total_trades else 0.0

# Parameter Sweep Ranges
bb_options = [2.0, 2.2, 2.4, 2.6, 2.8]
atr_options = [3.0, 3.5, 4.0, 4.5]
rr_options = [0.8, 1.0, 1.2, 1.5]

print("Starting parameter grid search for each token...")
for name in symbols:
    df = datasets[name]
    best_eq = -999999
    best_params = {}
    
    # Let's run a smart sweep
    for bb in bb_options:
        for atr in atr_options:
            for rr in rr_options:
                eq, trades, wr = backtest_single_symbol(df, name, bb, atr, rr, adx_val=25 if name in ["SOL","ADA","DOT"] else 30, rsi_low=25, rsi_high=75)
                if eq > best_eq and trades >= 15:
                    best_eq = eq
                    best_params = {"bb": bb, "atr": atr, "rr": rr, "trades": trades, "win_rate": wr}
                    
    print(f"\n🏆 Token {name} Best Config:")
    print(f"  BB: {best_params.get('bb')}, ATR: {best_params.get('atr')}, RR: {best_params.get('rr')}")
    print(f"  Ending Equity: ${best_eq:,.2f} (Return: {(best_eq-2000)/2000*100:+.1f}%)")
    print(f"  Trades: {best_params.get('trades')}, Win Rate: {best_params.get('win_rate')*100:.1f}%")
