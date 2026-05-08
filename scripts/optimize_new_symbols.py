"""
Optimization Sweep for High-Volume Candidates
-----------------------------------------------
Finds best params for the top volume USDT pairs identified on Binance.
Targeting an additional ~0.5 trades/day to reach the 1.0/day goal.
"""

import ccxt
import numpy as np
import pandas as pd
import os
import time

CSV_DIR     = "csv"
RESULTS_DIR = "results"
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

RESULTS_FILE = os.path.join(RESULTS_DIR, "new_symbol_optimization_results.txt")

# Constants
BB_PERIOD   = 20
EMA_PERIOD  = 200
ATR_PERIOD  = 14
ADX_PERIOD  = 14
COMMISSION  = 0.0006
SLIPPAGE    = 0.0005
LEVERAGE    = 20.0
START_CASH  = 10_000.0
FIXED_RISK  = 0.02
DAYS_BACK   = 3 * 365

# Parameter grid (Consistent with original sweep)
GRID_BB  = [2.0, 2.5, 3.0]
GRID_ATR = [4.0, 5.0, 6.0]
GRID_RR  = [1.0, 1.25]
GRID_ADX = [0, 15, 20, 25]

# High-Volume New Candidates
NEW_SYMBOLS = {
    "BNB/USDT":  "BNB",
    "NEAR/USDT": "NEAR",
    "SUI/USDT":  "SUI",
    "NOT/USDT":  "NOT",
    "TAO/USDT":  "TAO",
    "ONDO/USDT": "ONDO",
    "ENA/USDT":  "ENA",
    "FET/USDT":  "FET",
    "WIF/USDT":  "WIF",
    "SHIB/USDT": "SHIB",
}

def fetch_or_load(symbol, name, exchange):
    cache_file = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")
    if os.path.exists(cache_file):
        print(f"  {name:<5}: loading from cache")
        return pd.read_csv(cache_file, parse_dates=["datetime"], index_col="datetime")
    
    print(f"  {name:<5}: downloading...", end="", flush=True)
    end_ms = exchange.milliseconds()
    start_ms = end_ms - DAYS_BACK * 24 * 60 * 60 * 1000
    all_rows = []
    current = start_ms
    while current < end_ms:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, "15m", since=current, limit=1000)
            if not ohlcv: break
            all_rows.extend(ohlcv)
            current = ohlcv[-1][0] + 15 * 60 * 1000
            time.sleep(0.1)
        except:
            time.sleep(5)
    if not all_rows: return None
    df = pd.DataFrame(all_rows, columns=["timestamp","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df.to_csv(cache_file)
    print(f" {len(df):,} bars")
    return df

def calc_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calc_rsi(s, p=14):
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1/p, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/p, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))
def calc_atr(df, p=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"]  - df["close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(alpha=1/p, adjust=False).mean()
def calc_adx(df, p=14):
    pdm = df["high"].diff().clip(lower=0); ndm = (-df["low"].diff()).clip(lower=0)
    pdm = pdm.where(pdm > ndm, 0.0); ndm = ndm.where(ndm > pdm, 0.0)
    a = calc_atr(df, p)
    pdi = 100 * pdm.ewm(alpha=1/p, adjust=False).mean() / a
    ndi = 100 * ndm.ewm(alpha=1/p, adjust=False).mean() / a
    dx = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1/p, adjust=False).mean()

def simulate(close, high, low, ema, rsi, atr, adx, bb_top, bb_bot, atr_m, rr, adx_th):
    n = len(close)
    equity = START_CASH; max_eq = START_CASH; max_dd = 0.0
    wins = losses = 0; in_trade = False; cooldown = 0
    sl = tp = size = risk_amt = 0.0; side = 0
    warmup = 200
    for i in range(warmup, n - 1):
        if np.isnan(ema[i]): continue
        if cooldown > 0: cooldown -= 1; continue
        if not in_trade:
            if adx_th > 0 and adx[i] < adx_th: continue
            if close[i] > ema[i] and close[i] < bb_bot[i] and rsi[i] < 30:
                side = 1; fill = close[i] * (1+SLIPPAGE); sl_d = atr[i]*atr_m
                sl = fill - sl_d; tp = fill + sl_d*rr; risk_amt = equity*0.02
                size = min(risk_amt/sl_d, (equity*LEVERAGE)/fill); equity -= fill*size*COMMISSION; in_trade = True
            elif close[i] < ema[i] and close[i] > bb_top[i] and rsi[i] > 70:
                side = -1; fill = close[i] * (1-SLIPPAGE); sl_d = atr[i]*atr_m
                sl = fill + sl_d; tp = fill - sl_d*rr; risk_amt = equity*0.02
                size = min(risk_amt/sl_d, (equity*LEVERAGE)/fill); equity -= fill*size*COMMISSION; in_trade = True
        else:
            hit_sl = hit_tp = False; ex = 0.0
            if side == 1:
                if low[i] <= sl: hit_sl = True; ex = sl
                elif high[i] >= tp: hit_tp = True; ex = tp
            else:
                if high[i] >= sl: hit_sl = True; ex = sl
                elif low[i] <= tp: hit_tp = True; ex = tp
            if hit_sl or hit_tp:
                pnl = risk_amt*rr if hit_tp else -risk_amt
                equity += pnl - ex*size*COMMISSION
                if hit_tp: wins += 1
                else: losses += 1
                if equity > max_eq: max_eq = equity
                else: dd = (max_eq - equity)/max_eq*100; max_dd = max(max_dd, dd)
                in_trade = False; cooldown = 3
    total = wins + losses
    if total < 5: return None
    return {"wr": wins/total*100, "pnl": (equity-START_CASH)/START_CASH*100, "dd": max_dd, "trades": total}

def run():
    exchange = ccxt.binance({"enableRateLimit": True})
    results_summary = []
    for sym, name in NEW_SYMBOLS.items():
        df = fetch_or_load(sym, name, exchange)
        if df is None: continue
        close_s = df["close"]; ema = calc_ema(close_s, 200).values; rsi = calc_rsi(close_s).values
        atr = calc_atr(df).values; adx = calc_adx(df).values
        close = close_s.values; high = df["high"].values; low = df["low"].values
        
        best = None
        for bb in GRID_BB:
            mid = close_s.rolling(20).mean().values; std = close_s.rolling(20).std().values
            top = mid + bb*std; bot = mid - bb*std
            for atr_m in GRID_ATR:
                for rr in GRID_RR:
                    for adx_th in GRID_ADX:
                        r = simulate(close, high, low, ema, rsi, atr, adx, top, bot, atr_m, rr, adx_th)
                        if r and r["wr"] >= 50 and r["dd"] < 20:
                            score = r["pnl"] / max(r["dd"], 1.0)
                            if best is None or score > best["score"]:
                                best = {**r, "cfg": (bb, atr_m, rr, adx_th), "score": score}
        if best:
            res_str = f"{name:<5} | BB:{best['cfg'][0]} ATR:{best['cfg'][1]} RR:{best['cfg'][2]} ADX:{best['cfg'][3]} | WR:{best['wr']:.1f}% PnL:{best['pnl']:+.1f}% DD:{best['dd']:.1f}% | {best['trades']/3:.0f}/yr"
            print(res_str)
            results_summary.append(res_str)
        else:
            print(f"{name:<5} | No valid config found")
            
    with open(RESULTS_FILE, "w") as f:
        f.write("\n".join(results_summary))

if __name__ == "__main__":
    run()
