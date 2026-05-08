"""
Vectorized EMA Crossover Backtest
----------------------------------
Pure NumPy/Pandas — no Backtrader, no multiprocessing.
Runs 1000+ parameter combinations in seconds.
"""
import numpy as np
import pandas as pd
import itertools
import time
import os

COMMISSION = 0.0006   # Blofin taker fee per side
SLIPPAGE   = 0.0005   # 0.05% market order slippage
LEVERAGE   = 20.0
START_CASH = 10_000.0

# ---------------------------------------------------------------------------
# Indicator helpers (pure pandas — fast)
# ---------------------------------------------------------------------------

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl  = df['high'] - df['low']
    hc  = (df['high'] - df['close'].shift()).abs()
    lc  = (df['low']  - df['close'].shift()).abs()
    tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hi, lo, cl = df['high'], df['low'], df['close']
    pdm = hi.diff().clip(lower=0)
    ndm = (-lo.diff()).clip(lower=0)
    pdm = pdm.where(pdm > ndm, 0.0)
    ndm = ndm.where(ndm > pdm, 0.0)
    atr_v = atr(df, period)
    pdi = 100 * pdm.ewm(span=period, adjust=False).mean() / atr_v
    ndi = 100 * ndm.ewm(span=period, adjust=False).mean() / atr_v
    dx  = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(span=period, adjust=False).mean()

# ---------------------------------------------------------------------------
# Core simulation (vectorized trade-by-trade)
# ---------------------------------------------------------------------------

def simulate(df: pd.DataFrame,
             ema_fast: int, ema_slow: int,
             rsi_threshold: int,
             atr_multiplier: float, rr_ratio: float,
             risk_per_trade: float,
             adx_threshold: int = 0) -> dict:
    """
    Simulate EMA crossover strategy on df.
    Returns dict with win_rate, pnl_pct, max_dd, trade_count.
    """
    close  = df['close'].values
    high   = df['high'].values
    low    = df['low'].values
    n      = len(close)

    fast_v  = ema(df['close'], ema_fast).values
    slow_v  = ema(df['close'], ema_slow).values
    rsi_v   = rsi(df['close']).values
    atr_v   = atr(df).values
    adx_v   = adx(df).values if adx_threshold > 0 else np.full(n, 99.0)

    equity   = START_CASH
    max_eq   = START_CASH
    max_dd   = 0.0
    wins     = 0
    losses   = 0
    in_trade = False
    sl = tp = 0.0
    side = 0  # 1=long, -1=short

    warmup = max(ema_slow, 50)  # skip warmup bars

    for i in range(warmup, n - 1):
        if not in_trade:
            # ADX filter
            if adx_threshold > 0 and adx_v[i] < adx_threshold:
                continue

            # Crossover signals (compare i vs i-1)
            cross_up   = fast_v[i] > slow_v[i] and fast_v[i-1] <= slow_v[i-1]
            cross_down = fast_v[i] < slow_v[i] and fast_v[i-1] >= slow_v[i-1]

            if cross_up and rsi_v[i] > rsi_threshold:
                side = 1
                fill = close[i] * (1 + SLIPPAGE)
                sl_dist = atr_v[i] * atr_multiplier
                sl = fill - sl_dist
                tp = fill + sl_dist * rr_ratio
                # fee on entry
                risk_amt = equity * risk_per_trade
                size = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill)
                entry_fee = fill * size * COMMISSION
                equity -= entry_fee
                in_trade = True

            elif cross_down and rsi_v[i] < (100 - rsi_threshold):
                side = -1
                fill = close[i] * (1 - SLIPPAGE)
                sl_dist = atr_v[i] * atr_multiplier
                sl = fill + sl_dist
                tp = fill - sl_dist * rr_ratio
                risk_amt = equity * risk_per_trade
                size = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill)
                entry_fee = fill * size * COMMISSION
                equity -= entry_fee
                in_trade = True

        else:
            # Check if SL or TP hit on this bar
            hit_sl = hit_tp = False

            if side == 1:
                if low[i] <= sl:
                    hit_sl = True
                    exit_price = sl
                elif high[i] >= tp:
                    hit_tp = True
                    exit_price = tp
            else:
                if high[i] >= sl:
                    hit_sl = True
                    exit_price = sl
                elif low[i] <= tp:
                    hit_tp = True
                    exit_price = tp

            if hit_sl or hit_tp:
                # PnL = side × (exit - entry) × size  (simplified as fraction of sl_dist)
                if hit_tp:
                    trade_pnl = risk_amt * rr_ratio
                    wins += 1
                else:
                    trade_pnl = -risk_amt
                    losses += 1

                exit_fee = exit_price * size * COMMISSION
                equity += trade_pnl - exit_fee

                # Drawdown tracking
                if equity > max_eq:
                    max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd:
                        max_dd = dd

                in_trade = False

    total = wins + losses
    if total == 0:
        return None

    win_rate   = wins / total * 100
    pnl_pct    = (equity - START_CASH) / START_CASH * 100
    trades_pyr = total / 3.0

    return {
        'win_rate':       win_rate,
        'pnl_pct':        pnl_pct,
        'max_dd':         max_dd,
        'trades':         total,
        'trades_per_year': trades_pyr,
    }

