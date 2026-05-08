import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta

def fetch_data(symbol='BTC/USDT:USDT', timeframe='15m', days_back=3*365):
    exchange = ccxt.blofin({
        'enableRateLimit': True,
    })

    end_time = exchange.milliseconds()
    start_time = end_time - (days_back * 24 * 60 * 60 * 1000)

    all_ohlcv = []
    current_start = start_time

    print(f"Fetching {days_back} days of {timeframe} data for {symbol} from Blofin...")
    
    while current_start < end_time:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_start, limit=1000)
            if not ohlcv:
                break
            
            all_ohlcv.extend(ohlcv)
            current_start = ohlcv[-1][0] + exchange.parse_timeframe(timeframe) * 1000
            
            print(f"Fetched {len(ohlcv)} candles. Last candle date: {datetime.fromtimestamp(ohlcv[-1][0]/1000)}")
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('datetime', inplace=True)
    
    # Drop duplicates in case of overlap
    df = df[~df.index.duplicated(keep='first')]
    
    # Save to CSV
    filename = f"BTCUSDT_blofin_{timeframe}_3yrs.csv"
    df.to_csv(filename)
    print(f"Data saved to {filename} ({len(df)} candles)")
    return df

if __name__ == "__main__":
    fetch_data('BTC/USDT:USDT', '15m', 3 * 365)

