import sys
import os
import pandas as pd
import numpy as np

sys.path.append("/Users/johngiles/projects/tradingbot")
sys.path.append("/Users/johngiles/projects/tradingbot/scripts")

from sherpa_visual_audit import calc_ema, calc_atr, calc_adx, calc_rsi

OPTIMIZED_VALKYRIE_SYMBOL_CONFIGS = {
    "SOL":  {"bb": 2.0, "atr": 4.0, "rr": 1.2, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "LINK": {"bb": 2.6, "atr": 3.5, "rr": 0.8, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "BTC":  {"bb": 2.4, "atr": 3.0, "rr": 1.5, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "ADA":  {"bb": 2.4, "atr": 3.0, "rr": 1.0, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "DOT":  {"bb": 2.8, "atr": 4.5, "rr": 1.5, "adx": 25, "rsi_low": 25, "rsi_high": 75}
}

valkyrie_symbols = ["SOL", "LINK", "BTC", "ADA", "DOT"]
datasets = {}
for name in valkyrie_symbols:
    path = f"csv_blofin/blofin_{name}_15m.csv"
    df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
    cfg = OPTIMIZED_VALKYRIE_SYMBOL_CONFIGS[name]
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

states = {name: {"in_trade": False, "side": 0, "sl": 0.0, "tp": 0.0, "size": 0.0, "risk_amt": 0.0, "wins": 0, "losses": 0} for name in valkyrie_symbols}
equity_history = [(common_idx[0], equity)]
trade_dates = []

for i in range(200, n_bars - 1):
    # Exit Check
    for name, d in aligned.items():
        st = states[name]; cfg = OPTIMIZED_VALKYRIE_SYMBOL_CONFIGS[name]
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
            trade_dates.append(common_idx[i].date())
            
            max_eq = max(max_eq, equity)
            dd = (max_eq - equity) / max_eq * 100
            max_dd_val = max(max_dd_val, dd)
            equity_history.append((common_idx[i], equity))

    # Entry Check
    for name, d in aligned.items():
        st = states[name]; cfg = OPTIMIZED_VALKYRIE_SYMBOL_CONFIGS[name]
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

total_trades = len(trade_dates)
unique_days = len(set(trade_dates))
total_calendar_days = (common_idx[-1] - common_idx[0]).days
avg_trades_per_day = total_trades / total_calendar_days

print("DEEP OPTIMIZED STATS:")
print(f"  PnL Return: {((equity - start_balance)/start_balance)*100:.2f}%")
print(f"  Final Balance: ${equity:.2f}")
print(f"  Max Drawdown: {max_dd_val:.2f}%")
print(f"  Sharpe Ratio: {sharpe:.2f}")
print(f"  Total Trades: {total_trades}")
print(f"  Total Days on Trail: {total_calendar_days} days")
print(f"  Avg Trades per Day: {avg_trades_per_day:.3f} trades/day (approx 1 trade every {1/avg_trades_per_day:.1f} days)")
print(f"  Active Trading Days: {unique_days} days")
