import os
import sys
import json
import pandas as pd
import numpy as np

# Ensure we can import from the root directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database
from scripts.sherpa_visual_audit import (
    SYMBOL_CONFIGS,
    VALKYRIE_SYMBOL_CONFIGS,
    CSV_DIR,
    prepare_indicators,
    EMA_PERIOD,
    SLIPPAGE,
    TAKER_FEE,
    MAKER_FEE,
    LEVERAGE
)
from stock_backtester_daily import load_data_from_db, check_signal, FEE_RATE

def precalculate_crypto_trades(strategy_name="Mean Reversion Scalper"):
    print(f"⌛ Running 3-Year baseline for crypto strategy: {strategy_name}...")
    
    if strategy_name == "Valkyrie Elite Scalper":
        enabled_symbols = ["SOL", "LINK", "BTC", "ADA", "DOT", "ETH", "SUI"]
        cfg_source = VALKYRIE_SYMBOL_CONFIGS
    else:
        enabled_symbols = list(SYMBOL_CONFIGS.keys())
        cfg_source = SYMBOL_CONFIGS
        
    datasets = {}
    for name in enabled_symbols:
        path = os.path.join(CSV_DIR, f"blofin_{name}_15m.csv")
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        datasets[name] = prepare_indicators(df, cfg_source[name], strategy_name)
    
    if not datasets:
        print(f"❌ No datasets found for crypto strategy {strategy_name}")
        return []
        
    # Compounding simulation to discover exact trades
    all_indices = [v["index"] for v in datasets.values()]
    common_idx = all_indices[0]
    for idx in all_indices[1:]:
        common_idx = common_idx.union(idx)
    common_idx = common_idx.sort_values()
    n_bars = len(common_idx)
    
    aligned = {}
    for name, d in datasets.items():
        pos = d["index"].get_indexer(common_idx)
        valid = pos >= 0
        arr = {k: np.where(valid, d[k][np.where(valid, pos, 0)], np.nan) for k in ["close","high","low","ema","rsi","atr","adx","bb_top","bb_bot"]}
        aligned[name] = arr

    states = {name: {"in_trade": False, "side": 0, "sl": 0.0, "tp": 0.0, "size": 0.0, "risk_amt": 0.0, "entry_date": None, "entry_price": 0.0, "sl_dist": 0.0} for name in datasets}
    trades_list = []
    equity = 10000.0
    risk_val_decimal = 0.015  # 1.5% baseline risk

    for i in range(EMA_PERIOD, n_bars - 1):
        # 1. Check Exit
        for name, d in aligned.items():
            st = states[name]; cfg = cfg_source[name]
            if not st["in_trade"]:
                continue
            hi, lo, ex = d["high"][i], d["low"][i], d["close"][i]
            if np.isnan(hi):
                continue
            
            hit_sl = hit_tp = False
            if st["side"] == 1:
                if lo <= st["sl"]:
                    hit_sl = True
                    ex = st["sl"]
                elif hi >= st["tp"]:
                    hit_tp = True
                    ex = st["tp"]
            else:
                if hi >= st["sl"]:
                    hit_sl = True
                    ex = st["sl"]
                elif lo <= st["tp"]:
                    hit_tp = True
                    ex = st["tp"]

            if hit_sl or hit_tp:
                pnl = st["risk_amt"] * cfg["rr"] if hit_tp else -st["risk_amt"]
                fee_rate = MAKER_FEE if hit_tp else TAKER_FEE
                equity += pnl - ex * st["size"] * fee_rate
                
                trades_list.append({
                    "strategy": strategy_name,
                    "symbol": name,
                    "type": "crypto",
                    "entry_date": str(st["entry_date"]),
                    "exit_date": str(common_idx[i]),
                    "side": "LONG" if st["side"] == 1 else "SHORT",
                    "entry_price": float(st["entry_price"]),
                    "exit_price": float(ex),
                    "sl_dist": float(st["sl_dist"]),
                    "win": bool(hit_tp),
                    "rr_ratio": float(cfg["rr"]),
                    "fee_rate": float(fee_rate)
                })
                st["in_trade"] = False

        # 2. Check Entry
        for name, d in aligned.items():
            st = states[name]; cfg = cfg_source[name]
            if st["in_trade"]:
                continue
            close, ema_v, bb_top, bb_bot = d["close"][i], d["ema"][i], d["bb_top"][i], d["bb_bot"][i]
            if any(np.isnan(v) for v in [close, ema_v, bb_bot]):
                continue
            
            if strategy_name == "Valkyrie Elite Scalper":
                bandwidth = (bb_top - bb_bot) / close
                if bandwidth < 0.012 or d["adx"][i] > cfg["adx"]:
                    continue
                
                if close > ema_v and d["low"][i] < bb_bot and close >= bb_bot and d["rsi"][i] < cfg["rsi_low"]:
                    fill = close * (1 + SLIPPAGE)
                    sl_dist = d["atr"][i] * cfg["atr"]
                    st.update({
                        "side": 1,
                        "sl": fill - sl_dist,
                        "tp": fill + sl_dist * cfg["rr"],
                        "risk_amt": equity * risk_val_decimal,
                        "entry_date": common_idx[i],
                        "entry_price": fill,
                        "sl_dist": sl_dist,
                        "in_trade": True
                    })
                    st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                    equity -= fill * st["size"] * TAKER_FEE
                elif close < ema_v and d["high"][i] > bb_top and close <= bb_top and d["rsi"][i] > cfg["rsi_high"]:
                    fill = close * (1 - SLIPPAGE)
                    sl_dist = d["atr"][i] * cfg["atr"]
                    st.update({
                        "side": -1,
                        "sl": fill + sl_dist,
                        "tp": fill - sl_dist * cfg["rr"],
                        "risk_amt": equity * risk_val_decimal,
                        "entry_date": common_idx[i],
                        "entry_price": fill,
                        "sl_dist": sl_dist,
                        "in_trade": True
                    })
                    st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                    equity -= fill * st["size"] * TAKER_FEE
            else:
                if cfg["adx"] > 0 and d["adx"][i] < cfg["adx"]:
                    continue
                if close > ema_v and close < bb_bot and d["rsi"][i] < cfg["rsi"]:
                    fill = close * (1 + SLIPPAGE)
                    sl_dist = d["atr"][i] * cfg["atr"]
                    st.update({
                        "side": 1,
                        "sl": fill - sl_dist,
                        "tp": fill + sl_dist * cfg["rr"],
                        "risk_amt": equity * risk_val_decimal,
                        "entry_date": common_idx[i],
                        "entry_price": fill,
                        "sl_dist": sl_dist,
                        "in_trade": True
                    })
                    st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                    equity -= fill * st["size"] * TAKER_FEE
                elif not cfg.get("long_only") and close < ema_v and close > bb_top and d["rsi"][i] > (100 - cfg["rsi"]):
                    fill = close * (1 - SLIPPAGE)
                    sl_dist = d["atr"][i] * cfg["atr"]
                    st.update({
                        "side": -1,
                        "sl": fill + sl_dist,
                        "tp": fill - sl_dist * cfg["rr"],
                        "risk_amt": equity * risk_val_decimal,
                        "entry_date": common_idx[i],
                        "entry_price": fill,
                        "sl_dist": sl_dist,
                        "in_trade": True
                    })
                    st["size"] = min(st["risk_amt"] / sl_dist, (equity * LEVERAGE) / fill)
                    equity -= fill * st["size"] * TAKER_FEE
                    
    print(f"✅ Generated {len(trades_list)} trades for {strategy_name}")
    return trades_list

