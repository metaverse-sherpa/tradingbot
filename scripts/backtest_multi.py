"""
Multi-Symbol BB Scalper Backtest
----------------------------------
Downloads 3 years of 15m data for each symbol from Binance (free, no API key needed),
then runs the proven vectorized BB simulation on each.

Optimal params (from BTC 288-combo sweep):
  BB_Dev=2.5, ATR_M=6.0, RR=1.25, ADX>20

Results saved to: multi_symbol_results.txt
"""

import ccxt
import numpy as np
import pandas as pd
import time
import os
from datetime import datetime

CSV_DIR     = "csv"
RESULTS_DIR = "results"
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Strategy params (fixed at proven optimal)
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
SLIPPAGE       = 0.0005
LEVERAGE       = 20.0
START_CASH     = 10_000.0
DAYS_BACK      = 3 * 365
RESULTS_FILE   = os.path.join(RESULTS_DIR, "multi_symbol_results.txt")

# Binance spot symbols (tracks perp price very closely, 3yr history available)
SYMBOLS = {
    "BTC/USDT":  "BTC",
    "ETH/USDT":  "ETH",
    "SOL/USDT":  "SOL",
    "XRP/USDT":  "XRP",
    "DOGE/USDT": "DOGE",
    "ADA/USDT":  "ADA",
    "AVAX/USDT": "AVAX",
    "LINK/USDT": "LINK",
    "DOT/USDT":  "DOT",
    "LTC/USDT":  "LTC",
}

# ---------------------------------------------------------------------------
# Data fetching (cached to CSV)
# ---------------------------------------------------------------------------

