import mplfinance as mpf
import pandas as pd
import os

def generate_trade_chart(symbol, df, entry, tp, sl, side, open_ts=0):
    """
    Generates a candlestick chart with EMA, BB, RSI, and Green/Red R:R boxes.
    """
    df = df.copy()
    df.index = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 1. Calculate Indicators
    # EMA 200
    df["ema"] = df["close"].ewm(span=200, adjust=False).mean()
    # Bollinger Bands (20, 2)
    df["bb_mid"] = df["close"].rolling(window=20).mean()
    std = df["close"].rolling(window=20).std()
    df["bb_up"] = df["bb_mid"] + (2 * std)
    df["bb_low"] = df["bb_mid"] - (2 * std)
    # RSI (14)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))

    # 2. Define the R:R Box logic with 'where' mask
    start_time = pd.to_datetime(open_ts, unit='ms')
    where_mask = (df.index >= start_time)
    
    # 3. Setup Plots
    ap = [
        mpf.make_addplot(df["ema"], color='#2962FF', width=1.2), # EMA 200 (Blue)
        mpf.make_addplot(df[["bb_up", "bb_low"]], color='#26a69a', alpha=0.2, width=0.8), # BB (Greenish)
        mpf.make_addplot(df["rsi"], panel=1, color='#787b86', width=1, secondary_y=False) # RSI (Grey)
    ]

    style = mpf.make_mpf_style(base_mpf_style='charles', gridstyle='', facecolor='#161a1e', edgecolor='#2b2f36')
    
    filename = f"chart_{symbol.replace('/', '_')}.png"
    filepath = os.path.join(os.getcwd(), filename)
    
    # Create the lines for TP, SL, and Entry
    hlines_dict = dict(hlines=[tp, entry, sl], colors=['#26a69a', '#787b86', '#ef5350'], linestyle='--', linewidths=1.5)
    
    # Define the shaded boxes with the 'where' mask
    fb_tp = dict(y1=entry, y2=tp, where=where_mask, color='#26a69a', alpha=0.15)
    fb_sl = dict(y1=entry, y2=sl, where=where_mask, color='#ef5350', alpha=0.15)
    
    mpf.plot(df, type='candle', 
             style=style,
             title=f"\n{symbol} ({side}) - 15M Strategy Setup",
             ylabel='Price (USDT)',
             ylabel_lower='RSI',
             addplot=ap,
             hlines=hlines_dict,
             fill_between=[fb_tp, fb_sl],
             savefig=dict(fname=filepath, dpi=100, bbox_inches='tight'),
             volume=False,
             figratio=(16,10),
             figscale=1.2,
             panel_ratios=(6,2)) # RSI panel is smaller
             
    return filepath
