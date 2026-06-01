import sqlite3
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Configuration
INITIAL_CASH = 10000.0
PCT_PER_TRADE = 0.02
LEVERAGE = 5  # Typical stock swing-trading leverage
FEE_RATE = 0.0006
SLIPPAGE = 0.0005
DB_PATH = "data/stock_daily_cache.db"

SYMBOLS = [
    # Technology & Megacap growth
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "AVGO", "TSM", "NFLX", "AMD", "QCOM", "ORCL", "CRM", "META", "ANET", "NOW",
    # Semiconductors & Tech Hardware
    "ASML", "MU", "LRCX", "PANW",
    # Financials & Tech Hardware
    "GS", "MS", "CSCO", "AXP",
    # Consumer Discretionary & Retail
    "WMT", "COST", "CMG", "TJX", "MELI",
    # Industrials & Infrastructure
    "GE", "CAT", "ETN", "URI", "PH",
    # Healthcare & Biotech
    "LLY", "JNJ", "VRTX", "ISRG",
    # Energy
    "XOM", "CVX", "COP"
]

# Baseline Valkyrie Parameters (can be optimized later)
VALKYRIE_PARAMS = {
    'bb_dev': 2.4, 
    'atr_mult': 3.5, 
    'rr': 1.0, 
    'adx_max': 30, 
    'rsi_low': 25, 
    'rsi_high': 75
}

def load_data(symbol):
    conn = sqlite3.connect(DB_PATH)
    query = f"SELECT * FROM StockDailyData WHERE symbol = '{symbol}' ORDER BY date ASC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    if df.empty: return None
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    return df

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

def find_trades(symbol: str, df: pd.DataFrame, p: dict) -> list:
    d = df.copy()
    d["ema200"] = ema(d["close"], 200)
    d["rsi"] = rsi(d["close"], 14)
    d["atr"] = atr(d, 14)
    d["adx"] = adx(d, 14)
    
    mid = d["close"].rolling(20).mean().values
    std = d["close"].rolling(20).std().values
    d["bb_up"] = mid + p["bb_dev"] * std
    d["bb_low"] = mid - p["bb_dev"] * std
    
    open_p = d["open"].values
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
            # Baseline constraints based on fully formed daily candle
            if pd.isna(bb_up[i]) or pd.isna(bb_low[i]):
                continue
                
            bandwidth = (bb_up[i] - bb_low[i]) / close[i]
            if bandwidth < 0.012:
                continue
            
            if adx_v[i] > p["adx_max"]:
                continue
                
            # LONG Signal -> Execute next morning open
            if close[i] > ema_v[i] and low[i] < bb_low[i] and close[i] >= bb_low[i] and rsi_v[i] < p["rsi_low"]:
                side = 1
                entry_price = open_p[i+1] * (1 + SLIPPAGE)  # Executed at open next day
                atr_dist = atr_v[i] * p["atr_mult"]         # Distance based on signal day ATR
                sl_price = entry_price - atr_dist
                tp_price = entry_price + (atr_dist * p["rr"])
                entry_time = times[i+1]
                in_trade = True
                
            # SHORT Signal -> Execute next morning open
            elif close[i] < ema_v[i] and high[i] > bb_up[i] and close[i] <= bb_up[i] and rsi_v[i] > p["rsi_high"]:
                side = -1
                entry_price = open_p[i+1] * (1 - SLIPPAGE)
                atr_dist = atr_v[i] * p["atr_mult"]
                sl_price = entry_price + atr_dist
                tp_price = entry_price - (atr_dist * p["rr"])
                entry_time = times[i+1]
                in_trade = True
        else:
            # Check for gap risk or intra-day SL/TP hit on the CURRENT day
            hit_sl = hit_tp = False
            exit_price = 0.0
            
            if side == 1:
                # Did it gap past our SL/TP overnight?
                if open_p[i] <= sl_price:
                    hit_sl = True
                    exit_price = open_p[i]
                elif open_p[i] >= tp_price:
                    hit_tp = True
                    exit_price = open_p[i]
                # Did it hit SL/TP intraday?
                elif low[i] <= sl_price:
                    hit_sl = True
                    exit_price = sl_price
                elif high[i] >= tp_price:
                    hit_tp = True
                    exit_price = tp_price
            else:
                if open_p[i] >= sl_price:
                    hit_sl = True
                    exit_price = open_p[i]
                elif open_p[i] <= tp_price:
                    hit_tp = True
                    exit_price = open_p[i]
                elif high[i] >= sl_price:
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
                cooldown = 1
                
    return trades

