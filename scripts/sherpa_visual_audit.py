import numpy as np
import pandas as pd
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
import time

# ---------------------------------------------------------------------------
# Sherpa Visual Audit Settings
# ---------------------------------------------------------------------------
CSV_DIR         = "csv_blofin"
RESULTS_DIR     = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

START_CASH      = 10_000.0
LEVERAGE        = 20.0
TAKER_FEE       = 0.0006    # 0.06% Taker Fee (Entry / SL Market trigger)
MAKER_FEE       = 0.0002    # 0.02% Maker Fee (Resting TP Limit order)
SLIPPAGE        = 0.0005    # 0.05% Slippage on entry

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

VALKYRIE_SYMBOL_CONFIGS = {
    "SOL":  {"bb": 2.0, "atr": 4.0, "rr": 1.2, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "LINK": {"bb": 2.6, "atr": 3.5, "rr": 0.8, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "BTC":  {"bb": 2.4, "atr": 3.0, "rr": 1.5, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "ADA":  {"bb": 2.4, "atr": 3.0, "rr": 1.0, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "DOT":  {"bb": 2.8, "atr": 4.5, "rr": 1.5, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "ETH":  {"bb": 2.2, "atr": 3.5, "rr": 1.0, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "SUI":  {"bb": 2.2, "atr": 4.0, "rr": 0.8, "adx": 25, "rsi_low": 25, "rsi_high": 75}
}

def calc_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calc_rsi(s, p=14, wilder=False):
    d = s.diff()
    if wilder:
        g = d.clip(lower=0).ewm(alpha=1/p, adjust=False).mean()
        l = (-d.clip(upper=0)).ewm(alpha=1/p, adjust=False).mean()
    else:
        g = d.clip(lower=0).ewm(span=p, adjust=False).mean()
        l = (-d.clip(upper=0)).ewm(span=p, adjust=False).mean()
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

def prepare_indicators(df, cfg, strategy_name="Mean Reversion Scalper"):
    close_s = df["close"]; mid = close_s.rolling(BB_PERIOD).mean(); std = close_s.rolling(BB_PERIOD).std()
    is_wilder = (strategy_name == "Mean Reversion Scalper")
    return {
        "close": close_s.values, "high": df["high"].values, "low": df["low"].values,
        "ema": calc_ema(close_s, EMA_PERIOD).values, "rsi": calc_rsi(close_s, wilder=is_wilder).values,
        "atr": calc_atr(df).values, "adx": calc_adx(df).values,
        "bb_top": (mid + cfg["bb"] * std).values, "bb_bot": (mid - cfg["bb"] * std).values,
        "index": df.index,
    }

CRYPTO_INDICATORS_CACHE = {}

def run_visual_audit(risk_val_pct=1.5, enabled_symbols=None, user_id="admin", start_balance=10000.0, strategy_name="Mean Reversion Scalper"):
    """
    Performs a visual backtest and returns (stats, chart_path, df_eq)
    """
    global CRYPTO_INDICATORS_CACHE
    is_master = False
    
    if strategy_name == "Valkyrie Elite Scalper":
        valkyrie_symbols = ["SOL", "LINK", "BTC", "ADA", "DOT", "ETH", "SUI"]
        enabled_symbols = [s for s in (enabled_symbols or valkyrie_symbols) if s in valkyrie_symbols]
        cfg_source = VALKYRIE_SYMBOL_CONFIGS
    else:
        cfg_source = SYMBOL_CONFIGS
        if enabled_symbols is None:
            enabled_symbols = list(SYMBOL_CONFIGS.keys())
            if risk_val_pct == 1.5:
                is_master = True
        
    datasets = {}
    for name in enabled_symbols:
        path = os.path.join(CSV_DIR, f"blofin_{name}_15m.csv")
        if not os.path.exists(path): continue
        
        cache_key = (name, strategy_name)
        if cache_key in CRYPTO_INDICATORS_CACHE:
            datasets[name] = CRYPTO_INDICATORS_CACHE[cache_key]
        else:
            df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
            datasets[name] = prepare_indicators(df, cfg_source[name], strategy_name)
            CRYPTO_INDICATORS_CACHE[cache_key] = datasets[name]
    
    if not datasets: return None, None, None
    
    risk_val_decimal = risk_val_pct / 100.0
    
    # Standard Single Shared Account compounding model
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
            st = states[name]; cfg = cfg_source[name]
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
                fee_rate = MAKER_FEE if hit_tp else TAKER_FEE
                equity += pnl - ex * st["size"] * fee_rate
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
            st = states[name]; cfg = cfg_source[name]
            if st["in_trade"]: continue
            close, ema_v, bb_top, bb_bot = d["close"][i], d["ema"][i], d["bb_top"][i], d["bb_bot"][i]
            if any(np.isnan(v) for v in [close, ema_v, bb_bot]): continue
            
            if strategy_name == "Valkyrie Elite Scalper":
                # Valkyrie Entry Rules
                bandwidth = (bb_top - bb_bot) / close
                if bandwidth < 0.012 or d["adx"][i] > cfg["adx"]: continue
                
                # LONG
                if close > ema_v and d["low"][i] < bb_bot and close >= bb_bot and d["rsi"][i] < cfg["rsi_low"]:
                    fill = close * (1 + SLIPPAGE); sl_dist = d["atr"][i] * cfg["atr"]
                    st.update({"side": 1, "sl": fill - sl_dist, "tp": fill + sl_dist * cfg["rr"], "risk_amt": equity * risk_val_decimal, "in_trade": True})
                    st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                    equity -= fill * st["size"] * TAKER_FEE
                    st["in_trade"] = True
                # SHORT
                elif close < ema_v and d["high"][i] > bb_top and close <= bb_top and d["rsi"][i] > cfg["rsi_high"]:
                    fill = close * (1 - SLIPPAGE); sl_dist = d["atr"][i] * cfg["atr"]
                    st.update({"side": -1, "sl": fill + sl_dist, "tp": fill - sl_dist * cfg["rr"], "risk_amt": equity * risk_val_decimal, "in_trade": True})
                    st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                    equity -= fill * st["size"] * TAKER_FEE
                    st["in_trade"] = True
            else:
                # Mean Reversion Entry Rules
                if cfg["adx"] > 0 and d["adx"][i] < cfg["adx"]: continue
                if close > ema_v and close < bb_bot and d["rsi"][i] < cfg["rsi"]:
                    fill = close * (1 + SLIPPAGE); sl_dist = d["atr"][i] * cfg["atr"]
                    st.update({"side": 1, "sl": fill - sl_dist, "tp": fill + sl_dist * cfg["rr"], "risk_amt": equity * risk_val_decimal, "in_trade": True})
                    st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                    equity -= fill * st["size"] * TAKER_FEE
                    st["in_trade"] = True
                elif not cfg.get("long_only") and close < ema_v and close > bb_top and d["rsi"][i] > (100 - cfg["rsi"]):
                    fill = close * (1 - SLIPPAGE); sl_dist = d["atr"][i] * cfg["atr"]
                    st.update({"side": -1, "sl": fill + sl_dist, "tp": fill - sl_dist * cfg["rr"], "risk_amt": equity * risk_val_decimal, "in_trade": True})
                    st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                    equity -= fill * st["size"] * TAKER_FEE
                    st["in_trade"] = True

    df_eq = pd.DataFrame(equity_history, columns=["date", "equity"]).set_index("date")
    df_dd = pd.DataFrame(drawdowns, columns=["date", "drawdown"]).set_index("date")

    # --- Calculations ---
    # Annualized Sharpe Ratio
    daily_returns = df_eq["equity"].resample('D').last().pct_change(fill_method=None).dropna()
    if len(daily_returns) > 1:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
    else:
        sharpe = 0.0

    # Institutional 75/25 Layout
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1]}, facecolor="#121212")
    
    # 🏔️ Equity Chart
    ax1.plot(df_eq.index, df_eq["equity"], color="cyan", linewidth=2)
    ax1.set_title(f"Sherpa 3-Year Audit: {user_id}", color="white", fontsize=16)
    ax1.tick_params(colors="white")
    ax1.grid(alpha=0.1)
    ax1.set_facecolor("#121212")
    ax1.text(0.02, 0.9, f"Sharpe: {sharpe:.2f}", transform=ax1.transAxes, color='cyan', fontweight='bold', bbox=dict(facecolor='#1A1A1A', alpha=0.8))
    ax1.text(0.02, 0.05, f"Start: ${start_balance:,.2f}", transform=ax1.transAxes, color='white', fontweight='bold', bbox=dict(facecolor='#1A1A1A', alpha=0.8))
    ax1.text(0.98, 0.9, f"Final: ${equity:,.2f}", transform=ax1.transAxes, color='#39FF14', fontweight='bold', ha='right', bbox=dict(facecolor='#1A1A1A', alpha=0.8))
    
    # 🌊 Drawdown Chart
    ax2.fill_between(df_dd.index, df_dd["drawdown"], 0, color="red", alpha=0.2)
    ax2.plot(df_dd.index, df_dd["drawdown"], color="red", linewidth=0.8)
    ax2.tick_params(colors="white")
    ax2.set_facecolor("#121212")
    ax2.set_title("Drawdown (%)", color="white", fontsize=10)
    ax2.set_ylabel("Drawdown (%)", color="white")
    ax2.set_ylim(-100, 5) # 0-100% Scale for visual compression
    ax2.grid(True, alpha=0.1); ax2.tick_params(colors="white")
    
    # 📌 Annotate Max Drawdown Peak
    if not df_dd.empty:
        max_dd_date = df_dd["drawdown"].idxmin()
        min_dd_val = df_dd["drawdown"].min()
        ax2.annotate(f"Peak DD: {abs(min_dd_val):.1f}%", 
                     xy=(max_dd_date, min_dd_val), 
                     xytext=(0, -25), 
                     textcoords="offset points", 
                     ha='center', 
                     color="white", 
                     fontweight='bold',
                     bbox=dict(facecolor='#1A1A1A', alpha=0.8, edgecolor='red'),
                     arrowprops=dict(arrowstyle='->', color='red'))
    
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
    return stats, chart_path, df_eq

def generate_comparison_chart():
    """Generates a high-impact comparison chart between Standard and Institutional tiers."""
    # 1. Run Standard (5 tokens, 1.0% Risk)
    std_stats, _, df_std = run_visual_audit(1.0, ["BTC","ETH","SOL","DOGE","ADA"], user_id="tmp_std")
    plt.close('all')
    
    # 2. Run Institutional (All tokens, 1.0% Risk)
    inst_stats, _, df_inst = run_visual_audit(1.0, None, user_id="tmp_inst")
    plt.close('all')
    
    if df_std is None or df_inst is None: return None
    
    # --- Plotting ---
    plt.figure(figsize=(12, 8), facecolor="#121212")
    ax = plt.gca()
    ax.set_facecolor("#121212")
    
    # Plot Premium (Neon Green)
    plt.plot(df_inst.index, df_inst["equity"], color="#39FF14", linewidth=3, label=f"Premium (Sharpe: {inst_stats['sharpe']:.2f})")
    # Plot Free (White)
    plt.plot(df_std.index, df_std["equity"], color="white", linewidth=2, alpha=0.8, label=f"Free (Sharpe: {std_stats['sharpe']:.2f})")
    
    # End Labels (Multi-line for clarity)
    last_date = df_inst.index[-1]
    
    plt.annotate(f"Premium: ${inst_stats['final_equity']:,.0f}\n(+{inst_stats['pnl_pct']:,.0f}%)", 
                 (last_date, inst_stats['final_equity']), textcoords="offset points", xytext=(10,0), va='center', color="#39FF14", fontweight='bold')
    plt.annotate(f"Free: ${std_stats['final_equity']:,.0f}\n(+{std_stats['pnl_pct']:,.0f}%)", 
                 (last_date, std_stats['final_equity']), textcoords="offset points", xytext=(10,0), va='center', color="white", fontweight='bold')
    
    # Give room for labels
    plt.xlim(df_inst.index[0], df_inst.index[-1] + pd.Timedelta(days=120))
    
    plt.title("Metaverse Sherpa: Standard vs Premium Performance", color="white", fontsize=18, pad=30)
    plt.ylabel("Account Equity ($)", color="white")
    plt.grid(True, alpha=0.1)
    plt.tick_params(colors="white")
    plt.legend(facecolor="#1A1A1A", labelcolor="white", loc='upper left')
    
    save_path = os.path.join(RESULTS_DIR, "upsell_comparison.png")
    plt.savefig(save_path, dpi=150, facecolor="#121212")
    plt.close()
    return save_path

def generate_strategy_comparison_chart():
    """Generates a high-impact comparison chart between Mean Reversion and Valkyrie Elite strategies."""
    # 1. Run Mean Reversion (1.0% Risk, Recommended)
    mr_stats, _, df_mr = run_visual_audit(1.0, None, user_id="diag", strategy_name="Mean Reversion Scalper")
    plt.close('all')
    
    # 2. Run Valkyrie (1.5% Risk, Recommended)
    valkyrie_symbols = ["SOL", "LINK", "BTC", "ADA", "DOT", "ETH", "SUI"]
    valk_stats, _, df_valk = run_visual_audit(1.5, valkyrie_symbols, user_id="diag_inst", strategy_name="Valkyrie Elite Scalper")
    plt.close('all')
    
    if df_mr is None or df_valk is None: return None
    
    # --- Plotting ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]}, facecolor="#121212")
    
    ax1.set_facecolor("#121212")
    # Plot Mean Reversion (Neon Cyan)
    ax1.plot(df_mr.index, df_mr["equity"], color="#00FFFF", linewidth=2.5, label=f"Mean Reversion Scalper (Sharpe: {mr_stats['sharpe']:.2f}, Max DD: {abs(mr_stats['max_dd']):.1f}%)")
    # Plot Valkyrie (Neon Magenta)
    ax1.plot(df_valk.index, df_valk["equity"], color="#FF00FF", linewidth=2.5, label=f"Valkyrie Elite Scalper (Sharpe: {valk_stats['sharpe']:.2f}, Max DD: {abs(valk_stats['max_dd']):.1f}%)")
    
    # End Labels
    last_date = df_mr.index[-1]
    ax1.annotate(f"Mean Rev:\n${mr_stats['final_equity']:,.0f}\n(+{mr_stats['pnl_pct']:.1f}%)", 
                 (last_date, mr_stats['final_equity']), textcoords="offset points", xytext=(10,0), va='center', color="#00FFFF", fontweight='bold')
    ax1.annotate(f"Valkyrie:\n${valk_stats['final_equity']:,.0f}\n(+{valk_stats['pnl_pct']:.1f}%)", 
                 (last_date, valk_stats['final_equity']), textcoords="offset points", xytext=(10,0), va='center', color="#FF00FF", fontweight='bold')
    
    ax1.set_xlim(df_mr.index[0], df_mr.index[-1] + pd.Timedelta(days=120))
    ax1.set_title("Metaverse Sherpa: Mean Reversion vs Valkyrie Elite Performance Comparison", color="white", fontsize=16, pad=20)
    ax1.set_ylabel("Account Equity ($)", color="white")
    ax1.grid(True, alpha=0.1)
    ax1.tick_params(colors="white")
    ax1.legend(facecolor="#1A1A1A", labelcolor="white", loc='upper left', fontsize=11)
    
    # Drawdowns Subplot
    ax2.set_facecolor("#121212")
    
    # MR Drawdown
    mr_dd = (df_mr["equity"] - df_mr["equity"].cummax()) / df_mr["equity"].cummax() * 100
    ax2.plot(mr_dd.index, mr_dd, color="#00FFFF", linewidth=1, alpha=0.7, label="Mean Rev DD")
    
    # Valkyrie Drawdown
    valk_dd = (df_valk["equity"] - df_valk["equity"].cummax()) / df_valk["equity"].cummax() * 100
    ax2.plot(valk_dd.index, valk_dd, color="#FF00FF", linewidth=1, alpha=0.7, label="Valkyrie DD")
    
    ax2.set_ylim(-40, 2)
    ax2.set_ylabel("Drawdown (%)", color="white")
    ax2.grid(True, alpha=0.1)
    ax2.tick_params(colors="white")
    ax2.legend(facecolor="#1A1A1A", labelcolor="white", loc='lower left')
    
    fig.patch.set_facecolor("#121212")
    plt.tight_layout()
    
    save_path = os.path.join(RESULTS_DIR, "strategy_comparison.png")
    plt.savefig(save_path, dpi=150, facecolor="#121212")
    plt.close()
    return save_path


if __name__ == "__main__":
    import time
    s, p, _ = run_visual_audit(1.5)
    if s: print(f"Audit Complete! Final Equity: ${s['final_equity']:,.2f}")
