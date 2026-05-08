"""
VWAP Reversion Backtest
------------------------
Anchored daily VWAP with standard deviation bands.
Entry: price touches VWAP ± band (RSI confirmation)
TP:   price returns to VWAP midline
SL:   ATR-based hard stop

Results saved to vwap_results.txt
"""
import numpy as np
import pandas as pd
import itertools
import time

COMMISSION   = 0.0006
SLIPPAGE     = 0.0005
LEVERAGE     = 20.0
START_CASH   = 10_000.0
RESULTS_FILE = os.path.join("results", "vwap_results.txt")


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl  = df['high'] - df['low']
    hc  = (df['high'] - df['close'].shift()).abs()
    lc  = (df['low']  - df['close'].shift()).abs()
    tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calc_vwap_bands(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """
    Daily-anchored VWAP + rolling intra-session std deviation.
    Resets at midnight UTC each day.
    """
    d = df.copy()
    d['date']     = d.index.normalize()          # UTC midnight anchor
    d['tp']       = (d['high'] + d['low'] + d['close']) / 3
    d['tp_vol']   = d['tp'] * d['volume']

    d['cum_tv']   = d.groupby('date')['tp_vol'].cumsum()
    d['cum_v']    = d.groupby('date')['volume'].cumsum()
    d['vwap']     = d['cum_tv'] / d['cum_v'].replace(0, np.nan)

    # Intra-session expanding std of (typical_price - vwap)
    d['dev']      = d['tp'] - d['vwap']
    d['vwap_std'] = (
        d.groupby('date')['dev']
         .transform(lambda x: x.expanding().std())
         .bfill()
         .fillna(1.0)
    )

    return d['vwap'], d['vwap_std']


# ---------------------------------------------------------------------------
# Core vectorized simulation
# ---------------------------------------------------------------------------

def simulate(df: pd.DataFrame,
             band_mult: float,
             rsi_lower: int,
             rsi_upper: int,
             atr_sl_mult: float,
             risk_per_trade: float,
             min_std: float = 50.0   # ignore bands when std too narrow (< $50)
             ) -> dict | None:

    close  = df['close'].values
    high   = df['high'].values
    low    = df['low'].values
    vwap   = df['vwap'].values
    vstd   = df['vwap_std'].values
    rsi_v  = df['rsi'].values
    atr_v  = df['atr'].values
    n      = len(close)

    equity   = START_CASH
    max_eq   = START_CASH
    max_dd   = 0.0
    wins = losses = 0
    in_trade     = False
    sl = tp_price = size = risk_amt = 0.0
    side         = 0

    for i in range(50, n - 1):
        if np.isnan(vwap[i]) or np.isnan(vstd[i]) or np.isnan(rsi_v[i]):
            continue

        band = vstd[i] * band_mult
        if band < min_std:           # too narrow — skip choppy open
            continue

        upper = vwap[i] + band
        lower = vwap[i] - band

        if not in_trade:
            # LONG: price touches/pierces lower band + RSI oversold
            if close[i] <= lower and rsi_v[i] < rsi_lower:
                side       = 1
                fill       = close[i] * (1 + SLIPPAGE)
                sl_dist    = atr_v[i] * atr_sl_mult
                sl         = fill - sl_dist
                tp_price   = vwap[i]              # target = VWAP midline
                risk_amt   = equity * risk_per_trade
                size       = min(risk_amt / sl_dist,
                                 (equity * LEVERAGE) / fill)
                equity    -= fill * size * COMMISSION
                in_trade   = True

            # SHORT: price touches/pierces upper band + RSI overbought
            elif close[i] >= upper and rsi_v[i] > rsi_upper:
                side       = -1
                fill       = close[i] * (1 - SLIPPAGE)
                sl_dist    = atr_v[i] * atr_sl_mult
                sl         = fill + sl_dist
                tp_price   = vwap[i]
                risk_amt   = equity * risk_per_trade
                size       = min(risk_amt / sl_dist,
                                 (equity * LEVERAGE) / fill)
                equity    -= fill * size * COMMISSION
                in_trade   = True

        else:
            hit_sl = hit_tp = False

            if side == 1:
                if low[i]  <= sl:        hit_sl = True;  exit_px = sl
                elif high[i] >= tp_price: hit_tp = True; exit_px = tp_price
            else:
                if high[i] >= sl:        hit_sl = True;  exit_px = sl
                elif low[i]  <= tp_price: hit_tp = True; exit_px = tp_price

            if hit_sl or hit_tp:
                if hit_tp:
                    equity += risk_amt * (abs(tp_price - (exit_px if side==1 else exit_px))
                                         / (sl_dist if sl_dist else 1))
                    # Simpler: approximate TP PnL as side × (tp - entry) × size
                    pnl     = side * (tp_price - (sl + side * sl_dist)) * size
                    equity += max(pnl, 0)          # guard against numerical oddity
                    wins   += 1
                else:
                    equity -= risk_amt
                    losses += 1

                equity -= exit_px * size * COMMISSION

                if equity <= 0:
                    return None      # blown account

                if equity > max_eq:
                    max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd:
                        max_dd = dd

                in_trade = False

    total = wins + losses
    if total < 30:
        return None

    return {
        'win_rate':        wins / total * 100,
        'pnl_pct':         (equity - START_CASH) / START_CASH * 100,
        'max_dd':          max_dd,
        'trades':          total,
        'trades_per_year': total / 3.0,
    }


# ---------------------------------------------------------------------------
# Optimization sweep
# ---------------------------------------------------------------------------

def run():
    print("Loading data...", flush=True)
    df = pd.read_csv('BTCUSDT_15m_3yrs.csv',
                     parse_dates=['datetime'], index_col='datetime')
    print(f"Loaded {len(df):,} bars  ({df.index[0].date()} → {df.index[-1].date()})")

    print("Computing VWAP bands, RSI, ATR...", flush=True)
    df['vwap'], df['vwap_std'] = calc_vwap_bands(df)
    df['rsi'] = calc_rsi(df['close'])
    df['atr'] = calc_atr(df)
    print("Indicators ready.\n", flush=True)

    param_grid = list(itertools.product(
        [1.0, 1.5, 2.0, 2.5],   # band_mult  (VWAP std multiples)
        [30, 35, 40],             # rsi_lower
        [60, 65, 70],             # rsi_upper
        [1.0, 1.5, 2.0],         # atr_sl_mult
        [0.02, 0.03],             # risk_per_trade
    ))
    print(f"Sweeping {len(param_grid)} combinations...\n", flush=True)

    t0 = time.time()
    results = []
    for p in param_grid:
        band_m, rsi_l, rsi_u, atr_m, risk = p
        r = simulate(df, band_m, rsi_l, rsi_u, atr_m, risk)
        if r:
            r['cfg'] = dict(band_mult=band_m, rsi_lower=rsi_l, rsi_upper=rsi_u,
                            atr_sl_mult=atr_m, risk_pct=risk * 100)
            results.append(r)

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s — {len(results)} valid configs\n")

    for r in results:
        r['score'] = r['pnl_pct'] * (r['win_rate'] / 50.0) / max(r['max_dd'], 1.0)

    def row(i, r):
        c = r['cfg']
        return (f"  #{i:3d} | Band={c['band_mult']}σ, RSI={c['rsi_lower']}/{c['rsi_upper']}, "
                f"SL={c['atr_sl_mult']}×ATR, Risk={c['risk_pct']:.0f}% | "
                f"WR:{r['win_rate']:.1f}% | PnL:{r['pnl_pct']:+.1f}% | "
                f"DD:{r['max_dd']:.1f}% | Trades/yr:{r['trades_per_year']:.0f} | "
                f"Score:{r['score']:.2f}")

    lines = []
    sep   = "=" * 115

    # View 1: Top 15 by composite score
    top = sorted(results, key=lambda x: x['score'], reverse=True)
    lines.append(f"\n{sep}")
    lines.append("TOP 15 BY COMPOSITE SCORE")
    lines.append(sep)
    for i, r in enumerate(top[:15]): lines.append(row(i+1, r))

    # View 2: WR>=50%, DD<20%, best PnL
    safe = [r for r in results if r['win_rate'] >= 50 and r['max_dd'] < 20]
    lines.append(f"\n{sep}")
    lines.append(f"TOP 15 BY PnL  (WR≥50%, DD<20%)  —  {len(safe)} qualifying configs")
    lines.append(sep)
    for i, r in enumerate(sorted(safe, key=lambda x: x['pnl_pct'], reverse=True)[:15]):
        lines.append(row(i+1, r))

    # View 3: High frequency >= 365 trades/yr, WR>=50%, DD<20%
    hf = [r for r in safe if r['trades_per_year'] >= 365]
    lines.append(f"\n{sep}")
    lines.append(f"HIGH-FREQ  (WR≥50%, DD<20%, ≥365 trades/yr)  —  {len(hf)} configs")
    lines.append(sep)
    tgt = hf if hf else [r for r in safe if r['trades_per_year'] >= 100]
    for i, r in enumerate(sorted(tgt, key=lambda x: x['pnl_pct'], reverse=True)[:15]):
        lines.append(row(i+1, r))

    output = "\n".join(lines)
    print(output)

    with open(RESULTS_FILE, 'w') as f:
        f.write(output)
    print(f"\nResults saved to {RESULTS_FILE}")


if __name__ == '__main__':
    run()
