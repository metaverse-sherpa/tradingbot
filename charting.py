import os
import sys

# Ensure Matplotlib config directory is set to a writable local path in the workspace to prevent slow font cache rebuilds
if 'MPLCONFIGDIR' not in os.environ:
    os.environ['MPLCONFIGDIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", ".matplotlib")

import mplfinance as mpf
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import logging
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

# Use a non-interactive backend to save RAM and avoid VPS issues
matplotlib.use('Agg')

def generate_trade_chart(symbol, df, entry, tp, sl, side, open_ts=0, timeframe="15M", currency="USDT", current_price=0.0, strategy=""):
    """
    Generates a high-contrast Neon chart where TP/SL/Entry lines only start from open_ts.
    """
    # Normalize open_ts to milliseconds if it was passed in seconds
    if open_ts > 0 and open_ts < 10**11:
        open_ts = open_ts * 1000

    df = df.copy()
    df.index = pd.to_datetime(df['timestamp'], unit='ms')
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Incorporate live price into the chart
    if current_price > 0:
        last_idx = df.index[-1]
        now = pd.Timestamp.utcnow().tz_localize(None)
        
        # If the last candle is from a previous day, append a new daily candle
        if timeframe == "1D" and (now.date() > last_idx.date()):
             new_row = pd.DataFrame([{
                 'timestamp': int(now.timestamp() * 1000),
                 'open': df.loc[last_idx, 'close'],
                 'high': max(df.loc[last_idx, 'close'], current_price),
                 'low': min(df.loc[last_idx, 'close'], current_price),
                 'close': current_price,
                 'volume': 0
             }])
             new_row.index = pd.to_datetime(new_row['timestamp'], unit='ms')
             df = pd.concat([df, new_row])
        else:
             df.loc[df.index[-1], 'close'] = current_price
             df.loc[df.index[-1], 'high'] = max(df.loc[df.index[-1], 'high'], current_price)
             df.loc[df.index[-1], 'low'] = min(df.loc[df.index[-1], 'low'], current_price)
    
    # 1. Calculate Indicators on Full DataFrame
    strategy_lower = strategy.lower()

    # Calculate RSI based on strategy
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    if "sherpa" in strategy_lower or timeframe == "1D":
        # RSI(3) with simple rolling average (matching SherpaVelocityPullback in strategies.py)
        rsi_period = 3
        avg_gain = gain.rolling(window=rsi_period).mean()
        avg_loss = loss.rolling(window=rsi_period).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        rsi_label = "RSI (3)"
    else:
        # RSI(14) with EWM (matching ValkyrieEliteScalper in strategies.py)
        rsi_period = 14
        avg_gain = gain.ewm(span=rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(span=rsi_period, adjust=False).mean()
        rs = avg_gain / (avg_loss.replace(0, np.nan))
        df['rsi'] = 100 - (100 / (1 + rs))
        rsi_label = "RSI (14)"

    # Calculate EMAs and BBs
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["bb_mid"] = df["close"].rolling(window=20).mean()
    std = df["close"].rolling(window=20).std()
    df["bb_up"] = df["bb_mid"] + (2 * std)
    df["bb_low"] = df["bb_mid"] - (2 * std)

    # NOW slice the dataframe for plotting
    df = df.tail(30).copy()

    # Setup Vibrant Neon Addplots
    ap = []
    
    # Add RSI panel (explicitly set ylim=(0, 100) and secondary_y=False to ensure correct scale)
    ap.append(mpf.make_addplot(df['rsi'], panel=1, color='#FF9800', ylabel=rsi_label, ylim=(0, 100), secondary_y=False, width=1.0))
    # RSI overbought/oversold lines
    ap.append(mpf.make_addplot(pd.Series(70, index=df.index), panel=1, color='#FF1744', linestyle='-', width=1.5, alpha=1.0, ylim=(0, 100), secondary_y=False))
    ap.append(mpf.make_addplot(pd.Series(30, index=df.index), panel=1, color='#00C853', linestyle='-', width=1.5, alpha=1.0, ylim=(0, 100), secondary_y=False))

    # Add a marker (star/arrow) on the entry day
    if open_ts > 0:
        entry_time = pd.to_datetime(open_ts, unit='ms')
        if entry_time.tz is not None:
            entry_time = entry_time.tz_localize(None)
        entry_mask = (df.index <= entry_time)
        if entry_mask.any():
            entry_idx = df[entry_mask].index[-1]
            marker_prices = pd.Series(np.nan, index=df.index)
            is_long = side.upper() in ['LONG', 'BUY', 'L']
            if is_long:
                marker_prices.loc[entry_idx] = df.loc[entry_idx, 'low'] * 0.99
                ap.append(mpf.make_addplot(
                    marker_prices, 
                    type='scatter', 
                    markersize=150, 
                    marker='^', 
                    color='#00C853'
                ))
            else:
                marker_prices.loc[entry_idx] = df.loc[entry_idx, 'high'] * 1.01
                ap.append(mpf.make_addplot(
                    marker_prices, 
                    type='scatter', 
                    markersize=150, 
                    marker='v', 
                    color='#FF1744'
                ))

    fb_bb = None
    
    if "sherpa velocity" in strategy_lower or timeframe == "1D":
        # Add EMA 50 (Vibrant Neon Cyan)
        ap.append(mpf.make_addplot(df["ema_50"], color='#00E5FF', alpha=0.8, width=1.2))
        # Add EMA 200 (Vibrant Neon Purple/Magenta)
        ap.append(mpf.make_addplot(df["ema_200"], color='#D500F9', alpha=0.8, width=1.2))
    elif "valkyrie" in strategy_lower or timeframe != "1D":
        # Bollinger Bands - Upper/Lower (Vibrant Cyan, thicker)
        ap.append(mpf.make_addplot(df["bb_up"], color='#00E5FF', alpha=0.5, width=1.2))
        ap.append(mpf.make_addplot(df["bb_low"], color='#00E5FF', alpha=0.5, width=1.2))
        # Bollinger Mid (Subtle Dashed Cyan)
        ap.append(mpf.make_addplot(df["bb_mid"], color='#00E5FF', alpha=0.3, width=0.8, linestyle='--'))
        # Add EMA 200 (Vibrant Neon Purple/Magenta) for Valkyrie since it filters based on it
        ap.append(mpf.make_addplot(df["ema_200"], color='#D500F9', alpha=0.8, width=1.2))
        
        fb_bb = dict(y1=df["bb_up"].values, y2=df["bb_low"].values, color='#00E5FF', alpha=0.05)

    # 2. Define the R:R lines logic (Only start from open_ts)
    start_time = pd.to_datetime(open_ts, unit='ms')
    if start_time.tz is not None:
        start_time = start_time.tz_localize(None)
    past_candles = df.index[df.index <= start_time]
    if len(past_candles) > 0:
        actual_start_time = past_candles[-1]
        where_mask = (df.index >= actual_start_time)
    else:
        where_mask = (df.index >= start_time)
    
    # If the trade is brand new or open_ts is in the future (fewer than 8 candles match),
    # draw the R:R lines across the entire chart so they are beautifully visible!
    if where_mask.sum() < 8:
        where_mask[:] = True
    
    # Create price level series that are NaN before start_time
    tp_line = pd.Series(np.nan, index=df.index)
    entry_line = pd.Series(np.nan, index=df.index)
    sl_line = pd.Series(np.nan, index=df.index)
    
    if tp > 0:
        tp_line.loc[where_mask] = tp
        # TP Line (Neon Green) - Only starts from trade open
        ap.append(mpf.make_addplot(tp_line, color='#00C853', width=1.8, linestyle='-'))

    entry_line.loc[where_mask] = entry
    # Entry Line (White) - Only starts from trade open
    ap.append(mpf.make_addplot(entry_line, color='#FFFFFF', width=1.2, linestyle='--'))
    
    if sl > 0:
        sl_line.loc[where_mask] = sl
        # SL Line (Neon Red) - Only starts from trade open
        ap.append(mpf.make_addplot(sl_line, color='#FF1744', width=1.8, linestyle='-'))

    # Pro-Grade Dark Style
    style = mpf.make_mpf_style(
        base_mpf_style='charles', 
        gridstyle='', 
        facecolor='#121212', 
        edgecolor='#2b2f36',
        marketcolors=mpf.make_marketcolors(up='#00C853', down='#FF1744', inherit=True)
    )
    
    os.makedirs("pnl_cards", exist_ok=True)
    import hashlib
    params_str = f"{symbol}_{entry}_{tp}_{sl}_{side}_{current_price}"
    h = hashlib.md5(params_str.encode('utf-8')).hexdigest()
    filename = f"chart_{symbol.replace('/', '_')}_{h}.png"
    filepath = os.path.join(os.getcwd(), "pnl_cards", filename)
    
    # Shaded Areas (R:R Boxes)
    fill_areas = []
    if tp > 0:
        fill_areas.append(dict(y1=entry, y2=tp, where=where_mask, color='#00C853', alpha=0.10))
    if sl > 0:
        fill_areas.append(dict(y1=entry, y2=sl, where=where_mask, color='#FF1744', alpha=0.10))
    if 'fb_bb' in locals() and fb_bb is not None:
        fill_areas.append(fb_bb)
    
    # Generate the chart
    kwargs = dict(
        type='candle',
        style=style,
        title=f"\n{symbol} ({side}) - {timeframe} Setup" + (f" | {strategy}" if strategy else ""),
        ylabel=f'Price ({currency})',
        addplot=ap,
        volume=False,
        figratio=(16,10),
        figscale=0.9,
        panel_ratios=(4, 1),
        returnfig=True
    )
    
    if fill_areas:
        valid_areas = [fb for fb in fill_areas if fb is not None]
        if valid_areas:
            kwargs['fill_between'] = valid_areas
 
    import io
    fig, axlist = mpf.plot(df, **kwargs)
             
    # Save final figure to in-memory buffer first to avoid intermediate disk write
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=80, bbox_inches='tight')
    buf.seek(0)
    
    # CRITICAL: Explicitly close the figure to release memory!
    plt.close(fig)
 
    # --- 4. Premium Visual Assembly ---
    try:
        import media_gen
        prog_img = media_gen.generate_trade_progress_box(symbol, side, entry, tp, sl, current_price if current_price > 0 else df['close'].iloc[-1], width=1024, return_image=True)
        
        from PIL import Image
        chart_img = Image.open(buf).convert("RGBA")
        
        # Scale progress box to match chart width
        scale = chart_img.width / prog_img.width
        new_h = int(prog_img.height * scale)
        prog_img = prog_img.resize((chart_img.width, new_h), Image.Resampling.BILINEAR)
        
        # Combine vertically
        combined = Image.new("RGBA", (chart_img.width, chart_img.height + prog_img.height), (18, 18, 18, 255))
        combined.paste(chart_img, (0, 0), chart_img)
        combined.paste(prog_img, (0, chart_img.height), prog_img)
        
        combined.convert("RGB").save(filepath, "JPEG", quality=90)
        chart_img.close(); prog_img.close(); combined.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Visual assembly failed: {e}")
        raise e

    return filepath
