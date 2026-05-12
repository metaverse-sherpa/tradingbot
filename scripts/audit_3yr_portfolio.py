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

def run_portfolio(datasets, risk_pct=0.01):
    # ... (Logic remains similar but uses risk_pct)
    # Filter datasets based on symbols passed in
    # ...
    pass

def run_custom_audit(risk_pct, enabled_symbols):
    """
    Called by the Telegram bot to run a private simulation for a specific user.
    """
    datasets = {}
    for name in enabled_symbols:
        path = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")
        if not os.path.exists(path): continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        datasets[name] = prepare_indicators(df, SYMBOL_CONFIGS[name])
    
    if not datasets: return None
    
    # Run the simulation
    res = run_portfolio_internal(datasets, risk_pct / 100.0)
    return res

def run_portfolio_internal(datasets, risk_val):
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
                     "size": 0.0, "risk_amt": 0.0, "wins": 0, "losses": 0} for name in datasets}
    
    equity = START_CASH; max_eq = START_CASH; max_dd = 0.0

    for i in range(EMA_PERIOD, n_bars - 1):
        for name, d in datasets.items():
            st = states[name]; cfg = SYMBOL_CONFIGS[name]
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

        for name, d in datasets.items():
            st = states[name]; cfg = SYMBOL_CONFIGS[name]
            if st["in_trade"] or st["cooldown"] > 0:
                if st["cooldown"] > 0: st["cooldown"] -= 1
                continue
            
            arr = aligned[name]; close = arr["close"][i]; ema_v = arr["ema"][i]
            rsi_v = arr["rsi"][i]; atr_v = arr["atr"][i]; adx_v = arr["adx"][i]
            bb_top = arr["bb_top"][i]; bb_bot = arr["bb_bot"][i]
            if any(np.isnan(v) for v in [close, ema_v, bb_bot]): continue
            if cfg["adx"] > 0 and adx_v < cfg["adx"]: continue

            if close > ema_v and close < bb_bot and rsi_v < cfg["rsi"]:
                fill = close * (1 + SLIPPAGE); sl_dist = atr_v * cfg["atr"]
                st.update({"side": 1, "sl": fill - sl_dist, "tp": fill + sl_dist * cfg["rr"],
                           "risk_amt": equity * risk_val, "in_trade": True})
                st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity -= fill * st["size"] * COMMISSION
            elif not cfg.get("long_only") and close < ema_v and close > bb_top and rsi_v > (100 - cfg["rsi"]):
                fill = close * (1 - SLIPPAGE); sl_dist = atr_v * cfg["atr"]
                st.update({"side": -1, "sl": fill + sl_dist, "tp": fill - sl_dist * cfg["rr"],
                           "risk_amt": equity * risk_val, "in_trade": True})
                st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity -= fill * st["size"] * COMMISSION
        
    total_trades = sum(st["wins"] + st["losses"] for st in states.values())
    win_rate = sum(st["wins"] for st in states.values()) / total_trades * 100 if total_trades else 0
    
    return {"pnl_pct": (equity - START_CASH) / START_CASH * 100, "final_equity": equity,
            "max_dd": max_dd, "total_trades": total_trades, "win_rate": win_rate,
            "start": common_idx[EMA_PERIOD], "end": common_idx[-1]}

def run():
    # Standalone script run
    res = run_custom_audit(RISK_PER_TRADE * 100, list(SYMBOL_CONFIGS.keys()))
    if res:
        print(f"Final Equity: ${res['final_equity']:,.2f} | PnL: {res['pnl_pct']:+.1f}% | DD: {res['max_dd']:.1f}%")

if __name__ == "__main__": run()
