"""
Per-Symbol BB Parameter Optimization
--------------------------------------
Finds the best BB/ATR/RR/ADX parameters independently for each symbol.
Downloads missing data automatically from Binance (cached in csv/).
Results saved to results/symbol_optimization_results.txt
"""

import ccxt
import numpy as np
import pandas as pd
import os
import time

# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------
CSV_DIR     = "csv"
RESULTS_DIR = "results"
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

RESULTS_FILE = os.path.join(RESULTS_DIR, "symbol_optimization_results.txt")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BB_PERIOD   = 20
EMA_PERIOD  = 200
RSI_PERIOD  = 14
ATR_PERIOD  = 14
ADX_PERIOD  = 14
COMMISSION  = 0.0006
SLIPPAGE    = 0.0005
LEVERAGE    = 20.0
START_CASH  = 10_000.0
FIXED_RISK  = 0.02
DAYS_BACK   = 3 * 365

# Parameter grid
GRID_BB  = [2.0, 2.5, 3.0]
GRID_ATR = [4.0, 5.0, 6.0]
GRID_RR  = [1.0, 1.25]
GRID_ADX = [0, 15, 20, 25]

# ---------------------------------------------------------------------------
# Symbols — Binance spot symbol → short name
# Confirmed available on Binance with 3yr+ history (spot tracks perp closely)
# ---------------------------------------------------------------------------
SYMBOLS = {
    # Core basket (XRP and LTC dropped based on prior analysis)
    "BTC/USDT":  "BTC",
    "ETH/USDT":  "ETH",
    "SOL/USDT":  "SOL",
    "DOGE/USDT": "DOGE",
    "ADA/USDT":  "ADA",
    "AVAX/USDT": "AVAX",
    "LINK/USDT": "LINK",
    "DOT/USDT":  "DOT",
    # New candidates
    "TON/USDT":  "TON",
    "ZEC/USDT":  "ZEC",
    "TRX/USDT":  "TRX",
    "PEPE/USDT": "PEPE",
    # XAG/USDT (Silver) skipped — not available on Binance/Blofin crypto exchanges
}

# ---------------------------------------------------------------------------
# Data fetching (auto-downloads if cache missing)
# ---------------------------------------------------------------------------

