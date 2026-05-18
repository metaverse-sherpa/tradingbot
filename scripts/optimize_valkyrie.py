import os
import numpy as np
import pandas as pd

# Fees
MAKER_FEE = 0.0002
TAKER_FEE = 0.0006
SLIPPAGE = 0.0005

def ema(s: pd.Series, p: int) -> pd.Series:
    return s.ewm(span=p, adjust=False).mean()

def rsi(s: pd.Series, p: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(span=p, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=p, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def atr(df: pd.DataFrame, p: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1/p, adjust=False).mean()

def adx(df: pd.DataFrame, p: int = 14) -> pd.Series:
    pdm = df["high"].diff().clip(lower=0)
    ndm = (-df["low"].diff()).clip(lower=0)
    pdm = pdm.where(pdm > ndm, 0.0)
    ndm = ndm.where(ndm > pdm, 0.0)
    tr_ema = atr(df, p)
    pdi = 100 * pdm.ewm(alpha=1/p, adjust=False).mean() / tr_ema
    ndi = 100 * ndm.ewm(alpha=1/p, adjust=False).mean() / tr_ema
    dx = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1/p, adjust=False).mean()

def simulate(df: pd.DataFrame, p: dict) -> dict:
    d = df.copy()
    d["ema200"] = ema(d["close"], 200)
    d["rsi"] = rsi(d["close"], 14)
    d["atr"] = atr(d, 14)
    d["adx"] = adx(d, 14)
    
    mid = d["close"].rolling(20).mean()
    std = d["close"].rolling(20).std()
    d["bb_up"] = mid + p["bb_dev"] * std
    d["bb_low"] = mid - p["bb_dev"] * std
    
    close = d["close"].values
    high = d["high"].values
    low = d["low"].values
    ema_v = d["ema200"].values
    rsi_v = d["rsi"].values
    atr_v = d["atr"].values
    adx_v = d["adx"].values
    bb_up = d["bb_up"].values
    bb_low = d["bb_low"].values
    
    equity = 2000.0
    max_eq = 2000.0
    max_dd = 0.0
    wins = losses = 0
    in_trade = False
    side = 0
    entry_price = sl_price = tp_price = position_units = 0.0
    cooldown = 0
    warmup = 200
    
    for i in range(warmup, len(close) - 1):
        if cooldown > 0:
            cooldown -= 1
            continue
            
        if not in_trade:
            # Bandwidth filter (minimum 1.2% price distance to block horizontal consolidation chops)
            bandwidth = (bb_up[i] - bb_low[i]) / close[i]
            if bandwidth < 0.012:
                continue
            
            # Enforce range-bound ADX (Low ADX = sideways range, high ADX = trend breakout)
            if adx_v[i] > p["adx_max"]:
                continue
                
            # LONG Signal: Wick exhaustion rejection
            if close[i] > ema_v[i] and low[i] < bb_low[i] and close[i] >= bb_low[i] and rsi_v[i] < p["rsi_low"]:
                side = 1
                entry_price = close[i] * (1 + SLIPPAGE)
                atr_dist = atr_v[i] * p["atr_mult"]
                sl_price = entry_price - atr_dist
                tp_price = entry_price + (atr_dist * p["rr"])
                
                risk_amount = equity * 0.01
                position_size_usd = risk_amount / (atr_dist / entry_price)
                position_size_usd = min(position_size_usd, equity * 20.0)
                position_units = position_size_usd / entry_price
                
                equity -= entry_price * position_units * TAKER_FEE
                in_trade = True
                
            # SHORT Signal: Wick exhaustion rejection
            elif close[i] < ema_v[i] and high[i] > bb_up[i] and close[i] <= bb_up[i] and rsi_v[i] > p["rsi_high"]:
                side = -1
                entry_price = close[i] * (1 - SLIPPAGE)
                atr_dist = atr_v[i] * p["atr_mult"]
                sl_price = entry_price + atr_dist
                tp_price = entry_price - (atr_dist * p["rr"])
                
                risk_amount = equity * 0.01
                position_size_usd = risk_amount / (atr_dist / entry_price)
                position_size_usd = min(position_size_usd, equity * 20.0)
                position_units = position_size_usd / entry_price
                
                equity -= entry_price * position_units * TAKER_FEE
                in_trade = True
        else:
            hit_sl = hit_tp = False
            exit_price = 0.0
            if side == 1:
                if low[i] <= sl_price:
                    hit_sl = True
                    exit_price = sl_price
                elif high[i] >= tp_price:
                    hit_tp = True
                    exit_price = tp_price
            else:
                if high[i] >= sl_price:
                    hit_sl = True
                    exit_price = sl_price
                elif low[i] <= tp_price:
                    hit_tp = True
                    exit_price = tp_price
                    
            if hit_sl or hit_tp:
                pnl = position_units * (exit_price - entry_price) * side
                fee = exit_price * position_units * (MAKER_FEE if hit_tp else TAKER_FEE)
                equity += pnl - fee
                
                if hit_tp:
                    wins += 1
                else:
                    losses += 1
                    
                if equity > max_eq:
                    max_eq = equity
                else:
                    dd = (max_eq - equity) / max_eq * 100
                    if dd > max_dd:
                        max_dd = dd
                in_trade = False
                cooldown = 2
                
    total = wins + losses
    if total == 0:
        return {"wr": 0.0, "pnl": 0.0, "max_dd": 0.0, "trades": 0}
    return {"wr": wins / total * 100, "pnl": (equity - 2000.0) / 2000.0 * 100, "max_dd": max_dd, "trades": total}

def optimize():
    # Sweep across all major high-volume assets to select the absolute top 5
    symbols = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "LTC", "DOT", "LINK", "AVAX"]
    
    bb_devs = [2.2, 2.4, 2.6, 2.8]
    atr_mults = [2.5, 3.0, 3.5]
    rrs = [0.8, 1.0, 1.25]
    adx_maxes = [20, 25, 30]
    rsi_spaces = [
        {"rsi_low": 30, "rsi_high": 70},
        {"rsi_low": 25, "rsi_high": 75}
    ]
    
    print("="*70)
    print(" 🛡️ VALKYRIE 10-SYMBOL INSTITUTIONAL GRID SWEEP")
    print("="*70)
    
    all_results = []
    
    for s in symbols:
        path = f"csv/cache_{s}_15m.csv"
        if not os.path.exists(path):
            continue
            
        print(f"⚙️ Running sweep for {s}...")
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        
        best_pnl = -999.0
        best_wr = 0.0
        best_trades = 0
        best_params = {}
        
        for bb in bb_devs:
            for atr_m in atr_mults:
                for rr in rrs:
                    for adx_m in adx_maxes:
                        for rsi_c in rsi_spaces:
                            p = {
                                "bb_dev": bb, "atr_mult": atr_m, "rr": rr,
                                "adx_max": adx_m, **rsi_c, "bb_period": 20, "atr_period": 14
                            }
                            r = simulate(df, p)
                            
                            # Filter for high-integrity (Win Rate >= 60% and at least 15 trades)
                            if r["trades"] >= 15 and r["wr"] >= 60.0:
                                if r["pnl"] > best_pnl:
                                    best_pnl = r["pnl"]
                                    best_wr = r["wr"]
                                    best_trades = r["trades"]
                                    best_params = p
                                    
        if best_params:
            print(f"   ✨ {s} Winner: {best_pnl:+.1f}% PnL | {best_wr:.1f}% WR | {best_trades} trades")
            all_results.append({
                "symbol": s,
                "pnl": best_pnl,
                "wr": best_wr,
                "trades": best_trades,
                "params": best_params
            })
            
    # Sort symbols by PnL descending
    all_results.sort(key=lambda x: x["pnl"], reverse=True)
    
    print("\n" + "="*70)
    print("🏆 FINAL QUANTITATIVE LEADERBOARD (SORTED BY RETURN)")
    print("="*70)
    for idx, r in enumerate(all_results):
        print(f"{idx+1}. {r['symbol']}: Return: {r['pnl']:+.2f}% | WR: {r['wr']:.1f}% | Trades: {r['trades']}")
        
    print("\n" + "="*70)
    print("💎 TOP 5 CONVERTING CONFIGURED DICTIONARY")
    print("="*70)
    top_5 = all_results[:5]
    for r in top_5:
        print(f'    "{r["symbol"]}": {r["params"]},')
    print("="*70)

if __name__ == "__main__":
    optimize()
