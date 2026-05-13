import numpy as np
import pandas as pd
import os
import matplotlib.pyplot as plt
from datetime import datetime
import time

# ---------------------------------------------------------------------------
# Sherpa Visual Audit Settings
# ---------------------------------------------------------------------------
CSV_DIR         = "csv"
RESULTS_DIR     = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

START_CASH      = 10_000.0
RISK_PER_TRADE  = 0.015     # 1.5% of current equity per trade
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
    hl = df["high"] - df["low"]; hc = (df["high"] - df["close"].shift()).abs(); lc = (df["low"] - df["close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(alpha=1/p, adjust=False).mean()
def calc_adx(df, p=14):
    pdm = df["high"].diff().clip(lower=0); ndm = (-df["low"].diff()).clip(lower=0)
    pdm = pdm.where(pdm > ndm, 0.0); ndm = ndm.where(ndm > pdm, 0.0)
    a = calc_atr(df, p); pdi = 100 * pdm.ewm(alpha=1/p, adjust=False).mean() / a
    ndi = 100 * ndm.ewm(alpha=1/p, adjust=False).mean() / a
    dx = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1/p, adjust=False).mean()

def prepare_indicators(df, cfg):
    close_s = df["close"]; mid = close_s.rolling(BB_PERIOD).mean(); std = close_s.rolling(BB_PERIOD).std()
    return {
        "close": close_s.values, "high": df["high"].values, "low": df["low"].values,
        "ema": calc_ema(close_s, EMA_PERIOD).values, "rsi": calc_rsi(close_s).values,
        "atr": calc_atr(df).values, "adx": calc_adx(df).values,
        "bb_top": (mid + cfg["bb"] * std).values, "bb_bot": (mid - cfg["bb"] * std).values,
        "index": df.index,
    }

def run_visual_audit(risk_val_pct=1.5, enabled_symbols=None, user_id="admin", start_balance=10000.0):
    """
    Performs a visual backtest and returns (stats, chart_path)
    """
    is_master = False
    if enabled_symbols is None:
        enabled_symbols = list(SYMBOL_CONFIGS.keys())
        if risk_val_pct == 1.5:
            is_master = True
        
    datasets = {}
    for name in enabled_symbols:
        path = os.path.join(CSV_DIR, f"cache_{name}_15m.csv")
        if not os.path.exists(path): continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        datasets[name] = prepare_indicators(df, SYMBOL_CONFIGS[name])
    
    if not datasets: return None, None
    
    risk_val_decimal = risk_val_pct / 100.0
    
    all_indices = [v["index"] for v in datasets.values()]
    common_idx = all_indices[0]
    for idx in all_indices[1:]: common_idx = common_idx.union(idx)
    common_idx = common_idx.sort_values()
    n_bars = len(common_idx)
    
    aligned = {}
    for name, d in datasets.items():
        pos = d["index"].get_indexer(common_idx)
        valid = pos >= 0
        arr = {k: np.where(valid, d[k][np.where(valid, pos, 0)], np.nan) for k in ["close","high","low","ema","rsi","atr","adx","bb_top","bb_bot"]}
        aligned[name] = arr

    states = {name: {"in_trade": False, "side": 0, "sl": 0.0, "tp": 0.0, "size": 0.0, "risk_amt": 0.0, "wins": 0, "losses": 0} for name in datasets}
    equity = start_balance; equity_history = [(common_idx[0], equity)]
    max_eq = start_balance; drawdowns = [(common_idx[0], 0.0)]
    max_dd_val = 0.0

    for i in range(EMA_PERIOD, n_bars - 1):
        # 1. Check Exit
        for name, d in aligned.items():
            st = states[name]; cfg = SYMBOL_CONFIGS[name]
            if not st["in_trade"]: continue
            hi, lo, ex = d["high"][i], d["low"][i], d["close"][i]
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
                st["in_trade"] = False
                
                equity_history.append((common_idx[i], equity))
                max_eq = max(max_eq, equity)
                dd = (max_eq - equity) / max_eq * 100
                max_dd_val = max(max_dd_val, dd)
                drawdowns.append((common_idx[i], -dd))

        # 2. Check Entry
        for name, d in aligned.items():
            st = states[name]; cfg = SYMBOL_CONFIGS[name]
            if st["in_trade"]: continue
            close, ema_v, bb_top, bb_bot = d["close"][i], d["ema"][i], d["bb_top"][i], d["bb_bot"][i]
            if any(np.isnan(v) for v in [close, ema_v, bb_bot]): continue
            if cfg["adx"] > 0 and d["adx"][i] < cfg["adx"]: continue

            if close > ema_v and close < bb_bot and d["rsi"][i] < cfg["rsi"]:
                fill = close * (1 + SLIPPAGE); sl_dist = d["atr"][i] * cfg["atr"]
                st.update({"side": 1, "sl": fill - sl_dist, "tp": fill + sl_dist * cfg["rr"], "risk_amt": equity * risk_val_decimal, "in_trade": True})
                st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity -= fill * st["size"] * COMMISSION
            elif not cfg.get("long_only") and close < ema_v and close > bb_top and d["rsi"][i] > (100 - cfg["rsi"]):
                fill = close * (1 - SLIPPAGE); sl_dist = d["atr"][i] * cfg["atr"]
                st.update({"side": -1, "sl": fill + sl_dist, "tp": fill - sl_dist * cfg["rr"], "risk_amt": equity * risk_val_decimal, "in_trade": True})
                st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity -= fill * st["size"] * COMMISSION

    # --- Calculations ---
    df_eq = pd.DataFrame(equity_history, columns=["date", "equity"]).set_index("date")
    df_dd = pd.DataFrame(drawdowns, columns=["date", "drawdown"]).set_index("date")
    
    # Annualized Sharpe Ratio
    daily_returns = df_eq["equity"].resample('D').last().pct_change().dropna()
    if len(daily_returns) > 1:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
    else:
        sharpe = 0.0

    # Institutional 75/25 Layout
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1]})
    
    # Equity Curve (The Sherpa Trail)
    ax1.plot(df_eq.index, df_eq["equity"], color="cyan", linewidth=2.0)
    
    # Add Start/End Labels
    start_date, end_date = df_eq.index[0], df_eq.index[-1]
    ax1.annotate(f"${start_balance:,.0f}", (start_date, start_balance), textcoords="offset points", xytext=(-10,10), ha='center', color='white', fontweight='bold')
    ax1.annotate(f"${equity:,.0f}", (end_date, equity), textcoords="offset points", xytext=(-10,10), ha='center', color='cyan', fontweight='bold')

    ax1.set_title(f"Metaverse Sherpa: 3-Year Equity Trail ({risk_val_pct}% Risk)", color="white", fontsize=16, pad=20)
    ax1.set_ylabel("Account Equity ($)", color="white")
    ax1.grid(True, alpha=0.15); ax1.set_facecolor("#121212"); ax1.tick_params(colors="white")
    
    # Add Sharpe Metric Box
    ax1.text(0.02, 0.90, f"Sharpe Ratio: {sharpe:.2f}", transform=ax1.transAxes, color='cyan', fontweight='bold', fontsize=12, bbox=dict(facecolor='#1A1A1A', alpha=0.8, edgecolor='cyan'))

    # Drawdown Chart (The Valleys - Compressed for Authority)
    ax2.fill_between(df_dd.index, df_dd["drawdown"], 0, color="red", alpha=0.2)
    ax2.plot(df_dd.index, df_dd["drawdown"], color="red", linewidth=0.8)
    ax2.set_title("Strategy Drawdown (%)", color="white", fontsize=10)
    ax2.set_ylabel("Drawdown (%)", color="white")
    ax2.set_ylim(-100, 5) # 0-100% Scale for visual compression
    ax2.grid(True, alpha=0.1); ax2.set_facecolor("#121212"); ax2.tick_params(colors="white")
    
    fig.patch.set_facecolor("#121212")
    plt.tight_layout()
    
    if is_master and user_id == "admin":
        chart_path = os.path.join(RESULTS_DIR, "master_audit.png")
    else:
        chart_name = f"audit_{user_id}_{int(time.time())}.png"
        chart_path = os.path.join(RESULTS_DIR, chart_name)
        
    plt.savefig(chart_path, dpi=150, facecolor="#121212")
    plt.close() # Important for bot memory
    
    total_trades = sum(st["wins"] + st["losses"] for st in states.values())
    win_rate = (sum(st["wins"] for st in states.values()) / total_trades * 100) if total_trades else 0
    
    stats = {
        "pnl_pct": (equity - start_balance) / start_balance * 100,
        "final_equity": equity,
        "max_dd": max_dd_val,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "sharpe": sharpe
    }
    return stats, chart_path

if __name__ == "__main__":
    import time
    s, p = run_visual_audit(1.5)
    if s: print(f"Audit Complete! Final Equity: ${s['final_equity']:,.2f}")
