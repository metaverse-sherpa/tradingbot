"""
Frequency Boost Sweep — AVAX, ETH, ADA
-----------------------------------------
Adds RSI threshold as a new parameter to find configs that trade
more frequently while keeping WR >= 50%.

Current best (from full sweep, RSI fixed at 30/70):
  AVAX: BB=3.0, ATR×6, RR=1.25, NoADX  → 69.2% WR, 4 trades/yr
  ETH:  BB=3.0, ATR×5, RR=1.25, ADX>25 → 68.2% WR, 7 trades/yr
  ADA:  BB=2.5, ATR×6, RR=1.25, ADX>25 → 57.7% WR, 9 trades/yr

Goal: find configs with WR >= 50% and more trades/yr than above.
Results saved to results/frequency_boost_results.txt
"""

import numpy as np
import pandas as pd
import os
import time

CSV_DIR     = "csv"
RESULTS_DIR = "results"
RESULTS_FILE = os.path.join(RESULTS_DIR, "frequency_boost_results.txt")

# Fixed constants
BB_PERIOD  = 20
EMA_PERIOD = 200
ATR_PERIOD = 14
ADX_PERIOD = 14
COMMISSION = 0.0006
SLIPPAGE   = 0.0005
LEVERAGE   = 20.0
START_CASH = 10_000.0
FIXED_RISK = 0.02

# Expanded grid — adding RSI threshold as a new dimension
GRID_BB   = [2.0, 2.5, 3.0]
GRID_ATR  = [4.0, 5.0, 6.0]
GRID_RR   = [1.0, 1.25]
GRID_ADX  = [0, 15, 20, 25]
GRID_RSI  = [30, 35, 40]   # ← new: oversold threshold for longs (mirrored for shorts)

# Symbols to boost (cache files, min trades baseline to beat)
TARGETS = {
    "AVAX": {"file": os.path.join(CSV_DIR, "cache_AVAX_15m.csv"), "baseline_trades": 4},
    "ETH":  {"file": os.path.join(CSV_DIR, "cache_ETH_15m.csv"),  "baseline_trades": 7},
    "ADA":  {"file": os.path.join(CSV_DIR, "cache_ADA_15m.csv"),  "baseline_trades": 9},
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

# ---------------------------------------------------------------------------
# Fast inner simulation
# ---------------------------------------------------------------------------

def simulate(close, high, low, ema_v, rsi_v, atr_v, adx_v,
             bb_top, bb_bot, atr_mult, rr_ratio, adx_th, rsi_lower, risk):
    n        = len(close)
    rsi_upper = 100 - rsi_lower   # symmetric: e.g. lower=35 → upper=65
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

            if close[i] > ema_v[i] and close[i] < bb_bot[i] and rsi_v[i] < rsi_lower:
                side     = 1
                fill     = close[i] * (1 + SLIPPAGE)
                sl_dist  = atr_v[i] * atr_mult
                sl       = fill - sl_dist
                tp       = fill + sl_dist * rr_ratio
                risk_amt = equity * risk
                size     = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill)
                equity  -= fill * size * COMMISSION
                in_trade = True

            elif close[i] < ema_v[i] and close[i] > bb_top[i] and rsi_v[i] > rsi_upper:
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
# Main
# ---------------------------------------------------------------------------

def run():
    total_combos = (len(GRID_BB) * len(GRID_ATR) * len(GRID_RR)
                    * len(GRID_ADX) * len(GRID_RSI))
    print("=" * 70)
    print("  Frequency Boost Sweep — AVAX, ETH, ADA")
    print(f"  Grid: {total_combos} combos per symbol  "
          f"(adds RSI threshold: {GRID_RSI})")
    print("=" * 70)

    all_lines = []
    t0 = time.time()

    for name, meta in TARGETS.items():
        if not os.path.exists(meta["file"]):
            print(f"\n{name}: cache file not found — run optimize_symbols.py first")
            continue

        df = pd.read_csv(meta["file"], parse_dates=["datetime"], index_col="datetime")
        print(f"\n{name}: {len(df):,} bars  ({df.index[0].date()} → {df.index[-1].date()})",
              flush=True)

        close_s = df["close"]
        ema_v   = calc_ema(close_s, EMA_PERIOD).values
        rsi_v   = calc_rsi(close_s).values
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
                        for rsi_l in GRID_RSI:
                            r = simulate(close, high, low, ema_v, rsi_v,
                                         atr_v, adx_v, bb_top, bb_bot,
                                         atr_m, rr, adx_th, rsi_l, FIXED_RISK)
                            if r:
                                r["cfg"]   = dict(bb_dev=bb_dev, atr_mult=atr_m,
                                                  rr=rr, adx_th=adx_th, rsi_l=rsi_l)
                                r["score"] = (r["pnl_pct"] * (r["win_rate"] / 50.0)
                                              / max(r["max_dd"], 1.0))
                                results.append(r)

        baseline = meta["baseline_trades"]

        # Filter: WR >= 50%, DD < 20%, more trades than baseline
        boosted = [r for r in results
                   if r["win_rate"] >= 50
                   and r["max_dd"] < 20
                   and r["trades_per_year"] > baseline]
        boosted.sort(key=lambda x: x["trades_per_year"], reverse=True)

        # Also show: best WR >= 50%, any trades (for reference)
        any_wr50 = [r for r in results
                    if r["win_rate"] >= 50 and r["max_dd"] < 20]
        any_wr50.sort(key=lambda x: x["pnl_pct"], reverse=True)

        def fmt(r):
            c = r["cfg"]
            adx_s = f"ADX>{c['adx_th']}" if c["adx_th"] > 0 else "NoADX"
            return (f"BB={c['bb_dev']}, ATR×{c['atr_mult']}, RR={c['rr']}, "
                    f"{adx_s}, RSI<{c['rsi_l']} | "
                    f"WR:{r['win_rate']:.1f}% | PnL:{r['pnl_pct']:+.1f}% | "
                    f"DD:{r['max_dd']:.1f}% | {r['trades_per_year']:.0f} trades/yr")

        lines = []
        lines.append(f"\n{'─'*80}")
        lines.append(f"  {name}  (baseline: {baseline} trades/yr, WR: see above)")
        lines.append(f"{'─'*80}")
        lines.append(f"  Configs with WR≥50%, DD<20%, and MORE trades than baseline "
                     f"({len(boosted)} found):")
        if boosted:
            for i, r in enumerate(boosted[:10]):
                lines.append(f"    #{i+1} {fmt(r)}")
        else:
            lines.append("    None — relaxing RSI still couldn't beat the baseline trade count")
            lines.append("    while keeping WR≥50%.")

        lines.append(f"\n  Reference — best PnL configs with WR≥50%, DD<20% (all RSI):")
        for i, r in enumerate(any_wr50[:5]):
            lines.append(f"    #{i+1} {fmt(r)}")

        all_lines.extend(lines)
        for l in lines:
            print(l)

    elapsed = time.time() - t0
    all_lines.append(f"\nTotal time: {elapsed:.1f}s")
    print(f"\nTotal time: {elapsed:.1f}s")

    with open(RESULTS_FILE, "w") as f:
        f.write("\n".join(all_lines))
    print(f"Results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    run()
