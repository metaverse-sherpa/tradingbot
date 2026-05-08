"""
Combined Portfolio Backtest
-----------------------------
Runs all 11 symbols simultaneously with their individually-optimised
parameters, sharing a single equity pool.

Each trade risks RISK_PER_TRADE (1%) of current equity.
Multiple positions can be open simultaneously (one per symbol).

Results saved to results/portfolio_results.txt
"""

import numpy as np
import pandas as pd
import os
import time

CSV_DIR     = "csv"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)
RESULTS_FILE = os.path.join(RESULTS_DIR, "portfolio_results.txt")

# ---------------------------------------------------------------------------
# Portfolio settings
# ---------------------------------------------------------------------------
START_CASH      = 10_000.0
RISK_PER_TRADE  = 0.01      # 1% of equity per symbol per trade
LEVERAGE        = 20.0
COMMISSION      = 0.0006
SLIPPAGE        = 0.0005

BB_PERIOD = 20
EMA_PERIOD = 200

# ---------------------------------------------------------------------------
# Optimised per-symbol configs (includes frequency-boost updates)
# ---------------------------------------------------------------------------
SYMBOL_CONFIGS = {
    "BTC":  {"bb_dev": 2.5, "atr_mult": 6.0, "rr": 1.25, "adx_th": 20, "rsi_l": 30},
    "ETH":  {"bb_dev": 2.5, "atr_mult": 5.0, "rr": 1.25, "adx_th": 25, "rsi_l": 30},
    "SOL":  {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.25, "adx_th": 20, "rsi_l": 30},
    "DOGE": {"bb_dev": 2.0, "atr_mult": 5.0, "rr": 1.25, "adx_th":  0, "rsi_l": 30},
    "ADA":  {"bb_dev": 2.5, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 25, "rsi_l": 40},
    "AVAX": {"bb_dev": 3.0, "atr_mult": 6.0, "rr": 1.25, "adx_th": 20, "rsi_l": 35},
    "LINK": {"bb_dev": 2.0, "atr_mult": 6.0, "rr": 1.0,  "adx_th": 20, "rsi_l": 30},
    "DOT":  {"bb_dev": 2.5, "atr_mult": 4.0, "rr": 1.25, "adx_th": 20, "rsi_l": 30},
    "TON":  {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.25, "adx_th": 20, "rsi_l": 30},
    "ZEC":  {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 20, "rsi_l": 30},
    "PEPE": {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 25, "rsi_l": 30},
}

# ---------------------------------------------------------------------------
# Indicators (Wilder smoothing)
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

def prepare_indicators(df, cfg):
    """Compute all indicator arrays for a symbol."""
    close_s    = df["close"]
    mid        = close_s.rolling(BB_PERIOD).mean()
    std        = close_s.rolling(BB_PERIOD).std()
    bb_top     = (mid + cfg["bb_dev"] * std).values
    bb_bot     = (mid - cfg["bb_dev"] * std).values
    return {
        "close":  close_s.values,
        "high":   df["high"].values,
        "low":    df["low"].values,
        "ema":    calc_ema(close_s, EMA_PERIOD).values,
        "rsi":    calc_rsi(close_s).values,
        "atr":    calc_atr(df).values,
        "adx":    calc_adx(df).values,
        "bb_top": bb_top,
        "bb_bot": bb_bot,
        "index":  df.index,
    }

# ---------------------------------------------------------------------------
# Portfolio simulation — all symbols share one equity pool
# ---------------------------------------------------------------------------

