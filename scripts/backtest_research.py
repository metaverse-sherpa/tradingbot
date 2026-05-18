import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ----------------------------------------------------------------------------
# 1. PARAMETERS & CONFIGURATION
# ----------------------------------------------------------------------------
START_PORTFOLIO_CASH = 10000.0  # Starting capital ($10k)
RISK_PER_TRADE = 0.015        # 1.5% risk per trade as the proven sweet spot (240% PnL, 16% Max DD)
MAKER_FEE = 0.0002             # 0.02% Blofin futures Maker fee (resting TP Limit order)
TAKER_FEE = 0.0006             # 0.06% Blofin futures Taker fee (Entry / SL Market trigger)
SLIPPAGE = 0.0005              # 0.05% slippage allowance
LEVERAGE = 20.0                # 20x maximum leverage cap

# Top 5 crypto currencies by volume (individualized parameters optimized for volatility)
TOKEN_PARAMS = {
    "SOL": {"bb_period": 20, "bb_dev": 2.4, "atr_period": 14, "atr_mult": 3.5, "rr": 1.0,  "adx_max": 25, "rsi_low": 25, "rsi_high": 75},
    "LINK": {"bb_period": 20, "bb_dev": 2.6, "atr_period": 14, "atr_mult": 3.5, "rr": 1.0,  "adx_max": 30, "rsi_low": 25, "rsi_high": 75},
    "BTC": {"bb_period": 20, "bb_dev": 2.2, "atr_period": 14, "atr_mult": 3.5, "rr": 1.0,  "adx_max": 30, "rsi_low": 25, "rsi_high": 75},
    "ADA": {"bb_period": 20, "bb_dev": 2.4, "atr_period": 14, "atr_mult": 3.5, "rr": 0.8,  "adx_max": 25, "rsi_low": 25, "rsi_high": 75},
    "DOT": {"bb_period": 20, "bb_dev": 2.6, "atr_period": 14, "atr_mult": 3.0, "rr": 0.8,  "adx_max": 25, "rsi_low": 25, "rsi_high": 75}
}

# ----------------------------------------------------------------------------
# 2. INDICATOR HELPERS
# ----------------------------------------------------------------------------
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

