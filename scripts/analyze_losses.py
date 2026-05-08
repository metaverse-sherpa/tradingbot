"""
Trade Loss Analysis
---------------------
Re-runs the portfolio simulation recording every trade's metadata,
then analyses losing trades across 4 dimensions:
  1. Direction (Long vs Short)
  2. Hour of day at entry
  3. ADX level at entry
  4. Trade duration (bars until SL/TP hit)

Also tests a Longs-Only variant to see if dropping shorts improves WR.

Results saved to results/loss_analysis_results.txt
"""

import numpy as np
import pandas as pd
import os
import time

CSV_DIR     = "csv"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)
RESULTS_FILE = os.path.join(RESULTS_DIR, "loss_analysis_results.txt")

START_CASH     = 10_000.0
RISK_PER_TRADE = 0.01
LEVERAGE       = 20.0
COMMISSION     = 0.0006
SLIPPAGE       = 0.0005
BB_PERIOD      = 20
EMA_PERIOD     = 200

# AVAX removed based on low trade count and borderline WR
SYMBOL_CONFIGS = {
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
}

# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def calc_ema(s, p):   return s.ewm(span=p, adjust=False).mean()

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
# Portfolio simulation with full trade log
# ---------------------------------------------------------------------------

def run_simulation(datasets, longs_only=False):
    all_indices = [v["index"] for v in datasets.values()]
    common_idx  = all_indices[0]
    for idx in all_indices[1:]:
        common_idx = common_idx.intersection(idx)

    n_bars = len(common_idx)

    # Remap to common index
    aligned = {}
    for name, d in datasets.items():
        pos   = d["index"].get_indexer(common_idx)
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
        "entry_bar": 0, "entry_time": None,
        "adx_at_entry": 0.0, "rsi_at_entry": 0.0,
    } for name in SYMBOL_CONFIGS}

    equity   = START_CASH
    max_eq   = START_CASH
    max_dd   = 0.0
    warmup   = max(EMA_PERIOD, 42)
    trades   = []   # full trade log

    for i in range(warmup, n_bars - 1):
        ts = common_idx[i]

        # Close open positions
        for name, cfg in SYMBOL_CONFIGS.items():
            st  = states[name]
            if not st["in_trade"]:
                continue
            arr = aligned[name]
            hi  = arr["high"][i];  lo = arr["low"][i]
            hit_sl = hit_tp = False;  ex = 0.0

            if st["side"] == 1:
                if lo <= st["sl"]:  hit_sl = True; ex = st["sl"]
                elif hi >= st["tp"]: hit_tp = True; ex = st["tp"]
            else:
                if hi >= st["sl"]:  hit_sl = True; ex = st["sl"]
                elif lo <= st["tp"]: hit_tp = True; ex = st["tp"]

            if hit_sl or hit_tp:
                pnl     = st["risk_amt"] * cfg["rr"] if hit_tp else -st["risk_amt"]
                equity += pnl - ex * st["size"] * COMMISSION
                won     = hit_tp

                trades.append({
                    "symbol":        name,
                    "side":          "Long" if st["side"] == 1 else "Short",
                    "won":           won,
                    "entry_time":    st["entry_time"],
                    "exit_time":     ts,
                    "entry_hour":    st["entry_time"].hour,
                    "duration_bars": i - st["entry_bar"],
                    "adx_at_entry":  st["adx_at_entry"],
                    "rsi_at_entry":  st["rsi_at_entry"],
                    "pnl":           pnl,
                })

                st["in_trade"] = False;  st["cooldown"] = 3
                if equity > max_eq: max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd: max_dd = dd

        # New entries
        for name, cfg in SYMBOL_CONFIGS.items():
            st  = states[name]
            if st["in_trade"]: continue
            if st["cooldown"] > 0: st["cooldown"] -= 1; continue

            arr    = aligned[name]
            close  = arr["close"][i];  ema_v  = arr["ema"][i]
            rsi_v  = arr["rsi"][i];    atr_v  = arr["atr"][i]
            adx_v  = arr["adx"][i];    bb_top = arr["bb_top"][i];  bb_bot = arr["bb_bot"][i]
            rsi_u  = 100 - cfg["rsi_l"]

            if any(np.isnan(v) for v in [ema_v, rsi_v, atr_v, adx_v, bb_top, bb_bot]):
                continue
            if cfg["adx_th"] > 0 and adx_v < cfg["adx_th"]:
                continue

            entered = False
            if close > ema_v and close < bb_bot and rsi_v < cfg["rsi_l"]:
                fill          = close * (1 + SLIPPAGE)
                sl_dist       = atr_v * cfg["atr_mult"]
                st["side"]    = 1
                st["sl"]      = fill - sl_dist
                st["tp"]      = fill + sl_dist * cfg["rr"]
                entered       = True
            elif not longs_only and close < ema_v and close > bb_top and rsi_v > rsi_u:
                fill          = close * (1 - SLIPPAGE)
                sl_dist       = atr_v * cfg["atr_mult"]
                st["side"]    = -1
                st["sl"]      = fill + sl_dist
                st["tp"]      = fill - sl_dist * cfg["rr"]
                entered       = True

            if entered:
                st["risk_amt"]      = equity * RISK_PER_TRADE
                st["size"]          = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                st["entry_bar"]     = i
                st["entry_time"]    = ts
                st["adx_at_entry"]  = adx_v
                st["rsi_at_entry"]  = rsi_v
                equity             -= fill * st["size"] * COMMISSION
                st["in_trade"]      = True

    return trades, equity, max_dd, n_bars, common_idx

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyse(trades, label, equity, max_dd, n_bars, common_idx):
    df     = pd.DataFrame(trades)
    total  = len(df)
    wins   = df["won"].sum()
    wr     = wins / total * 100 if total else 0
    years  = n_bars / (4 * 24 * 365)
    pnl    = (equity - START_CASH) / START_CASH * 100
    tpy    = total / years

    lines = []
    lines.append(f"\n{'='*65}")
    lines.append(f"  {label}")
    lines.append(f"{'='*65}")
    lines.append(f"  Period:       {common_idx[0].date()} → {common_idx[-1].date()}")
    lines.append(f"  Final equity: ${equity:,.2f}  (PnL: {pnl:+.1f}%)")
    lines.append(f"  Win rate:     {wr:.1f}%   ({int(wins)}W / {total-int(wins)}L of {total} trades)")
    lines.append(f"  Max DD:       {max_dd:.1f}%")
    lines.append(f"  Trades/yr:    {tpy:.0f}  ({tpy/365:.2f}/day)")

    if total == 0:
        return lines

    losses = df[~df["won"]]
    wins_df = df[df["won"]]

    # 1. Long vs Short breakdown
    lines.append(f"\n  --- 1. Direction Breakdown ---")
    for side in ["Long", "Short"]:
        sub = df[df["side"] == side]
        if len(sub) == 0: continue
        sub_wr = sub["won"].mean() * 100
        lines.append(f"  {side:<6}: {len(sub):>3} trades | WR: {sub_wr:.1f}% | "
                     f"Wins: {sub['won'].sum():.0f}  Losses: {(~sub['won']).sum():.0f}")

    # 2. Loss by hour of entry
    lines.append(f"\n  --- 2. Losses by Hour of Entry (UTC) ---")
    hourly = df.groupby("entry_hour")["won"].agg(["count","sum"])
    hourly["wr"] = hourly["sum"] / hourly["count"] * 100
    hourly["losses"] = hourly["count"] - hourly["sum"]
    bad_hours = hourly[hourly["wr"] < 45].sort_values("losses", ascending=False)
    good_hours = hourly[hourly["wr"] >= 55].sort_values("wr", ascending=False)
    lines.append(f"  Bad hours (WR<45%): {list(bad_hours.index.astype(int))}")
    lines.append(f"  Good hours (WR≥55%): {list(good_hours.index.astype(int))}")
    for hour in range(0, 24, 4):
        row = hourly.loc[hour] if hour in hourly.index else None
        if row is None: continue
        bar = "█" * int(row["wr"] / 5)
        lines.append(f"  {hour:02d}:00 UTC | {int(row['count']):>3} trades | "
                     f"WR: {row['wr']:>5.1f}% {bar}")

    # 3. ADX level at entry
    lines.append(f"\n  --- 3. Win Rate by ADX at Entry ---")
    df["adx_bin"] = pd.cut(df["adx_at_entry"],
                           bins=[0, 20, 25, 30, 35, 40, 100],
                           labels=["<20","20-25","25-30","30-35","35-40",">40"])
    adx_grp = df.groupby("adx_bin", observed=True)["won"].agg(["count","mean"])
    adx_grp["wr"] = adx_grp["mean"] * 100
    for bin_label, row in adx_grp.iterrows():
        if row["count"] == 0: continue
        bar = "█" * int(row["wr"] / 5)
        lines.append(f"  ADX {bin_label:<6} | {int(row['count']):>3} trades | "
                     f"WR: {row['wr']:>5.1f}% {bar}")

    # 4. Duration analysis
    lines.append(f"\n  --- 4. Trade Duration (bars until SL/TP) ---")
    lines.append(f"  Winning trades  — avg: {wins_df['duration_bars'].mean():.0f} bars "
                 f"| median: {wins_df['duration_bars'].median():.0f} bars "
                 f"| max: {wins_df['duration_bars'].max():.0f} bars")
    lines.append(f"  Losing  trades  — avg: {losses['duration_bars'].mean():.0f} bars "
                 f"| median: {losses['duration_bars'].median():.0f} bars "
                 f"| max: {losses['duration_bars'].max():.0f} bars")
    quick_losses = losses[losses["duration_bars"] <= 4]
    lines.append(f"  Quick losses (≤4 bars / ≤1hr): {len(quick_losses)} "
                 f"({len(quick_losses)/len(losses)*100:.0f}% of all losses)")

    # 5. Per-symbol WR
    lines.append(f"\n  --- 5. Per-Symbol Win Rate ---")
    for name in SYMBOL_CONFIGS:
        sub = df[df["symbol"] == name]
        if len(sub) == 0: continue
        sub_wr = sub["won"].mean() * 100
        flag   = "⚠️ " if sub_wr < 50 else "✅"
        lines.append(f"  {name:<5}: {len(sub):>3} trades | WR: {sub_wr:.1f}%  {flag}")

    return lines

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    print("Loading data...")
    datasets = {}
    for name in SYMBOL_CONFIGS:
        path = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")
        if not os.path.exists(path):
            print(f"  {name}: missing")
            continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        datasets[name] = prepare(df, SYMBOL_CONFIGS[name])
        print(f"  {name:<5}: {len(df):,} bars")

    all_lines = []

    # Run 1: Full strategy (longs + shorts)
    print("\nRun 1: Full strategy (Longs + Shorts)...")
    t0 = time.time()
    trades, equity, max_dd, n_bars, cidx = run_simulation(datasets, longs_only=False)
    print(f"  Done in {time.time()-t0:.1f}s — {len(trades)} trades")
    lines = analyse(trades, "FULL STRATEGY — Longs + Shorts", equity, max_dd, n_bars, cidx)
    all_lines.extend(lines)
    for l in lines: print(l)

    # Run 2: Longs-only
    print("\nRun 2: Longs-only variant...")
    t0 = time.time()
    trades2, equity2, max_dd2, n_bars2, cidx2 = run_simulation(datasets, longs_only=True)
    print(f"  Done in {time.time()-t0:.1f}s — {len(trades2)} trades")
    lines2 = analyse(trades2, "LONGS ONLY — Shorts Disabled", equity2, max_dd2, n_bars2, cidx2)
    all_lines.extend(lines2)
    for l in lines2: print(l)

    # Summary comparison
    df1 = pd.DataFrame(trades)
    df2 = pd.DataFrame(trades2)
    summary = [
        f"\n{'='*65}",
        "  COMPARISON SUMMARY",
        f"{'='*65}",
        f"  {'Metric':<20} {'Full (L+S)':>14} {'Longs Only':>14}",
        "  " + "-"*50,
        f"  {'Final Equity':<20} ${equity:>12,.2f} ${equity2:>12,.2f}",
        f"  {'PnL':<20} {(equity-START_CASH)/START_CASH*100:>13.1f}% "
        f"{(equity2-START_CASH)/START_CASH*100:>13.1f}%",
        f"  {'Win Rate':<20} {df1['won'].mean()*100:>13.1f}% "
        f"{df2['won'].mean()*100:>13.1f}%",
        f"  {'Max Drawdown':<20} {max_dd:>13.1f}% {max_dd2:>13.1f}%",
        f"  {'Total Trades':<20} {len(df1):>14} {len(df2):>14}",
        f"  {'Trades/yr':<20} {len(df1)/(n_bars/(4*24*365)):>13.0f} "
        f"{len(df2)/(n_bars/(4*24*365)):>13.0f}",
    ]
    all_lines.extend(summary)
    for l in summary: print(l)

    output = "\n".join(all_lines)
    with open(RESULTS_FILE, "w") as f:
        f.write(output)
    print(f"\nSaved to {RESULTS_FILE}")


if __name__ == "__main__":
    run()
