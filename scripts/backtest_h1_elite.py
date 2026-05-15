"""
H1/M4 'Elite Crypto' Backtest
-----------------------------
Migrating the 'Elite 60% Club' logic to the Crypto Fleet.
Timeframe: H1 (1 Hour)
Indicator: Supertrend (10, 4) + 200 EMA
"""

import pandas as pd
import numpy as np
import os
import time

CSV_DIR = "csv"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Elite Parameters (Conservative 1% Audit)
# ---------------------------------------------------------------------------
ST_PERIOD      = 10
ST_MULTIPLIERS = [5.0] # Locked to the Crypto Golden Ratio
EMA_PERIOD     = 200
COMMISSION     = 0.0006 
SLIPPAGE       = 0.0005
START_CASH     = 10_000.0
RISK_PER_TRADE = 0.01  # Updated to 1% as requested
LEVERAGE       = 10.0

# 🚀 Full Fleet Expansion
SYMBOLS = [
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", 
    "DOT", "LTC", "TON", "ZEC", "PEPE", "BNB", "NEAR", "SUI", 
    "NOT", "TAO", "ONDO", "ENA", "FET", "WIF", "SHIB", "TRX"
]

def calculate_supertrend(df, period=10, multiplier=4):
    df = df.copy()
    hl2 = (df['high'] + df['low']) / 2
    # ATR calculation
    tr = pd.concat([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    f_up  = hl2 + (multiplier * atr)
    f_low = hl2 - (multiplier * atr)
    st = [True] * len(df)
    
    # Supertrend loop
    for i in range(1, len(df)):
        if df['close'].iloc[i-1] > f_low.iloc[i-1]:
            f_low.iloc[i] = max(f_low.iloc[i], f_low.iloc[i-1])
        if df['close'].iloc[i-1] < f_up.iloc[i-1]:
            f_up.iloc[i] = min(f_up.iloc[i], f_up.iloc[i-1])
            
        if df['close'].iloc[i] > f_up.iloc[i]:
            st[i] = True
        elif df['close'].iloc[i] < f_low.iloc[i]:
            st[i] = False
        else:
            st[i] = st[i-1]
            
    df['supertrend'] = st
    return df

def simulate(df: pd.DataFrame, symbol: str) -> dict:
    # 1. Resample to H1
    h1 = df.resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()
    
    # 2. Indicators
    h1['ema_200'] = h1['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    h1 = calculate_supertrend(h1, ST_PERIOD, ST_MULT)
    
    close = h1['close'].values
    st_v  = h1['supertrend'].values
    ema_v = h1['ema_200'].values
    n = len(h1)
    
    equity = START_CASH; wins = losses = 0; in_trade = False; side = 0; entry_px = 0.0
    warmup = 200

    for i in range(warmup, n - 1):
        if not in_trade:
            # LONG: Supertrend turns Green + Price > EMA 200
            if st_v[i] and not st_v[i-1] and close[i] > ema_v[i]:
                side = 1; entry_px = close[i] * (1 + SLIPPAGE)
                notional = equity * RISK_PER_TRADE * LEVERAGE
                equity -= notional * COMMISSION
                in_trade = True
            
            # SHORT: Supertrend turns Red + Price < EMA 200
            elif not st_v[i] and st_v[i-1] and close[i] < ema_v[i]:
                side = -1; entry_px = close[i] * (1 - SLIPPAGE)
                notional = equity * RISK_PER_TRADE * LEVERAGE
                equity -= notional * COMMISSION
                in_trade = True
        
        else:
            # EXIT on Supertrend Flip
            exit_px = 0.0
            if (side == 1 and not st_v[i]) or (side == -1 and st_v[i]):
                exit_px = close[i] * (1 - SLIPPAGE if side == 1 else 1 + SLIPPAGE)
                pnl_pct = (exit_px - entry_px) / entry_px if side == 1 else (entry_px - exit_px) / entry_px
                pnl = notional * pnl_pct
                equity += pnl - (notional * COMMISSION)
                if pnl > 0: wins += 1
                else: losses += 1
                in_trade = False

    total = wins + losses
    if total == 0: return {"trades": 0}
    return {
        "wr": wins/total*100, 
        "pnl_pct": (equity - START_CASH)/START_CASH*100, 
        "trades": total,
        "final_balance": equity
    }

def run():
    print("="*80)
    print(" 🌍 H1 'ELITE CRYPTO' FLEET AUDIT (Sweep: Mult 3.0 -> 6.0)")
    print("="*80)
    
    for mult in ST_MULTIPLIERS:
        print(f"\n🚀 Testing Multiplier: {mult}")
        print(f"{'Symbol':<8} {'WR':>6} {'PnL':>9} {'Trades':>7} {'Final Balance'}")
        print("-" * 60)
        
        for s in SYMBOLS:
            csv_path = f"csv/cache_{s}_15m.csv"
            if not os.path.exists(csv_path): continue
            df = pd.read_csv(csv_path, parse_dates=['datetime'], index_col='datetime')
            
            # 🏔️ Simulation with Dynamic Multiplier
            # Resample & Indicators inside simulate
            h1 = df.resample('1h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
            h1['ema_200'] = h1['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
            h1 = calculate_supertrend(h1, ST_PERIOD, mult)
            
            # Simple simulate function adapted for local vars
            close = h1['close'].values; st_v = h1['supertrend'].values; ema_v = h1['ema_200'].values
            equity = START_CASH; wins = losses = 0; in_trade = False; side = 0; entry_px = 0.0
            for i in range(200, len(h1) - 1):
                if not in_trade:
                    if st_v[i] and not st_v[i-1] and close[i] > ema_v[i]:
                        side = 1; entry_px = close[i] * (1 + SLIPPAGE); notional = equity * RISK_PER_TRADE * LEVERAGE; equity -= notional * COMMISSION; in_trade = True
                    elif not st_v[i] and st_v[i-1] and close[i] < ema_v[i]:
                        side = -1; entry_px = close[i] * (1 - SLIPPAGE); notional = equity * RISK_PER_TRADE * LEVERAGE; equity -= notional * COMMISSION; in_trade = True
                else:
                    if (side == 1 and not st_v[i]) or (side == -1 and st_v[i]):
                        exit_px = close[i] * (1 - SLIPPAGE if side == 1 else 1 + SLIPPAGE)
                        pnl_pct = (exit_px - entry_px) / entry_px if side == 1 else (entry_px - exit_px) / entry_px
                        pnl = notional * pnl_pct
                        equity += pnl - (notional * COMMISSION)
                        if pnl > 0: wins += 1
                        else: losses += 1
                        in_trade = False
            
            total = wins + losses
            if total > 0:
                print(f"{s:<8} {wins/total*100:>5.1f}% {((equity-START_CASH)/START_CASH*100):>+8.1f}% {total:>7} ${equity:,.2f}")

if __name__ == "__main__":
    run()