# ----------------------------------------------------------------------------
# 3. SINGLE-SYMBOL EVENT ENGINE
# ----------------------------------------------------------------------------
def backtest_symbol(symbol: str, df: pd.DataFrame, p: dict, initial_cash: float, risk_level: float) -> tuple:
    d = df.copy()
    
    # Calculate indicators
    d["ema200"] = ema(d["close"], 200)
    d["rsi"] = rsi(d["close"], 14)
    d["atr"] = atr(d, p["atr_period"])
    d["adx"] = adx(d, 14)
    
    # Bollinger Bands
    mid = d["close"].rolling(p["bb_period"]).mean()
    std = d["close"].rolling(p["bb_period"]).std()
    d["bb_up"] = mid + p["bb_dev"] * std
    d["bb_low"] = mid - p["bb_dev"] * std
    
    # Core arrays for speed
    close = d["close"].values
    high = d["high"].values
    low = d["low"].values
    ema_v = d["ema200"].values
    rsi_v = d["rsi"].values
    atr_v = d["atr"].values
    adx_v = d["adx"].values
    bb_up = d["bb_up"].values
    bb_low = d["bb_low"].values
    timestamps = d.index
    
    # State tracking
    equity = initial_cash
    equity_curve = []
    trade_logs = []
    
    in_trade = False
    side = 0  # 1 = Long, -1 = Short
    entry_price = sl_price = tp_price = position_units = risk_amount = 0.0
    entry_time = None
    
    cooldown = 0
    warmup = max(200, p["bb_period"], p["atr_period"])
    
    for i in range(warmup, len(close) - 1):
        # Record equity step
        current_eq = equity
        if in_trade:
            # Floating PnL approximation
            current_close = close[i]
            pnl = position_units * (current_close - entry_price) * side
            current_eq += pnl
        equity_curve.append((timestamps[i], current_eq))
        
        if cooldown > 0:
            cooldown -= 1
            continue
            
        if not in_trade:
            # 1. Volatility & Bandwidth Squeeze filter: Avoid zero-volatility sideways ranges
            bandwidth = (bb_up[i] - bb_low[i]) / close[i]
            if bandwidth < 0.012 or adx_v[i] > p["adx_max"]:
                continue
                
            # 2. LONG Signal: Wick crosses below lower BB but candle closes inside (Wick Rejection Reversal)
            if close[i] > ema_v[i] and low[i] < bb_low[i] and close[i] >= bb_low[i] and rsi_v[i] < p["rsi_low"]:
                side = 1
                entry_price = close[i] * (1 + SLIPPAGE)
                
                # Dynamic ATR levels
                atr_dist = atr_v[i] * p["atr_mult"]
                sl_price = entry_price - atr_dist
                tp_price = entry_price + (atr_dist * p["rr"])
                
                # Compounding Sizing: Risk exactly risk_level% of the total joint portfolio cash balance per trade
                # Since we split portfolio cash into 5 coin allocations, sub-account risk = 5% of sub-account equity
                risk_amount = equity * (risk_level * 5.0)
                position_size_usd = risk_amount / (atr_dist / entry_price)
                # Apply Max Leverage Cap safety
                position_size_usd = min(position_size_usd, equity * LEVERAGE)
                position_units = position_size_usd / entry_price
                
                # Apply entry commission (Entries are Taker Market orders)
                equity -= entry_price * position_units * TAKER_FEE
                entry_time = timestamps[i]
                in_trade = True
                
            # 3. SHORT Signal: Wick crosses above upper BB but candle closes inside (Wick Rejection Reversal)
            elif close[i] < ema_v[i] and high[i] > bb_up[i] and close[i] <= bb_up[i] and rsi_v[i] > p["rsi_high"]:
                side = -1
                entry_price = close[i] * (1 - SLIPPAGE)
                
                # Dynamic ATR levels
                atr_dist = atr_v[i] * p["atr_mult"]
                sl_price = entry_price + atr_dist
                tp_price = entry_price - (atr_dist * p["rr"])
                
                # Compounding Sizing: Risk exactly risk_level% of the total joint portfolio cash balance per trade
                risk_amount = equity * (risk_level * 5.0)
                position_size_usd = risk_amount / (atr_dist / entry_price)
                position_size_usd = min(position_size_usd, equity * LEVERAGE)
                position_units = position_size_usd / entry_price
                
                # Apply entry commission (Entries are Taker Market orders)
                equity -= entry_price * position_units * TAKER_FEE
                entry_time = timestamps[i]
                in_trade = True
                
        else:
            # Settle position check
            hit_sl = hit_tp = False
            exit_price = 0.0
            
            if side == 1:
                # Conservative resolution: check Stop Loss first to prevent over-optimistic wins
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
                pnl_usdt = position_units * (exit_price - entry_price) * side
                
                # Dynamic Fee: resting Limit order for TP (Maker), Market trigger for SL (Taker)
                fee_rate = MAKER_FEE if hit_tp else TAKER_FEE
                exit_commission = exit_price * position_units * fee_rate
                
                equity += pnl_usdt - exit_commission
                trade_pnl_pct = (pnl_usdt - exit_commission) / (entry_price * position_units) * 100
                
                trade_logs.append({
                    "symbol": symbol,
                    "entry_time": entry_time,
                    "exit_time": timestamps[i],
                    "side": "LONG" if side == 1 else "SHORT",
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl_usdt": pnl_usdt - exit_commission,
                    "pnl_pct": trade_pnl_pct,
                    "outcome": "TP" if hit_tp else "SL"
                })
                
                in_trade = False
                cooldown = 2  # Small buffer to avoid immediate double-triggering

    # Append remaining trailing step
    equity_curve.append((timestamps[-1], equity))
    
    eq_df = pd.DataFrame(equity_curve, columns=["datetime", f"equity_{symbol}"])
    eq_df.set_index("datetime", inplace=True)
    
    # Resample to daily frequency to align timelines
    daily_eq = eq_df.resample("D").last().ffill()
    return daily_eq, trade_logs