def precalculate_stock_trades():
    print("⌛ Running 3-Year baseline for stock strategy: Sherpa Velocity Pullback...")
    data_dict = load_data_from_db()
    
    best_params = {
        "rsi_period": 3,
        "rsi_entry": 10,
        "rsi_exit": 65,
        "atr_sl_mult": 3.0,
        "trend_ema": "ema_200",
        "long_only": True
    }
    
    processed_data = {}
    for sym, df in data_dict.items():
        # calculate indicators just like stock_backtester_daily.py does
        from stock_backtester_daily import calculate_indicators
        processed_data[sym] = calculate_indicators(df, "Velocity_Pullback", best_params)
        
    all_dates = sorted(list(set().union(*(df.index for df in processed_data.values()))))
    
    cash = 10000.0
    active_trades = {}
    trades_list = []
    equity = 10000.0
    pct_per_trade = 0.01 # 1.0% baseline
    
    atr_sl_mult = best_params["atr_sl_mult"]
    rr_ratio = 1.5
    sym_indices = {sym: {date: i for i, date in enumerate(df.index)} for sym, df in processed_data.items()}
    
    for t_idx, date in enumerate(all_dates):
        # exits
        symbols_to_close = []
        for sym, t in active_trades.items():
            df = processed_data[sym]
            if date not in df.index:
                continue
            
            bar = df.loc[date]
            o, h, l, c = bar['open'], bar['high'], bar['low'], bar['close']
            sl, tp, shares, entry_price = t['sl'], t['tp'], t['shares'], t['entry_price']
            
            exited = False
            exit_price = None
            exit_reason = None
            
            if t['type'] == "LONG":
                idx_list = df.index.tolist()
                if date in idx_list:
                    curr_idx = idx_list.index(date)
                    if curr_idx > 0:
                        prev_date_in_df = idx_list[curr_idx - 1]
                        prev_bar = df.loc[prev_date_in_df]
                        if prev_bar['close'] > prev_bar['sma_5'] or prev_bar['rsi'] > best_params["rsi_exit"]:
                            exited = True
                            exit_price = o
                            exit_reason = "DYNAMIC_EXIT"
                            
                if not exited:
                    if o <= sl:
                        exited = True
                        exit_price = o
                        exit_reason = "STOP_LOSS (GAP)"
                    elif o >= tp:
                        exited = True
                        exit_price = o
                        exit_reason = "TAKE_PROFIT (GAP)"
                    elif l <= sl and h >= tp:
                        exited = True
                        exit_price = sl
                        exit_reason = "STOP_LOSS (CONSERVATIVE)"
                    elif l <= sl:
                        exited = True
                        exit_price = sl
                        exit_reason = "STOP_LOSS"
                    elif h >= tp:
                        exited = True
                        exit_price = tp
                        exit_reason = "TAKE_PROFIT"
                        
            if exited:
                gross_pnl = (exit_price - entry_price) * shares
                exit_value = exit_price * shares
                fee = exit_value * FEE_RATE
                net_pnl = gross_pnl - fee - t['entry_fee']
                cash += exit_value - fee
                
                trades_list.append({
                    "strategy": "Sherpa Velocity Pullback",
                    "symbol": sym,
                    "type": "stock",
                    "entry_date": str(t['entry_date']),
                    "exit_date": str(date),
                    "side": "LONG",
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "sl_dist": float(t['sl_dist']),
                    "win": bool("TAKE_PROFIT" in exit_reason or (gross_pnl > 0 and "DYNAMIC_EXIT" in exit_reason)),
                    "rr_ratio": float(rr_ratio),
                    "fee_rate": float(FEE_RATE),
                    "exit_reason": exit_reason
                })
                symbols_to_close.append(sym)
                
        for sym in symbols_to_close:
            active_trades.pop(sym)
            
        # equity calculation
        calc_equity = cash
        for sym, t in active_trades.items():
            df = processed_data[sym]
            c_p = df.loc[date, 'close'] if date in df.index else t['entry_price']
            calc_equity += t['shares'] * c_p
            
        # entry
        if t_idx == 0:
            continue
            
        prev_date = all_dates[t_idx - 1]
        signals = []
        for sym in processed_data.keys():
            if sym in active_trades:
                continue
            df = processed_data[sym]
            if prev_date not in df.index or date not in df.index:
                continue
            prev_idx = sym_indices[sym][prev_date]
            sig = check_signal(df, prev_idx, "Velocity_Pullback", best_params)
            if sig:
                signals.append((sym, sig))
                
        signals.sort(key=lambda x: x[0])
        
        for sym, sig_type in signals:
            df = processed_data[sym]
            bar = df.loc[date]
            entry_price = bar['open']
            prev_bar = df.loc[prev_date]
            atr = prev_bar['atr']
            if np.isnan(atr) or atr <= 0:
                continue
                
            D = atr_sl_mult * atr
            if D < entry_price * 0.005:
                D = entry_price * 0.005
                
            sl = entry_price - D
            tp = entry_price + (rr_ratio * D)
            
            risk_dollars = calc_equity * pct_per_trade
            shares = risk_dollars / D
            position_notional = shares * entry_price
            
            if position_notional > cash:
                shares = cash / entry_price
                position_notional = shares * entry_price
                
            entry_fee = position_notional * FEE_RATE
            
            if shares > 0.01 and position_notional > 10.0 and cash >= (position_notional + entry_fee):
                cash -= (position_notional + entry_fee)
                active_trades[sym] = {
                    "type": "LONG",
                    "entry_date": date,
                    "entry_price": entry_price,
                    "sl": sl,
                    "tp": tp,
                    "shares": shares,
                    "notional": position_notional,
                    "entry_fee": entry_fee,
                    "sl_dist": D
                }
                
    print(f"✅ Generated {len(trades_list)} trades for Sherpa Velocity Pullback")
    return trades_list

def main():
    all_trades = []
    
    # 1. Mean Reversion Scalper
    all_trades.extend(precalculate_crypto_trades("Mean Reversion Scalper"))
    
    # 2. Valkyrie Elite Scalper
    all_trades.extend(precalculate_crypto_trades("Valkyrie Elite Scalper"))
    
    # 3. Sherpa Velocity Pullback (Stock)
    all_trades.extend(precalculate_stock_trades())
    
    # Save to data/precalculated_trades.json
    os.makedirs("data", exist_ok=True)
    with open("data/precalculated_trades.json", "w") as f:
        json.dump(all_trades, f, indent=2)
        
    print("🎉 Precalculation complete! Trades saved to data/precalculated_trades.json")

if __name__ == "__main__":
    main()