# ---------------------------------------------------------------------------
# Optimization sweep
# ---------------------------------------------------------------------------

def run_optimization(data_file=os.path.join('csv', 'BTCUSDT_15m_3yrs.csv')):
    df = pd.read_csv(data_file, parse_dates=['datetime'], index_col='datetime')
    print(f"Loaded {len(df):,} bars  ({df.index[0].date()} → {df.index[-1].date()})\n")

    param_grid = list(itertools.product(
        [5, 8, 13],           # ema_fast
        [21, 34, 50],         # ema_slow
        [45, 50, 55],         # rsi_threshold
        [1.0, 1.5, 2.0, 3.0],# atr_multiplier
        [1.0, 1.25, 1.5],     # rr_ratio
        [0, 20],              # adx_threshold
        [0.02, 0.03],         # risk_per_trade
    ))
    # Remove invalid (fast >= slow)
    param_grid = [p for p in param_grid if p[0] < p[1]]

    print(f"Sweeping {len(param_grid)} combinations...", flush=True)
    t0 = time.time()

    results = []
    for p in param_grid:
        fast, slow, rsi_th, atr_m, rr, adx_th, risk = p
        r = simulate(df, fast, slow, rsi_th, atr_m, rr, risk, adx_th)
        if r and r['trades'] >= 30:
            r['cfg'] = {
                'ema_fast': fast, 'ema_slow': slow,
                'rsi_threshold': rsi_th, 'atr_multiplier': atr_m,
                'rr_ratio': rr, 'adx_threshold': adx_th,
                'risk_per_trade': risk,
            }
            results.append(r)

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s — {len(results)} valid configs (30+ trades)\n")

    # Composite score
    for r in results:
        r['score'] = r['pnl_pct'] * (r['win_rate'] / 50.0) / max(r['max_dd'], 1.0)

    def fmt(i, r):
        c = r['cfg']
        adx_s = f"ADX>{c['adx_threshold']}" if c['adx_threshold'] else "No ADX"
        print(f"  #{i:2d} | EMA {c['ema_fast']}/{c['ema_slow']}, RSI>{c['rsi_threshold']}, "
              f"ATR={c['atr_multiplier']}, RR={c['rr_ratio']}, Risk={c['risk_per_trade']*100:.0f}%, {adx_s} | "
              f"WR:{r['win_rate']:.1f}% | PnL:{r['pnl_pct']:+.1f}% | "
              f"DD:{r['max_dd']:.1f}% | Trades/yr:{r['trades_per_year']:.0f} | Score:{r['score']:.2f}")

    # --- View 1: Top 10 by score ---
    top_score = sorted(results, key=lambda x: x['score'], reverse=True)
    print("=" * 120)
    print("TOP 10 BY COMPOSITE SCORE")
    print("=" * 120)
    for i, r in enumerate(top_score[:10]):
        fmt(i + 1, r)

    # --- View 2: WR>=50%, DD<20%, best PnL ---
    safe = [r for r in results if r['win_rate'] >= 50 and r['max_dd'] < 20]
    safe_pnl = sorted(safe, key=lambda x: x['pnl_pct'], reverse=True)
    print(f"\n{'=' * 120}")
    print(f"TOP 10 BY PnL  (WR≥50%, DD<20%)  —  {len(safe)} qualifying configs")
    print(f"{'=' * 120}")
    for i, r in enumerate(safe_pnl[:10]):
        fmt(i + 1, r)

    # --- View 3: High frequency ≥365 trades/yr, WR≥50%, DD<20% ---
    hf = [r for r in safe if r['trades_per_year'] >= 365]
    hf_pnl = sorted(hf, key=lambda x: x['pnl_pct'], reverse=True)
    print(f"\n{'=' * 120}")
    print(f"HIGH-FREQ (WR≥50%, DD<20%, ≥365 trades/yr)  —  {len(hf)} configs")
    print(f"{'=' * 120}")
    if hf_pnl:
        for i, r in enumerate(hf_pnl[:10]):
            fmt(i + 1, r)
    else:
        print("  None found at this threshold. Showing ≥100 trades/yr instead:")
        med = [r for r in safe if r['trades_per_year'] >= 100]
        for i, r in enumerate(sorted(med, key=lambda x: x['pnl_pct'], reverse=True)[:10]):
            fmt(i + 1, r)


if __name__ == '__main__':
    run_optimization()
