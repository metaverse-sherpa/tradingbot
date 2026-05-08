"""
Optimized Portfolio Backtest — Before vs After
-------------------------------------------------
Runs 3 variants side-by-side to measure the exact impact of each optimization:

  Variant A (baseline):  current strategy
  Variant B (optimized): ADX upper cap=35 + DOGE longs-only
  Variant C (full):      A + B + session filter (block 04:00 & 12:00 UTC)

Results saved to results/optimized_results.txt
"""

import numpy as np
import pandas as pd
import os
import time

CSV_DIR     = "csv"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)
RESULTS_FILE = os.path.join(RESULTS_DIR, "optimized_results.txt")

START_CASH     = 10_000.0
RISK_PER_TRADE = 0.01
LEVERAGE       = 20.0
COMMISSION     = 0.0006
SLIPPAGE       = 0.0005
BB_PERIOD      = 20
EMA_PERIOD     = 200

# Expanded Basket: 20 Symbols (10 Original + 10 High Volume)
SYMBOL_CONFIGS = {
    # Original 10
    "BTC":  {"bb_dev": 2.5, "atr_mult": 6.0, "rr": 1.25, "adx_th": 20, "rsi_l": 30},
    "ETH":  {"bb_dev": 2.5, "atr_mult": 5.0, "rr": 1.25, "adx_th": 25, "rsi_l": 30},
    "SOL":  {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.25, "adx_th": 20, "rsi_l": 30},
    "DOGE": {"bb_dev": 2.0, "atr_mult": 5.0, "rr": 1.25, "adx_th":  0, "rsi_l": 30},
    "ADA":  {"bb_dev": 2.5, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 25, "rsi_l": 40},
    "LINK": {"bb_dev": 2.0, "atr_mult": 6.0, "rr": 1.0,  "adx_th": 20, "rsi_l": 30},
    "DOT":  {"bb_dev": 2.5, "atr_mult": 4.0, "rr": 1.25, "adx_th": 20, "rsi_l": 30},
    "TON":  {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.25, "adx_th": 20, "rsi_l": 30},
    "ZEC":  {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 20, "rsi_l": 30},
    "PEPE": {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 25, "rsi_l": 30},
    # New 10 (High Volume)
    "BNB":  {"bb_dev": 2.5, "atr_mult": 4.0, "rr": 1.25, "adx_th": 25, "rsi_l": 30},
    "NEAR": {"bb_dev": 3.0, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 25, "rsi_l": 30},
    "SUI":  {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 25, "rsi_l": 30},
    "NOT":  {"bb_dev": 2.0, "atr_mult": 6.0, "rr": 1.25, "adx_th":  0, "rsi_l": 30},
    "TAO":  {"bb_dev": 2.0, "atr_mult": 5.0, "rr": 1.25, "adx_th":  0, "rsi_l": 30},
    "ONDO": {"bb_dev": 2.5, "atr_mult": 5.0, "rr": 1.25, "adx_th":  0, "rsi_l": 30},
    "ENA":  {"bb_dev": 2.0, "atr_mult": 4.0, "rr": 1.0,  "adx_th": 25, "rsi_l": 30},
    "FET":  {"bb_dev": 2.0, "atr_mult": 6.0, "rr": 1.0,  "adx_th": 25, "rsi_l": 30},
    "WIF":  {"bb_dev": 3.0, "atr_mult": 5.0, "rr": 1.25, "adx_th": 25, "rsi_l": 30},
    "SHIB": {"bb_dev": 2.5, "atr_mult": 6.0, "rr": 1.25, "adx_th": 15, "rsi_l": 30},
}

ADX_UPPER_CAP  = 35          # block entries when trend is too strong
BAD_HOURS_UTC  = {4, 12}     # low-liquidity / low-WR session hours
DOGE_LONG_ONLY = {"DOGE"}    # symbols where shorts are disabled

# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def calc_ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def calc_rsi(s, p=14):
    d    = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1/p, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/p, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))

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

def prepare(df, cfg):
    close_s = df["close"]
    mid     = close_s.rolling(BB_PERIOD).mean()
    std     = close_s.rolling(BB_PERIOD).std()
    return {
        "close":  close_s.values,
        "high":   df["high"].values,
        "low":    df["low"].values,
        "ema":    calc_ema(close_s, EMA_PERIOD).values,
        "rsi":    calc_rsi(close_s).values,
        "atr":    calc_atr(df).values,
        "adx":    calc_adx(df).values,
        "bb_top": (mid + cfg["bb_dev"] * std).values,
        "bb_bot": (mid - cfg["bb_dev"] * std).values,
        "index":  df.index,
    }

# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def run_simulation(datasets, adx_cap=False, doge_longs_only=False,
                   session_filter=False):
    all_indices = [v["index"] for v in datasets.values()]
    master_idx = max(all_indices, key=len)
    n_bars = len(master_idx)
    print(f"  Master timeline: {master_idx[0].date()} → {master_idx[-1].date()} "
          f"({n_bars:,} bars / {n_bars/(4*24*365):.1f} yrs)")

    aligned = {}
    for name, d in datasets.items():
        pos   = d["index"].get_indexer(master_idx)
        valid = pos >= 0
        arr   = {}
        for key in ["close","high","low","ema","rsi","atr","adx","bb_top","bb_bot"]:
            a       = d[key]
            arr[key] = np.where(valid, a[np.where(valid, pos, 0)], np.nan)
        aligned[name] = arr

    states = {name: {
        "in_trade": False, "cooldown": 0,
        "side": 0, "sl": 0.0, "tp": 0.0,
        "size": 0.0, "risk_amt": 0.0,
        "wins": 0, "losses": 0,
    } for name in SYMBOL_CONFIGS}

    equity = START_CASH
    max_eq = START_CASH
    max_dd = 0.0
    warmup = max(EMA_PERIOD, 42)

    for i in range(warmup, n_bars - 1):
        ts   = master_idx[i]
        hour = ts.hour

        # Close open positions
        for name, cfg in SYMBOL_CONFIGS.items():
            st  = states[name]
            if not st["in_trade"]: continue
            arr = aligned[name]
            hi  = arr["high"][i]; lo = arr["low"][i]
            hit_sl = hit_tp = False; ex = 0.0

            if st["side"] == 1:
                if lo <= st["sl"]:   hit_sl = True; ex = st["sl"]
                elif hi >= st["tp"]: hit_tp = True; ex = st["tp"]
            else:
                if hi >= st["sl"]:   hit_sl = True; ex = st["sl"]
                elif lo <= st["tp"]: hit_tp = True; ex = st["tp"]

            if hit_sl or hit_tp:
                pnl     = st["risk_amt"] * cfg["rr"] if hit_tp else -st["risk_amt"]
                equity += pnl - ex * st["size"] * COMMISSION
                if hit_tp: st["wins"]   += 1
                else:      st["losses"] += 1
                st["in_trade"] = False; st["cooldown"] = 3
                if equity > max_eq: max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd: max_dd = dd

        # New entries
        for name, cfg in SYMBOL_CONFIGS.items():
            st = states[name]
            if st["in_trade"]: continue
            if st["cooldown"] > 0: st["cooldown"] -= 1; continue

            # Session filter
            if session_filter and hour in BAD_HOURS_UTC:
                continue

            arr    = aligned[name]
            close  = arr["close"][i]; ema_v  = arr["ema"][i]
            rsi_v  = arr["rsi"][i];   atr_v  = arr["atr"][i]
            adx_v  = arr["adx"][i];   bb_top = arr["bb_top"][i]; bb_bot = arr["bb_bot"][i]
            rsi_u  = 100 - cfg["rsi_l"]

            if any(np.isnan(v) for v in [ema_v, rsi_v, atr_v, adx_v, bb_top, bb_bot]):
                continue
            if cfg["adx_th"] > 0 and adx_v < cfg["adx_th"]:
                continue
            # ADX upper cap — skip when trend is too strong for mean reversion
            if adx_cap and adx_v > ADX_UPPER_CAP:
                continue

            entered = False
            if close > ema_v and close < bb_bot and rsi_v < cfg["rsi_l"]:
                fill    = close * (1 + SLIPPAGE)
                sl_dist = atr_v * cfg["atr_mult"]
                st["side"] = 1
                st["sl"]   = fill - sl_dist
                st["tp"]   = fill + sl_dist * cfg["rr"]
                entered    = True
            elif close < ema_v and close > bb_top and rsi_v > rsi_u:
                # DOGE longs-only filter
                if doge_longs_only and name in DOGE_LONG_ONLY:
                    continue
                fill    = close * (1 - SLIPPAGE)
                sl_dist = atr_v * cfg["atr_mult"]
                st["side"] = -1
                st["sl"]   = fill + sl_dist
                st["tp"]   = fill - sl_dist * cfg["rr"]
                entered    = True

            if entered:
                st["risk_amt"] = equity * RISK_PER_TRADE
                st["size"]     = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity        -= fill * st["size"] * COMMISSION
                st["in_trade"] = True

    total_w = sum(s["wins"]   for s in states.values())
    total_l = sum(s["losses"] for s in states.values())
    total   = total_w + total_l
    years   = n_bars / (4 * 24 * 365)

    sym_stats = {name: {"wins": s["wins"], "losses": s["losses"],
                        "trades": s["wins"]+s["losses"]}
                 for name, s in states.items()}

    return {
        "equity":       equity,
        "pnl_pct":      (equity - START_CASH) / START_CASH * 100,
        "max_dd":       max_dd,
        "total_trades": total,
        "win_rate":     total_w / total * 100 if total else 0,
        "trades_per_yr": total / years,
        "years":        years,
        "sym_stats":    sym_stats,
        "start":        master_idx[0].date(),
        "end":          master_idx[-1].date(),
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    print("Loading data...")
    datasets = {}
    for name in SYMBOL_CONFIGS:
        path = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")
        if not os.path.exists(path):
            print(f"  {name}: missing cache"); continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        datasets[name] = prepare(df, SYMBOL_CONFIGS[name])
        print(f"  {name:<5}: {len(df):,} bars")

    variants = [
        ("A — Baseline",              dict(adx_cap=False, doge_longs_only=False, session_filter=False)),
        ("B — ADX cap + DOGE longs",  dict(adx_cap=True,  doge_longs_only=True,  session_filter=False)),
        ("C — B + Session filter",    dict(adx_cap=True,  doge_longs_only=True,  session_filter=True)),
    ]

    results = []
    for label, opts in variants:
        print(f"\nRunning {label}...", flush=True)
        t0  = time.time()
        res = run_simulation(datasets, **opts)
        print(f"  Done in {time.time()-t0:.1f}s — {res['total_trades']} trades")
        res["label"] = label
        results.append(res)

    lines = []

    # Per-variant details
    for res in results:
        lines.append(f"\n{'='*65}")
        lines.append(f"  {res['label']}")
        lines.append(f"{'='*65}")
        lines.append(f"  Period:       {res['start']} → {res['end']}")
        lines.append(f"  Final equity: ${res['equity']:,.2f}  (PnL: {res['pnl_pct']:+.1f}%)")
        lines.append(f"  Win rate:     {res['win_rate']:.1f}%")
        lines.append(f"  Max DD:       {res['max_dd']:.1f}%")
        lines.append(f"  Trades:       {res['total_trades']}  "
                     f"({res['trades_per_yr']:.0f}/yr, {res['trades_per_yr']/365:.2f}/day)")
        lines.append(f"\n  Per-symbol:")
        lines.append(f"  {'Symbol':<6} {'Trades':>7} {'Trades/yr':>10} {'WR':>6}")
        lines.append("  " + "-"*34)
        for name, s in res["sym_stats"].items():
            if s["trades"] == 0: continue
            wr  = s["wins"] / s["trades"] * 100
            tpy = s["trades"] / res["years"]
            flag = "✅" if wr >= 50 else "⚠️ "
            lines.append(f"  {name:<6} {s['trades']:>7}  {tpy:>8.0f}/yr  {wr:>5.1f}%  {flag}")

    # Comparison summary
    lines.append(f"\n{'='*65}")
    lines.append("  COMPARISON SUMMARY")
    lines.append(f"{'='*65}")
    lines.append(f"  {'Metric':<20} {'Baseline':>12} {'B (Opt)':>12} {'C (Full)':>12}")
    lines.append("  " + "-"*58)
    metrics = [
        ("Final Equity",   lambda r: f"${r['equity']:,.0f}"),
        ("PnL",            lambda r: f"{r['pnl_pct']:+.1f}%"),
        ("Win Rate",       lambda r: f"{r['win_rate']:.1f}%"),
        ("Max Drawdown",   lambda r: f"{r['max_dd']:.1f}%"),
        ("Total Trades",   lambda r: str(r['total_trades'])),
        ("Trades/yr",      lambda r: f"{r['trades_per_yr']:.0f}"),
        ("Trades/day",     lambda r: f"{r['trades_per_yr']/365:.2f}"),
    ]
    for name, fn in metrics:
        vals = [fn(r) for r in results]
        lines.append(f"  {name:<20} {vals[0]:>12} {vals[1]:>12} {vals[2]:>12}")

    output = "\n".join(lines)
    print("\n" + output)
    with open(RESULTS_FILE, "w") as f:
        f.write(output)
    print(f"\nSaved to {RESULTS_FILE}")


if __name__ == "__main__":
    run()