def fetch_or_load(symbol: str, name: str, exchange) -> pd.DataFrame | None:
    cache_file = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")

    if os.path.exists(cache_file):
        print(f"  {name:<5}: loading from cache", flush=True)
        df = pd.read_csv(cache_file, parse_dates=["datetime"], index_col="datetime")
        return df

    print(f"  {name:<5}: downloading from Binance...", end="", flush=True)
    end_ms   = exchange.milliseconds()
    start_ms = end_ms - DAYS_BACK * 24 * 60 * 60 * 1000
    all_rows = []
    current  = start_ms

    while current < end_ms:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, "15m", since=current, limit=1000)
            if not ohlcv:
                break
            all_rows.extend(ohlcv)
            current = ohlcv[-1][0] + 15 * 60 * 1000
            time.sleep(0.1)
        except Exception as e:
            print(f"\n    Error: {e} — retrying")
            time.sleep(5)

    if not all_rows:
        print(" NO DATA (symbol may not exist on Binance)")
        return None

    df = pd.DataFrame(all_rows, columns=["timestamp","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df.to_csv(cache_file)
    print(f" {len(df):,} bars ({df.index[0].date()} → {df.index[-1].date()})")
    return df

# ---------------------------------------------------------------------------
# Indicators — Wilder smoothing (alpha = 1/period)
# ---------------------------------------------------------------------------

def calc_ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def calc_rsi(s, p=14):
    d    = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1/p, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/p, adjust=False).mean()
    rs   = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def calc_atr(df, p=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"]  - df["close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(alpha=1/p, adjust=False).mean()

def calc_adx(df, p=14):
    pdm = df["high"].diff().clip(lower=0)
    ndm = (-df["low"].diff()).clip(lower=0)
    pdm = pdm.where(pdm > ndm, 0.0)
    ndm = ndm.where(ndm > pdm, 0.0)
    a   = calc_atr(df, p)
    pdi = 100 * pdm.ewm(alpha=1/p, adjust=False).mean() / a
    ndi = 100 * ndm.ewm(alpha=1/p, adjust=False).mean() / a
    dx  = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1/p, adjust=False).mean()

# ---------------------------------------------------------------------------
# Fast inner simulation (precomputed numpy arrays)
# ---------------------------------------------------------------------------

def simulate_inner(close, high, low, ema_v, rsi_v, atr_v, adx_v,
                   bb_top, bb_bot, atr_mult, rr_ratio, adx_th, risk):
    n        = len(close)
    equity   = START_CASH
    max_eq   = START_CASH
    max_dd   = 0.0
    wins = losses = 0
    in_trade = False
    cooldown = 0
    sl = tp = size = risk_amt = sl_dist = 0.0
    side = 0
    warmup = max(EMA_PERIOD, ADX_PERIOD * 3)

    for i in range(warmup, n - 1):
        if np.isnan(ema_v[i]) or np.isnan(adx_v[i]) or np.isnan(bb_bot[i]):
            continue

        if cooldown > 0:
            cooldown -= 1
            continue

        if not in_trade:
            if adx_th > 0 and adx_v[i] < adx_th:
                continue

            if close[i] > ema_v[i] and close[i] < bb_bot[i] and rsi_v[i] < 30:
                side     = 1
                fill     = close[i] * (1 + SLIPPAGE)
                sl_dist  = atr_v[i] * atr_mult
                sl       = fill - sl_dist
                tp       = fill + sl_dist * rr_ratio
                risk_amt = equity * risk
                size     = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill)
                equity  -= fill * size * COMMISSION
                in_trade = True

            elif close[i] < ema_v[i] and close[i] > bb_top[i] and rsi_v[i] > 70:
                side     = -1
                fill     = close[i] * (1 - SLIPPAGE)
                sl_dist  = atr_v[i] * atr_mult
                sl       = fill + sl_dist
                tp       = fill - sl_dist * rr_ratio
                risk_amt = equity * risk
                size     = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill)
                equity  -= fill * size * COMMISSION
                in_trade = True
        else:
            hit_sl = hit_tp = False
            exit_px = 0.0

            if side == 1:
                if low[i]  <= sl:   hit_sl = True; exit_px = sl
                elif high[i] >= tp: hit_tp = True; exit_px = tp
            else:
                if high[i] >= sl:   hit_sl = True; exit_px = sl
                elif low[i]  <= tp: hit_tp = True; exit_px = tp

            if hit_sl or hit_tp:
                pnl     = risk_amt * rr_ratio if hit_tp else -risk_amt
                equity += pnl - exit_px * size * COMMISSION
                if hit_tp: wins   += 1
                else:      losses += 1

                if equity <= 0:
                    return None

                if equity > max_eq: max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd: max_dd = dd

                in_trade = False
                cooldown = 3

    total = wins + losses
    if total < 5:
        return None

    return {
        "win_rate":        wins / total * 100,
        "pnl_pct":         (equity - START_CASH) / START_CASH * 100,
        "max_dd":          max_dd,
        "trades":          total,
        "trades_per_year": total / 3.0,
    }

# ---------------------------------------------------------------------------
# Per-symbol optimization
# ---------------------------------------------------------------------------

