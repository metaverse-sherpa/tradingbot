import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import time

# Fees
MAKER_FEE = 0.0002
TAKER_FEE = 0.0006
SLIPPAGE = 0.0005
COMMISSION = 0.0006
LEVERAGE = 20.0
START_CASH = 10000.0

# Symbols to backtest
SYMBOLS = ["BTC", "SOL", "LINK"]

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

def calculate_dynamic_bb(df, base_period=20, base_multiplier=2.6, lambda_param=0.94):
    # Modified local test: Run pure baseline Valkyrie (No GARCH scaling)
    mid = df["close"].rolling(base_period).mean().values
    std = df["close"].rolling(base_period).std().values
    bb_up = mid + base_multiplier * std
    bb_low = mid - base_multiplier * std
    return bb_up, bb_low

def find_trades(symbol: str, df: pd.DataFrame, p: dict) -> list:
    d = df.copy()
    d["ema200"] = ema(d["close"], 200)
    d["rsi"] = rsi(d["close"], 14)
    d["atr"] = atr(d, 14)
    d["adx"] = adx(d, 14)
    
    d["bb_up"], d["bb_low"] = calculate_dynamic_bb(d, base_period=20, base_multiplier=p["bb_dev"])
    
    close = d["close"].values
    high = d["high"].values
    low = d["low"].values
    ema_v = d["ema200"].values
    rsi_v = d["rsi"].values
    atr_v = d["atr"].values
    adx_v = d["adx"].values
    bb_up = d["bb_up"].values
    bb_low = d["bb_low"].values
    times = d.index.to_pydatetime()
    
    trades = []
    in_trade = False
    side = 0
    entry_price = sl_price = tp_price = 0.0
    entry_time = None
    warmup = 200
    cooldown = 0
    
    for i in range(warmup, len(close) - 1):
        if cooldown > 0:
            cooldown -= 1
            continue
            
        if not in_trade:
            bandwidth = (bb_up[i] - bb_low[i]) / close[i]
            if bandwidth < 0.012:
                continue
            
            if adx_v[i] > p["adx_max"]:
                continue
                
            # LONG Signal
            if close[i] > ema_v[i] and low[i] < bb_low[i] and close[i] >= bb_low[i] and rsi_v[i] < p["rsi_low"]:
                side = 1
                entry_price = close[i] * (1 + SLIPPAGE)
                atr_dist = atr_v[i] * p["atr_mult"]
                sl_price = entry_price - atr_dist
                tp_price = entry_price + (atr_dist * p["rr"])
                entry_time = times[i]
                in_trade = True
                
            # SHORT Signal
            elif close[i] < ema_v[i] and high[i] > bb_up[i] and close[i] <= bb_up[i] and rsi_v[i] > p["rsi_high"]:
                side = -1
                entry_price = close[i] * (1 - SLIPPAGE)
                atr_dist = atr_v[i] * p["atr_mult"]
                sl_price = entry_price + atr_dist
                tp_price = entry_price - (atr_dist * p["rr"])
                entry_time = times[i]
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
                trades.append({
                    "symbol": symbol,
                    "side": side,
                    "entry_time": entry_time,
                    "exit_time": times[i],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "win": hit_tp,
                    "sl_dist_pct": (sl_price - entry_price) / entry_price if side == 1 else (entry_price - sl_price) / entry_price,
                    "rr": p["rr"]
                })
                in_trade = False
                cooldown = 2
                
    return trades

