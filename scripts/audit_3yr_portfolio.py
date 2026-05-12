import numpy as np
import pandas as pd
import os
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Audit Settings (Matched to Live Bot)
# ---------------------------------------------------------------------------
CSV_DIR         = "csv"
RESULTS_DIR     = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)
RESULTS_FILE    = os.path.join(RESULTS_DIR, "audit_3yr_results.txt")

START_CASH      = 10_000.0
RISK_PER_TRADE  = 0.015     # 1.5% of equity per trade
LEVERAGE        = 20.0
COMMISSION      = 0.0006    # 0.06%
SLIPPAGE        = 0.0005    # 0.05%

BB_PERIOD = 20
EMA_PERIOD = 200

# Exact configs from live_bot_multi.py
SYMBOL_CONFIGS = {
    "BTC":  {"bb": 2.5, "atr": 6.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "ETH":  {"bb": 2.5, "atr": 5.0, "rr": 1.25, "adx": 25, "rsi": 30},
    "SOL":  {"bb": 2.0, "atr": 4.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "DOGE": {"bb": 2.0, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30, "long_only": True},
    "ADA":  {"bb": 2.5, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 40},
    "LINK": {"bb": 2.0, "atr": 6.0, "rr": 1.0,  "adx": 20, "rsi": 30},
    "DOT":  {"bb": 2.5, "atr": 4.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "TON":  {"bb": 2.0, "atr": 4.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "ZEC":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 20, "rsi": 30},
    "PEPE": {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "BNB":  {"bb": 2.5, "atr": 4.0, "rr": 1.25, "adx": 25, "rsi": 30},
    "NEAR": {"bb": 3.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "SUI":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "NOT":  {"bb": 2.0, "atr": 6.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "TAO":  {"bb": 2.0, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "ONDO": {"bb": 2.5, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "ENA":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "FET":  {"bb": 2.0, "atr": 6.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "WIF":  {"bb": 3.0, "atr": 5.0, "rr": 1.25, "adx": 25, "rsi": 30},
}

def calc_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calc_rsi(s, p=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/p, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/p, adjust=False).mean()
    rs = g / l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)
def calc_atr(df, p=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(alpha=1/p, adjust=False).mean()
def calc_adx(df, p=14):
    pdm = df["high"].diff().clip(lower=0); ndm = (-df["low"].diff()).clip(lower=0)
    pdm = pdm.where(pdm > ndm, 0.0); ndm = ndm.where(ndm > pdm, 0.0)
    a = calc_atr(df, p); pdi = 100 * pdm.ewm(alpha=1/p, adjust=False).mean() / a
    ndi = 100 * ndm.ewm(alpha=1/p, adjust=False).mean() / a
    dx = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1/p, adjust=False).mean()

def prepare_indicators(df, cfg):
    close_s = df["close"]
    mid = close_s.rolling(BB_PERIOD).mean()
    std = close_s.rolling(BB_PERIOD).std()
    return {
        "close": close_s.values, "high": df["high"].values, "low": df["low"].values,
        "ema": calc_ema(close_s, EMA_PERIOD).values, "rsi": calc_rsi(close_s).values,
        "atr": calc_atr(df).values, "adx": calc_adx(df).values,
        "bb_top": (mid + cfg["bb"] * std).values, "bb_bot": (mid - cfg["bb"] * std).values,
        "index": df.index,
    }

def run_portfolio(datasets):
    all_indices = [v["index"] for v in datasets.values()]
    common_idx = all_indices[0]
    for idx in all_indices[1:]: common_idx = common_idx.union(idx)
    common_idx = common_idx.sort_values()

    n_bars = len(common_idx)
    aligned = {}
    for name, d in datasets.items():
        pos = d["index"].get_indexer(common_idx)
        valid = pos >= 0
        arr = {}
        for key in ["close","high","low","ema","rsi","atr","adx","bb_top","bb_bot"]:
            arr[key] = np.where(valid, d[key][np.where(valid, pos, 0)], np.nan)
        aligned[name] = arr

    states = {name: {"in_trade": False, "cooldown": 0, "side": 0, "sl": 0.0, "tp": 0.0,
                     "size": 0.0, "risk_amt": 0.0, "wins": 0, "losses": 0} for name in SYMBOL_CONFIGS}
    
    equity = START_CASH; max_eq = START_CASH; max_dd = 0.0; eq_curve = []

    for i in range(EMA_PERIOD, n_bars - 1):
        for name, cfg in SYMBOL_CONFIGS.items():
            st = states[name]
            if not st["in_trade"]: continue
            arr = aligned[name]; hi = arr["high"][i]; lo = arr["low"][i]; ex = arr["close"][i]
            if np.isnan(hi): continue
            
            hit_sl = hit_tp = False
            if st["side"] == 1:
                if lo <= st["sl"]: hit_sl = True; ex = st["sl"]
                elif hi >= st["tp"]: hit_tp = True; ex = st["tp"]
            else:
                if hi >= st["sl"]: hit_sl = True; ex = st["sl"]
                elif lo <= st["tp"]: hit_tp = True; ex = st["tp"]

            if hit_sl or hit_tp:
                pnl = st["risk_amt"] * cfg["rr"] if hit_tp else -st["risk_amt"]
                equity += pnl - ex * st["size"] * COMMISSION
                if hit_tp: st["wins"] += 1
                else: st["losses"] += 1
                st["in_trade"] = False; st["cooldown"] = 3
                if equity > max_eq: max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd: max_dd = dd

        for name, cfg in SYMBOL_CONFIGS.items():
            st = states[name]
            if st["in_trade"] or st["cooldown"] > 0:
                if st["cooldown"] > 0: st["cooldown"] -= 1
                continue
            
            arr = aligned[name]; close = arr["close"][i]; ema_v = arr["ema"][i]
            rsi_v = arr["rsi"][i]; atr_v = arr["atr"][i]; adx_v = arr["adx"][i]
            bb_top = arr["bb_top"][i]; bb_bot = arr["bb_bot"][i]
            if any(np.isnan(v) for v in [close, ema_v, bb_bot]): continue
            
            if cfg["adx"] > 0 and adx_v < cfg["adx"]: continue

            # Long
            if close > ema_v and close < bb_bot and rsi_v < cfg["rsi"]:
                fill = close * (1 + SLIPPAGE); sl_dist = atr_v * cfg["atr"]
                st.update({"side": 1, "sl": fill - sl_dist, "tp": fill + sl_dist * cfg["rr"],
                           "risk_amt": equity * RISK_PER_TRADE, "in_trade": True})
                st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity -= fill * st["size"] * COMMISSION
            
            # Short (unless long_only)
            elif not cfg.get("long_only") and close < ema_v and close > bb_top and rsi_v > (100 - cfg["rsi"]):
                fill = close * (1 - SLIPPAGE); sl_dist = atr_v * cfg["atr"]
                st.update({"side": -1, "sl": fill + sl_dist, "tp": fill - sl_dist * cfg["rr"],
                           "risk_amt": equity * RISK_PER_TRADE, "in_trade": True})
                st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity -= fill * st["size"] * COMMISSION
        
        eq_curve.append(equity)

    total_trades = sum(st["wins"] + st["losses"] for st in states.values())
    win_rate = sum(st["wins"] for st in states.values()) / total_trades * 100 if total_trades else 0
    
    return {"pnl_pct": (equity - START_CASH) / START_CASH * 100, "final_equity": equity,
            "max_dd": max_dd, "total_trades": total_trades, "win_rate": win_rate,
            "start": common_idx[EMA_PERIOD], "end": common_idx[-1]}

def run_solo(name, d):
    cfg = SYMBOL_CONFIGS[name]
    close = d["close"]; high = d["high"]; low = d["low"]; ema_v = d["ema"]
    rsi_v = d["rsi"]; atr_v = d["atr"]; adx_v = d["adx"]; bb_top = d["bb_top"]; bb_bot = d["bb_bot"]
    
    equity = START_CASH; max_eq = START_CASH; max_dd = 0.0
    wins = losses = 0; in_trade = False; cooldown = 0
    side = 0; sl = tp = size = risk_amt = 0.0

    for i in range(EMA_PERIOD, len(close) - 1):
        if cooldown > 0: cooldown -= 1; continue
        if not in_trade:
            if cfg["adx"] > 0 and adx_v[i] < cfg["adx"]: continue
            if close[i] > ema_v[i] and close[i] < bb_bot[i] and rsi_v[i] < cfg["rsi"]:
                side = 1; fill = close[i] * (1 + SLIPPAGE); sl_dist = atr_v[i] * cfg["atr"]
                sl = fill - sl_dist; tp = fill + sl_dist * cfg["rr"]; risk_amt = equity * RISK_PER_TRADE
                size = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill); equity -= fill * size * COMMISSION; in_trade = True
            elif not cfg.get("long_only") and close[i] < ema_v[i] and close[i] > bb_top[i] and rsi_v[i] > (100 - cfg["rsi"]):
                side = -1; fill = close[i] * (1 - SLIPPAGE); sl_dist = atr_v[i] * cfg["atr"]
                sl = fill + sl_dist; tp = fill - sl_dist * cfg["rr"]; risk_amt = equity * RISK_PER_TRADE
                size = min(risk_amt / sl_dist, (equity * LEVERAGE) / fill); equity -= fill * size * COMMISSION; in_trade = True
        else:
            hit_sl = hit_tp = False; ex = 0.0
            if side == 1:
                if low[i] <= sl: hit_sl = True; ex = sl
                elif high[i] >= tp: hit_tp = True; ex = tp
            else:
                if high[i] >= sl: hit_sl = True; ex = sl
                elif low[i] <= tp: hit_tp = True; ex = tp
            if hit_sl or hit_tp:
                pnl = risk_amt * cfg["rr"] if hit_tp else -risk_amt
                equity += pnl - ex * size * COMMISSION
                if hit_tp: wins += 1
                else: losses += 1
                in_trade = False; cooldown = 3
                if equity > max_eq: max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd: max_dd = dd
    t = wins + losses
    return {"trades": t, "wr": wins/t*100 if t else 0, "dd": max_dd}

def run():
    datasets = {}
    print("Loading data...")
    for name in SYMBOL_CONFIGS:
        path = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")
        if not os.path.exists(path): continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        datasets[name] = prepare_indicators(df, SYMBOL_CONFIGS[name])
    
    print("Running solo audits...")
    sym_stats = []
    for name, d in datasets.items():
        res = run_solo(name, d)
        sym_stats.append({"name": name, **res})
    
    print("Running master portfolio simulation...")
    res = run_portfolio(datasets)
    
    lines = []
    lines.append("="*60)
    lines.append(f"  Audit Period: {res['start'].date()} -> {res['end'].date()}")
    lines.append(f"  Starting: ${START_CASH:,.2f} | Final: ${res['final_equity']:,.2f}")
    lines.append(f"  Total PnL: {res['pnl_pct']:+.1f}% | Win Rate: {res['win_rate']:.1f}%")
    lines.append(f"  Max Drawdown: {res['max_dd']:.1f}% | Total Trades: {res['total_trades']}")
    lines.append("="*60)
    lines.append(f"\n  {'Symbol':<6} {'Trades':>7} {'Win Rate':>10} {'Max DD':>8}")
    lines.append("  " + "-"*35)
    for s in sorted(sym_stats, key=lambda x: x["wr"], reverse=True):
        lines.append(f"  {s['name']:<6} {s['trades']:>7} {s['wr']:>9.1f}% {s['dd']:>7.1f}%")
    
    output = "\n".join(lines)
    print("\n" + output + "\n")
    with open(RESULTS_FILE, "w") as f: f.write(output)

if __name__ == "__main__": run()