def run_stock_portfolio_backtest():
    all_trades = []
    print("=" * 80)
    print(" 🔮 RUNNING VALKYRIE STOCK PORTFOLIO BACKTEST (DAILY/1D)")
    print("=" * 80)
    
    for s in SYMBOLS:
        df = load_data(s)
        if df is None:
            print(f"❌ Missing data in DB for {s}")
            continue
            
        print(f"📊 Analyzing {s}...")
        trades = find_trades(s, df, VALKYRIE_PARAMS)
        all_trades.extend(trades)
        print(f"   Generated {len(trades)} trades for {s}")
        
    if not all_trades:
        print("❌ No trades generated.")
        return
        
    all_trades.sort(key=lambda x: x["entry_time"])
    
    cash = INITIAL_CASH
    equity_curve = [(all_trades[0]["entry_time"], cash)]
    wins = losses = 0
    max_eq = INITIAL_CASH
    max_dd = 0.0
    
    for t in all_trades:
        risk_amt = cash * PCT_PER_TRADE
        sl_pct = abs(t["sl_dist_pct"])
        
        position_size_usd = risk_amt / sl_pct if sl_pct > 0 else cash
        position_size_usd = min(position_size_usd, cash * LEVERAGE)
        position_units = position_size_usd / t["entry_price"]
        
        cash -= t["entry_price"] * position_units * FEE_RATE
        
        if t["win"]:
            trade_pnl = position_units * (t["exit_price"] - t["entry_price"]) * t["side"]
            exit_fee = t["exit_price"] * position_units * FEE_RATE
            wins += 1
        else:
            trade_pnl = position_units * (t["exit_price"] - t["entry_price"]) * t["side"]
            exit_fee = t["exit_price"] * position_units * FEE_RATE
            losses += 1
            
        cash += trade_pnl - exit_fee
        equity_curve.append((t["exit_time"], cash))
        
        if cash > max_eq:
            max_eq = cash
        else:
            dd = (max_eq - cash) / max_eq * 100
            if dd > max_dd:
                max_dd = dd
                
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0.0
    final_pnl_pct = ((cash - INITIAL_CASH) / INITIAL_CASH) * 100
    
    df_eq = pd.DataFrame(equity_curve, columns=["date", "equity"]).set_index("date")
    daily_returns = df_eq["equity"].resample('D').last().ffill().pct_change().dropna()
    if len(daily_returns) > 1:
        sharpe_ratio = (daily_returns.mean() / (daily_returns.std() + 1e-10)) * np.sqrt(252)
    else:
        sharpe_ratio = 0.0
        
    print("\n" + "=" * 80)
    print(" 🏆 VALKYRIE STOCK PORTFOLIO PERFORMANCE SCORECARD (1D)")
    print("=" * 80)
    print(f"Total Trades              : {total_trades}")
    print(f"Win Rate                  : {win_rate:.2f}%")
    print(f"Max Drawdown              : {max_dd:.2f}%")
    print(f"Cumulative PnL            : {final_pnl_pct:.2f}%")
    print(f"Sharpe Ratio              : {sharpe_ratio:.2f}")
    print("=" * 80)
    
    # Visualization
    dates = [x[0] for x in equity_curve]
    eq_values = [x[1] for x in equity_curve]
    peaks = np.maximum.accumulate(eq_values)
    dd_curve = -100 * (peaks - eq_values) / peaks
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]}, facecolor="#0B0E14")
    
    ax1.plot(dates, eq_values, color="#3cd7ff", linewidth=2.5, label="Valkyrie Daily Stocks")
    ax1.set_title(f"Valkyrie Stock Portfolio Backtest 1D ({len(SYMBOLS)} Symbols) | PnL: {final_pnl_pct:.1f}%", color="#FFFFFF", fontsize=16, fontweight='bold', pad=15)
    ax1.set_facecolor("#141A24")
    ax1.tick_params(colors="#FFFFFF")
    ax1.grid(True, color="#3a4b5c", alpha=0.3)
    ax1.set_ylabel("Portfolio Value ($)", color="#FFFFFF", fontsize=12)
    
    ax2.fill_between(dates, dd_curve, 0, color="#FF1744", alpha=0.3)
    ax2.plot(dates, dd_curve, color="#FF1744", linewidth=1.2)
    ax2.set_facecolor("#141A24")
    ax2.tick_params(colors="#FFFFFF")
    ax2.grid(True, color="#3a4b5c", alpha=0.3)
    ax2.set_ylabel("Drawdown (%)", color="#FFFFFF", fontsize=12)
    
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    
    plt.tight_layout()
    os.makedirs("results", exist_ok=True)
    out_path = "results/valkyrie_stock_daily_backtest.png"
    plt.savefig(out_path, dpi=180, facecolor="#0B0E14")
    plt.close()
    print(f"\n📈 Chart successfully saved to: {out_path}")

if __name__ == "__main__":
    run_stock_portfolio_backtest()
