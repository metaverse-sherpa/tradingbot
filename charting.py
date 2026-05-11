import mplfinance as mpf
import pandas as pd
import os

def generate_trade_chart(symbol, df, entry, tp, sl, side):
    """
    Generates a 15m candlestick chart with Green/Red R:R boxes.
    Saves to a temporary file and returns the path.
    """
    # 1. Prepare Data for mplfinance
    df.index = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 2. Define the R:R Box logic
    # We use fill_between to create the shaded boxes
    # Green box: Entry to TP
    # Red box: Entry to SL
    
    # Calculate limits for the Y-axis so boxes are visible
    all_prices = [entry, tp, sl] + df['high'].tolist() + df['low'].tolist()
    y_min = min(all_prices) * 0.995
    y_max = max(all_prices) * 1.005
    
    # Style settings
    style = mpf.make_mpf_style(base_mpf_style='charles', gridstyle='', facecolor='#161a1e', edgecolor='#2b2f36')
    
    # Setup the plot
    filename = f"chart_{symbol.replace('/', '_')}.png"
    filepath = os.path.join(os.getcwd(), filename)
    
    # Create the lines for TP, SL, and Entry
    hlines_dict = dict(hlines=[tp, entry, sl], colors=['#26a69a', '#787b86', '#ef5350'], linestyle='--', linewidths=1.5)
    
    # Generate the plot
    # Note: We use 'fill_between' via the addplot feature if needed, 
    # but for a "mini chart", clean lines are often better. 
    # Let's add the boxes using the 'fill_between' parameter in mpf.plot
    
    fb_tp = dict(y1=entry, y2=tp, where=None, color='#26a69a', alpha=0.15)
    fb_sl = dict(y1=entry, y2=sl, where=None, color='#ef5350', alpha=0.15)
    
    mpf.plot(df, type='candle', 
             style=style,
             title=f"\n{symbol} ({side}) - 4H Trade Setup",
             ylabel='',
             hlines=hlines_dict,
             fill_between=[fb_tp, fb_sl],
             savefig=dict(fname=filepath, dpi=100, bbox_inches='tight'),
             volume=False,
             figratio=(16,9),
             figscale=1.2)
             
    return filepath
