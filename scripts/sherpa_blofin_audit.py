import numpy as np
import pandas as pd
import os
import matplotlib.pyplot as plt
from datetime import datetime
import time

# ---------------------------------------------------------------------------
# Blofin DEEP Audit Settings (20 Symbol Fleet)
# ---------------------------------------------------------------------------
CSV_DIR         = "csv_blofin"
RESULTS_DIR     = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

START_CASH      = 10_000.0
RISK_PER_TRADE  = 0.01
LEVERAGE        = 20.0
COMMISSION      = 0.0006
SLIPPAGE        = 0.0005

BB_PERIOD = 20
EMA_PERIOD = 200

# Tuned Configs from Production
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
    "SHIB": {"bb": 2.5, "atr": 6.0, "rr": 1.25, "adx": 15, "rsi": 30},
}

def calc_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calc_rsi(s, p=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/p, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/p, adjust=False).mean()
    return 100 - 100 / (1 + (g / l.replace(0, np.nan)))
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

def run_blofin_deep_audit():
    datasets = {}
    for name in SYMBOL_CONFIGS.keys():
        path = os.path.join(CSV_DIR, f"blofin_{name}_15m.csv")
        if not os.path.exists(path): continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        datasets[name] = prepare_indicators(df, SYMBOL_CONFIGS[name])
    
    if not datasets: return print("No Deep Blofin data found.")
    
    all_indices = [v["index"] for v in datasets.values()]
    common_idx = all_indices[0]
    for idx in all_indices[1:]: common_idx = common_idx.union(idx)
    common_idx = common_idx.sort_values(); n_bars = len(common_idx)
    
    aligned = {}
    for name, d in datasets.items():
        pos = d["index"].get_indexer(common_idx); valid = pos >= 0
        aligned[name] = {k: np.where(valid, d[k][np.where(valid, pos, 0)], np.nan) for k in ["close","high","low","ema","rsi","atr","adx","bb_top","bb_bot"]}

    states = {name: {"in_trade": False, "side": 0, "sl": 0.0, "tp": 0.0, "size": 0.0, "risk_amt": 0.0, 
                     "long_wins": 0, "long_losses": 0, "short_wins": 0, "short_losses": 0} for name in datasets}
    equity = START_CASH; equity_history = [(common_idx[0], equity)]
    max_eq = START_CASH; drawdowns = [(common_idx[0], 0.0)]; max_dd_val = 0.0

    print(f"🧐 Auditing {len(datasets)} symbols on Blofin Deep Data...")

    for i in range(EMA_PERIOD, n_bars - 1):
        for name, d in aligned.items():
            st = states[name]; cfg = SYMBOL_CONFIGS[name]
            if st["in_trade"]:
                hi, lo, ex = d["high"][i], d["low"][i], d["close"][i]
                if np.isnan(hi): continue
                hit_sl = hit_tp = False
                if st["side"] == 1:
                    if lo <= st["sl"]: hit_sl = True; ex = st["sl"]
                    elif hi >= st["tp"]: hit_tp = True; ex = st["tp"]
                    if hit_sl or hit_tp:
                        if hit_tp: st["long_wins"] += 1
                        else: st["long_losses"] += 1
                else:
                    if hi >= st["sl"]: hit_sl = True; ex = st["sl"]
                    elif lo <= st["tp"]: hit_tp = True; ex = st["tp"]
                    if hit_sl or hit_tp:
                        if hit_tp: st["short_wins"] += 1
                        else: st["short_losses"] += 1
                
                if hit_sl or hit_tp:
                    pnl = st["risk_amt"] * cfg["rr"] if hit_tp else -st["risk_amt"]
                    equity += pnl - ex * st["size"] * COMMISSION
                    st["in_trade"] = False
                    equity_history.append((common_idx[i], equity)); max_eq = max(max_eq, equity)
                    dd = (max_eq - equity) / max_eq * 100; max_dd_val = max(max_dd_val, dd); drawdowns.append((common_idx[i], -dd))
            else:
                close, ema_v, bb_top, bb_bot = d["close"][i], d["ema"][i], d["bb_top"][i], d["bb_bot"][i]
                if any(np.isnan(v) for v in [close, ema_v, bb_bot]): continue
                if cfg["adx"] > 0 and d["adx"][i] < cfg["adx"]: continue
                if close > ema_v and close < bb_bot and d["rsi"][i] < cfg["rsi"]:
                    fill = close*(1+SLIPPAGE); sd = d["atr"][i]*cfg["atr"]
                    st.update({"side": 1, "sl": fill-sd, "tp": fill+sd*cfg["rr"], "risk_amt": equity*RISK_PER_TRADE, "in_trade": True})
                    st["size"] = min(st["risk_amt"]/sd, (equity*LEVERAGE)/fill); equity -= fill*st["size"]*COMMISSION
                elif not cfg.get("long_only") and close < ema_v and close > bb_top and d["rsi"][i] > (100-cfg["rsi"]):
                    fill = close*(1-SLIPPAGE); sd = d["atr"][i]*cfg["atr"]
                    st.update({"side": -1, "sl": fill+sd, "tp": fill-sd*cfg["rr"], "risk_amt": equity*RISK_PER_TRADE, "in_trade": True})
                    st["size"] = min(st["risk_amt"]/sd, (equity*LEVERAGE)/fill); equity -= fill*st["size"]*COMMISSION

    # Calculations & Plotting
    df_eq = pd.DataFrame(equity_history, columns=["date", "equity"]).set_index("date")
    df_dd = pd.DataFrame(drawdowns, columns=["date", "drawdown"]).set_index("date")
    daily_returns = df_eq["equity"].resample('D').last().pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365) if len(daily_returns) > 1 else 0

    # 📊 PER-SYMBOL BREAKDOWN
    print("\n" + "="*85)
    print(f"{'Symbol':<8} {'Long WR':>10} {'(T)':>4} | {'Short WR':>10} {'(T)':>4} | {'Overall':>9} {'(T)':>4}")
    print("-" * 85)
    
    total_l_w, total_l_l = 0, 0
    total_s_w, total_s_l = 0, 0
    symbol_stats = []

    for name, st in states.items():
        lw, ll = st["long_wins"], st["long_losses"]
        sw, sl = st["short_wins"], st["short_losses"]
        total_l_w += lw; total_l_l += ll
        total_s_w += sw; total_s_l += sl
        
        tw = lw + ll + sw + sl
        if tw > 0:
            wr = ((lw + sw) / tw) * 100
            l_wr = (lw / (lw + ll) * 100) if (lw + ll) > 0 else 0
            s_wr = (sw / (sw + sl) * 100) if (sw + sl) > 0 else 0
            symbol_stats.append({
                "name": name, "wr": wr, "trades": tw,
                "l_wr": l_wr, "l_t": lw + ll,
                "s_wr": s_wr, "s_t": sw + sl
            })

    symbol_stats.sort(key=lambda x: x["wr"], reverse=True)

    for s in symbol_stats:
        print(f"{s['name']:<8} {s['l_wr']:>8.1f}% {s['l_t']:>4} | {s['s_wr']:>8.1f}% {s['s_t']:>4} | {s['wr']:>8.1f}% {s['trades']:>4}")

    # Institutional 75/25 Layout
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1]}, facecolor="#121212")
    
    # 🏔️ Equity Chart
    ax1.plot(df_eq.index, df_eq["equity"], color="cyan", linewidth=2)
    ax1.set_title("Blofin DEEP Audit (20-Symbol Fleet)", color="white", fontsize=16)
    ax1.tick_params(colors="white")
    ax1.grid(alpha=0.1)
    ax1.set_facecolor("#121212")
    ax1.text(0.02, 0.9, f"Sharpe: {sharpe:.2f}\nFinal: ${equity:,.2f}", transform=ax1.transAxes, color='cyan', fontweight='bold', bbox=dict(facecolor='#1A1A1A', alpha=0.8))
    
    # 🌊 Drawdown Chart
    ax2.fill_between(df_dd.index, df_dd["drawdown"], 0, color="red", alpha=0.2)
    ax2.plot(df_dd.index, df_dd["drawdown"], color="red", linewidth=0.8)
    ax2.tick_params(colors="white")
    ax2.grid(alpha=0.1)
    ax2.set_facecolor("#121212")
    ax2.set_title("Drawdown (%)", color="white", fontsize=10)
    
    plt.tight_layout(); plt.savefig(os.path.join(RESULTS_DIR, "blofin_deep_audit.png"), dpi=150, facecolor="#121212")
    
    total_trades = total_l_w + total_l_l + total_s_w + total_s_l
    final_wr = ((total_l_w + total_s_w) / total_trades * 100) if total_trades else 0
    l_wr = (total_l_w / (total_l_w + total_l_l) * 100) if (total_l_w + total_l_l) > 0 else 0
    s_wr = (total_s_w / (total_s_w + total_s_l) * 100) if (total_s_w + total_s_l) > 0 else 0
    
    # Calculate Days
    days = (common_idx[-1] - common_idx[0]).days
    avg_daily = total_trades / days if days > 0 else 0
    
    print("-" * 85)
    print(f"TOTALS:  {l_wr:>8.1f}% {total_l_w+total_l_l:>4} | {s_wr:>8.1f}% {total_s_w+total_s_l:>4} | {final_wr:>8.1f}% {total_trades:>4}")
    print("="*85)
    print(f"Avg Trades/Day: {avg_daily:.1f}")
    print(f"Final Equity:   ${equity:,.2f} | Sharpe: {sharpe:.2f} | MaxDD: {max_dd_val:.1f}%\n")

if __name__ == "__main__":
    run_blofin_deep_audit()
