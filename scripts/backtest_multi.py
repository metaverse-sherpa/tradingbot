"""
Multi-Symbol BB Scalper Backtest (PURE BASELINE)
-----------------------------------------------
Original logic without any RVOL or Hardened ADX filters.
"""

import numpy as np
import pandas as pd
import os

CSV_DIR     = "csv"
BB_PERIOD   = 20
BB_DEV      = 2.5
EMA_PERIOD  = 200
RSI_PERIOD  = 14
ATR_PERIOD  = 14
ATR_MULT    = 6.0
RR_RATIO    = 1.25
ADX_THRESHOLD = 20
COMMISSION  = 0.0006
SLIPPAGE    = 0.0005
LEVERAGE    = 20.0
START_CASH  = 10_000.0

SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT", "LTC"]

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def rsi(s, p=14):
    d = s.diff(); g = d.clip(lower=0).ewm(span=p, adjust=False).mean(); l = (-d.clip(upper=0)).ewm(span=p, adjust=False).mean()
    return 100 - 100 / (1 + (g / l.replace(0, np.nan)))
def atr(df, p=14):
    hl = df["high"] - df["low"]; hc = (df["high"] - df["close"].shift()).abs(); lc = (df["low"] - df["close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(alpha=1/p, adjust=False).mean()
def adx(df, p=14):
    pdm = df["high"].diff().clip(lower=0); ndm = (-df["low"].diff()).clip(lower=0); pdm = pdm.where(pdm > ndm, 0.0); ndm = ndm.where(ndm > pdm, 0.0); a = atr(df, p)
    pdi = 100 * pdm.ewm(alpha=1/p, adjust=False).mean() / a; ndi = 100 * ndm.ewm(alpha=1/p, adjust=False).mean() / a; dx = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1/p, adjust=False).mean()

def simulate(df: pd.DataFrame, risk_per_trade: float) -> dict:
    d = df.copy()
    d["ema"] = ema(d["close"], EMA_PERIOD)
    d["rsi"] = rsi(d["close"], RSI_PERIOD)
    d["atr"] = atr(d, ATR_PERIOD)
    d["adx"] = adx(d, 14) # Fixed: Was using ADX_THRESHOLD (20) as the period
    mid = d["close"].rolling(BB_PERIOD).mean(); std = d["close"].rolling(BB_PERIOD).std()
    d["bb_top"] = mid + BB_DEV * std; d["bb_bot"] = mid - BB_DEV * std
    
    close = d["close"].values; high = d["high"].values; low = d["low"].values; ema_v = d["ema"].values; rsi_v = d["rsi"].values; atr_v = d["atr"].values; adx_v = d["adx"].values; bb_top = d["bb_top"].values; bb_bot = d["bb_bot"].values
    
    equity = START_CASH; max_eq = START_CASH; max_dd = 0.0; wins = losses = 0; in_trade = False; side = 0; sl = tp = size = risk = 0.0; warmup = 200; cooldown = 0

    for i in range(warmup, len(close) - 1):
        if cooldown > 0:
            cooldown -= 1
            continue

        if not in_trade:
            if adx_v[i] < ADX_THRESHOLD: continue
            if close[i] > ema_v[i] and close[i] < bb_bot[i] and rsi_v[i] < 30: # LONG
                side = 1; fill = close[i]*(1+SLIPPAGE); sd = atr_v[i]*ATR_MULT; sl = fill-sd; tp = fill+sd*RR_RATIO; risk = equity*risk_per_trade; size = min(risk/sd, (equity*LEVERAGE)/fill); equity -= fill*size*COMMISSION; in_trade = True
            elif close[i] < ema_v[i] and close[i] > bb_top[i] and rsi_v[i] > 70: # SHORT
                side = -1; fill = close[i]*(1-SLIPPAGE); sd = atr_v[i]*ATR_MULT; sl = fill+sd; tp = fill-sd*RR_RATIO; risk = equity*risk_per_trade; size = min(risk/sd, (equity*LEVERAGE)/fill); equity -= fill*size*COMMISSION; in_trade = True
        else:
            hs = ht = False; ex = 0.0
            if side == 1:
                if low[i] <= sl: hs = True; ex = sl
                elif high[i] >= tp: ht = True; ex = tp
            else:
                if high[i] >= sl: hs = True; ex = sl
                elif low[i] <= tp: ht = True; ex = tp
            if hs or ht:
                p = risk*RR_RATIO if ht else -risk
                equity += p - ex*size*COMMISSION
                if ht: wins += 1
                else: losses += 1
                if equity > max_eq: max_eq = equity
                else:
                    dd = (max_eq - equity)/max_eq*100
                    if dd > max_dd: max_dd = dd
                in_trade = False; cooldown = 3

    total = wins + losses
    if total == 0: return {"trades": 0}
    return {"wr": wins/total*100, "pnl_pct": (equity - START_CASH)/START_CASH*100, "max_dd": max_dd, "trades": total}

def run():
    print("="*60)
    print(" 🌍 PURE BASELINE SCALPER AUDIT (Binance 3-Year)")
    print("="*60)
    print(f"{'Symbol':<8} {'WR':>6} {'PnL':>9} {'MaxDD':>7} {'Trades'}")
    print("-" * 60)
    for s in SYMBOLS:
        path = f"csv/cache_{s}_15m.csv"
        if not os.path.exists(path): continue
        df = pd.read_csv(path, parse_dates=['datetime'], index_col='datetime')
        r = simulate(df, 0.01) # 1% Risk
        if r['trades'] > 0:
            print(f"{s:<8} {r['wr']:>5.1f}% {r['pnl_pct']:>+8.1f}% {r['max_dd']:>6.1f}% {r['trades']:>7}")

if __name__ == "__main__":
    run()
