"""
Blofin Native Data Validation Backtest
--------------------------------------
Downloads historical data DIRECTLY from Blofin to compare against Binance results.
Validates if lower volume/liquidity on Blofin impacts our BB Scalper winrate.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import ccxt
import numpy as np
import pandas as pd
import time
from datetime import datetime
from database import get_exchange_client, get_all_active_users

CSV_DIR     = "csv_blofin"
RESULTS_DIR = "results"
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Strategy params (Locked to Institutional Standard)
# ---------------------------------------------------------------------------
BB_PERIOD      = 20
BB_DEV         = 2.5
EMA_PERIOD     = 200
RSI_PERIOD     = 14
ATR_PERIOD     = 14
ATR_MULT       = 6.0
RR_RATIO       = 1.25
ADX_PERIOD     = 14
ADX_THRESHOLD  = 20
COMMISSION     = 0.0006   # Blofin taker fee
SLIPPAGE       = 0.0010   # Increased to 0.1% to account for Blofin liquidity concerns
LEVERAGE       = 20.0
START_CASH     = 10_000.0
DAYS_BACK      = 3 * 365
RESULTS_FILE   = os.path.join(RESULTS_DIR, "blofin_validation_results.txt")

# Blofin perp symbols
SYMBOLS = {
    "BTC/USDT:USDT":  "BTC",
    "ETH/USDT:USDT":  "ETH",
    "SOL/USDT:USDT":  "SOL",
    "XRP/USDT:USDT":  "XRP",
    "DOGE/USDT:USDT": "DOGE",
}

# ---------------------------------------------------------------------------
# Data fetching (Native Blofin)
# ---------------------------------------------------------------------------

def fetch_blofin_data(symbol: str, name: str, exchange):
    cache_file = os.path.join(CSV_DIR, f"blofin_{name}_15m.csv")

    if os.path.exists(cache_file):
        print(f"  {name}: loading from Blofin cache...")
        df = pd.read_csv(cache_file, parse_dates=["datetime"], index_col="datetime")
        return df

    print(f"  {name}: probing Blofin history depth...", end="", flush=True)
    end_ms = exchange.milliseconds()
    # Try 3 months first, then 1 month, then 1 week
    windows = [90, 30, 14, 7]
    all_ohlcv = []
    
    for days in windows:
        start_ms = end_ms - days * 24 * 60 * 60 * 1000
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, "15m", since=start_ms, limit=1000)
            if ohlcv:
                print(f" found {days}d depth. Downloading...", end="", flush=True)
                current = ohlcv[0][0]
                while current < end_ms:
                    batch = exchange.fetch_ohlcv(symbol, "15m", since=current, limit=1000)
                    if not batch: break
                    all_ohlcv.extend(batch)
                    current = batch[-1][0] + 15 * 60 * 1000
                    time.sleep(0.1)
                break
        except:
            continue

    if not all_ohlcv:
        # Final fallback: just get the most recent 1000
        print(" deep history restricted. Fetching latest 1,000 bars...", end="", flush=True)
        all_ohlcv = exchange.fetch_ohlcv(symbol, "15m", limit=1000)

    if not all_ohlcv:
        print(" NO DATA (Blofin may have shorter history)")
        return None

    df = pd.DataFrame(all_ohlcv, columns=["timestamp","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df.to_csv(cache_file)
    print(f" {len(df):,} bars retrieved.")
    return df

# ---------------------------------------------------------------------------
# Indicators & Simulation (Identical to Binance script)
# ---------------------------------------------------------------------------

def ema(s, p):     return s.ewm(span=p, adjust=False).mean()
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
    d["ema"] = ema(d["close"], EMA_PERIOD); d["rsi"] = rsi(d["close"], RSI_PERIOD); d["atr"] = atr(d, ATR_PERIOD); d["adx"] = adx(d, ADX_PERIOD)
    
    # 🏔️ New Hardened Logic
    BB_DEV_H = 2.7; ADX_TH_H = 25; RVOL_TH = 1.5
    
    mid = d["close"].rolling(BB_PERIOD).mean(); std = d["close"].rolling(BB_PERIOD).std()
    d["bb_top"] = mid + BB_DEV_H * std; d["bb_bot"] = mid - BB_DEV_H * std
    d["avg_vol"] = d["volume"].rolling(20).mean(); d["rvol"] = d["volume"] / d["avg_vol"]
    
    close = d["close"].values; high = d["high"].values; low = d["low"].values; ema_v = d["ema"].values; rsi_v = d["rsi"].values; atr_v = d["atr"].values; adx_v = d["adx"].values; rvol_v = d["rvol"].values; bb_top = d["bb_top"].values; bb_bot = d["bb_bot"].values
    
    equity = START_CASH; max_eq = START_CASH; max_dd = 0.0; wins = losses = 0; in_trade = False; cooldown = 0; sl = tp = size = risk_amt = sl_dist = 0.0; side = 0; warmup = 200

    for i in range(warmup, len(close) - 1):
        if np.isnan(ema_v[i]) or np.isnan(adx_v[i]): continue
        if cooldown > 0: cooldown -= 1; continue
        if not in_trade:
            if adx_v[i] < ADX_TH_H: continue
            if rvol_v[i] < RVOL_TH: continue
            if close[i] > ema_v[i] and close[i] < bb_bot[i] and rsi_v[i] < 30: # LONG
                side = 1; fill = close[i] * (1 + SLIPPAGE); sl_dist = atr_v[i] * ATR_MULT; sl = fill - sl_dist; tp = fill + sl_dist * RR_RATIO; risk_amt = equity * risk_per_trade; size = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill); equity -= fill * size * COMMISSION; in_trade = True
            elif close[i] < ema_v[i] and close[i] > bb_top[i] and rsi_v[i] > 70: # SHORT
                side = -1; fill = close[i] * (1 - SLIPPAGE); sl_dist = atr_v[i] * ATR_MULT; sl = fill + sl_dist; tp = fill - sl_dist * RR_RATIO; risk_amt = equity * risk_per_trade; size = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill); equity -= fill * size * COMMISSION; in_trade = True
        else:
            hit_sl = hit_tp = False; exit_px = 0.0
            if side == 1:
                if low[i] <= sl: hit_sl = True; exit_px = sl
                elif high[i] >= tp: hit_tp = True; exit_px = tp
            else:
                if high[i] >= sl: hit_sl = True; exit_px = sl
                elif low[i] <= tp: hit_tp = True; exit_px = tp
            if hit_sl or hit_tp:
                pnl = risk_amt * RR_RATIO if hit_tp else -risk_amt
                equity += pnl - exit_px * size * COMMISSION
                if hit_tp: wins += 1
                else: losses += 1
                if equity > max_eq: max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd: max_dd = dd
                in_trade = False; cooldown = 3

    total = wins + losses
    if total == 0: return {"trades": 0}
    return {"wins": wins, "losses": losses, "trades": total, "win_rate": wins/total*100, "pnl_pct": (equity - START_CASH)/START_CASH*100, "max_dd": max_dd}

def run():
    print("=" * 65)
    print("  BLOFIN NATIVE DATA VALIDATION")
    print("  Objective: Confirm if Blofin liquidity impacts BB Scalper")
    print("=" * 65)
    
    # 🛠️ Schema Re-Sync
    import database
    database.init_db()
    
    # Use your first active user's client to fetch data
    users = get_all_active_users()
    if not users:
        print("❌ No active users found to pull Blofin data.")
        return
    exchange = get_exchange_client(users[0])
    
    datasets = {}
    for sym, name in SYMBOLS.items():
        df = fetch_blofin_data(sym, name, exchange)
        if df is not None:
            datasets[name] = df

    print(f"\nStep 2: Running simulations at 1.5% risk (Institutional Standard)\n")
    
    lines = []
    lines.append(f"{'Symbol':<6} {'WR':>6} {'PnL':>8} {'MaxDD':>7} {'Trades':>7} {'Bars'}")
    lines.append("-" * 55)
    
    for name, df in datasets.items():
        r = simulate(df, 0.015)
        if r["trades"] > 0:
            lines.append(f"{name:<6} {r['win_rate']:>5.1f}% {r['pnl_pct']:>+7.1f}% {r['max_dd']:>6.1f}% {r['trades']:>7} {len(df):>7}")
        else:
            lines.append(f"{name:<6} NO TRADES FOUND")
            
    output = "\n".join(lines)
    print(output)
    with open(RESULTS_FILE, "w") as f: f.write(output)

if __name__ == "__main__":
    run()
