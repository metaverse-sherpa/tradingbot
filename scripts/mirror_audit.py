"""
Mirror Audit: Binance vs Blofin (Last 1000 Bars)
-----------------------------------------------
Runs the BB Scalper on the exact same 10-day window for both exchanges.
Audits the 'Signal Drift' caused by Blofin liquidity.
"""

import ccxt
import pandas as pd
import numpy as np
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import database

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

def run_sim(df):
    # (Identical to production logic)
    BB_DEV = 2.5; ATR_MULT = 6.0; RR_RATIO = 1.25; ADX_TH = 20; COMM = 0.0006; SLIP = 0.0005
    d = df.copy()
    d["ema"] = ema(d["close"], 200); d["rsi"] = rsi(d["close"]); d["atr"] = atr(d); d["adx"] = adx(d)
    mid = d["close"].rolling(20).mean(); std = d["close"].rolling(20).std()
    d["bb_top"] = mid + BB_DEV * std; d["bb_bot"] = mid - BB_DEV * std
    c = d["close"].values; h = d["high"].values; l = d["low"].values; e_v = d["ema"].values; r_v = d["rsi"].values; a_v = d["atr"].values; adx_v = d["adx"].values; bt = d["bb_top"].values; bb = d["bb_bot"].values
    equity = 10000.0; wins = 0; losses = 0; in_trade = False; side = 0; sl = tp = size = risk = 0.0
    for i in range(200, len(c)-1):
        if not in_trade:
            if adx_v[i] < ADX_TH: continue
            if c[i] > e_v[i] and c[i] < bb[i] and r_v[i] < 30: # LONG
                side = 1; fill = c[i]*(1+SLIP); sd = a_v[i]*ATR_MULT; sl = fill-sd; tp = fill+sd*RR_RATIO; risk = equity*0.015; size = min(risk/sd, (equity*20)/fill); equity -= fill*size*COMM; in_trade = True
            elif c[i] < e_v[i] and c[i] > bt[i] and r_v[i] > 70: # SHORT
                side = -1; fill = c[i]*(1-SLIP); sd = a_v[i]*ATR_MULT; sl = fill+sd; tp = fill-sd*RR_RATIO; risk = equity*0.015; size = min(risk/sd, (equity*20)/fill); equity -= fill*size*COMM; in_trade = True
        else:
            hs = ht = False; ex = 0.0
            if side == 1:
                if l[i] <= sl: hs = True; ex = sl
                elif h[i] >= tp: ht = True; ex = tp
            else:
                if h[i] >= sl: hs = True; ex = sl
                elif l[i] <= tp: ht = True; ex = tp
            if hs or ht:
                p = risk*RR_RATIO if ht else -risk
                equity += p - ex*size*COMM
                if ht: wins += 1
                else: losses += 1
                in_trade = False
    return {"wr": (wins/(wins+losses)*100) if (wins+losses)>0 else 0, "trades": wins+losses, "pnl": equity-10000.0}

def run_audit():
    print("🏔️ Starting Mirror Audit (Binance vs Blofin)...")
    bin_ex = ccxt.binance(); blo_ex = ccxt.blofin()
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    
    for s in symbols:
        print(f"\nAudit: {s}")
        blo_sym = f"{s}:USDT"
        blo_data = blo_ex.fetch_ohlcv(blo_sym, "15m", limit=1000)
        start_ts = blo_data[0][0]
        bin_data = bin_ex.fetch_ohlcv(s, "15m", since=start_ts, limit=1000)
        
        df_blo = pd.DataFrame(blo_data, columns=["t","open","high","low","close","v"])
        df_bin = pd.DataFrame(bin_data, columns=["t","open","high","low","close","v"])
        
        r_blo = run_sim(df_blo)
        r_bin = run_sim(df_bin)
        
        print(f"  Blofin:  {r_blo['trades']} trades | WR: {r_blo['wr']:.1f}% | PnL: ${r_blo['pnl']:.2f}")
        print(f"  Binance: {r_bin['trades']} trades | WR: {r_bin['wr']:.1f}% | PnL: ${r_bin['pnl']:.2f}")

if __name__ == "__main__":
    run_audit()
