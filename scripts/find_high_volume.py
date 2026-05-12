import ccxt
import pandas as pd

def get_top_volume_symbols(limit=20):
    exchange = ccxt.binance()
    markets = exchange.fetch_tickers()
    
    # Filter for USDT pairs and sort by quote volume (USDT volume)
    usdt_pairs = [
        {
            'symbol': ticker['symbol'],
            'volume': ticker['quoteVolume']
        }
        for symbol, ticker in markets.items()
        if symbol.endswith('/USDT') and ticker['quoteVolume'] is not None
    ]
    
    df = pd.DataFrame(usdt_pairs)
    df = df.sort_values(by='volume', ascending=False)
    
    return df.head(limit)

if __name__ == "__main__":
    print("Fetching top volume symbols on Binance...")
    top_symbols = get_top_volume_symbols(30)
    print(top_symbols)
    
    # Current basket (19 tokens)
    current_basket = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "ADA/USDT", 
                      "LINK/USDT", "DOT/USDT", "TON/USDT", "ZEC/USDT", "PEPE/USDT",
                      "BNB/USDT", "NEAR/USDT", "SUI/USDT", "NOT/USDT", "TAO/USDT", 
                      "ONDO/USDT", "ENA/USDT", "FET/USDT", "WIF/USDT"]
    
    # Filter out current basket and some stablecoins/leveraged tokens
    exclude = [s.replace('/', '') for s in current_basket] + ['USDCUSDT', 'FDUSDUSDT', 'TUSDUSDT', 'EURIUSDT', 'AEURUSDT', 'USDTUSDT']
    
    candidates = []
    for _, row in top_symbols.iterrows():
        clean_sym = row['symbol'].replace('/', '')
        if clean_sym not in exclude and 'UP' not in clean_sym and 'DOWN' not in clean_sym:
            candidates.append(row['symbol'])
            
    print("\nRecommended New Candidates (High Volume):")
    for c in candidates[:10]:
        print(f"  - {c}")