def optimize_symbol(name: str, df: pd.DataFrame) -> list:
    close_s = df["close"]
    ema_v   = calc_ema(close_s, EMA_PERIOD).values
    rsi_v   = calc_rsi(close_s, RSI_PERIOD).values
    atr_v   = calc_atr(df, ATR_PERIOD).values
    adx_v   = calc_adx(df, ADX_PERIOD).values
    close   = close_s.values
    high    = df["high"].values
    low     = df["low"].values

    results = []
    for bb_dev in GRID_BB:
        mid    = close_s.rolling(BB_PERIOD).mean().values
        std    = close_s.rolling(BB_PERIOD).std().values
        bb_top = mid + bb_dev * std
        bb_bot = mid - bb_dev * std
        for atr_m in GRID_ATR:
            for rr in GRID_RR:
                for adx_th in GRID_ADX:
                    r = simulate_inner(close, high, low, ema_v, rsi_v,
                                       atr_v, adx_v, bb_top, bb_bot,
                                       atr_m, rr, adx_th, FIXED_RISK)
                    if r:
                        r["cfg"]   = dict(bb_dev=bb_dev, atr_mult=atr_m,
                                          rr=rr, adx_th=adx_th)
                        r["score"] = (r["pnl_pct"] * (r["win_rate"] / 50.0)
                                      / max(r["max_dd"], 1.0))
                        results.append(r)
    return results

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    exchange = ccxt.binance({"enableRateLimit": True})

    print("=" * 70)
    print("  BB Parameter Optimization — All Symbols")
    print("=" * 70)
    print("\nStep 1: Data (cached in csv/, downloading if missing)...")

    datasets = {}
    for sym, name in SYMBOLS.items():
        df = fetch_or_load(sym, name, exchange)
        if df is not None and len(df) > 1000:
            datasets[name] = df

    print(f"\nStep 2: Optimizing {len(datasets)} symbols × 216 combos...\n")

    lines = []
    best_per_symbol = {}
    t0 = time.time()

    for name, df in datasets.items():
        t1 = time.time()
        results = optimize_symbol(name, df)
        elapsed = time.time() - t1
        print(f"  {name:<5}: {len(results):>3} valid configs in {elapsed:.1f}s", flush=True)

        if not results:
            lines.append(f"\n{name}: No valid configs found")
            continue

        top_score = sorted(results, key=lambda x: x["score"], reverse=True)
        top_pnl   = sorted([r for r in results
                            if r["win_rate"] >= 50 and r["max_dd"] < 20],
                           key=lambda x: x["pnl_pct"], reverse=True)

        def cfg_str(r):
            c = r["cfg"]
            adx_s = f"ADX>{c['adx_th']}" if c["adx_th"] > 0 else "NoADX"
            return (f"BB={c['bb_dev']}, ATR×{c['atr_mult']}, RR={c['rr']}, {adx_s} | "
                    f"WR:{r['win_rate']:.1f}% | PnL:{r['pnl_pct']:+.1f}% | "
                    f"DD:{r['max_dd']:.1f}% | {r['trades_per_year']:.0f} trades/yr")

        lines.append(f"\n{'─'*80}")
        lines.append(f"  {name}  ({df.index[0].date()} → {df.index[-1].date()})  "
                     f"[{len(df):,} bars]")
        lines.append(f"{'─'*80}")
        lines.append("  Top 5 by composite score:")
        for i, r in enumerate(top_score[:5]):
            lines.append(f"    #{i+1} {cfg_str(r)}  [score:{r['score']:.2f}]")

        if top_pnl:
            lines.append("  Best with WR≥50% and DD<20%:")
            for i, r in enumerate(top_pnl[:3]):
                lines.append(f"    #{i+1} {cfg_str(r)}")
            best_per_symbol[name] = top_pnl[0]
        else:
            lines.append("  ⚠️  No config achieved WR≥50% + DD<20%")
            best_per_symbol[name] = top_score[0]

    # Final summary
    lines.append(f"\n{'='*82}")
    lines.append("  FINAL SUMMARY — Best config per symbol")
    lines.append(f"{'='*82}")
    lines.append(f"  {'Symbol':<6} {'BB':>5} {'ATR':>5} {'RR':>5} {'ADX':>6} "
                 f"{'WR':>6} {'PnL':>8} {'DD':>7} {'Trades/yr':>10}  Use?")
    lines.append("  " + "-"*80)

    recommended = []
    total_trades = 0
    for name, r in best_per_symbol.items():
        c    = r["cfg"]
        use  = "✅" if r["win_rate"] >= 50 and r["max_dd"] < 20 and r["pnl_pct"] > 0 else "⚠️ "
        adx_s = f">{c['adx_th']}" if c["adx_th"] > 0 else "off"
        lines.append(f"  {name:<6} {c['bb_dev']:>5} {c['atr_mult']:>5} {c['rr']:>5} "
                     f"{adx_s:>6} {r['win_rate']:>5.1f}% {r['pnl_pct']:>+7.1f}% "
                     f"{r['max_dd']:>6.1f}% {r['trades_per_year']:>9.0f}/yr  {use}")
        if r["win_rate"] >= 50 and r["max_dd"] < 20 and r["pnl_pct"] > 0:
            recommended.append(name)
            total_trades += r["trades_per_year"]

    lines.append(f"\n  ✅ Confirmed edge: {recommended}")
    lines.append(f"  📊 Combined trades/year: ~{total_trades:.0f}  "
                 f"(~{total_trades/365:.1f}/day)")
    lines.append(f"\n  Total time: {time.time()-t0:.1f}s")

    output = "\n".join(lines)
    print("\n" + output)

    with open(RESULTS_FILE, "w") as f:
        f.write(output)
    print(f"\nResults saved to {RESULTS_FILE}")


if __name__ == "__main__":
    run()