def run_portfolio(datasets: dict) -> dict:
    # Align all symbols to a common time index
    # Use the intersection of all dates for apples-to-apples comparison
    all_indices = [v["index"] for v in datasets.values()]
    common_idx  = all_indices[0]
    for idx in all_indices[1:]:
        common_idx = common_idx.intersection(idx)

    n_bars = len(common_idx)
    print(f"  Common timeline: {common_idx[0].date()} → {common_idx[-1].date()} "
          f"({n_bars:,} bars)")

    # Remap each symbol's arrays to the common index positions
    aligned = {}
    for name, d in datasets.items():
        pos = d["index"].get_indexer(common_idx)
        valid = pos >= 0
        arr = {}
        for key in ["close","high","low","ema","rsi","atr","adx","bb_top","bb_bot"]:
            a = d[key]
            arr[key] = np.where(valid, a[np.where(valid, pos, 0)], np.nan)
        aligned[name] = arr

    # Per-symbol trade state
    states = {name: {
        "in_trade": False, "cooldown": 0,
        "side": 0, "sl": 0.0, "tp": 0.0,
        "size": 0.0, "risk_amt": 0.0, "sl_dist": 0.0,
        "wins": 0, "losses": 0,
    } for name in SYMBOL_CONFIGS}

    equity   = START_CASH
    max_eq   = START_CASH
    max_dd   = 0.0
    warmup   = max(EMA_PERIOD, 42)   # generous warmup
    equity_curve = []

    for i in range(warmup, n_bars - 1):
        # --- 1. Close any open positions that hit SL/TP ---
        for name, cfg in SYMBOL_CONFIGS.items():
            st = states[name]
            if not st["in_trade"]:
                continue
            arr    = aligned[name]
            hi     = arr["high"][i]
            lo     = arr["low"][i]
            ex     = arr["close"][i]
            hit_sl = hit_tp = False

            if st["side"] == 1:
                if lo <= st["sl"]:  hit_sl = True; ex = st["sl"]
                elif hi >= st["tp"]: hit_tp = True; ex = st["tp"]
            else:
                if hi >= st["sl"]:  hit_sl = True; ex = st["sl"]
                elif lo <= st["tp"]: hit_tp = True; ex = st["tp"]

            if hit_sl or hit_tp:
                pnl     = st["risk_amt"] * cfg["rr"] if hit_tp else -st["risk_amt"]
                equity += pnl - ex * st["size"] * COMMISSION
                if hit_tp: st["wins"]   += 1
                else:      st["losses"] += 1
                st["in_trade"] = False
                st["cooldown"] = 3
                if equity > max_eq: max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd: max_dd = dd

        # --- 2. Check for new entries ---
        for name, cfg in SYMBOL_CONFIGS.items():
            st = states[name]
            if st["in_trade"]:
                continue
            if st["cooldown"] > 0:
                st["cooldown"] -= 1
                continue

            arr    = aligned[name]
            close  = arr["close"][i]
            ema_v  = arr["ema"][i]
            rsi_v  = arr["rsi"][i]
            atr_v  = arr["atr"][i]
            adx_v  = arr["adx"][i]
            bb_top = arr["bb_top"][i]
            bb_bot = arr["bb_bot"][i]
            rsi_u  = 100 - cfg["rsi_l"]

            if any(np.isnan(v) for v in [ema_v, rsi_v, atr_v, adx_v, bb_top, bb_bot]):
                continue
            if cfg["adx_th"] > 0 and adx_v < cfg["adx_th"]:
                continue

            if close > ema_v and close < bb_bot and rsi_v < cfg["rsi_l"]:
                fill          = close * (1 + SLIPPAGE)
                sl_dist       = atr_v * cfg["atr_mult"]
                st["side"]    = 1
                st["sl"]      = fill - sl_dist
                st["tp"]      = fill + sl_dist * cfg["rr"]
                st["risk_amt"]= equity * RISK_PER_TRADE
                st["size"]    = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                st["sl_dist"] = sl_dist
                equity       -= fill * st["size"] * COMMISSION
                st["in_trade"]= True

            elif close < ema_v and close > bb_top and rsi_v > rsi_u:
                fill          = close * (1 - SLIPPAGE)
                sl_dist       = atr_v * cfg["atr_mult"]
                st["side"]    = -1
                st["sl"]      = fill + sl_dist
                st["tp"]      = fill - sl_dist * cfg["rr"]
                st["risk_amt"]= equity * RISK_PER_TRADE
                st["size"]    = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                st["sl_dist"] = sl_dist
                equity       -= fill * st["size"] * COMMISSION
                st["in_trade"]= True

        equity_curve.append(equity)

    # Gather per-symbol stats
    sym_stats = {}
    total_wins = total_losses = 0
    for name, st in states.items():
        w, l = st["wins"], st["losses"]
        total_wins   += w
        total_losses += l
        sym_stats[name] = {"wins": w, "losses": l, "trades": w + l}

    total_trades = total_wins + total_losses
    years        = n_bars / (4 * 24 * 365)   # 15m bars per year
    wr           = total_wins / total_trades * 100 if total_trades else 0
    pnl_pct      = (equity - START_CASH) / START_CASH * 100

    return {
        "equity_curve": equity_curve,
        "final_equity": equity,
        "pnl_pct":      pnl_pct,
        "max_dd":       max_dd,
        "total_trades": total_trades,
        "win_rate":     wr,
        "trades_per_yr": total_trades / years,
        "years":        years,
        "sym_stats":    sym_stats,
        "start":        common_idx[0],
        "end":          common_idx[-1],
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    print("=" * 65)
    print("  Combined Portfolio Backtest — 11 Symbols")
    print(f"  Risk/trade: {RISK_PER_TRADE*100:.0f}% | Leverage: {LEVERAGE}x")
    print(f"  Starting equity: ${START_CASH:,.0f}")
    print("=" * 65)

    # Load cached data
    print("\nLoading data...")
    datasets = {}
    for name in SYMBOL_CONFIGS:
        path = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")
        if not os.path.exists(path):
            print(f"  {name}: ⚠️  cache missing — run optimize_symbols.py first")
            continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        print(f"  {name:<5}: {len(df):,} bars  ({df.index[0].date()} → {df.index[-1].date()})")
        datasets[name] = prepare_indicators(df, SYMBOL_CONFIGS[name])

    print(f"\nRunning portfolio simulation ({len(datasets)} symbols)...")
    t0  = time.time()
    res = run_portfolio(datasets)
    elapsed = time.time() - t0

    # Build output
    lines = []
    lines.append("\n" + "=" * 65)
    lines.append("  PORTFOLIO RESULTS")
    lines.append("=" * 65)
    lines.append(f"  Period:          {res['start'].date()} → {res['end'].date()}")
    lines.append(f"  Duration:        {res['years']:.1f} years")
    lines.append(f"  Starting equity: ${START_CASH:,.2f}")
    lines.append(f"  Final equity:    ${res['final_equity']:,.2f}")
    lines.append(f"  Total PnL:       {res['pnl_pct']:+.1f}%")
    lines.append(f"  Win Rate:        {res['win_rate']:.1f}%")
    lines.append(f"  Max Drawdown:    {res['max_dd']:.1f}%")
    lines.append(f"  Total Trades:    {res['total_trades']}  ({res['trades_per_yr']:.0f}/yr,  "
                 f"{res['trades_per_yr']/365:.2f}/day)")
    lines.append("")

    lines.append("  Per-Symbol Breakdown:")
    lines.append(f"  {'Symbol':<6} {'Trades':>7} {'Trades/yr':>10} {'WR':>6}")
    lines.append("  " + "-" * 35)
    for name, s in res["sym_stats"].items():
        if s["trades"] == 0:
            continue
        wr = s["wins"] / s["trades"] * 100 if s["trades"] else 0
        tpy = s["trades"] / res["years"]
        lines.append(f"  {name:<6} {s['trades']:>7}  {tpy:>8.0f}/yr  {wr:>5.1f}%")

    lines.append(f"\n  Simulation time: {elapsed:.1f}s")

    output = "\n".join(lines)
    print(output)

    with open(RESULTS_FILE, "w") as f:
        f.write(output)
    print(f"\nSaved to {RESULTS_FILE}")


if __name__ == "__main__":
    run()