def fetch_or_load(symbol: str, name: str, exchange) -> pd.DataFrame | None:
    cache_file = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")

    if os.path.exists(cache_file):
        print(f"  {name}: loading from cache ({cache_file})")
        df = pd.read_csv(cache_file, parse_dates=["datetime"], index_col="datetime")
        return df

    print(f"  {name}: downloading from Binance...", end="", flush=True)
    end_ms    = exchange.milliseconds()
    start_ms  = end_ms - DAYS_BACK * 24 * 60 * 60 * 1000
    all_ohlcv = []
    current   = start_ms

    while current < end_ms:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, "15m", since=current, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            current = ohlcv[-1][0] + 15 * 60 * 1000
            time.sleep(0.1)   # be kind to Binance rate limits
        except Exception as e:
            print(f"\n    Error: {e} — retrying in 5s")
            time.sleep(5)

    if not all_ohlcv:
        print(" NO DATA")
        return None

    df = pd.DataFrame(all_ohlcv, columns=["timestamp","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df.to_csv(cache_file)
    print(f" {len(df):,} bars ({df.index[0].date()} → {df.index[-1].date()})")
    return df

# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def ema(s, p):     return s.ewm(span=p, adjust=False).mean()

def rsi(s, p=14):
    d    = s.diff()
    gain = d.clip(lower=0).ewm(span=p, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(span=p, adjust=False).mean()
    rs   = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def atr(df, p=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"]  - df["close"].shift()).abs()
    # Wilder smoothing: alpha = 1/p  (matches Backtrader's ATR)
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(alpha=1/p, adjust=False).mean()

def adx(df, p=14):
    pdm = df["high"].diff().clip(lower=0)
    ndm = (-df["low"].diff()).clip(lower=0)
    pdm = pdm.where(pdm > ndm, 0.0)
    ndm = ndm.where(ndm > pdm, 0.0)
    a   = atr(df, p)
    # Wilder smoothing: alpha = 1/p  (matches Backtrader's ADX exactly)
    pdi = 100 * pdm.ewm(alpha=1/p, adjust=False).mean() / a
    ndi = 100 * ndm.ewm(alpha=1/p, adjust=False).mean() / a
    dx  = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1/p, adjust=False).mean()

# ---------------------------------------------------------------------------
# Vectorized BB simulation
# ---------------------------------------------------------------------------

def simulate(df: pd.DataFrame, risk_per_trade: float) -> dict:
    d              = df.copy()
    d["ema"]       = ema(d["close"], EMA_PERIOD)
    d["rsi"]       = rsi(d["close"], RSI_PERIOD)
    d["atr"]       = atr(d, ATR_PERIOD)
    d["adx"]       = adx(d, ADX_PERIOD)
    mid            = d["close"].rolling(BB_PERIOD).mean()
    std            = d["close"].rolling(BB_PERIOD).std()
    d["bb_top"]    = mid + BB_DEV * std
    d["bb_bot"]    = mid - BB_DEV * std

    close  = d["close"].values
    high   = d["high"].values
    low    = d["low"].values
    ema_v  = d["ema"].values
    rsi_v  = d["rsi"].values
    atr_v  = d["atr"].values
    adx_v  = d["adx"].values
    bb_top = d["bb_top"].values
    bb_bot = d["bb_bot"].values
    n      = len(close)

    equity   = START_CASH
    max_eq   = START_CASH
    max_dd   = 0.0
    wins = losses = 0
    in_trade  = False
    cooldown  = 0          # bars to wait before next entry (prevents immediate re-entry)
    sl = tp = size = risk_amt = sl_dist = 0.0
    side = 0
    warmup = max(EMA_PERIOD, 50)

    for i in range(warmup, n - 1):
        if np.isnan(ema_v[i]) or np.isnan(adx_v[i]):
            continue

        # Count down cooldown after each exit
        if cooldown > 0:
            cooldown -= 1
            continue

        if not in_trade:
            if adx_v[i] < ADX_THRESHOLD:
                continue

            # LONG
            if close[i] > ema_v[i] and close[i] < bb_bot[i] and rsi_v[i] < 30:
                side     = 1
                fill     = close[i] * (1 + SLIPPAGE)
                sl_dist  = atr_v[i] * ATR_MULT
                sl       = fill - sl_dist
                tp       = fill + sl_dist * RR_RATIO
                risk_amt = equity * risk_per_trade
                size     = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill)
                equity  -= fill * size * COMMISSION
                in_trade = True

            # SHORT
            elif close[i] < ema_v[i] and close[i] > bb_top[i] and rsi_v[i] > 70:
                side     = -1
                fill     = close[i] * (1 - SLIPPAGE)
                sl_dist  = atr_v[i] * ATR_MULT
                sl       = fill + sl_dist
                tp       = fill - sl_dist * RR_RATIO
                risk_amt = equity * risk_per_trade
                size     = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill)
                equity  -= fill * size * COMMISSION
                in_trade = True

        else:
            hit_sl = hit_tp = False
            exit_px = 0.0

            if side == 1:
                if low[i]  <= sl:  hit_sl = True; exit_px = sl
                elif high[i] >= tp: hit_tp = True; exit_px = tp
            else:
                if high[i] >= sl:  hit_sl = True; exit_px = sl
                elif low[i]  <= tp: hit_tp = True; exit_px = tp

            if hit_sl or hit_tp:
                pnl      = risk_amt * RR_RATIO if hit_tp else -risk_amt
                equity  += pnl - exit_px * size * COMMISSION
                if hit_tp: wins   += 1
                else:      losses += 1

                if equity <= 0:
                    return {"blown": True, "wins": wins, "losses": losses}

                if equity > max_eq:  max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd: max_dd = dd

                in_trade = False
                cooldown = 3       # wait 3 bars (45 min) before next entry

    total = wins + losses
    if total == 0:
        return {"blown": False, "wins": 0, "losses": 0, "trades": 0}

    return {
        "blown":           False,
        "wins":            wins,
        "losses":          losses,
        "trades":          total,
        "win_rate":        wins / total * 100,
        "pnl_pct":         (equity - START_CASH) / START_CASH * 100,
        "max_dd":          max_dd,
        "trades_per_year": total / 3.0,
        "final_equity":    equity,
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    exchange = ccxt.binance({"enableRateLimit": True})

    print("=" * 65)
    print("  Multi-Symbol BB Backtest")
    print(f"  Params: BB={BB_DEV}σ, ATR×{ATR_MULT}, RR={RR_RATIO}, ADX>{ADX_THRESHOLD}")
    print(f"  Fees: {COMMISSION*100:.2f}% taker + {SLIPPAGE*100:.2f}% slippage")
    print("=" * 65)
    print("\nStep 1: Fetching data (cached after first run)...")

    datasets = {}
    for sym, name in SYMBOLS.items():
        df = fetch_or_load(sym, name, exchange)
        if df is not None:
            datasets[name] = df

    print(f"\nStep 2: Running simulations at 1% and 3% risk per trade...\n")

    rows = []
    for name, df in datasets.items():
        r1 = simulate(df, 0.01)
        r3 = simulate(df, 0.03)
        rows.append({"name": name, "r1": r1, "r3": r3, "bars": len(df),
                     "start": df.index[0].date(), "end": df.index[-1].date()})

    # Build output
    lines = []
    lines.append("\n" + "=" * 100)
    lines.append("RESULTS: 1% risk per trade  (multi-symbol bot default)")
    lines.append("=" * 100)
    lines.append(f"  {'Symbol':<6} {'WR':>6} {'PnL':>8} {'MaxDD':>7} {'Trades':>7} {'Trades/yr':>10} {'Period'}")
    lines.append("  " + "-" * 95)

    keep_1pct = []
    for row in rows:
        r = row["r1"]
        if r.get("blown") or r.get("trades", 0) == 0:
            lines.append(f"  {row['name']:<6}  {'BLOWN/NO TRADES':>50}")
        else:
            flag = "✅" if r["win_rate"] >= 50 and r["max_dd"] < 20 and r["pnl_pct"] > 0 else "⚠️ "
            lines.append(f"  {row['name']:<6} {r['win_rate']:>5.1f}% {r['pnl_pct']:>+7.1f}% "
                         f"{r['max_dd']:>6.1f}% {r['trades']:>7} {r['trades_per_year']:>9.0f}/yr "
                         f"  {row['start']}→{row['end']}  {flag}")
            if r["win_rate"] >= 50 and r["max_dd"] < 20 and r["pnl_pct"] > 0:
                keep_1pct.append(row["name"])

    lines.append("\n" + "=" * 100)
    lines.append("RESULTS: 3% risk per trade  (reference — matches BTC backtest)")
    lines.append("=" * 100)
    lines.append(f"  {'Symbol':<6} {'WR':>6} {'PnL':>8} {'MaxDD':>7} {'Trades':>7} {'Trades/yr':>10}")
    lines.append("  " + "-" * 70)

    keep_3pct = []
    for row in rows:
        r = row["r3"]
        if r.get("blown") or r.get("trades", 0) == 0:
            lines.append(f"  {row['name']:<6}  {'BLOWN/NO TRADES':>50}")
        else:
            flag = "✅" if r["win_rate"] >= 50 and r["max_dd"] < 20 and r["pnl_pct"] > 0 else "⚠️ "
            lines.append(f"  {row['name']:<6} {r['win_rate']:>5.1f}% {r['pnl_pct']:>+7.1f}% "
                         f"{r['max_dd']:>6.1f}% {r['trades']:>7} {r['trades_per_year']:>9.0f}/yr  {flag}")
            if r["win_rate"] >= 50 and r["max_dd"] < 20 and r["pnl_pct"] > 0:
                keep_3pct.append(row["name"])

    lines.append(f"\n✅ Symbols passing WR≥50%, DD<20%, PnL>0% (1% risk): {keep_1pct}")
    lines.append(f"✅ Symbols passing WR≥50%, DD<20%, PnL>0% (3% risk): {keep_3pct}")
    lines.append(f"\nRecommended SYMBOLS list for live_bot_multi.py:")
    lines.append(f"  {[s+'/USDT:USDT' for s in keep_1pct]}")

    output = "\n".join(lines)
    print(output)

    with open(RESULTS_FILE, "w") as f:
        f.write(output)
    print(f"\nResults saved to {RESULTS_FILE}")


if __name__ == "__main__":
    run()
