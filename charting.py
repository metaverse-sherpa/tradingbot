import mplfinance as mpf
import pandas as pd
import os

def generate_trade_chart(symbol, df, entry, tp, sl, side, open_ts=0):
    """
    Generates a candlestick chart with Green/Red R:R boxes starting from open_ts.
    """
    # 1. Prepare Data for mplfinance
    df.index = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 2. Define the R:R Box logic with 'where' mask
    # This ensures boxes only start from when the trade opened
    start_time = pd.to_datetime(open_ts, unit='ms')
    where_mask = (df.index >= start_time)
    
    # Style settings
    style = mpf.make_mpf_style(base_mpf_style='charles', gridstyle='', facecolor='#161a1e', edgecolor='#2b2f36')
    
    # Setup the plot
    filename = f"chart_{symbol.replace('/', '_')}.png"
    filepath = os.path.join(os.getcwd(), filename)
    
    # Create the lines for TP, SL, and Entry
    hlines_dict = dict(hlines=[tp, entry, sl], colors=['#26a69a', '#787b86', '#ef5350'], linestyle='--', linewidths=1.5)
    
    # Define the shaded boxes with the 'where' mask
    fb_tp = dict(y1=entry, y2=tp, where=where_mask, color='#26a69a', alpha=0.15)
    fb_sl = dict(y1=entry, y2=sl, where=where_mask, color='#ef5350', alpha=0.15)
    
    mpf.plot(df, type='candle', 
             style=style,
             title=f"\n{symbol} ({side}) - 1H Trade Setup",
             ylabel='',
             hlines=hlines_dict,
             fill_between=[fb_tp, fb_sl],
             savefig=dict(fname=filepath, dpi=100, bbox_inches='tight'),
             volume=False,
             figratio=(16,9),
             figscale=1.2)
             
    return filepath
