import mplfinance as mpf
import pandas as pd
import numpy as np
import os

def generate_trade_chart(symbol, df, entry, tp, sl, side, open_ts=0):
    """
    Generates a high-contrast Neon chart where TP/SL/Entry lines only start from open_ts.
    """
    df = df.copy()
    df.index = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 1. Calculate Indicators
    df["ema"] = df["close"].ewm(span=200, adjust=False).mean()
    df["bb_mid"] = df["close"].rolling(window=20).mean()
    std = df["close"].rolling(window=20).std()
    df["bb_up"] = df["bb_mid"] + (2 * std)
    df["bb_low"] = df["bb_mid"] - (2 * std)

    # 2. Define the R:R lines logic (Only start from open_ts)
    start_time = pd.to_datetime(open_ts, unit='ms')
    where_mask = (df.index >= start_time)
    
    # Create price level series that are NaN before start_time
    tp_line = pd.Series(np.nan, index=df.index)
    entry_line = pd.Series(np.nan, index=df.index)
    sl_line = pd.Series(np.nan, index=df.index)
    
    tp_line.loc[where_mask] = tp
    entry_line.loc[where_mask] = entry
    sl_line.loc[where_mask] = sl
    
    # 3. Vibrant Neon Addplots
    ap = [
        
        # Bollinger Bands - Upper/Lower (Vibrant Cyan, thicker)
        mpf.make_addplot(df["bb_up"], color='#00E5FF', alpha=0.5, width=1.2),
        mpf.make_addplot(df["bb_low"], color='#00E5FF', alpha=0.5, width=1.2),
        # Bollinger Mid (Subtle Dashed Cyan)
        mpf.make_addplot(df["bb_mid"], color='#00E5FF', alpha=0.3, width=0.8, linestyle='--'),
        
        # TP Line (Neon Green) - Only starts from trade open
        mpf.make_addplot(tp_line, color='#00C853', width=1.8, linestyle='-'),
        # Entry Line (White) - Only starts from trade open
        mpf.make_addplot(entry_line, color='#FFFFFF', width=1.2, linestyle='--'),
        # SL Line (Neon Red) - Only starts from trade open
        mpf.make_addplot(sl_line, color='#FF1744', width=1.8, linestyle='-')
    ]

    # Pro-Grade Dark Style
    style = mpf.make_mpf_style(
        base_mpf_style='charles', 
        gridstyle='', 
        facecolor='#121212', 
        edgecolor='#2b2f36',
        marketcolors=mpf.make_marketcolors(up='#00C853', down='#FF1744', inherit=True)
    )
    
    os.makedirs("pnl_cards", exist_ok=True)
    filename = f"chart_{symbol.replace('/', '_')}.png"
    filepath = os.path.join(os.getcwd(), "pnl_cards", filename)
    
    # Shaded Areas (R:R Boxes + Bollinger Cloud)
    fb_tp = dict(y1=entry, y2=tp, where=where_mask, color='#00C853', alpha=0.10)
    fb_sl = dict(y1=entry, y2=sl, where=where_mask, color='#FF1744', alpha=0.10)
    fb_bb = dict(y1=df["bb_up"].values, y2=df["bb_low"].values, color='#00E5FF', alpha=0.05)
    
    mpf.plot(df, type='candle', 
             style=style,
             title=f"\n{symbol} ({side}) - 15M Strategy Setup",
             ylabel='Price (USDT)',
             addplot=ap,
             fill_between=[fb_tp, fb_sl, fb_bb],
             savefig=dict(fname=filepath, dpi=120, bbox_inches='tight'),
             volume=False,
             figratio=(16,9),
             figscale=1.3)
             
    return filepath