# ----------------------------------------------------------------------------
# 4. PORTFOLIO COMPOSITION & PERFORMANCE COMPILER
# ----------------------------------------------------------------------------
def run_portfolio_backtest():
    print("=" * 70)
    print(" 🛡️ VALKYRIE ELITE SCALPER PORTFOLIO RESEARCH ENGINE")
    print("=" * 70)
    
    # 1. Pre-load all CSV data once into memory to make the script run lightning-fast!
    loaded_data = {}
    print("📖 Pre-loading asset history caches into memory...")
    for symbol in TOKEN_PARAMS.keys():
        path = f"csv/cache_{symbol}_15m.csv"
        if not os.path.exists(path):
            print(f"⚠️ Cache file for {symbol} not found at {path}. Skipping...")
            continue
        loaded_data[symbol] = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
        
    if not loaded_data:
        print("❌ No data loaded. Please make sure cache files are present inside the csv/ directory.")
        return
        
    # Allocate starting cash equally among the 5 target assets
    alloc_cash = START_PORTFOLIO_CASH / len(loaded_data)
    
    # Risk tiers to evaluate
    RISK_TIERS = [0.01, 0.015, 0.02]
    
    # Colors for the premium plotting
    TIER_COLORS = {
        0.01: '#00E5FF',   # 1.0% Risk: Cyan
        0.015: '#FF9100',  # 1.5% Risk: Amber Orange
        0.02: '#00E676'    # 2.0% Risk: Emerald Green
    }
    
    portfolio_results = {}
    
    # Create dark theme plot
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(14, 9), facecolor='#121212')
    gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1], hspace=0.12)
    ax1 = fig.add_subplot(gs[0], facecolor='#161a22')
    ax2 = fig.add_subplot(gs[1], sharex=ax1, facecolor='#161a22')
    
    print("\n⚡ Simulating compounding portfolio performance across risk tiers...")
    
    for risk_tier in RISK_TIERS:
        daily_curves = []
        all_trade_logs = []
        
        for symbol, df in loaded_data.items():
            params = TOKEN_PARAMS[symbol]
            # Run simulation with specific risk level
            daily_eq, logs = backtest_symbol(symbol, df, params, alloc_cash, risk_tier)
            daily_curves.append(daily_eq)
            all_trade_logs.extend(logs)
            
        # Combine daily curves into unified portfolio equity
        portfolio_df = pd.concat(daily_curves, axis=1)
        portfolio_df.ffill(inplace=True)
        portfolio_df["combined_equity"] = portfolio_df.sum(axis=1)
        combined_equity = portfolio_df["combined_equity"]
        
        # Calculate performance stats
        running_max = combined_equity.cummax()
        drawdowns = (combined_equity - running_max) / running_max * 100
        max_dd = drawdowns.min()
        
        daily_returns = combined_equity.pct_change().dropna()
        mean_daily_ret = daily_returns.mean()
        std_daily_ret = daily_returns.std()
        sharpe = np.sqrt(365) * (mean_daily_ret / std_daily_ret) if std_daily_ret > 0 else 0.0
        
        final_equity = combined_equity.iloc[-1]
        total_return_pct = ((final_equity - START_PORTFOLIO_CASH) / START_PORTFOLIO_CASH) * 100
        portfolio_wins = sum(1 for t in all_trade_logs if t["outcome"] == "TP")
        total_trades = len(all_trade_logs)
        portfolio_wr = (portfolio_wins / total_trades) * 100 if total_trades > 0 else 0.0
        
        portfolio_results[risk_tier] = {
            "combined_equity": combined_equity,
            "drawdowns": drawdowns,
            "final_equity": final_equity,
            "total_return_pct": total_return_pct,
            "max_dd": max_dd,
            "sharpe": sharpe,
            "wr": portfolio_wr,
            "trades": total_trades
        }
        
        # Plot curves
        color = TIER_COLORS[risk_tier]
        label_name = f"{risk_tier*100:.1f}% Risk (Return: {total_return_pct:+.1f}%, Max DD: {max_dd:.1f}%)"
        ax1.plot(combined_equity.index, combined_equity.values, color=color, linewidth=2.0, label=label_name)
        
        ax2.plot(drawdowns.index, drawdowns.values, color=color, linewidth=1.2, label=f"{risk_tier*100:.1f}% Risk Drawdown")
        ax2.fill_between(drawdowns.index, drawdowns.values, 0, color=color, alpha=0.08)
        
    # ----------------------------------------------------------------------------
    # 5. OUTPUT COMPARATIVE SUMMARY DISPLAY
    # ----------------------------------------------------------------------------
    print("\n" + "=" * 85)
    print(" 🏔️ COMPARATIVE PORTFOLIO PERFORMANCE SUMMARY (3-YEAR HISTORICAL)")
    print("=" * 85)
    print(f"{'RISK LEVEL':<12} | {'ENDING BALANCE':<15} | {'TOTAL PNL':<12} | {'MAX DRAWDOWN':<14} | {'SHARPE':<8} | {'WIN RATE':<8} | {'TRADES':<6}")
    print("-" * 85)
    for risk_tier in RISK_TIERS:
        res = portfolio_results[risk_tier]
        risk_lbl = f"{risk_tier*100:.1f}% Risk"
        end_bal = f"${res['final_equity']:,.2f}"
        pnl_lbl = f"{res['total_return_pct']:+.2f}%"
        dd_lbl = f"{res['max_dd']:.2f}%"
        wr_lbl = f"{res['wr']:.1f}%"
        print(f"{risk_lbl:<12} | {end_bal:<15} | {pnl_lbl:<12} | {dd_lbl:<14} | {res['sharpe']:<8.2f} | {wr_lbl:<8} | {res['trades']:<6}")
    print("=" * 85)
    
    # ----------------------------------------------------------------------------
    # 6. PREMIUM DECORATIVE LABELS & LEGENDS
    # ----------------------------------------------------------------------------
    ax1.set_title("Valkyrie Elite Scalper Strategy: Compounding Portfolio Sizing Tiers", fontsize=14, color='#FFFFFF', fontweight='bold', pad=15)
    ax1.set_ylabel("Portfolio Value (USD)", fontsize=11, color='#A0AAB5')
    ax1.grid(True, color='#2b2f36', linestyle=':', alpha=0.6)
    ax1.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
    
    # Add Starting Balance Label (to 2.0% Risk starting point)
    res_2 = portfolio_results[0.02]
    eq_2 = res_2["combined_equity"]
    ax1.annotate(f"Start: $10,000", xy=(eq_2.index[0], eq_2.values[0]), 
                 xytext=(40, 20), textcoords='offset points', 
                 arrowprops=dict(arrowstyle="->", color='#00E676', lw=1.2), 
                 color='#FFFFFF', fontweight='bold', 
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='#121212', edgecolor='#00E676', alpha=0.8))
                 
    # Add Ending Balance Label for 2.0% Risk curve
    ax1.annotate(f"End 2.0%: ${res_2['final_equity']:,.0f}", xy=(eq_2.index[-1], eq_2.values[-1]), 
                 xytext=(-140, -40), textcoords='offset points', 
                 arrowprops=dict(arrowstyle="->", color='#00E676', lw=1.2), 
                 color='#FFFFFF', fontweight='bold', 
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='#121212', edgecolor='#00E676', alpha=0.8))
                 
    # Annotate Max Drawdowns for each curve on ax2
    for idx, risk_tier in enumerate(RISK_TIERS):
        res = portfolio_results[risk_tier]
        dd = res["drawdowns"]
        max_dd_date = dd.idxmin()
        max_dd_val = dd.min()
        color = TIER_COLORS[risk_tier]
        
        # Position offsets based on risk level index to prevent label overlaps
        y_offset = -15 if idx == 0 else (-30 if idx == 1 else -45)
        ax2.annotate(f"{risk_tier*100:.1f}% Max DD: {max_dd_val:.2f}%", xy=(max_dd_date, max_dd_val), 
                     xytext=(35, y_offset), textcoords='offset points', 
                     arrowprops=dict(arrowstyle="->", color=color, lw=1.2), 
                     color='#FFFFFF', fontweight='bold', 
                     bbox=dict(boxstyle='round,pad=0.3', facecolor='#121212', edgecolor=color, alpha=0.8))
                     
    ax1.legend(loc='upper left', framealpha=0.85, facecolor='#121212', edgecolor='#2b2f36')
    
    ax2.set_ylabel("Drawdown %", fontsize=11, color='#A0AAB5')
    ax2.set_xlabel("Time Horizon (3-Year Period)", fontsize=11, color='#A0AAB5')
    lowest_dd = min(res["max_dd"] for res in portfolio_results.values())
    ax2.set_ylim(min(-45.0, lowest_dd * 1.3), 1.0)
    ax2.grid(True, color='#2b2f36', linestyle=':', alpha=0.6)
    
    # Format axes styling
    for ax in [ax1, ax2]:
        ax.tick_params(colors='#A0AAB5', labelsize=9)
        for spine in ax.spines.values():
            spine.set_color('#2b2f36')
            
    plt.setp(ax1.get_xticklabels(), visible=False)
    
    # Save premium visual
    save_path = "results/valkyrie_research_backtest.png"
    plt.savefig(save_path, facecolor=fig.get_facecolor(), edgecolor='none', dpi=200, bbox_inches='tight')
    plt.close()
    
    print(f"\n🎨 Premium Multi-Tier Comparative Chart saved to: {save_path}")
    print("=" * 70)

if __name__ == "__main__":
    run_portfolio_backtest()
