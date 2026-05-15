import mplfinance as mpf
import pandas as pd
import numpy as np
import os
import matplotlib
import matplotlib.pyplot as plt

# Use a non-interactive backend to save RAM and avoid VPS issues
matplotlib.use('Agg')

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
    
    # Generate the chart
    fig, axlist = mpf.plot(df, type='candle', 
             style=style,
             title=f"\n{symbol} ({side}) - 15M Strategy Setup",
             ylabel='Price (USDT)',
             addplot=ap,
             fill_between=[fb_tp, fb_sl, fb_bb],
             volume=False,
             figratio=(16,10),
             figscale=1.3,
             returnfig=True)
             
    # --- 4. Add Trade Progress Bar Subplot ---
    try:
        # Create a small progress axis at the bottom
        # We'll use the existing figure and add a new axes
        # [left, bottom, width, height] in normalized coordinates
        ax_progress = fig.add_axes([0.15, 0.05, 0.7, 0.05])
        ax_progress.set_facecolor('#121212')
        ax_progress.set_xlim(min(sl, tp, entry), max(sl, tp, entry))
        ax_progress.set_ylim(-1, 1)
        ax_progress.set_yticks([])
        ax_progress.set_xticks([])
        
        # Draw the main line
        ax_progress.hlines(0, min(sl, tp), max(sl, tp), color='#444444', linewidth=2, alpha=0.5)
        
        # Draw Ticks
        ax_progress.vlines(sl, -0.5, 0.5, color='#FF1744', linewidth=3, label='SL')
        ax_progress.vlines(tp, -0.5, 0.5, color='#00C853', linewidth=3, label='TP')
        ax_progress.vlines(entry, -0.3, 0.3, color='#FFFFFF', linewidth=1.5, linestyle='--')
        
        # Labels
        ax_progress.text(sl, -0.8, 'SL', color='#FF1744', fontsize=8, ha='center', fontweight='bold')
        ax_progress.text(tp, -0.8, 'TP', color='#00C853', fontsize=8, ha='center', fontweight='bold')
        ax_progress.text(entry, 0.6, 'ENTRY', color='#FFFFFF', fontsize=7, ha='center', alpha=0.7)
        
        # Current Position (The Dot)
        current_price = df['close'].iloc[-1]
        dot_color = '#00E5FF' # Neon Cyan
        if current_price >= entry and side == 'LONG': dot_color = '#00C853'
        elif current_price < entry and side == 'LONG': dot_color = '#FF1744'
        elif current_price <= entry and side == 'SHORT': dot_color = '#00C853'
        elif current_price > entry and side == 'SHORT': dot_color = '#FF1744'
        
        ax_progress.plot(current_price, 0, marker='o', markersize=10, color=dot_color, markeredgecolor='white', markeredgewidth=1)
        
        # Progress Text
        roe = ((current_price - entry) / entry * 100) if side == 'LONG' else ((entry - current_price) / entry * 100)
        ax_progress.text(current_price, 0.5, f"{roe:+.2f}%", color=dot_color, fontsize=9, ha='center', fontweight='bold')
        
        # Remove spines
        for spine in ax_progress.spines.values(): spine.set_visible(False)
    except Exception as e:
        print(f"Progress bar failed: {e}")

    # Save final figure
    fig.savefig(filepath, dpi=100, bbox_inches='tight')
    
    # CRITICAL: Explicitly close the figure to release memory!
    plt.close(fig)
    return filepath
