import asyncio

# Global CCXT markets cache to prevent rate-limiting and redundant loading of contracts
SHARED_MARKETS = {}
SHARED_MARKETS_TIME = {}
SHARED_MARKETS_LOCK = asyncio.Lock()
