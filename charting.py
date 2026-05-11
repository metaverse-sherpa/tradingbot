import mplfinance as mpf
import pandas as pd
import os

def generate_trade_chart(symbol, df, entry, tp, sl, side, open_ts=0):
    """
    Generates a high-contrast Neon chart with clear indicators.
    """
    df = df.copy()
    df.index = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 1. Calculate Indicators
    df["ema"] = df["close"].ewm(span=200, adjust=False).mean()
    df["bb_mid"] = df["close"].rolling(window=20).mean()
    std = df["close"].rolling(window=20).std()
    df["bb_up"] = df["bb_mid"] + (2 * std)
    df["bb_low"] = df["bb_mid"] - (2 * std)

    # 2. Define the R:R Box logic
    start_time = pd.to_datetime(open_ts, unit='ms')
    where_mask = (df.index >= start_time)
    
    # 3. Vibrant Neon Addplots
    ap = [
        # EMA 200 (Bright Neon Yellow)
        mpf.make_addplot(df["ema"], color='#FFEB3B', width=1.8),
        # Bollinger Bands (Vibrant Cyan)
        mpf.make_addplot(df[["bb_up", "bb_low"]], color='#00E5FF', alpha=0.4, width=1.0)
    ]

    # Pro-Grade Dark Style
    style = mpf.make_mpf_style(
        base_mpf_style='charles', 
        gridstyle='', 
        facecolor='#121212', 
        edgecolor='#2b2f36',
        marketcolors=mpf.make_marketcolors(up='#00C853', down='#FF1744', inherit=True)
    )
    
    filename = f"chart_{symbol.replace('/', '_')}.png"
    filepath = os.path.join(os.getcwd(), filename)
    
    # Precise trade level lines
    hlines_dict = dict(hlines=[tp, entry, sl], colors=['#00C853', '#FFFFFF', '#FF1744'], linestyle='-', linewidths=1.2, alpha=0.6)
    
    # Shaded R:R Boxes
    fb_tp = dict(y1=entry, y2=tp, where=where_mask, color='#00C853', alpha=0.12)
    fb_sl = dict(y1=entry, y2=sl, where=where_mask, color='#FF1744', alpha=0.12)
    
    mpf.plot(df, type='candle', 
             style=style,
             title=f"\n{symbol} ({side}) - 15M Strategy Setup",
             ylabel='Price (USDT)',
             addplot=ap,
             hlines=hlines_dict,
             fill_between=[fb_tp, fb_sl],
             savefig=dict(fname=filepath, dpi=120, bbox_inches='tight'),
             volume=False,
             figratio=(16,9),
             figscale=1.3)
             
    return filepath
