import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web_api.routes_custom_strategies import load_historical_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def pre_cache():
    assets = [
        ("crypto", "1h", "BTC/USDT"),
        ("crypto", "1h", "ETH/USDT"),
        ("stock", "1h", "AAPL"),
        ("stock", "1h", "SPY"),
        ("stock", "1h", "TSLA")
    ]
    
    for asset_type, timeframe, symbol in assets:
        logger.info(f"Caching {asset_type} {symbol} {timeframe}...")
        data = load_historical_data(asset_type=asset_type, timeframe=timeframe, symbol=symbol)
        if data:
            logger.info(f"Successfully cached {symbol} with {len(list(data.values())[0])} rows.")
        else:
            logger.error(f"Failed to cache {symbol}.")

if __name__ == "__main__":
    pre_cache()
