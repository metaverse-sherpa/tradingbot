import sys
import os
import pandas as pd
import numpy as np

sys.path.append("/Users/johngiles/projects/tradingbot")
sys.path.append("/Users/johngiles/projects/tradingbot/scripts")

from sherpa_visual_audit import calc_ema, calc_atr, calc_adx, calc_rsi

# Base Optimized Valkyrie configs
OPTIMIZED_VALKYRIE_SYMBOL_CONFIGS = {
    "SOL":  {"bb": 2.0, "atr": 4.0, "rr": 1.2, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "LINK": {"bb": 2.6, "atr": 3.5, "rr": 0.8, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "BTC":  {"bb": 2.4, "atr": 3.0, "rr": 1.5, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "ADA":  {"bb": 2.4, "atr": 3.0, "rr": 1.0, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "DOT":  {"bb": 2.8, "atr": 4.5, "rr": 1.5, "adx": 25, "rsi_low": 25, "rsi_high": 75}
}

valkyrie_symbols = ["SOL", "LINK", "BTC", "ADA", "DOT"]
candidates = ["ETH", "BNB", "TON", "NEAR", "SUI", "DOGE"]

def simulate_portfolio(symbols_list, configs_dict):
    datasets = {}
    for name in symbols_list:
        path = f"csv_blofin/blofin_{name}_15m.csv"
        if not os.path.exists(path): continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        cfg = configs_dict[name]
        datasets[name] = {
            "close": df["close"].values, "high": df["high"].values, "low": df["low"].values,
            "ema": calc_ema(df["close"], 200).values, "rsi": calc_rsi(df["close"], wilder=False).values,
            "atr": calc_atr(df).values, "adx": calc_adx(df).values,
            "bb_top": (df["close"].rolling(20).mean() + cfg["bb"] * df["close"].rolling(20).std()).values,
            "bb_bot": (df["close"].rolling(20).mean() - cfg["bb"] * df["close"].rolling(20).std()).values,
            "index": df.index,
        }

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

    start_balance = 180.0
    equity = start_balance
    max_eq = start_balance
    max_dd_val = 0.0

    TAKER_FEE = 0.0006
    MAKER_FEE = 0.0002
    SLIPPAGE = 0.0005
    LEVERAGE = 20.0
    risk_val_decimal = 0.015

    states = {name: {"in_trade": False, "side": 0, "sl": 0.0, "tp": 0.0, "size": 0.0, "risk_amt": 0.0, "wins": 0, "losses": 0} for name in symbols_list}
    equity_history = [(common_idx[0], equity)]
    
    for i in range(200, n_bars - 1):
        # Exit Check
        for name, d in aligned.items():
            st = states[name]; cfg = configs_dict[name]
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
                
                max_eq = max(max_eq, equity)
                dd = (max_eq - equity) / max_eq * 100
                max_dd_val = max(max_dd_val, dd)
                equity_history.append((common_idx[i], equity))

        # Entry Check
        for name, d in aligned.items():
            st = states[name]; cfg = configs_dict[name]
            if st["in_trade"]: continue
            close, ema_v, bb_top, bb_bot, high, low = d["close"][i], d["ema"][i], d["bb_top"][i], d["bb_bot"][i], d["high"][i], d["low"][i]
            if any(np.isnan(v) for v in [close, ema_v, bb_bot, high, low]): continue
            
            bandwidth = (bb_top - bb_bot) / close
            if bandwidth < 0.012 or d["adx"][i] > cfg["adx"]: continue
            
            # LONG
            if close > ema_v and low < bb_bot and close >= bb_bot and d["rsi"][i] < cfg["rsi_low"]:
                fill = close * (1 + SLIPPAGE); sl_dist = d["atr"][i] * cfg["atr"]
                st.update({"side": 1, "sl": fill - sl_dist, "tp": fill + sl_dist * cfg["rr"], "risk_amt": equity * risk_val_decimal, "in_trade": True})
                st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity -= fill * st["size"] * TAKER_FEE
            # SHORT
            elif close < ema_v and high > bb_top and close <= bb_top and d["rsi"][i] > cfg["rsi_high"]:
                fill = close * (1 - SLIPPAGE); sl_dist = d["atr"][i] * cfg["atr"]
                st.update({"side": -1, "sl": fill + sl_dist, "tp": fill - sl_dist * cfg["rr"], "risk_amt": equity * risk_val_decimal, "in_trade": True})
                st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                equity -= fill * st["size"] * TAKER_FEE

    df_eq = pd.DataFrame(equity_history, columns=["date", "equity"]).set_index("date")
    daily_returns = df_eq["equity"].resample('D').last().pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365) if len(daily_returns) > 1 else 0.0
    total_trades = sum(st["wins"] + st["losses"] for st in states.values())
    win_rate = (sum(st["wins"] for st in states.values()) / total_trades * 100) if total_trades else 0.0
    
    return equity, max_dd_val, sharpe, total_trades, win_rate

# Pre-optimize each candidate on its own first
print("Optimizing candidates individually...")
datasets_raw = {}
for name in candidates:
    path = f"csv_blofin/blofin_{name}_15m.csv"
    if not os.path.exists(path): continue
    df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
    datasets_raw[name] = df

candidate_configs = {}

bb_options = [2.2, 2.4, 2.6, 2.8]
atr_options = [3.0, 3.5, 4.0, 4.5]
rr_options = [0.8, 1.0, 1.2, 1.5]

for name in candidates:
    df = datasets_raw[name]
    best_pnl = -999999
    best_cfg = {}
    
    # Run a simplified single symbol optimization to find the best configuration
    for bb in bb_options:
        for atr in atr_options:
            for rr in rr_options:
                close = df["close"].values
                high = df["high"].values
                low = df["low"].values
                ema = calc_ema(df["close"], 200).values
                rsi = calc_rsi(df["close"], wilder=False).values
                atr_v = calc_atr(df).values
                adx = calc_adx(df).values
                mid = df["close"].rolling(20).mean(); std = df["close"].rolling(20).std()
                bb_top = (mid + bb * std).values
                bb_bot = (mid - bb * std).values
                
                sub_eq = 2000.0
                in_trade = False
                side = 0
                sl = tp = size = risk_amt = 0.0
                cooldown = 0
                wins = losses = 0
                
                for i in range(200, len(close) - 1):
                    if cooldown > 0:
                        cooldown -= 1
                        continue
                    if not in_trade:
                        bandwidth = (bb_top[i] - bb_bot[i]) / close[i]
                        if bandwidth < 0.012 or adx[i] > 25: continue
                        if close[i] > ema[i] and low[i] < bb_bot[i] and close[i] >= bb_bot[i] and rsi[i] < 25:
                            side = 1
                            fill = close[i] * 1.0005
                            sl_d = atr_v[i] * atr
                            sl = fill - sl_d
                            tp = fill + sl_d * rr
                            risk_amt = sub_eq * 0.075
                            size = min(risk_amt / sl_d, (sub_eq * 20.0) / fill)
                            sub_eq -= fill * size * 0.0006
                            in_trade = True
                        elif close[i] < ema[i] and high[i] > bb_top[i] and close[i] <= bb_top[i] and rsi[i] > 75:
                            side = -1
                            fill = close[i] * 0.9995
                            sl_d = atr_v[i] * atr
                            sl = fill + sl_d
                            tp = fill - sl_d * rr
                            risk_amt = sub_eq * 0.075
                            size = min(risk_amt / sl_d, (sub_eq * 20.0) / fill)
                            sub_eq -= fill * size * 0.0006
                            in_trade = True
                    else:
                        hi, lo = high[i], low[i]
                        hit_sl = hit_tp = False
                        if side == 1:
                            if lo <= sl: hit_sl = True; ex = sl
                            elif hi >= tp: hit_tp = True; ex = tp
                        else:
                            if hi >= sl: hit_sl = True; ex = sl
                            elif lo <= tp: hit_tp = True; ex = tp
                        if hit_sl or hit_tp:
                            pnl = risk_amt * rr if hit_tp else -risk_amt
                            sub_eq += pnl - (sl if hit_sl else tp) * size * (0.0002 if hit_tp else 0.0006)
                            if hit_tp: wins += 1
                            else: losses += 1
                            in_trade = False
                            cooldown = 2
                
                total = wins + losses
                if total >= 15 and sub_eq > best_pnl:
                    best_pnl = sub_eq
                    best_cfg = {"bb": bb, "atr": atr, "rr": rr, "adx": 25, "rsi_low": 25, "rsi_high": 75}
                    
    if best_cfg:
        candidate_configs[name] = best_cfg
        print(f"  {name} Optimized: BB: {bb}, ATR: {atr}, RR: {rr} (Sub-Return: {(best_pnl-2000)/2000*100:+.1f}%)")

# Base stats
print("\nCalculating Base Portfolio Stats (Top 5: SOL, LINK, BTC, ADA, DOT)...")
base_eq, base_dd, base_sharpe, base_trades, base_wr = simulate_portfolio(valkyrie_symbols, OPTIMIZED_VALKYRIE_SYMBOL_CONFIGS)
print(f"  Base PnL: +{((base_eq-180)/180)*100:.2f}% | Max DD: {base_dd:.2f}% | Sharpe: {base_sharpe:.2f} | Trades: {base_trades}")

results = []
# Now test adding candidates one by one
print("\nTesting candidate additions...")
for cand, cfg in candidate_configs.items():
    test_symbols = valkyrie_symbols + [cand]
    test_configs = {**OPTIMIZED_VALKYRIE_SYMBOL_CONFIGS, cand: cfg}
    
    eq, dd, sharpe, trades, wr = simulate_portfolio(test_symbols, test_configs)
    pnl_pct = ((eq - 180)/180)*100
    
    impact_pnl = pnl_pct - ((base_eq-180)/180)*100
    impact_dd = dd - base_dd
    impact_sharpe = sharpe - base_sharpe
    
    results.append({
        "Symbol": cand,
        "BB": cfg["bb"],
        "ATR": cfg["atr"],
        "RR": cfg["rr"],
        "PnL": f"{pnl_pct:.2f}% ({impact_pnl:+.2f}%)",
        "Max DD": f"{dd:.2f}% ({impact_dd:+.2f}%)",
        "Sharpe": f"{sharpe:.2f} ({impact_sharpe:+.2f})",
        "Trades": trades,
        "Win Rate": f"{wr:.1f}%",
        "Keep": "YES ✅" if impact_pnl >= -5.0 and impact_dd <= 3.0 and impact_sharpe >= -0.5 else "NO ❌"
    })

df_res = pd.DataFrame(results)
print("\n=== SYSTEMATIC CANDIDATE RESULTS ===")
print(df_res.to_string(index=False))

# Test combined YES portfolio
yes_symbols = [r["Symbol"] for r in results if r["Keep"] == "YES ✅"]
if yes_symbols:
    print(f"\nTesting combined portfolio: Base + {yes_symbols}...")
    comb_symbols = valkyrie_symbols + yes_symbols
    comb_configs = {**OPTIMIZED_VALKYRIE_SYMBOL_CONFIGS}
    for ys in yes_symbols:
        comb_configs[ys] = candidate_configs[ys]
        
    c_eq, c_dd, c_sharpe, c_trades, c_wr = simulate_portfolio(comb_symbols, comb_configs)
    print(f"  Combined PnL: +{((c_eq-180)/180)*100:.2f}%")
    print(f"  Combined Max DD: {c_dd:.2f}%")
    print(f"  Combined Sharpe: {c_sharpe:.2f}")
    print(f"  Combined Trades: {c_trades}")