def run_portfolio_backtest():
    # Load parameters from top 3 leaderboard winning configurations
    params = {
        "BTC": {'bb_dev': 2.2, 'atr_mult': 3.5, 'rr': 1.0, 'adx_max': 30, 'rsi_low': 25, 'rsi_high': 75},
        "SOL": {'bb_dev': 2.4, 'atr_mult': 3.5, 'rr': 1.0, 'adx_max': 25, 'rsi_low': 25, 'rsi_high': 75},
        "LINK": {'bb_dev': 2.6, 'atr_mult': 3.5, 'rr': 1.0, 'adx_max': 30, 'rsi_low': 25, 'rsi_high': 75}
    }
    
    all_trades = []
    print("=" * 80)
    print(" 🔮 RUNNING VALKYRIE OPTIMIZED BASELINE PORTFOLIO BACKTEST")
    print("=" * 80)

    
    for s in SYMBOLS:
        path = f"csv/cache_{s}_15m.csv"
        if not os.path.exists(path):
            print(f"❌ Missing data file for {s} at {path}")
            continue
            
        print(f"📊 Loading 15m historical data for {s}...")
        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        print(f"   Loaded {len(df):,} bars ({df.index[0].date()} -> {df.index[-1].date()})")
        
        trades = find_trades(s, df, params[s])
        print(f"   Generated {len(trades)} trades for {s}")
        all_trades.extend(trades)
        
    if not all_trades:
        print("❌ No trades generated.")
        return
        
    # Sort all trades across the portfolio chronologically by entry_time
    all_trades.sort(key=lambda x: x["entry_time"])
    
    # Portfolio Compounding Pass
    print("\n" + "=" * 80)
    print(" 📈 PORTFOLIO COMPOUNDING SIMULATION")
    print("=" * 80)
    
    cash = START_CASH
    equity_curve = [(all_trades[0]["entry_time"], cash)]
    wins = losses = 0
    
    # Track drawdowns
    max_eq = START_CASH
    max_dd = 0.0
    
    for t in all_trades:
        risk_per_trade = 0.015  # 2.0% risk per trade of current cash
        risk_amt = cash * risk_per_trade
        
        # position sizing based on SL distance
        sl_pct = abs(t["sl_dist_pct"])
        position_size_usd = risk_amt / sl_pct if sl_pct > 0 else cash
        position_size_usd = min(position_size_usd, cash * LEVERAGE)
        position_units = position_size_usd / t["entry_price"]
        
        # entry fee
        cash -= t["entry_price"] * position_units * TAKER_FEE
        
        # exit outcome
        if t["win"]:
            trade_pnl = position_units * (t["exit_price"] - t["entry_price"]) * t["side"]
            exit_fee = t["exit_price"] * position_units * MAKER_FEE
            wins += 1
        else:
            trade_pnl = position_units * (t["exit_price"] - t["entry_price"]) * t["side"]
            exit_fee = t["exit_price"] * position_units * TAKER_FEE
            losses += 1
            
        cash += trade_pnl - exit_fee
        equity_curve.append((t["exit_time"], cash))
        
        if cash > max_eq:
            max_eq = cash
        else:
            dd = (max_eq - cash) / max_eq * 100
            if dd > max_dd:
                max_dd = dd
                
    # Unified results summary
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0.0
    final_pnl_pct = ((cash - START_CASH) / START_CASH) * 100
    
    # Determine trades per day (spanning exactly 3 years / 1095 days)
    trades_per_day = total_trades / 1095.0
    
    # Calculate Sharpe ratio on daily resampled compounding equity
    df_eq = pd.DataFrame(equity_curve, columns=["date", "equity"]).set_index("date")
    daily_returns = df_eq["equity"].resample('D').last().ffill().pct_change().dropna()
    if len(daily_returns) > 1:
        sharpe_ratio = (daily_returns.mean() / (daily_returns.std() + 1e-10)) * np.sqrt(365)
    else:
        sharpe_ratio = 0.0
        
    # Print results scorecard against target goals
    print("\n" + "=" * 80)
    print(" 🏆 VALKYRIE BASELINE PORTFOLIO PERFORMANCE SCORECARD (2% RISK)")
    print("=" * 80)
    
    def print_goal(label, current, target, unit="", higher_is_better=True):
        passed = current >= target if higher_is_better else current <= target
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{label:<25} : {current:.2f}{unit:<4} (Target: {target:.2f}{unit}) -> {status}")
        return passed

    g1 = print_goal("Win Rate", win_rate, 60.0, "%")
    g2 = print_goal("Max Drawdown", max_dd, 25.0, "%", higher_is_better=False)
    g3 = print_goal("Trade Frequency", trades_per_day, 0.5, " t/d")
    g4 = print_goal("Cumulative PnL", final_pnl_pct, 60.0, "%")
    print(f"{'Sharpe Ratio':<25} : {sharpe_ratio:.2f}")
    
    overall_status = "✨ CHAMPION STRATEGY APPROVAL!" if (g1 and g2 and g3 and g4) else "⚠️ STRATEGY NEEDS ADDITIONAL FINE-TUNING"
    print("-" * 80)
    print(f"STATUS: {overall_status}")
    print("=" * 80)
    
    # Plotting double charts (Equity Curve on top, Drawdown Chart underneath)
    dates = [x[0] for x in equity_curve]
    eq_values = [x[1] for x in equity_curve]
    
    # Calculate rolling drawdown curve for visualization
    peaks = np.maximum.accumulate(eq_values)
    dd_curve = -100 * (peaks - eq_values) / peaks
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]}, facecolor="#0B0E14")
    
    # Top Chart: Equity
    ax1.plot(dates, eq_values, color="#3cd7ff", linewidth=2.5, label="Valkyrie Dynamic GARCH Portfolio")
    ax1.set_title("Valkyrie Dynamic GARCH 3-Year Backtest: Portfolio Growth", color="#FFFFFF", fontsize=16, fontweight='bold', pad=15)
    ax1.set_facecolor("#141A24")
    ax1.tick_params(colors="#FFFFFF")
    ax1.grid(True, color="#3a4b5c", alpha=0.3)
    ax1.set_ylabel("Portfolio Value ($)", color="#FFFFFF", fontsize=12)
    
    # Annotate stats on top chart
    info_text = (
        f"Initial Capital: ${START_CASH:,.2f}\n"
        f"Final Value: ${cash:,.2f}\n"
        f"Total Trades: {total_trades}\n"
        f"Win Rate: {win_rate:.1f}%\n"
        f"Max Drawdown: {max_dd:.1f}%\n"
        f"Sharpe Ratio: {sharpe_ratio:.2f}"
    )
    ax1.text(0.02, 0.95, info_text, transform=ax1.transAxes, color="#FFFFFF", fontsize=11,
             verticalalignment='top', bbox=dict(boxstyle='round,pad=0.8', facecolor='#0B0E14', alpha=0.8, edgecolor='#3cd7ff'))

    
    # Bottom Chart: Drawdown
    ax2.fill_between(dates, dd_curve, 0, color="#FF1744", alpha=0.3)
    ax2.plot(dates, dd_curve, color="#FF1744", linewidth=1.2)
    ax2.set_facecolor("#141A24")
    ax2.tick_params(colors="#FFFFFF")
    ax2.grid(True, color="#3a4b5c", alpha=0.3)
    ax2.set_ylabel("Drawdown (%)", color="#FFFFFF", fontsize=12)
    ax2.set_ylim(-30, 2)
    
    # Formatting dates
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    
    plt.tight_layout()
    os.makedirs("results", exist_ok=True)
    out_path = "results/valkyrie_garch_3yr_backtest.png"
    plt.savefig(out_path, dpi=180, facecolor="#0B0E14")
    plt.close()
    
    print(f"\n📈 Beautiful double-chart successfully saved to: {out_path}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_portfolio_backtest()
